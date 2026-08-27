"""Projekt - der Gegenstand, um den die ganze Prognose kreist.

Ein in Clockodo angelegtes Projekt gilt als beauftragt; Storno auf
Projektebene ist deshalb kein Thema. Das Projekt haelt sein Auftragsvolumen (Budget),
seinen Verbrauch und die Anteile der beteiligten Personen - und leitet daraus die
Groessen ab.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date

    from .kunde import Kunde
    from .mitarbeiter import Mitarbeiter
    from .projektanteil import Projektanteil

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Budget:
    """Das vereinbarte Volumen eines Projekts.

    ``budget.amount`` ist das Auftragsvolumen. Ob dort wirklich ein
    Euro-Gesamtbudget steht, entscheiden drei weitere Felder:

    * ``monetaer`` false: der Betrag ist eine **Stundenzahl**. Der Fall kommt vor, nur
      bei inaktiven Projekten. Als Euro gelesen waere das ein stiller Faktor-Fehler.
    * ``intervall`` gesetzt: Budget je Intervall statt Gesamtbudget. Laut
      Clockod-API ist das ein **Integer-Enum**
      (0 wochenweise, 1 monatlich, 2 quartalsweise, 3 jaehrlich) und kein String.
    * ``aus_teilprojekten``: das Budget stammt aus Teilprojekten.
    """

    betrag: float | None = None
    monetaer: bool = True
    hart: bool = False
    intervall: int | None = None
    aus_teilprojekten: bool = False

    @property
    def gesetzt(self) -> bool:
        return self.betrag is not None

    @property
    def sonderfall(self) -> str | None:
        """Warum der Betrag kein Euro-Gesamtbudget ist, oder ``None``."""
        if not self.gesetzt:
            return None
        if not self.monetaer:
            return "Budget in Stunden statt in Euro"
        if self.intervall is not None:
            return "Budget je Intervall statt Gesamtbudget"
        if self.aus_teilprojekten:
            return "Budget stammt aus Teilprojekten"
        return None

    @property
    def verwertbar(self) -> bool:
        """Ob der Betrag als Euro-Gesamtbudget gelesen werden darf."""
        return self.gesetzt and self.sonderfall is None

    @property
    def auftragsvolumen(self) -> float | None:
        """Das Auftragsvolumen in Euro, ``None`` wenn keines bezifferbar ist."""
        return float(self.betrag) if self.betrag and self.verwertbar else None


OHNE_BUDGET = Budget()


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
    deadline: date | None = None
    automatic_completion: bool = False

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
        return self.budget.auftragsvolumen

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
        return self.aktiv and not self.abgeschlossen and self.budget.verwertbar

    @property
    def automatischer_abschluss(self) -> date | None:
        """Ab wann das Projekt automatisch abgeschlossen wird, ``None`` ohne einen.

        Nur gesetzt, wenn ``automatic_completion`` aktiv ist - eine reine ``deadline``
        ohne diesen Schalter ist unverbindlich und beendet das Projekt nicht
        zuverlaessig (nur ``active``, ``completed`` und
        ``completed_at`` gelten als zuverlaessiges Endesignal). Ab diesem Datum traegt
        das Projekt keinen Umsatz mehr bei.
        """
        return self.deadline if self.automatic_completion else None

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
