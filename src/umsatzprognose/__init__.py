"""Umsatzprognose - Baustein Bestand (Clockodo), additiv Schulungsanmeldungen und Kosten.

Rollierende 1-3-Monats-Prognose des Umsatzes aus laufenden, in Clockodo angelegten
Projekten, ergaenzt um Schulungsanmeldungen und eine Kostenprognose aus Google Sheets.

Siehe CLAUDE.md fuer das vollstaendige Aufbau-Diagramm. Der uebliche Einstieg ist eine
Zeile::

    from umsatzprognose import Dashboard

    dashboard = Dashboard.laden()
"""

from umsatzprognose.clockodo import BestandRepository, ClockodoClient, ClockodoCredentials
from umsatzprognose.darstellung import Dashboard
from umsatzprognose.domaene import (
    Bestand,
    Budget,
    Hinweis,
    Kunde,
    Mitarbeiter,
    Monatsumsatz,
    Projekt,
    Projektanteil,
    Umsatzhistorie,
)
from umsatzprognose.kosten import KostenRepository
from umsatzprognose.schulungen import SchulungenRepository

__all__ = [
    "Bestand",
    "BestandRepository",
    "Budget",
    "ClockodoClient",
    "ClockodoCredentials",
    "Dashboard",
    "Hinweis",
    "KostenRepository",
    "Kunde",
    "Mitarbeiter",
    "Monatsumsatz",
    "Projekt",
    "Projektanteil",
    "SchulungenRepository",
    "Umsatzhistorie",
]
