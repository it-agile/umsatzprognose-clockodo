"""Projekt - der Gegenstand, um den die ganze Prognose kreist.

Ein in Clockodo angelegtes Projekt gilt laut Spec als beauftragt; Storno auf
Projektebene ist deshalb kein Thema. Das Projekt haelt sein Auftragsvolumen (Budget),
seinen Verbrauch und die Anteile der beteiligten Personen - und leitet daraus die
Groessen aus Spec 5.1 ab.

Was hier bewusst **nicht** steht, ist die Prognose selbst. Sie ist nicht projektweise
zerlegbar: der Kapazitaetsdeckel aus 5.4 Schritt 4 wirkt je Person ueber **alle** ihre
Projekte, und ein Simulationslauf ist eine Ziehung ueber das gesamte Portfolio. Ein
Projekt, das seine Prognose allein rechnet, kann den Deckel nicht kennen, und die Summe
unabhaengig gerechneter Projektverteilungen ist nicht die Portfolio-Bandbreite. Das
Projekt liefert deshalb Regeln und Zustand, die Simulation sitzt am
:class:`~umsatzprognose.domaene.bestand.Bestand`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from umsatzprognose.domaene.kunde import Kunde
from umsatzprognose.domaene.mitarbeiter import Mitarbeiter
from umsatzprognose.domaene.projektanteil import Projektanteil


@dataclass(frozen=True)
class Budget:
    """Das vereinbarte Volumen eines Projekts.

    Spec Abschnitt 4 nennt ``budget.amount`` als Auftragsvolumen. Ob dort wirklich ein
    Euro-Gesamtbudget steht, entscheiden drei weitere Felder - am 24.08.2026 an den 895
    Projekten der Installation geprueft:

    * ``monetaer`` false: der Betrag ist eine **Stundenzahl** (8 Projekte, alle inaktiv,
      mit Werten wie 6, 12, 48). Als Euro gelesen waere das ein stiller Faktor-Fehler.
    * ``intervall`` gesetzt: Budget je Intervall statt Gesamtbudget - die Formel aus
      5.1 gilt dann nicht.
    * ``aus_teilprojekten``: das Budget stammt aus Teilprojekten.

    Bei den aktiven Projekten trat keiner der drei Faelle auf, keiner ist also an
    echten Zahlen durchgerechnet. Statt eine plausible Umrechnung zu erfinden, gilt ein
    solches Budget als nicht verwertbar; der Grund steht in :attr:`sonderfall` und
    erreicht ueber einen Hinweis die Darstellung. Eine sichtbare Untererfassung ist
    besser als eine still falsche Euro-Zahl.

    ``hart`` (``budget.hard``) ist in dieser Installation ueberall false, wo es zaehlt:
    Budgets sind weiche Grenzen, der Verbrauch kann sie ueberschreiten. Fuer die
    Prognose gilt trotzdem eine harte Grenze - siehe
    :attr:`Projekt.restvolumen_prognosewirksam`.
    """

    betrag: float | None = None
    monetaer: bool = True
    hart: bool = False
    intervall: str | None = None
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
        return float(self.betrag) if self.verwertbar else None


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
        """``Auftragsvolumen - Verbrauch``, vorzeichenbehaftet (Spec 5.1).

        Negativ heisst: das Budget ist historisch ueberschritten. Diese Groesse wird
        nicht verworfen - Haeufigkeit und Hoehe von Ueberschreitungen sind laut Spec
        ein Kalibrierungssignal und kein Fehler. ``None``, wenn das Projekt kein
        bezifferbares Auftragsvolumen hat; dann gibt es kein Restvolumen, und eine 0
        waere eine andere Aussage.
        """
        if self.auftragsvolumen is None:
            return None
        return self.auftragsvolumen - self.verbrauchtes_volumen

    @property
    def restvolumen_prognosewirksam(self) -> float | None:
        """Bei 0 gekapptes Restvolumen - was noch abgerufen werden kann (Spec 5.1).

        Seit Spec v0.5 gilt: eine Ueberschreitung kann nur historisch entstehen, die
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
        """Ob das Projekt in die Prognose eingeht: aktiv und mit verwertbarem Budget.

        Die Abgrenzung auf aktive Projekte deckt die Spec nicht ab; sie ist eine
        Annahme (von 895 Projekten sind 122 aktiv) und gehoert bestaetigt.
        """
        return self.aktiv and self.budget.verwertbar

    @property
    def effektiver_stundensatz(self) -> float | None:
        """Erzielter Umsatz je geleisteter Stunde, ``None`` ohne erfasste Zeit.

        Aus ``Verbrauch / Stunden`` abgeleitet und nicht aus dem Feld ``hourly_rate``:
        das ist genau dann gesetzt, wenn ein Projekt einen einheitlichen Satz und keine
        Pauschalleistungen hat - bei 92 von 870 Gruppen, dort meist 0. Auch wo beides
        vorliegt, weicht der abgeleitete Satz vom nominalen ab, weil nicht jede erfasste
        Stunde abgerechnet wird.

        Die in Spec 5.1 verlangte **Normalisierung von Pauschalleistungen** ist damit
        noch nicht abgedeckt: acht Gruppen haben Umsatz ohne jede erfasste Zeit und
        liefern hier ``None``. Die Definition des effektiven Stundensatzes steht in
        Spec v0.3, die dem Repository nicht vorliegt.
        """
        if not self.verbrauchte_stunden:
            return None
        return self.verbrauchtes_volumen / self.verbrauchte_stunden

    @property
    def beteiligte(self) -> tuple[Mitarbeiter, ...]:
        return tuple(anteil.mitarbeiter for anteil in self.anteile)

    def anteil_je_mitarbeiter(self) -> dict[Mitarbeiter, float]:
        """Der historische Stundenanteil je Person (Spec 5.4, Schritt 3).

        Die Anteile summieren sich zu 1. Ohne erfasste Stunden gibt es keinen
        Schluessel - dann ist das Ergebnis leer, statt gleichmaessig zu verteilen.
        """
        gesamt = sum(anteil.stunden for anteil in self.anteile)
        if not gesamt:
            return {}
        return {anteil.mitarbeiter: anteil.stunden / gesamt for anteil in self.anteile}
