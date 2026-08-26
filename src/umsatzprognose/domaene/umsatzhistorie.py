"""Umsatzhistorie - der tatsaechliche Umsatz je Monat.

Die erste Groesse im Dashboard und die einzige, die sich keinem Projekt zuordnen laesst:
gemeint ist der **Gesamtumsatz** aller Buchungen eines Monats, einschliesslich der
Buchungen auf einen Kunden ohne Projekt. Genau deshalb steht sie neben Projekt und
Kunde und nicht in ihnen.

Zwei Festlegungen, die sich aus den Daten ergeben und nicht aus der Spec:

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

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

MONATSNAMEN = (
    "Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
    "Jul", "Aug", "Sep", "Okt", "Nov", "Dez",
)  # fmt: skip


def _vormonat(jahr: int, monat: int) -> tuple[int, int]:
    return (jahr - 1, 12) if monat == 1 else (jahr, monat - 1)


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
        """Etwa ``Sep 2025``.

        Fest verdrahtet statt ueber ``locale``: in Colab ist keine deutsche Locale
        gesetzt, ``%b`` liefert dort englische Namen.
        """
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
            jahr, monat = _vormonat(jahr, monat)
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

    def summe(self, anzahl: int | None = None) -> float:
        """Umsatz der abgeschlossenen Monate."""
        return sum(m.umsatz for m in self.abgeschlossene(anzahl))

    def durchschnitt(self, anzahl: int | None = None) -> float:
        """Mittlerer Monatsumsatz der abgeschlossenen Monate, 0 wenn es keine gibt."""
        monate = self.abgeschlossene(anzahl)
        return self.summe(anzahl) / len(monate) if monate else 0.0
