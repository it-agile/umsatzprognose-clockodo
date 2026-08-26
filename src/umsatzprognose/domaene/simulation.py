"""Simulation - die Monte-Carlo-Rechnung aus Spec 5.4.

Ein Lauf zieht je Horizontmonat und Projekt eine Abrufquote aus der portfolioweiten
Verteilung (5.2), rechnet sie ueber den effektiven Stundensatz in Stunden um, verteilt
sie auf die beteiligten Personen nach ihrem historischen Anteil
(:meth:`~umsatzprognose.domaene.projekt.Projekt.anteil_je_mitarbeiter`) und deckelt den
Bedarf je Person projektuebergreifend gegen ihre verfuegbare Kapazitaet (5.3). Das
Restvolumen wandert von Monat zu Monat weiter; die Fachobjekte selbst bleiben
unveraendert, der Lauf-Zustand ist ein einfaches Dictionary neben ihnen (siehe
:mod:`umsatzprognose.domaene.bestand`).

**Stundensatz 0 und ``None`` werden identisch behandelt.** Beide erzeugen laut Spec 5.1
und der Entscheidung vom 26.08.2026 "keinen Stundenbedarf" - ein Projekt ohne
ableitbaren Satz kann seinen gewuenschten Euro-Betrag nicht in Stunden umrechnen und
geht deshalb ungedeckelt (ohne Kapazitaetsverbrauch) in die Prognose ein, begrenzt nur
durch sein Restvolumen.

**Monat 1 ist angebrochen.** Gezogene Abrufquote und verfuegbare Kapazitaet werden mit
dem Anteil der ab dem Stichtag verbleibenden Arbeitstage am Monat skaliert - hier als
Anteil der Wochentage Montag bis Freitag verstanden, ohne Feiertage oder individuelle
Abwesenheiten, weil das schon die Kapazitaetsrechnung selbst leistet.

**Der Cutoff durch ``automatic_completion`` gilt monatsweise, nicht taggenau**
(Entscheidung 26.08.2026): der Horizontmonat, der die ``deadline`` enthaelt, zaehlt noch
voll, der erste vollstaendig danach liegende Monat liefert 0. Eine taggenaue Skalierung
wie bei Monat 1 waere je Projekt individuell noetig statt einmal global fuer den ganzen
Horizont - der Mehraufwand steht in keinem Verhaeltnis zur gewonnenen Genauigkeit.

**Bereits gebuchte Betraege je Horizontmonat sind die Untergrenze** (5.4): sie zaehlen
gegen dasselbe Restvolumen wie der simulierte Betrag, werden also nicht zusaetzlich
abgerufen, koennen es aber nach oben korrigieren, wenn die Simulation weniger zieht als
schon real gebucht ist.

Kapazitaeten haengen nur an Stichtag und Horizontmonat, nicht am Lauf - sie werden daher
einmal vor der Lauf-Schleife berechnet und nicht bei jedem der 10.000 Laeufe neu
(:meth:`~umsatzprognose.domaene.mitarbeiter.Mitarbeiter.verfuegbare_kapazitaet` iteriert
selbst schon ueber jeden Tag des Monats).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .bestand import Bestand
    from .projekt import Projekt

from calendar import monthrange
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from random import Random

from .prognose import KONFIDENZNIVEAUS, NochKeinePrognose, Prognose

Monat = tuple[int, int]  # (jahr, monat)


def _ordnung(jahr: int, monat: int) -> int:
    """Monate seit Jahr 0 - macht Fortzaehlung ueber Jahresgrenzen trivial."""
    return jahr * 12 + (monat - 1)


def _aus_ordnung(ordnung: int) -> Monat:
    return (ordnung // 12, ordnung % 12 + 1)


def _horizontmonate(stichtag: date, monate: int) -> tuple[Monat, ...]:
    """Die Horizontmonate, beginnend mit dem Monat des Stichtags (Spec 5.4)."""
    start = _ordnung(stichtag.year, stichtag.month)
    return tuple(_aus_ordnung(start + i) for i in range(monate))


def _anteil_verbleibender_arbeitstage(stichtag: date) -> float:
    """Anteil der ab dem Stichtag verbleibenden Wochentage Mo-Fr am Monat des Stichtags.

    0.0 in dem (praktisch nicht vorkommenden) Fall eines Monats ganz ohne Wochentag.
    """
    letzter_tag = monthrange(stichtag.year, stichtag.month)[1]

    def arbeitstag(tag: int) -> bool:
        return date(stichtag.year, stichtag.month, tag).weekday() < 5

    gesamt = sum(1 for tag in range(1, letzter_tag + 1) if arbeitstag(tag))
    rest = sum(1 for tag in range(stichtag.day, letzter_tag + 1) if arbeitstag(tag))
    return rest / gesamt if gesamt else 0.0


def _traegt_noch_bei(projekt: Projekt, monat: Monat) -> bool:
    """Ob das Projekt in diesem Horizontmonat noch Umsatz beitraegt (Spec 5.4 Schritt 1).

    Ohne ``automatic_completion``/``deadline`` immer ``True``. Sonst: der Monat, der die
    ``deadline`` enthaelt, zaehlt noch voll, der erste vollstaendig danach liegende
    Monat liefert 0 (Entscheidung 26.08.2026, siehe Modul-Docstring).
    """
    abschluss = projekt.automatischer_abschluss
    if abschluss is None:
        return True
    return (abschluss.year, abschluss.month) >= monat


@dataclass(frozen=True)
class MonteCarloPrognose(Prognose):
    """Das Ergebnis der Monte-Carlo-Simulation (Spec 5.4/5.5).

    Traegt nur fertig aggregierte Kennzahlen - die 10.000 Einzellaeufe selbst werden
    nicht aufgehoben, sie waeren als Speicherlast ohne Gegenwert.
    """

    _horizontmonate: tuple[Monat, ...]
    laeufe: int
    _monatswerte: Mapping[float, tuple[float, ...]]
    _summe: Mapping[float, float]
    _gebucht: tuple[float, ...]
    _kapazitaet_limitierend_anteil: float

    @property
    def vorhanden(self) -> bool:
        return True

    @property
    def begruendung(self) -> str:
        return (
            f"Monte-Carlo-Simulation ueber {self.laeufe} Laeufe, "
            f"Horizont {len(self._horizontmonate)} Monat(e)."
        )

    def horizontmonate(self) -> tuple[Monat, ...]:
        return self._horizontmonate

    def monatswerte(self) -> dict[float, list[float]]:
        return {niveau: list(werte) for niveau, werte in self._monatswerte.items()}

    def gebucht(self) -> list[float]:
        return list(self._gebucht)

    def summe(self) -> dict[float, float]:
        return dict(self._summe)

    def kapazitaet_limitierend_anteil(self) -> float:
        return self._kapazitaet_limitierend_anteil


def _quantil(sortierte_werte: list[float], anteil: float) -> float:
    """Empirisches Quantil, linear zwischen den Ordnungsstatistiken interpoliert."""
    if not sortierte_werte:
        return 0.0
    stelle = anteil * (len(sortierte_werte) - 1)
    unten = int(stelle)
    oben = min(unten + 1, len(sortierte_werte) - 1)
    rest = stelle - unten
    return sortierte_werte[unten] * (1.0 - rest) + sortierte_werte[oben] * rest


def simulieren(
    bestand: Bestand,
    monate: int = 3,
    *,
    laeufe: int = 10000,
    zufall: Random | None = None,
) -> Prognose:
    """Die Monte-Carlo-Simulation aus Spec 5.4.

    Aufgerufen ueber :meth:`~umsatzprognose.domaene.bestand.Bestand.simulieren`, nicht
    direkt - der Bestand ist der fachlich richtige Einstieg (siehe dessen Docstring).

    Args:
        bestand: das Portfolio zum Stichtag.
        monate: Laenge des Horizonts, 1 bis 3 (Spec 5.4).
        laeufe: Anzahl der Monte-Carlo-Laeufe, 10.000 laut Spec.
        zufall: der Zufallsgenerator; wer den Startwert setzt, ist der Aufrufer - ein
            Lauf muss wiederholbar sein (siehe
            :meth:`~umsatzprognose.domaene.abrufquote.Abrufquotenverteilung.ziehen`).
    """
    if monate < 1:
        raise ValueError(f"Der Horizont braucht mindestens einen Monat, nicht {monate}")

    verteilung = bestand.abrufquotenverteilung()
    scope = bestand.im_prognose_scope
    if not verteilung.vorhanden or not scope:
        return NochKeinePrognose()

    zufall = zufall if zufall is not None else Random()
    horizont = _horizontmonate(bestand.stichtag, monate)
    skalierung_monat1 = _anteil_verbleibender_arbeitstage(bestand.stichtag)

    # Statische Groessen: einmal aus den Fachobjekten gelesen, nicht bei jedem Lauf neu.
    saetze = {p.id: p.effektiver_stundensatz for p in scope}
    startvolumen = {p.id: p.restvolumen_prognosewirksam or 0.0 for p in scope}
    anteile = {
        p.id: tuple((m.id, anteil) for m, anteil in p.anteil_je_mitarbeiter().items())
        for p in scope
    }
    traegt_bei = {(p.id, monat): _traegt_noch_bei(p, monat) for p in scope for monat in horizont}

    verlaeufe_je_projekt = {v.projekt.id: v for v in bestand.verbrauchsverlaeufe}
    gebucht: dict[tuple[int, Monat], float] = {}
    for p in scope:
        verlauf = verlaeufe_je_projekt.get(p.id)
        if verlauf is None:
            continue
        # Monat 0 ist der Stichtagsmonat: verlauf.gebucht() kommt aus einer
        # Monatsgruppierung ohne Tagesgrenze und liefert deshalb den ganzen Monat, vor
        # und nach dem Stichtag zusammen. Der Teil vor dem Stichtag ist schon als
        # Verbrauch (5.1) vom Restvolumen abgezogen ("es taucht hier nicht wieder auf",
        # Spec 5.4) - als Untergrenze fuer Monat 0 gezaehlt, wuerde er ein zweites Mal
        # auftauchen. Fuer Monat 0 gibt es deshalb keine Untergrenze aus gebuchten
        # Betraegen; was dort schon feststeht, zeigt die Historie
        # (``Umsatzhistorie.laufender``) getrennt.
        for monat in horizont[1:]:
            betrag = verlauf.gebucht(*monat)
            if betrag:
                gebucht[(p.id, monat)] = betrag

    # Kapazitaet ist stichtags- und monatsabhaengig, aber laufunabhaengig - einmal
    # vorab berechnen statt 10.000-mal (siehe Modul-Docstring).
    kapazitaet = {
        (m.id, monat): m.verfuegbare_kapazitaet(*monat)
        for m in bestand.mitarbeiter
        for monat in horizont
    }

    monatssummen: dict[Monat, list[float]] = {monat: [] for monat in horizont}
    laufsummen: list[float] = []
    kapazitaet_limitierte_laeufe = 0

    for _ in range(laeufe):
        restvolumen = dict(startvolumen)
        lauf_summe = 0.0
        lauf_kapazitaet_limitiert = False

        for index, monat in enumerate(horizont):
            skalierung = skalierung_monat1 if index == 0 else 1.0

            # Schritt 1+2: gewuenschter Verbrauch je Projekt, auf das Restvolumen
            # begrenzt; Schritt 3 (Euro -> Stunden), wo ein Satz das erlaubt.
            gewuenscht_euro: dict[int, float] = {}
            gewuenscht_stunden: dict[int, float] = {}
            for p in scope:
                if not traegt_bei[(p.id, monat)]:
                    continue
                rv = restvolumen[p.id]
                if rv <= 0:
                    continue
                quote = verteilung.ziehen(zufall) * skalierung
                verbrauch = min(rv, quote * rv)
                gewuenscht_euro[p.id] = verbrauch
                satz = saetze[p.id]
                if satz:
                    gewuenscht_stunden[p.id] = verbrauch / satz

            # Schritt 3 (Aufteilung) + Schritt 4 (Kapazitaetsdeckel je Person).
            bedarf_je_person: dict[int, float] = defaultdict(float)
            bedarf_person_projekt: dict[tuple[int, int], float] = {}
            for projekt_id, stunden in gewuenscht_stunden.items():
                for mitarbeiter_id, anteil in anteile[projekt_id]:
                    anteilige_stunden = stunden * anteil
                    bedarf_je_person[mitarbeiter_id] += anteilige_stunden
                    bedarf_person_projekt[(mitarbeiter_id, projekt_id)] = anteilige_stunden

            faktor_je_person: dict[int, float] = {}
            for mitarbeiter_id, bedarf in bedarf_je_person.items():
                verfuegbar = kapazitaet.get((mitarbeiter_id, monat), 0.0) * skalierung
                if bedarf > verfuegbar:
                    faktor_je_person[mitarbeiter_id] = max(0.0, verfuegbar / bedarf)
                    lauf_kapazitaet_limitiert = True

            gelieferte_stunden: dict[int, float] = defaultdict(float)
            for (mitarbeiter_id, projekt_id), stunden in bedarf_person_projekt.items():
                faktor = faktor_je_person.get(mitarbeiter_id, 1.0)
                gelieferte_stunden[projekt_id] += stunden * faktor

            # Schritt 5+6: zurueck in Euro, Untergrenze aus bereits Gebuchtem, Restvolumen
            # fortschreiben.
            monat_summe = 0.0
            for p in scope:
                satz = saetze[p.id]
                if p.id in gewuenscht_stunden:
                    geliefert = gelieferte_stunden.get(p.id, 0.0) * satz if satz else 0.0
                elif p.id in gewuenscht_euro:
                    geliefert = gewuenscht_euro[p.id]
                else:
                    geliefert = 0.0

                tatsaechlich = max(geliefert, gebucht.get((p.id, monat), 0.0))
                restvolumen[p.id] = max(0.0, restvolumen[p.id] - tatsaechlich)
                monat_summe += tatsaechlich

            monatssummen[monat].append(monat_summe)
            lauf_summe += monat_summe

        laufsummen.append(lauf_summe)
        if lauf_kapazitaet_limitiert:
            kapazitaet_limitierte_laeufe += 1

    monatswerte = {
        niveau: tuple(_quantil(sorted(monatssummen[monat]), 1.0 - niveau) for monat in horizont)
        for niveau in KONFIDENZNIVEAUS
    }
    sortierte_laufsummen = sorted(laufsummen)
    summe = {niveau: _quantil(sortierte_laufsummen, 1.0 - niveau) for niveau in KONFIDENZNIVEAUS}
    gebucht_je_monat = tuple(
        sum(gebucht.get((p.id, monat), 0.0) for p in scope) for monat in horizont
    )

    return MonteCarloPrognose(
        _horizontmonate=horizont,
        laeufe=laeufe,
        _monatswerte=monatswerte,
        _summe=summe,
        _gebucht=gebucht_je_monat,
        _kapazitaet_limitierend_anteil=kapazitaet_limitierte_laeufe / laeufe,
    )
