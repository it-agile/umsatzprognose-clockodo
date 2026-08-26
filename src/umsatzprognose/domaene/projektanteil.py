"""Projektanteil - was eine Person auf einem Projekt geleistet hat.

Die Verbindung zwischen :class:`~umsatzprognose.domaene.projekt.Projekt` und
:class:`~umsatzprognose.domaene.mitarbeiter.Mitarbeiter`, und damit die Grundlage des
Aufteilungsschluessels aus Spec 5.4, Schritt 3: der historische Anteil je Person an den
Gesamtstunden des Projekts, unveraendert in die Zukunft fortgeschrieben.

**Bewusst aggregiert, nicht als Einzelbuchung.** Die Spec nennt fuer diesen Zweck
``/v2/entries`` mit ``users_id`` je Eintrag. Das waeren allein fuer die letzten zwoelf
Monate mehrere Seiten Einzeleintraege (geprueft am 24.08.2026), aus denen genau
die Summe zu bilden waere, die die API bereits bildet: ``/v2/entrygroups`` mit
``grouping[]=projects_id&grouping[]=users_id`` liefert je Projekt eine Untergruppe je
Person mit ``duration`` und ``revenue``. Der Begriff Zeitbuchung bleibt damit im Modell,
aber in aggregierter Form. Braucht eine spaetere Auswertung wirklich die Aufloesung auf
den einzelnen Eintrag - etwa ``type`` zur Trennung von Pauschalleistungen -, kommt sie
als eigene Objektsorte dazu.
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
