"""Abrufquote - die einzige Unsicherheit, die dieses Modell kennt.

Ein in Clockodo angelegtes Projekt gilt als beauftragt, das Budget steht. Offen
ist allein, **wie viel** vom offenen Restvolumen in einem Monat tatsaechlich abgerufen
wird. Genau das ist die Abrufquote, nicht als Formel, sondern
als **empirische Verteilung** aus der eigenen Historie: eine Beobachtung je Projekt und
Monat, gezogen wird spaeter mit Zuruecklegen daraus.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .projekt import Projekt

from dataclasses import dataclass
from functools import cached_property

import numpy as np

from .umsatzhistorie import MONATSNAMEN


@dataclass(frozen=True)
class Abrufquote:
    """Eine einzelne Beobachtung: ein Projekt in einem Monat.

    Attributes:
        projekt: das beobachtete Projekt - mitgefuehrt, damit eine auffaellige Quote
            benennbar bleibt und nicht als anonyme Zahl in der Verteilung verschwindet.
        verbrauch: der in diesem Monat abgerufene Betrag in Euro.
        restvolumen_zu_monatsbeginn: das Restvolumen am ersten Tag des Monats, aus dem
            **heutigen** Budget zurueckgerechnet (siehe
            :class:`~umsatzprognose.domaene.verbrauchsverlauf.Verbrauchsverlauf`).
    """

    projekt: Projekt
    jahr: int
    monat: int
    verbrauch: float
    restvolumen_zu_monatsbeginn: float

    def __post_init__(self) -> None:
        if self.restvolumen_zu_monatsbeginn <= 0:
            raise ValueError(
                "Eine Abrufquote braucht ein Restvolumen > 0 zu Monatsbeginn; "
                f"hier: {self.restvolumen_zu_monatsbeginn}"
            )

    def __str__(self) -> str:
        return f"{self.beschriftung}: {self.wert:.3f}"

    @property
    def wert(self) -> float:
        """Der Anteil des offenen Restvolumens, der im Monat abgerufen wurde."""
        return self.verbrauch / self.restvolumen_zu_monatsbeginn

    @property
    def schluessel(self) -> tuple[int, int]:
        return (self.jahr, self.monat)

    @property
    def beschriftung(self) -> str:
        """Etwa ``Kunde / Projekt, Jun 2026``."""
        return f"{self.projekt.bezeichnung}, {MONATSNAMEN[self.monat - 1]} {self.jahr}"


@dataclass(frozen=True)
class Abrufquotenverteilung:
    """Die empirische Verteilung der Abrufquote ueber alle Projekt-Monate.

    **Portfolioweit und nicht je Projekt.** ein
    einzelnes Projekt hat zu wenige Monate, um eine eigene Verteilung zu tragen.

    Die Verteilung ist ein Vorrat an beobachteten Quoten, aus dem die Simulation zieht -
    kein Modell mit Parametern. Sie hat damit weder Verteilungsannahme noch Rand: sie
    kann nichts liefern, was nicht schon einmal vorkam.
    """

    quoten: tuple[Abrufquote, ...] = ()

    @classmethod
    def aus_quoten(cls, quoten: Iterable[Abrufquote]) -> Abrufquotenverteilung:
        """Die Verteilung aus beliebig gelieferten Beobachtungen; Reihenfolge egal."""
        return cls(tuple(quoten))

    def __str__(self) -> str:
        if not self.vorhanden:
            return "keine Beobachtungen"
        return (
            f"{self.anzahl} Projekt-Monate, Median {self.median:.3f}, "
            f"Mittelwert {self.mittelwert:.3f}, "
            f"davon {self.anteil_ohne_abruf:.0%} ohne Abruf"
        )

    @property
    def anzahl(self) -> int:
        return len(self.quoten)

    @property
    def vorhanden(self) -> bool:
        """Ob ueberhaupt gezogen werden kann."""
        return bool(self.quoten)

    # cached_property schreibt in ``__dict__`` und umgeht damit ``__setattr__`` - das
    # funktioniert auch an einer frozen dataclass. Gerechnet wird die Sortierung
    # deshalb einmal und nicht bei jeder Ziehung: die Simulation zieht je Lauf,
    # Projekt und Monat, das sind bei 10.000 Laeufen ueber alle Projekte des Scope und
    # drei Monate weit mehr als eine Million Ziehungen.
    @cached_property
    def _werte(self) -> tuple[float, ...]:
        return tuple(sorted(quote.wert for quote in self.quoten))

    @cached_property
    def _werte_array(self) -> np.ndarray:
        """``_werte`` als Array - fuer die vektorisierte Ziehung in ``ziehen_array``."""
        return np.array(self._werte)

    def werte(self) -> tuple[float, ...]:
        """Alle beobachteten Quoten, aufsteigend sortiert."""
        return self._werte

    def quantil(self, anteil: float) -> float | None:
        """Das empirische Quantil, linear zwischen den Ordnungsstatistiken.

        ``None``, wenn es keine Beobachtungen gibt - eine 0 waere hier die Aussage
        "nichts wird abgerufen" und damit eine andere.
        """
        if not 0.0 <= anteil <= 1.0:
            raise ValueError(f"Ein Quantil liegt zwischen 0 und 1, nicht bei {anteil}")
        werte = self._werte
        if not werte:
            return None
        stelle = anteil * (len(werte) - 1)
        unten = int(stelle)
        oben = min(unten + 1, len(werte) - 1)
        rest = stelle - unten
        return werte[unten] * (1.0 - rest) + werte[oben] * rest

    @property
    def median(self) -> float | None:
        return self.quantil(0.5)

    @property
    def mittelwert(self) -> float | None:
        werte = self._werte
        return sum(werte) / len(werte) if werte else None

    @property
    def anteil_ohne_abruf(self) -> float:
        """Anteil der Projekt-Monate, in denen nichts abgerufen wurde.

        Die aussagekraeftigste Kennzahl der Verteilung: sie entscheidet darueber, wie oft
        die Simulation einen Monat ohne Umsatz zieht, und damit ueber die Breite der
        Bandbreite nach unten.
        """
        if not self.quoten:
            return 0.0
        return sum(1 for wert in self._werte if wert == 0.0) / self.anzahl

    @property
    def anteil_ueber_budget(self) -> float:
        """Anteil der Beobachtungen mit einer Quote ueber 1 - weiche Budgets."""
        if not self.quoten:
            return 0.0
        return sum(1 for wert in self._werte if wert > 1.0) / self.anzahl

    def hoechste(self, anzahl: int = 5) -> tuple[Abrufquote, ...]:
        """Die auffaelligsten Beobachtungen - fuer die Kalibrierung."""
        return tuple(sorted(self.quoten, key=lambda q: q.wert, reverse=True)[:anzahl])

    def ziehen(self, zufall: np.random.Generator) -> float:
        """Eine Quote, mit Zuruecklegen gezogen.

        Der Zufallsgenerator wird uebergeben und nicht hier erzeugt: ein Lauf muss
        wiederholbar sein, und wer den Startwert setzt, ist der Aufrufer.
        """
        if not self.quoten:
            raise ValueError("Aus einer leeren Verteilung kann nicht gezogen werden")
        return float(zufall.choice(self._werte_array))

    def ziehungen(self, anzahl: int, zufall: np.random.Generator) -> tuple[float, ...]:
        """``anzahl`` Quoten in einem Zug - unabhaengig und mit Zuruecklegen."""
        if not self.quoten:
            raise ValueError("Aus einer leeren Verteilung kann nicht gezogen werden")
        return tuple(float(wert) for wert in zufall.choice(self._werte_array, size=anzahl))

    def ziehen_array(self, form: tuple[int, ...], zufall: np.random.Generator) -> np.ndarray:
        """Wie :meth:`ziehungen`, aber als Array beliebiger Form statt als Tupel.

        Fuer die Monte-Carlo-Simulation: sie zieht die Quoten aller Laeufe und
        Projekte eines Horizontmonats in einem Aufruf statt einzeln ueber
        :meth:`ziehen` - der Gewinn der numpy-Umstellung entsteht durch das
        Vektorisieren ueber die Laeufe, nicht durch den Zufallsgenerator allein.
        """
        if not self.quoten:
            raise ValueError("Aus einer leeren Verteilung kann nicht gezogen werden")
        return zufall.choice(self._werte_array, size=form)
