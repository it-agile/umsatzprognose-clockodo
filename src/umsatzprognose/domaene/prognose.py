"""Prognose - die Ausgabe der Simulation, und die Naht, an der sie andockt.

Zwei Implementierungen: :class:`NochKeinePrognose` sagt aus, dass es keine Bandbreite
gibt, und warum - etwa weil die Abrufquote-Verteilung mangels Beobachtungen nicht
geschaetzt werden konnte oder kein Projekt im Prognose-Scope liegt. Die Monte-Carlo-
Simulation selbst,
:class:`~umsatzprognose.domaene.simulation.MonteCarloPrognose`, liefert die tatsaechliche
Bandbreite; beide werden ueber
:meth:`umsatzprognose.domaene.bestand.Bestand.simulieren` erreicht, das je nach Datenlage
zwischen ihnen entscheidet.

``Prognose`` ist ein :class:`~typing.Protocol`, keine gemeinsame Basisklasse: beide
Implementierungen erfuellen es rein strukturell (von mypy geprueft), ohne davon zu
erben - nirgends im Code wird per ``isinstance`` gegen ``Prognose`` geprueft, eine
nominale Vererbungsbeziehung waere hier nur ballast.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from decimal import Decimal

    from .kunde import Kunde

from dataclasses import dataclass

# die Bandbreite wird auf diesen Niveaus ausgewiesen.
KONFIDENZNIVEAUS = (0.95, 0.85, 0.50)


@dataclass(frozen=True, slots=True)
class Umsatzspanne:
    """Zusaetzlich simulierter Umsatz in einem Horizontmonat.

    "Zusaetzlich" heisst: ueber den bereits gebuchten Betrag hinaus (siehe
    :class:`Umsatzanteil`). ``minimum``/``maximum`` sind das 5-%- bzw. 95-%-Quantil
    ueber alle Laeufe (die Grenzen des 95-%-Konfidenzbands, nicht die absoluten
    Extreme), ``mittelwert`` der Mittelwert ueber alle Laeufe. Anders als ein Median
    addieren sich die Mittelwerte der Projekte eines Kunden und die der Kunden
    exakt zum Mittelwert des Monats.
    """

    minimum: Decimal
    mittelwert: Decimal
    maximum: Decimal


@dataclass(frozen=True, slots=True)
class Umsatzanteil:
    """Der Anteil eines Projekts oder Kunden an der Prognose, je Horizontmonat.

    Beide Tupel haben die Reihenfolge von :meth:`Prognose.horizontmonate`. ``gebucht``
    ist der bereits gebuchte Betrag (steht fest, ohne Spanne), ``simuliert`` der
    zusaetzlich simulierte Umsatz.
    """

    gebucht: tuple[Decimal, ...]
    simuliert: tuple[Umsatzspanne, ...]


@dataclass(frozen=True, slots=True)
class Projektumsatz:
    """Ein Projekt und sein :class:`Umsatzanteil`. ``name`` ist der Projektname ohne den
    Kunden - der steht in :class:`Kundenumsatz`."""

    name: str
    anteil: Umsatzanteil


@dataclass(frozen=True, slots=True)
class Kundenumsatz:
    """Ein Kunde, sein :class:`Umsatzanteil` und die Projekte, aus denen er sich ergibt.

    ``kunde`` ist ``None`` fuer Projekte ohne Kunden. ``projekte`` enthaelt nur
    Projekte mit gebuchtem oder simuliertem Umsatz im Horizont.
    """

    kunde: Kunde | None
    anteil: Umsatzanteil
    projekte: tuple[Projektumsatz, ...]


class Prognose(Protocol):
    """Das Ergebnis eines Prognoselaufs ueber den Bestand."""

    @property
    def vorhanden(self) -> bool:
        """Ob belastbare Zahlen vorliegen."""
        ...

    @property
    def begruendung(self) -> str:
        """Eine Zeile fuer die Darstellung - was die Prognose sagt oder warum nicht."""
        ...

    def horizontmonate(self) -> tuple[tuple[int, int], ...]:
        """Die Monate des Horizonts (Jahr, Monat), in der Reihenfolge von :meth:`monatswerte`
        und :meth:`gebucht`."""
        ...

    def monatswerte(self) -> dict[float, list[Decimal]]:
        """Je Konfidenzniveau ein Umsatzwert pro Monat des Horizonts."""
        ...

    def gebucht(self) -> list[Decimal]:
        """Bereits gebuchter Betrag je Horizontmonat.

        Fuer den Stichtagsmonat immer 0: dort laesst sich der Anteil vor dem Stichtag
        nicht von dem danach trennen (Monatsgruppierung ohne Tagesgrenze), und was vor
        dem Stichtag schon feststand, zeigt die Historie getrennt.
        """
        ...

    def summe(self) -> dict[float, Decimal]:
        """Je Konfidenzniveau der Umsatz ueber den gesamten Horizont."""
        ...

    def kapazitaet_limitierend_anteil(self) -> float:
        """Anteil der Laeufe, in denen die Kapazitaet der Engpass war.

        Die Groesse unterscheidet einen Nachfrage- von einem Kapazitaetsengpass und ist
        ein geforderter Output, nicht ein Nebenprodukt.
        """
        ...

    def kapazitaet_je_projekt(self) -> dict[int, float]:
        """Median der ueber den Horizont gelieferten Stunden je Projekt-ID.

        Zeigt, wie sich die in der Simulation tatsaechlich verbrauchte Kapazitaet auf
        die Projekte im Prognose-Scope verteilt - Projekte ohne ableitbaren
        Stundensatz (Pauschalleistungen) tragen 0 bei, weil fuer sie kein
        Stundenbedarf ableitbar ist.
        """
        ...

    def ohne_budget(self) -> list[Decimal]:
        """Median des Umsatzes der Projekte ohne Budget je Horizontmonat.

        Der Anteil von :meth:`monatswerte` (Niveau 50 %), der auf Projekte ohne Budget
        entfaellt (siehe :mod:`umsatzprognose.domaene.ohne_budget`); 0 je Monat, wenn
        das Modell aus war. Der Median einer Teilmenge, nicht die Differenz zweier
        Mediane: beide Zahlen summieren sich nicht exakt zum Gesamtmedian.
        """
        ...

    def umsatz_je_kunde(self) -> list[Kundenumsatz]:
        """Je Kunde der gebuchte und der zusaetzlich simulierte Umsatz je Horizontmonat,
        aufgeschluesselt nach den Projekten des Kunden.

        Die gebuchten Betraege summieren sich je Monat auf :meth:`gebucht`, die
        Mittelwerte der simulierten Spannen auf den Mittelwert des Monats minus
        :meth:`gebucht`. Kunden und Projekte ohne gebuchten oder simulierten Umsatz im
        Horizont fehlen. Schulungsanmeldungen sind kein Teil der Simulation.
        """
        ...


@dataclass(frozen=True, slots=True)
class NochKeinePrognose:
    """Es gibt keine Prognose, und zwar aus einem benennbaren Grund.

    Erfuellt :class:`Prognose` strukturell, ohne davon zu erben (siehe Moduldocstring).
    """

    fehlt: str = (
        "Für den Bestand gibt es keine Bandbreite: entweder liegt kein Projekt im "
        "Prognose-Scope, oder die Abrufquote-Verteilung konnte mangels "
        "Beobachtungen mit Restvolumen > 0 zu Monatsbeginn nicht geschätzt werden."
    )

    @property
    def vorhanden(self) -> bool:
        return False

    @property
    def begruendung(self) -> str:
        return self.fehlt

    def horizontmonate(self) -> tuple[tuple[int, int], ...]:
        return ()

    def monatswerte(self) -> dict[float, list[Decimal]]:
        return {}

    def gebucht(self) -> list[Decimal]:
        return []

    def summe(self) -> dict[float, Decimal]:
        return {}

    def kapazitaet_limitierend_anteil(self) -> float:
        return 0.0

    def kapazitaet_je_projekt(self) -> dict[int, float]:
        return {}

    def ohne_budget(self) -> list[Decimal]:
        return []

    def umsatz_je_kunde(self) -> list[Kundenumsatz]:
        return []
