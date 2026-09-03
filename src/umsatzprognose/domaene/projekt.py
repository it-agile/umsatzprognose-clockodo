"""Projekt - der Gegenstand, um den die ganze Prognose kreist.

Ein in Clockodo angelegtes Projekt gilt als beauftragt; Storno auf
Projektebene ist deshalb kein Thema. Das Projekt haelt sein Auftragsvolumen (Budget),
seinen Verbrauch und die Anteile der beteiligten Personen - und leitet daraus die
Groessen ab.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, assert_never

if TYPE_CHECKING:
    from datetime import date

    from .kunde import Kunde
    from .mitarbeiter import Mitarbeiter
    from .projektanteil import Projektanteil

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Gesamtbudget:
    """Der Normalfall: ``betrag`` ist ein Euro-Gesamtbudget."""

    betrag: float
    hart: bool = False


@dataclass(frozen=True)
class StundenBudget:
    """``amount`` ist eine Stundenzahl, kein Euro-Betrag.

    Der Fall kommt vor, nur bei inaktiven Projekten. Als Euro gelesen waere das ein
    stiller Faktor-Fehler.
    """

    stunden: float


@dataclass(frozen=True)
class IntervallBudget:
    """Budget je Intervall statt Gesamtbudget.

    ``intervall`` ist laut Clockodo-API ein **Integer-Enum** (0 wochenweise,
    1 monatlich, 2 quartalsweise, 3 jaehrlich) und kein String.
    """

    betrag: float
    intervall: int


@dataclass(frozen=True)
class TeilprojektBudget:
    """Das Budget stammt aus Teilprojekten."""

    betrag: float | None = None


@dataclass(frozen=True)
class KeinBudget:
    """Kein Budget hinterlegt."""


# Das vereinbarte Volumen eines Projekts - eine geschlossene Menge sich gegenseitig
# ausschliessender Faelle, keine Kombination aus Flags. Welcher Fall vorliegt,
# entscheidet clockodo.projekte.budget() beim Mapping der Clockodo-Antwort.
Budget = Gesamtbudget | StundenBudget | IntervallBudget | TeilprojektBudget | KeinBudget

OHNE_BUDGET = KeinBudget()


def sonderfall(budget: Budget) -> str | None:
    """Warum der Betrag kein Euro-Gesamtbudget ist, oder ``None``."""
    match budget:
        case Gesamtbudget():
            return None
        case StundenBudget():
            return "Budget in Stunden statt in Euro"
        case IntervallBudget():
            return "Budget je Intervall statt Gesamtbudget"
        case TeilprojektBudget():
            return "Budget stammt aus Teilprojekten"
        case KeinBudget():
            return "kein Budget gesetzt"
        case _:
            assert_never(budget)


def auftragsvolumen(budget: Budget) -> float | None:
    """Das Auftragsvolumen in Euro, ``None`` wenn keines bezifferbar ist."""
    match budget:
        case Gesamtbudget(betrag=betrag):
            return betrag
        case _:
            return None


def verwertbar(budget: Budget) -> bool:
    """Ob der Betrag als Euro-Gesamtbudget gelesen werden darf."""
    return auftragsvolumen(budget) is not None


@dataclass(frozen=True)
class Projekt:
    """Ein beauftragtes Projekt mit Volumen, Verbrauch und Beteiligten."""

    id: int
    name: str | None = None
    kunde: Kunde | None = None
    aktiv: bool = False
    abgeschlossen: bool = False
    budget: Budget = OHNE_BUDGET
    verbrauchtes_volumen: float = 0.0
    verbrauchte_stunden: float = 0.0
    anteile: tuple[Projektanteil, ...] = field(default_factory=tuple)
    stundensatz_uebersteuerung: float | None = None
    # Clockodo kennt ``deadline`` und ``automatic_completion`` getrennt - eine
    # ``deadline`` allein ist unverbindlich. ``clockodo.projekte`` fuehrt das schon
    # beim Mapping zu diesem einen Feld zusammen. Ab diesem Datum traegt das Projekt
    # keinen Umsatz mehr bei.
    automatischer_abschluss: date | None = None

    def __str__(self) -> str:
        return self.bezeichnung

    @property
    def bezeichnung(self) -> str:
        """Kunde und Projektname - die Form, in der Fachexperten Projekte kennen."""
        teile = [str(self.kunde) if self.kunde else None, self.name]
        beschriftet = " / ".join(t for t in teile if t)
        return beschriftet or f"Projekt {self.id}"

    @property
    def auftragsvolumen(self) -> float | None:
        return auftragsvolumen(self.budget)

    @property
    def restvolumen_roh(self) -> float | None:
        """``Auftragsvolumen - Verbrauch``, vorzeichenbehaftet.

        Negativ heisst: das Budget ist historisch ueberschritten. Diese Groesse wird
        nicht verworfen - Haeufigkeit und Hoehe von Ueberschreitungen sind
        ein Kalibrierungssignal und kein Fehler. ``None``, wenn das Projekt kein
        bezifferbares Auftragsvolumen hat; dann gibt es kein Restvolumen, und eine 0
        waere eine andere Aussage.
        """
        if self.auftragsvolumen is None:
            return None
        return self.auftragsvolumen - self.verbrauchtes_volumen

    @property
    def restvolumen_prognosewirksam(self) -> float | None:
        """Bei 0 gekapptes Restvolumen - was noch abgerufen werden kann.

        Eine Ueberschreitung kann nur historisch entstehen, die
        Prognose ueberschreitet das Budget nicht. Ein Projekt mit ueberschrittenem
        Budget traegt damit 0 zur Prognose bei.
        """
        roh = self.restvolumen_roh
        return None if roh is None else max(0.0, roh)

    @property
    def budget_ueberschritten(self) -> bool:
        roh = self.restvolumen_roh
        return roh is not None and roh < 0

    @property
    def im_prognose_scope(self) -> bool:
        """Ob das Projekt in die Prognose eingeht.

        Drei Bedingungen, alle drei noetig: das Projekt ist ``aktiv``, es ist **nicht**
        ``abgeschlossen``, und sein Budget ist als Euro-Gesamtbudget lesbar.
        """
        return self.aktiv and not self.abgeschlossen and verwertbar(self.budget)

    @property
    def effektiver_stundensatz(self) -> float | None:
        """Erzielter Umsatz je geleisteter Stunde, ``None`` ohne erfasste Zeit."""
        if self.stundensatz_uebersteuerung is not None:
            return self.stundensatz_uebersteuerung
        if not self.verbrauchte_stunden:
            return None
        return self.verbrauchtes_volumen / self.verbrauchte_stunden

    @property
    def beteiligte(self) -> tuple[Mitarbeiter, ...]:
        return tuple(anteil.mitarbeiter for anteil in self.anteile)

    def anteil_je_mitarbeiter(self) -> dict[Mitarbeiter, float]:
        """Der historische Stundenanteil je Person.

        Die Anteile summieren sich zu 1. Ohne erfasste Stunden gibt es keinen
        Schluessel - dann ist das Ergebnis leer, statt gleichmaessig zu verteilen.
        """
        gesamt = sum(anteil.stunden for anteil in self.anteile)
        if not gesamt:
            return {}
        return {anteil.mitarbeiter: anteil.stunden / gesamt for anteil in self.anteile}
