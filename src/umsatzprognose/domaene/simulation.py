"""Simulation - die Monte-Carlo-Rechnung.

Ein Lauf zieht je Horizontmonat und Projekt eine Abrufquote aus der portfolioweiten
Verteilung, rechnet sie ueber den effektiven Stundensatz in Stunden um, verteilt
sie auf die beteiligten Personen nach ihrem historischen Anteil
(:meth:`~umsatzprognose.domaene.projekt.Projekt.anteil_je_mitarbeiter`) und deckelt den
Bedarf je Person projektuebergreifend gegen ihre verfuegbare Kapazitaet. Das
Restvolumen wandert von Monat zu Monat weiter.

**Stundensatz 0 und ``None`` werden identisch behandelt.** Beide erzeugen
"keinen Stundenbedarf" - ein Projekt ohne
ableitbaren Satz kann seinen gewuenschten Euro-Betrag nicht in Stunden umrechnen und
geht deshalb ungedeckelt (ohne Kapazitaetsverbrauch) in die Prognose ein, begrenzt nur
durch sein Restvolumen.

**Monat 1 ist angebrochen.** Gezogene Abrufquote und verfuegbare Kapazitaet werden mit
dem Anteil der ab dem Stichtag verbleibenden Arbeitstage am Monat skaliert - hier als
Anteil der Wochentage Montag bis Freitag verstanden, ohne Feiertage oder individuelle
Abwesenheiten.

**Der Cutoff durch ``automatic_completion`` gilt monatsweise, nicht taggenau**: der
Horizontmonat, der die ``deadline`` enthaelt, zaehlt noch
voll, der erste vollstaendig danach liegende Monat liefert 0. Eine taggenaue Skalierung
wie bei Monat 1 waere je Projekt individuell noetig statt einmal global fuer den ganzen
Horizont.

**Bereits gebuchte Betraege je Horizontmonat sind die Untergrenze**: sie zaehlen
gegen dasselbe Restvolumen wie der simulierte Betrag, werden also nicht zusaetzlich
abgerufen, koennen es aber nach oben korrigieren, wenn die Simulation weniger zieht als
schon real gebucht ist.

Kapazitaeten haengen nur an Stichtag und Horizontmonat, nicht am Lauf - sie werden daher
einmal vor der Lauf-Schleife berechnet und nicht bei jedem der 10.000 Laeufe neu
(:meth:`~umsatzprognose.domaene.mitarbeiter.Mitarbeiter.verfuegbare_kapazitaet` iteriert
selbst schon ueber jeden Tag des Monats).

**Euro-Groessen laufen als ``Decimal`` an den Fachobjekten, als ``float`` in der
Schleife selbst.** Die vektorisierte numpy-Rechnung (10.000 Laeufe gleichzeitig) traegt
mit ``Decimal``-Objektarrays weder ``np.quantile`` noch die uebrigen Vektoroperationen
performant mit - :func:`_aufbauen` wandelt deshalb beim Einlesen der Fachobjekte
gezielt in ``float`` um, :func:`_ergebnis` beim Verlassen der Schleife per :func:`_euro`
zurueck in ``Decimal``, auf den Cent gerundet: jenseits davon traegt eine Summe
zehntausender float-Additionen ohnehin keine belastbare Genauigkeit mehr.
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
from decimal import Decimal

import numpy as np

from umsatzprognose.util import Monat, monatsfolge, ordnung

from .prognose import KONFIDENZNIVEAUS, NochKeinePrognose, Prognose

NULL_EURO = Decimal("0")


def _euro(betrag: float) -> Decimal:
    """Ein aus der float-basierten Simulationsschleife zurueckgerechneter Euro-Betrag,
    auf den Cent gerundet (siehe Moduldocstring)."""
    return Decimal(str(round(betrag, 2)))


def _horizontmonate(stichtag: date, monate: int) -> tuple[Monat, ...]:
    """Die Horizontmonate, beginnend mit dem Monat des Stichtags."""
    return tuple(monatsfolge((stichtag.year, stichtag.month), monate))


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
    """Ob das Projekt in diesem Horizontmonat noch Umsatz beitraegt.

    Ohne ``automatic_completion``/``deadline`` immer ``True``. Sonst: der Monat, der die
    ``deadline`` enthaelt, zaehlt noch voll, der erste vollstaendig danach liegende
    Monat liefert 0.
    """
    abschluss = projekt.automatischer_abschluss
    if abschluss is None:
        return True
    return (abschluss.year, abschluss.month) >= monat


@dataclass(frozen=True, slots=True)
class MonteCarloPrognose:
    """Das Ergebnis der Monte-Carlo-Simulation.

    Erfuellt das :class:`~.prognose.Prognose`-Protocol strukturell, ohne davon zu
    erben (siehe dessen Moduldocstring).

    Traegt nur fertig aggregierte Kennzahlen - die 10.000 Einzellaeufe selbst werden
    nicht aufgehoben, sie waeren als Speicherlast ohne Gegenwert. Eine dieser
    Kennzahlen ist :meth:`kapazitaet_je_projekt`: der Median der ueber den Horizont
    gelieferten Stunden je Projekt, ueber alle Laeufe - zeigt, wohin die verbrauchte
    Kapazitaet tatsaechlich geht, nicht nur ob sie insgesamt knapp war (siehe
    :meth:`kapazitaet_limitierend_anteil`).
    """

    _horizontmonate: tuple[Monat, ...]
    laeufe: int
    _monatswerte: Mapping[float, tuple[Decimal, ...]]
    _summe: Mapping[float, Decimal]
    _gebucht: tuple[Decimal, ...]
    _kapazitaet_limitierend_anteil: float
    _kapazitaet_je_projekt: Mapping[int, float]

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

    def monatswerte(self) -> dict[float, list[Decimal]]:
        return {niveau: list(werte) for niveau, werte in self._monatswerte.items()}

    def gebucht(self) -> list[Decimal]:
        return list(self._gebucht)

    def summe(self) -> dict[float, Decimal]:
        return dict(self._summe)

    def kapazitaet_limitierend_anteil(self) -> float:
        return self._kapazitaet_limitierend_anteil

    def kapazitaet_je_projekt(self) -> dict[int, float]:
        return dict(self._kapazitaet_je_projekt)


def _verbrauchsplan(
    scope: tuple[Projekt, ...], horizont: tuple[Monat, ...]
) -> tuple[np.ndarray, np.ndarray]:
    """Deterministischer Verbrauch je Projekt mit gesetztem
    ``verbrauchsplan_zielmonat`` (siehe dessen Docstring in
    :mod:`umsatzprognose.domaene.projekt`) - ersetzt fuer diese Projekte in
    :func:`simulieren` die aus der portfolioweiten Verteilung gezogene Abrufquote.

    ``hat_plan`` markiert die betroffenen Projekte, ``plan_betrag`` traegt je
    Horizontmonat den geplanten Euro-Betrag (0 fuer Projekte ohne Plan und fuer
    Monate nach dem Zielmonat) - das restliche Volumen linear auf die Monate ab
    ``horizont[0]`` bis einschliesslich dem Zielmonat verteilt. Ein Zielmonat vor
    ``horizont[0]`` wird auf ``horizont[0]`` gekappt: "haette laengst vollstaendig
    verbraucht sein sollen" wird zu "vollstaendig im ersten Horizontmonat".
    """
    hat_plan = np.zeros(len(scope), dtype=bool)
    plan_betrag = np.zeros((len(horizont), len(scope)))
    for i, p in enumerate(scope):
        ziel = p.verbrauchsplan_zielmonat
        if ziel is None:
            continue
        ziel_effektiv = max(ziel, horizont[0])
        anzahl = ordnung(*ziel_effektiv) - ordnung(*horizont[0]) + 1
        rate = float(p.restvolumen_prognosewirksam or NULL_EURO) / anzahl
        hat_plan[i] = True
        for j, monat in enumerate(horizont):
            plan_betrag[j, i] = rate if monat <= ziel_effektiv else 0.0
    return hat_plan, plan_betrag


@dataclass(frozen=True, slots=True)
class _Aufbau:
    """Die laufunabhaengigen Groessen vor der Monte-Carlo-Schleife - einmal aus den
    Fachobjekten gelesen statt bei jedem der ``laeufe`` Laeufe neu, siehe
    :func:`_aufbauen`."""

    horizont: tuple[Monat, ...]
    skalierung_monat1: float
    startvolumen: np.ndarray
    hat_satz: np.ndarray
    saetze: np.ndarray
    saetze_sicher: np.ndarray
    anteil_matrix: np.ndarray
    kapazitaet: np.ndarray
    traegt_bei: np.ndarray
    gebucht: np.ndarray
    hat_plan: np.ndarray
    plan_betrag: np.ndarray


def _aufbauen(bestand: Bestand, scope: tuple[Projekt, ...], monate: int) -> _Aufbau:
    """Baut die laufunabhaengigen Arrays vor der Monte-Carlo-Schleife in
    :func:`simulieren` (siehe Moduldocstring, Abschnitt Kapazitaeten)."""
    horizont = _horizontmonate(bestand.stichtag, monate)
    skalierung_monat1 = _anteil_verbleibender_arbeitstage(bestand.stichtag)

    startvolumen = np.array([float(p.restvolumen_prognosewirksam or NULL_EURO) for p in scope])
    saetze = np.array([float(p.effektiver_stundensatz or NULL_EURO) for p in scope])
    # Satz 0 und ``None`` werden identisch behandelt: beide
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
    hat_plan, plan_betrag = _verbrauchsplan(scope, horizont)

    # Monat 0 ist der Stichtagsmonat: ``verlauf.gebucht()`` kommt aus einer
    # Monatsgruppierung ohne Tagesgrenze und liefert deshalb den ganzen Monat, vor und
    # nach dem Stichtag zusammen. Der Teil vor dem Stichtag ist schon als Verbrauch
    # vom Restvolumen abgezogen ("es taucht hier nicht wieder auf" -
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
                gebucht[j, i] = float(betrag)

    return _Aufbau(
        horizont=horizont,
        skalierung_monat1=skalierung_monat1,
        startvolumen=startvolumen,
        hat_satz=hat_satz,
        saetze=saetze,
        saetze_sicher=saetze_sicher,
        anteil_matrix=anteil_matrix,
        kapazitaet=kapazitaet,
        traegt_bei=traegt_bei,
        gebucht=gebucht,
        hat_plan=hat_plan,
        plan_betrag=plan_betrag,
    )


def _ergebnis(
    aufbau: _Aufbau,
    scope: tuple[Projekt, ...],
    *,
    laeufe: int,
    monatssummen: np.ndarray,
    kapazitaet_limitiert_je_lauf: np.ndarray,
    stunden_je_projekt: np.ndarray,
) -> MonteCarloPrognose:
    """Baut die :class:`MonteCarloPrognose` aus den Ergebnis-Arrays der Monte-Carlo-
    Schleife in :func:`simulieren`."""
    laufsummen = monatssummen.sum(axis=0)

    monatswerte = {
        niveau: tuple(
            _euro(np.quantile(monatssummen[index], 1.0 - niveau))
            for index in range(len(aufbau.horizont))
        )
        for niveau in KONFIDENZNIVEAUS
    }
    summe = {niveau: _euro(np.quantile(laufsummen, 1.0 - niveau)) for niveau in KONFIDENZNIVEAUS}
    gebucht_je_monat = tuple(_euro(x) for x in aufbau.gebucht.sum(axis=1))
    kapazitaet_je_projekt = {
        p.id: float(np.quantile(stunden_je_projekt[:, i], 0.5)) for i, p in enumerate(scope)
    }

    return MonteCarloPrognose(
        _horizontmonate=aufbau.horizont,
        laeufe=laeufe,
        _monatswerte=monatswerte,
        _summe=summe,
        _gebucht=gebucht_je_monat,
        _kapazitaet_limitierend_anteil=float(kapazitaet_limitiert_je_lauf.sum() / laeufe),
        _kapazitaet_je_projekt=kapazitaet_je_projekt,
    )


def simulieren(
    bestand: Bestand,
    monate: int = 3,
    *,
    laeufe: int = 10000,
    zufall: np.random.Generator | None = None,
) -> Prognose:
    """Die Monte-Carlo-Simulation.

    Aufgerufen ueber :meth:`~umsatzprognose.domaene.bestand.Bestand.simulieren`, nicht
    direkt - der Bestand ist der fachlich richtige Einstieg (siehe dessen Docstring).

    Args:
        bestand: das Portfolio zum Stichtag.
        monate: Laenge des Horizonts, 1 bis 3.
        laeufe: Anzahl der Monte-Carlo-Laeufe, 10.000.
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
    aufbau = _aufbauen(bestand, scope, monate)

    # Lauf-Zustand: alle ``laeufe`` Restvolumen-Verlaeufe gleichzeitig als Array
    # (laeufe, Projekte im Scope) statt 10.000 Dictionaries.
    restvolumen = np.tile(aufbau.startvolumen, (laeufe, 1))
    monatssummen = np.zeros((len(aufbau.horizont), laeufe))
    kapazitaet_limitiert_je_lauf = np.zeros(laeufe, dtype=bool)
    stunden_je_projekt = np.zeros((laeufe, len(scope)))

    for index, _monat in enumerate(aufbau.horizont):
        skalierung = aufbau.skalierung_monat1 if index == 0 else 1.0

        # Schritt 1+2: gewuenschter Verbrauch je Lauf und Projekt, auf das
        # Restvolumen begrenzt; Schritt 3 (Euro -> Stunden), wo ein Satz das erlaubt.
        # Projekte mit Verbrauchsplan (aufbau.hat_plan) ersetzen die gezogene
        # Abrufquote durch den vorab linear verteilten Betrag (siehe
        # _verbrauchsplan) - deterministisch ueber alle Laeufe, nur durch das
        # laufabhaengige Restvolumen und den Kapazitaetsdeckel weiter unten begrenzt.
        gilt = aufbau.traegt_bei[index] & (restvolumen > 0)
        quote = verteilung.ziehen_array((laeufe, len(scope)), zufall) * skalierung
        stochastisch = np.minimum(restvolumen, quote * restvolumen)
        deterministisch = np.minimum(restvolumen, aufbau.plan_betrag[index])
        gewuenscht_euro = np.where(
            gilt, np.where(aufbau.hat_plan, deterministisch, stochastisch), 0.0
        )
        gewuenscht_stunden = np.where(aufbau.hat_satz, gewuenscht_euro / aufbau.saetze_sicher, 0.0)

        # Schritt 3 (Aufteilung) + Schritt 4 (Kapazitaetsdeckel je Person, ueber alle
        # ihre Projekte). Die Ruecktransformation von der Kuerzung je Person auf einen
        # Kuerzungsfaktor je Projekt geht ueber dieselbe Matrix, nur transponiert - so
        # bleibt der (Laeufe, Projekte, Personen)-Tensor, den eine dritte Achse
        # bräuchte, ungebaut (siehe Modul-Docstring).
        bedarf_je_person = gewuenscht_stunden @ aufbau.anteil_matrix
        verfuegbar = aufbau.kapazitaet[index] * skalierung
        ueberschritten = bedarf_je_person > verfuegbar
        bedarf_sicher = np.where(bedarf_je_person > 0, bedarf_je_person, 1.0)
        faktor_je_person = np.where(ueberschritten, verfuegbar / bedarf_sicher, 1.0)
        kapazitaet_limitiert_je_lauf |= ueberschritten.any(axis=1)

        effektiver_faktor = faktor_je_person @ aufbau.anteil_matrix.T
        gelieferte_stunden = gewuenscht_stunden * effektiver_faktor

        # Schritt 5+6: zurueck in Euro, Untergrenze aus bereits Gebuchtem, Restvolumen
        # fortschreiben.
        geliefert = np.where(aufbau.hat_satz, gelieferte_stunden * aufbau.saetze, gewuenscht_euro)
        tatsaechlich = np.maximum(geliefert, aufbau.gebucht[index])
        restvolumen = np.maximum(0.0, restvolumen - tatsaechlich)
        monatssummen[index] = tatsaechlich.sum(axis=1)
        # Aus ``tatsaechlich`` zurueckgerechnet statt ``gelieferte_stunden`` verwendet:
        # nur ``tatsaechlich`` kennt die Untergrenze aus bereits Gebuchtem
        # (``gebucht[index]`` oben), damit bleiben Euro- und Stunden-Sicht auf
        # demselben Betrag konsistent.
        stunden_je_projekt += np.where(aufbau.hat_satz, tatsaechlich / aufbau.saetze_sicher, 0.0)

    return _ergebnis(
        aufbau,
        scope,
        laeufe=laeufe,
        monatssummen=monatssummen,
        kapazitaet_limitiert_je_lauf=kapazitaet_limitiert_je_lauf,
        stunden_je_projekt=stunden_je_projekt,
    )
