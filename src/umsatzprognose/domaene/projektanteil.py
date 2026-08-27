"""Projektanteil - was eine Person auf einem Projekt geleistet hat.

Die Verbindung zwischen :class:`~umsatzprognose.domaene.projekt.Projekt` und
:class:`~umsatzprognose.domaene.mitarbeiter.Mitarbeiter`, und damit die Grundlage des
Aufteilungsschluessels: der historische Anteil je Person an den
Gesamtstunden des Projekts, unveraendert in die Zukunft fortgeschrieben.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .mitarbeiter import Mitarbeiter

from dataclasses import dataclass


@dataclass(frozen=True)
class Projektanteil:
    """Geleistete Stunden und erzielter Umsatz einer Person auf einem Projekt."""

    mitarbeiter: Mitarbeiter
    stunden: float
    umsatz: float = 0.0
