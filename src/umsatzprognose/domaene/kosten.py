"""Kostenprognose - Gesamtkosten je Monat aus einer externen Planungstabelle.

**Additiv und unabhaengig von der Bestand-Simulation**, wie
:mod:`umsatzprognose.domaene.schulung`: kein Monte-Carlo-Lauf, keine Bandbreite - der
Betrag je Monat steht in der externen Kostenplanung schon fest.

**Anders als der Schulungsplan gilt die Kostenprognose auch fuer bereits vergangene und
den laufenden Monat**, nicht nur fuer den Prognosehorizont: Clockodo liefert keine
Ist-Kosten, nur Umsaetze aus Einsaetzen, also gibt es keine andere Quelle fuer
Vergangenheitsmonate. :class:`Kostenplan` filtert deshalb, anders als
:class:`~umsatzprognose.domaene.schulung.Schulungsplan`, nicht nach einem Stichtag -
welche Monate gebraucht werden, entscheidet allein der Aufrufer ueber die an
:meth:`Kostenplan.kosten_je_monat` uebergebenen Monate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, assert_never

if TYPE_CHECKING:
    from collections.abc import Sequence

from dataclasses import dataclass, field

from .hinweis import Hinweis
from .umsatzhistorie import MONATSNAMEN

Monat = tuple[int, int]  # (jahr, monat)


@dataclass(frozen=True)
class Geschaetzt:
    """Noch keine Erfassung nachgezogen - die Pauschale gilt unveraendert."""


@dataclass(frozen=True)
class Erfasst:
    """Die tatsaechlich erfassten Allgemeinkosten, aus den ``AB {Monat}``-Reitern."""

    betrag: float


# Ob fuer einen Kostenposten schon eine Erfassung vorliegt oder nur die Pauschale
# gilt - eine geschlossene Menge zweier Faelle, kein optionaler Betrag: ein
# bewusst erfasster Wert von 0 ist ein vorliegender Wert, keine fehlende Erfassung.
Kostenerfassung = Geschaetzt | Erfasst


@dataclass(frozen=True)
class Kostenposten:
    """Die Kosten eines Kalendermonats laut Kostenplanungstabelle.

    ``pauschale`` ist die von Anfang an geplante Kostenpauschale (Gehälter + Spesen +
    Allgemeinkosten, meist), ``allgemeinkosten`` deren Allgemeinkosten-Anteil, den die
    Erfassung ersetzt, und ``erfassung`` die tatsächliche Erfassung der
    Allgemeinkosten - anfangs :class:`Geschaetzt`, weil die Erfassung erst mit
    Zeitverzug aus den ``AB {Monat}``-Reitern nachgezogen wird. Sobald
    :class:`Erfasst`, ersetzt ihr Betrag ausschliesslich den Allgemeinkosten-Anteil
    der Pauschale; Gehälter und Spesen bleiben unveraendert Teil der Pauschale.
    """

    jahr: int
    monat: int
    pauschale: float
    allgemeinkosten: float = 0.0
    erfassung: Kostenerfassung = Geschaetzt()

    @property
    def kosten(self) -> float:
        """Pauschale, mit erfassten Allgemeinkosten statt der geschaetzten, sobald vorhanden."""
        match self.erfassung:
            case Geschaetzt():
                return self.pauschale
            case Erfasst(betrag=betrag):
                return self.pauschale - self.allgemeinkosten + betrag
            case _:
                assert_never(self.erfassung)

    @property
    def schluessel(self) -> Monat:
        return (self.jahr, self.monat)


@dataclass(frozen=True)
class Kostenplan:
    """Alle geladenen Kostenposten.

    Attributes:
        abbildungshinweise: Befunde aus dem Laden der Google-Sheets-Dateien - fehlende
            Konfiguration fuer ein Jahr, eine nicht lesbare Datei. Siehe
            :meth:`~umsatzprognose.kosten.kosten.KostenRepository.laden`.
    """

    posten: tuple[Kostenposten, ...] = ()
    abbildungshinweise: tuple[Hinweis, ...] = field(default_factory=tuple)

    def kosten_je_monat(self, monate: Sequence[Monat]) -> list[float]:
        """Gesamtkosten je uebergebenem Monat, 0 ohne passenden Posten."""
        summen: dict[Monat, float] = {}
        for posten in self.posten:
            summen[posten.schluessel] = summen.get(posten.schluessel, 0.0) + posten.kosten
        return [summen.get(monat, 0.0) for monat in monate]

    def summe(self, monate: Sequence[Monat]) -> float:
        return sum(self.kosten_je_monat(monate))

    def hat_erfassung_je_monat(self, monate: Sequence[Monat]) -> list[bool]:
        """Ob fuer den Monat eine tatsaechliche Kostenerfassung vorliegt statt nur
        der geschaetzten Pauschale - Grundlage fuer die Darstellung (siehe
        :mod:`umsatzprognose.darstellung.diagramme`)."""
        erfasst = {p.schluessel for p in self.posten if isinstance(p.erfassung, Erfasst)}
        return [monat in erfasst for monat in monate]

    def hinweise(self, monate: Sequence[Monat]) -> tuple[Hinweis, ...]:
        """Befunde aus der Abbildung, plus fehlende Monate.

        Ob ein Monat fehlt, weil die Datei nicht geladen wurde, oder weil sie geladen
        ist, aber keinen Posten fuer diesen Monat enthaelt, sieht fuer den Leser gleich
        aus - beides ist kein Fehler, sondern eine Datenluecke, die sich in 0
        niederschlaegt.
        """
        vorhanden = {p.schluessel for p in self.posten}
        fehlend = [monat for monat in monate if monat not in vorhanden]
        fachlich = (
            (
                Hinweis(
                    "Für diese Monate liegt keine Kostenprognose vor - die Kosten "
                    "werden mit 0 angenommen",
                    tuple(f"{MONATSNAMEN[monat - 1]} {jahr}" for jahr, monat in fehlend),
                ),
            )
            if fehlend
            else ()
        )
        return self.abbildungshinweise + fachlich
