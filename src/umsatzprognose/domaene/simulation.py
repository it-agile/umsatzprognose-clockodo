"""Simulation - die Monte-Carlo-Rechnung aus Spec 5.4.

Ein Lauf zieht je Horizontmonat und Projekt eine Abrufquote aus der portfolioweiten
Verteilung (5.2), rechnet sie ueber den effektiven Stundensatz in Stunden um, verteilt
sie auf die beteiligten Personen nach ihrem historischen Anteil
(:meth:`~umsatzprognose.domaene.projekt.Projekt.anteil_je_mitarbeiter`) und deckelt den
Bedarf je Person projektuebergreifend gegen ihre verfuegbare Kapazitaet (5.3). Das
Restvolumen wandert von Monat zu Monat weiter; die Fachobjekte selbst bleiben
unveraendert, der Lauf-Zustand steht als numpy-Array neben ihnen, nicht in ihnen (siehe
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

**Seit dem 27.08.2026 rechnet die Simulation mit numpy, und zwar ueber alle Laeufe
gleichzeitig.** Der Zufallsgenerator alleine auszutauschen (``random.Random`` gegen
``numpy.random.Generator``) haette nichts gebracht - der Aufwand steckte in der
10.000-mal wiederholten Python-Schleife, nicht im Ziehen einer einzelnen Zahl. Der
Lauf-Zustand ist deshalb kein Dictionary mehr je Projekt, sondern ein Array der Form
``(laeufe, Projekte im Scope)``; ein Monat der Simulation ist eine Handvoll
Array-Operationen statt einer Python-Schleife ueber Projekte innerhalb einer Schleife
ueber Laeufe. Die Aufteilung auf Personen (Schritt 3) und der Kapazitaetsdeckel
(Schritt 4) laufen ueber eine ``(Projekte, Personen)``-Matrix aus
:meth:`~umsatzprognose.domaene.projekt.Projekt.anteil_je_mitarbeiter`: einmal vorwaerts
multipliziert ergibt sie den Bedarf je Person, einmal (transponiert) zurueck den
Kuerzungsfaktor je Projekt - das haelt den dritten, nur gedachten Tensor
``(Laeufe, Projekte, Personen)`` aus dem Speicher, den eine direkte Umsetzung der
Ruecktransformation brauchen wuerde. Die Fachregeln selbst (Kapazitaetsdeckel
projektuebergreifend, Restvolumen-Fortschreibung, Cutoff durch
``automatic_completion``, Untergrenze aus Gebuchtem) sind unveraendert - nur ihre
Ausfuehrungsform wechselt von Skalar-Python zu Array-numpy.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .bestand import Bestand
    from .projekt import Projekt

from calendar import monthrange
from dataclasses import dataclass
from datetime import date

import numpy as np

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


def simulieren(
    bestand: Bestand,
    monate: int = 3,
    *,
    laeufe: int = 10000,
    zufall: np.random.Generator | None = None,
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

    zufall = zufall if zufall is not None else np.random.default_rng()
    horizont = _horizontmonate(bestand.stichtag, monate)
    skalierung_monat1 = _anteil_verbleibender_arbeitstage(bestand.stichtag)

    # Statische Groessen: einmal aus den Fachobjekten gelesen und als Array angelegt,
    # nicht bei jedem der ``laeufe`` Laeufe neu (siehe Modul-Docstring).
    startvolumen = np.array([p.restvolumen_prognosewirksam or 0.0 for p in scope])
    saetze = np.array([p.effektiver_stundensatz or 0.0 for p in scope])
    # Satz 0 und ``None`` werden identisch behandelt (Entscheidung 26.08.2026): beide
    # erzeugen keinen Stundenbedarf, der gewuenschte Betrag geht ungedeckelt ein.
    hat_satz = saetze != 0.0
    saetze_sicher = np.where(hat_satz, saetze, 1.0)  # Divisor, ungenutzt wo hat_satz falsch

    # Die Aufteilungsmatrix (Projekte x Personen) aus Schritt 3: einmal aus
    # ``anteil_je_mitarbeiter()`` aufgebaut statt bei jedem Lauf neu abgefragt.
    anteile_je_projekt = [p.anteil_je_mitarbeiter() for p in scope]
    mitarbeiter_index: dict[int, int] = {}
    for anteile in anteile_je_projekt:
        for m in anteile:
            mitarbeiter_index.setdefault(m.id, len(mitarbeiter_index))
    anteil_matrix = np.zeros((len(scope), len(mitarbeiter_index)))
    for i, anteile in enumerate(anteile_je_projekt):
        for m, anteil in anteile.items():
            anteil_matrix[i, mitarbeiter_index[m.id]] = anteil

    # Kapazitaet ist stichtags- und monatsabhaengig, aber laufunabhaengig - einmal
    # vorab je Person und Horizontmonat berechnet, nicht ``laeufe``-mal
    # (:meth:`~umsatzprognose.domaene.mitarbeiter.Mitarbeiter.verfuegbare_kapazitaet`
    # iteriert selbst schon ueber jeden Tag des Monats). Eine Person ohne
    # Stammdatensatz in ``bestand.mitarbeiter`` gilt mit Kapazitaet 0, wie zuvor.
    kapazitaet_je_id = {m.id: m for m in bestand.mitarbeiter}
    mitarbeiter_ids = list(mitarbeiter_index)
    kapazitaet = np.array(
        [
            [
                kapazitaet_je_id[mid].verfuegbare_kapazitaet(*monat)
                if mid in kapazitaet_je_id
                else 0.0
                for mid in mitarbeiter_ids
            ]
            for monat in horizont
        ]
    )

    traegt_bei = np.array([[_traegt_noch_bei(p, monat) for p in scope] for monat in horizont])

    # Monat 0 ist der Stichtagsmonat: ``verlauf.gebucht()`` kommt aus einer
    # Monatsgruppierung ohne Tagesgrenze und liefert deshalb den ganzen Monat, vor und
    # nach dem Stichtag zusammen. Der Teil vor dem Stichtag ist schon als Verbrauch
    # (5.1) vom Restvolumen abgezogen ("es taucht hier nicht wieder auf", Spec 5.4) -
    # als Untergrenze fuer Monat 0 gezaehlt, wuerde er ein zweites Mal auftauchen. Fuer
    # Monat 0 gibt es deshalb keine Untergrenze aus gebuchten Betraegen; was dort schon
    # feststeht, zeigt die Historie (``Umsatzhistorie.laufender``) getrennt.
    verlaeufe_je_projekt = {v.projekt.id: v for v in bestand.verbrauchsverlaeufe}
    gebucht = np.zeros((len(horizont), len(scope)))
    for i, p in enumerate(scope):
        verlauf = verlaeufe_je_projekt.get(p.id)
        if verlauf is None:
            continue
        for j, monat in enumerate(horizont[1:], start=1):
            betrag = verlauf.gebucht(*monat)
            if betrag:
                gebucht[j, i] = betrag

    # Lauf-Zustand: alle ``laeufe`` Restvolumen-Verlaeufe gleichzeitig als Array
    # (laeufe, Projekte im Scope) statt 10.000 Dictionaries (siehe Modul-Docstring).
    restvolumen = np.tile(startvolumen, (laeufe, 1))
    monatssummen = np.zeros((len(horizont), laeufe))
    kapazitaet_limitiert_je_lauf = np.zeros(laeufe, dtype=bool)

    for index, _monat in enumerate(horizont):
        skalierung = skalierung_monat1 if index == 0 else 1.0

        # Schritt 1+2: gewuenschter Verbrauch je Lauf und Projekt, auf das
        # Restvolumen begrenzt; Schritt 3 (Euro -> Stunden), wo ein Satz das erlaubt.
        gilt = traegt_bei[index] & (restvolumen > 0)
        quote = verteilung.ziehen_array((laeufe, len(scope)), zufall) * skalierung
        gewuenscht_euro = np.where(gilt, np.minimum(restvolumen, quote * restvolumen), 0.0)
        gewuenscht_stunden = np.where(hat_satz, gewuenscht_euro / saetze_sicher, 0.0)

        # Schritt 3 (Aufteilung) + Schritt 4 (Kapazitaetsdeckel je Person, ueber alle
        # ihre Projekte). Die Ruecktransformation von der Kuerzung je Person auf einen
        # Kuerzungsfaktor je Projekt geht ueber dieselbe Matrix, nur transponiert - so
        # bleibt der (Laeufe, Projekte, Personen)-Tensor, den eine dritte Achse
        # bräuchte, ungebaut (siehe Modul-Docstring).
        bedarf_je_person = gewuenscht_stunden @ anteil_matrix
        verfuegbar = kapazitaet[index] * skalierung
        ueberschritten = bedarf_je_person > verfuegbar
        bedarf_sicher = np.where(bedarf_je_person > 0, bedarf_je_person, 1.0)
        faktor_je_person = np.where(ueberschritten, verfuegbar / bedarf_sicher, 1.0)
        kapazitaet_limitiert_je_lauf |= ueberschritten.any(axis=1)

        effektiver_faktor = faktor_je_person @ anteil_matrix.T
        gelieferte_stunden = gewuenscht_stunden * effektiver_faktor

        # Schritt 5+6: zurueck in Euro, Untergrenze aus bereits Gebuchtem, Restvolumen
        # fortschreiben.
        geliefert = np.where(hat_satz, gelieferte_stunden * saetze, gewuenscht_euro)
        tatsaechlich = np.maximum(geliefert, gebucht[index])
        restvolumen = np.maximum(0.0, restvolumen - tatsaechlich)
        monatssummen[index] = tatsaechlich.sum(axis=1)

    laufsummen = monatssummen.sum(axis=0)

    monatswerte = {
        niveau: tuple(
            float(np.quantile(monatssummen[index], 1.0 - niveau)) for index in range(len(horizont))
        )
        for niveau in KONFIDENZNIVEAUS
    }
    summe = {niveau: float(np.quantile(laufsummen, 1.0 - niveau)) for niveau in KONFIDENZNIVEAUS}
    gebucht_je_monat = tuple(float(x) for x in gebucht.sum(axis=1))

    return MonteCarloPrognose(
        _horizontmonate=horizont,
        laeufe=laeufe,
        _monatswerte=monatswerte,
        _summe=summe,
        _gebucht=gebucht_je_monat,
        _kapazitaet_limitierend_anteil=float(kapazitaet_limitiert_je_lauf.sum() / laeufe),
    )
