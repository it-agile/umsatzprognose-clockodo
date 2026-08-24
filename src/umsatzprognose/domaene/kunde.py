"""Kunde - Auftraggeber eines Projekts.

Traegt nur, was die Prognose braucht: eine Identitaet und einen Namen fuer die
Darstellung. Die Zuordnung zeigt vom Projekt zum Kunden, nicht zurueck; welche
Projekte zu einem Kunden gehoeren, beantwortet der
:class:`~umsatzprognose.domaene.bestand.Bestand`. Das haelt beide Objekte
unveraenderlich - eine wechselseitige Referenz waere anders nicht aufzubauen.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Kunde:
    """Ein Auftraggeber."""

    id: int
    name: str | None = None

    def __str__(self) -> str:
        return self.name or f"Kunde {self.id}"
