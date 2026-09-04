"""Umsatzhistorie - der tatsaechliche Umsatz je Monat.

Die erste Groesse im Dashboard und die einzige, die sich keinem Projekt zuordnen laesst:
gemeint ist der **Gesamtumsatz** aller Buchungen eines Monats, einschliesslich der
Buchungen auf einen Kunden ohne Projekt.

**Der laufende Monat wird getrennt gefuehrt.** Am Stichtag ist er unvollstaendig und
liegt deutlich unter dem Monatsschnitt der abgeschlossenen Monate. In einer
Kennzahl "Umsatz der letzten zwoelf Monate" wuerde er das Ergebnis verfaelschen, im
Diagramm ist er als abgesetzter Balken dagegen aussagekraeftig. :meth:`abgeschlossene`
liefert deshalb nur vollstaendige Monate, :attr:`laufender` den angebrochenen.

**Monate ohne Buchungen fehlen in der Antwort** und werden von :meth:`zum_stichtag` mit
0 aufgefuellt, damit die Zeitachse durchgehend ist und eine Luecke nicht wie ein
fehlender Monat aussieht.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from datetime import date

from dataclasses import dataclass

from umsatzprognose.util import Monat, vormonat

from .hinweis import Hinweis

MONATSNAMEN = (
    "Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
    "Jul", "Aug", "Sep", "Okt", "Nov", "Dez",
)  # fmt: skip


def fehlende_monate_hinweis(
    text: str, monate: Sequence[Monat], vorhanden: Iterable[Monat]
) -> tuple[Hinweis, ...]:
    """Ein :class:`Hinweis` fuer die Monate aus ``monate``, die nicht in ``vorhanden`` stehen.

    Gemeinsames Muster von :class:`~umsatzprognose.domaene.kosten.Kostenplan` und
    :class:`~umsatzprognose.domaene.schulung.Schulungsplan`: ob ein Monat fehlt, weil
    die Quelle nicht geladen wurde oder weil sie geladen ist, aber keinen Eintrag fuer
    diesen Monat enthaelt, sieht fuer den Leser gleich aus - beides ist keine
    Fehlermeldung, sondern eine Datenluecke, die sich in 0 niederschlaegt.
    """
    fehlend = [monat for monat in monate if monat not in set(vorhanden)]
    if not fehlend:
        return ()
    return (Hinweis(text, tuple(f"{MONATSNAMEN[monat - 1]} {jahr}" for jahr, monat in fehlend)),)


@dataclass(frozen=True)
class Monatsumsatz:
    """Umsatz und geleistete Stunden eines Kalendermonats."""

    jahr: int
    monat: int
    umsatz: float = 0.0
    stunden: float = 0.0

    def __str__(self) -> str:
        return self.beschriftung

    @property
    def beschriftung(self) -> str:
        """Etwa ``Sep 2025``"""
        return f"{MONATSNAMEN[self.monat - 1]} {self.jahr}"

    @property
    def schluessel(self) -> tuple[int, int]:
        return (self.jahr, self.monat)

    def enthaelt(self, tag: date) -> bool:
        return (tag.year, tag.month) == self.schluessel


@dataclass(frozen=True)
class Umsatzhistorie:
    """Eine lueckenlose Folge von Monatsumsaetzen bis zum Stichtag."""

    stichtag: date
    monate: tuple[Monatsumsatz, ...] = ()

    @classmethod
    def zum_stichtag(
        cls,
        monate: Iterable[Monatsumsatz],
        stichtag: date,
        *,
        abgeschlossene: int = 12,
    ) -> Umsatzhistorie:
        """Baut die Historie aus beliebig gelieferten Monaten.

        Args:
            monate: gefundene Monatsumsaetze, Reihenfolge und Vollstaendigkeit egal.
            stichtag: der Tag, an dem die Prognose erstellt wird.
            abgeschlossene: Anzahl vollstaendiger Monate vor dem laufenden.

        Returns:
            Die ``abgeschlossene`` letzten vollstaendigen Monate plus den laufenden, in
            zeitlicher Reihenfolge und ohne Luecken. Nicht gelieferte Monate stehen mit
            0 darin, ueberzaehlige aeltere Monate werden verworfen.
        """
        vorhanden = {m.schluessel: m for m in monate}
        reihe: list[Monatsumsatz] = []
        jahr, monat = stichtag.year, stichtag.month
        for _ in range(abgeschlossene + 1):
            reihe.append(vorhanden.get((jahr, monat), Monatsumsatz(jahr, monat)))
            jahr, monat = vormonat(jahr, monat)
        return cls(stichtag=stichtag, monate=tuple(reversed(reihe)))

    @property
    def laufender(self) -> Monatsumsatz | None:
        """Der angebrochene Monat des Stichtags, ``None`` wenn er nicht enthalten ist."""
        for monat in self.monate:
            if monat.enthaelt(self.stichtag):
                return monat
        return None

    def abgeschlossene(self, anzahl: int | None = None) -> tuple[Monatsumsatz, ...]:
        """Die vollstaendigen Monate, aelteste zuerst; ohne den laufenden."""
        vollstaendig = tuple(m for m in self.monate if not m.enthaelt(self.stichtag))
        return vollstaendig[-anzahl:] if anzahl else vollstaendig

    def letzte(self, anzahl: int | None = None) -> Umsatzhistorie:
        """Die letzten ``anzahl`` abgeschlossenen Monate plus der laufende, als eigene Historie.

        Ohne ``anzahl`` (``None``) unveraendert die gesamte Historie - Kurzform fuer
        Ansichten, die bewusst nicht auf ein Fenster begrenzen, etwa den
        Gewinn/Verlust-Jahresvergleich, der jedes geladene Jahr zeigen soll.
        """
        if anzahl is None:
            return self
        abgeschlossene = self.abgeschlossene(anzahl)
        laufender = self.laufender
        monate = (*abgeschlossene, laufender) if laufender is not None else abgeschlossene
        return type(self)(stichtag=self.stichtag, monate=monate)

    def summe(self, anzahl: int | None = None) -> float:
        """Umsatz der abgeschlossenen Monate."""
        return sum(m.umsatz for m in self.abgeschlossene(anzahl))

    def durchschnitt(self, anzahl: int | None = None) -> float:
        """Mittlerer Monatsumsatz der abgeschlossenen Monate, 0 wenn es keine gibt."""
        monate = self.abgeschlossene(anzahl)
        return self.summe(anzahl) / len(monate) if monate else 0.0
