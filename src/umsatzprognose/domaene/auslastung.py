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
