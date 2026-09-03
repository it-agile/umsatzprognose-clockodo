"""Auslastung - Anteil abrechenbarer Arbeitszeit an der verfuegbaren Kapazitaet.

**Additiv und unabhaengig von der Bestand-Simulation**, wie
:mod:`umsatzprognose.domaene.kosten` und :mod:`umsatzprognose.domaene.schulung`: keine
Bandbreite, kein Monte-Carlo-Lauf. "Abrechenbar" zaehlt Clockodos Billable-Status 1
(abrechenbar, noch nicht fakturiert) und 2 (bereits fakturiert) zusammen - Status 0
(nicht abrechenbar, etwa interne Taetigkeiten) zaehlt nicht mit. Die verfuegbare
Kapazitaet je Monat kommt aus
:meth:`~umsatzprognose.domaene.mitarbeiter.Mitarbeiter.verfuegbare_kapazitaet`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .mitarbeiter import Mitarbeiter

from dataclasses import dataclass


@dataclass(frozen=True)
class Auslastungsmonat:
    """Abrechenbare Stunden einer Person in einem Kalendermonat."""

    mitarbeiter: Mitarbeiter
    jahr: int
    monat: int
    abrechenbare_stunden: float = 0.0

    @property
    def verfuegbare_stunden(self) -> float:
        return self.mitarbeiter.verfuegbare_kapazitaet(self.jahr, self.monat)

    @property
    def quote(self) -> float | None:
        """Anteil abrechenbarer Stunden an der verfuegbaren Kapazitaet.

        ``None`` ohne verfuegbare Kapazitaet in diesem Monat, statt einer
        Division durch 0 oder einer irrefuehrenden 0%-Auslastung.
        """
        verfuegbar = self.verfuegbare_stunden
        return None if verfuegbar <= 0 else self.abrechenbare_stunden / verfuegbar


@dataclass(frozen=True)
class Auslastungssumme:
    """Abrechenbare und verfuegbare Stunden einer Person, aufsummiert ueber mehrere Monate.

    Der einzelne Kalendermonat einer :class:`Auslastungsmonat`-Reihe ist fuer einen
    verlaesslichen Blick auf die Auslastung zu kurz - der laufende Monat etwa ist immer
    unvollstaendig gebucht. :meth:`je_mitarbeiter` fasst deshalb ein ganzes Fenster
    abgeschlossener Monate je Person zu einer Gesamtquote zusammen.
    """

    mitarbeiter: Mitarbeiter
    abrechenbare_stunden: float
    verfuegbare_stunden: float

    @property
    def quote(self) -> float | None:
        """Anteil abrechenbarer an verfuegbaren Stunden ueber den gesamten Zeitraum.

        ``None`` ohne verfuegbare Kapazitaet im Zeitraum, statt einer Division durch 0.
        """
        return (
            None
            if self.verfuegbare_stunden <= 0
            else self.abrechenbare_stunden / self.verfuegbare_stunden
        )

    @staticmethod
    def je_mitarbeiter(auslastungen: Iterable[Auslastungsmonat]) -> tuple[Auslastungssumme, ...]:
        """Fasst beliebig viele Monate je Person zu einer Gesamtquote zusammen.

        Reihenfolge und Anzahl der Monate je Person sind egal - typischerweise die
        abgeschlossenen Monate eines Beobachtungsfensters, ohne den laufenden Monat.
        """
        gruppen: dict[int, list[Auslastungsmonat]] = {}
        for eintrag in auslastungen:
            gruppen.setdefault(eintrag.mitarbeiter.id, []).append(eintrag)
        return tuple(
            Auslastungssumme(
                mitarbeiter=eintraege[0].mitarbeiter,
                abrechenbare_stunden=sum(e.abrechenbare_stunden for e in eintraege),
                verfuegbare_stunden=sum(e.verfuegbare_stunden for e in eintraege),
            )
            for eintraege in gruppen.values()
        )
