"""Umsatzprognose - Baustein Bestand (Clockodo).

Rollierende 1-3-Monats-Prognose des Umsatzes aus laufenden, in Clockodo angelegten
Projekten.

Das Paket ist in drei Schichten geschnitten, mit genau einer erlaubten
Abhaengigkeitsrichtung::

    darstellung  ->  domaene  <-  clockodo

* :mod:`umsatzprognose.domaene` - die Fachobjekte: Kunde, Projekt, Mitarbeiter,
  Projektanteil, Umsatzhistorie und der Bestand als Ganzes. Kennt weder JSON noch HTTP.
* :mod:`umsatzprognose.clockodo` - der Zugriff auf die API und die Uebersetzung ihrer
  Antworten in Fachobjekte. Traegt das gesammelte Wissen ueber die Eigenheiten dieser
  API.
* :mod:`umsatzprognose.darstellung` - Diagramme, Tabellen und das
  :class:`~umsatzprognose.darstellung.dashboard.Dashboard`, das die Notebooks benutzen.

Der uebliche Einstieg ist eine Zeile::

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

__all__ = [
    "Bestand",
    "BestandRepository",
    "Budget",
    "ClockodoClient",
    "ClockodoCredentials",
    "Dashboard",
    "Hinweis",
    "Kunde",
    "Mitarbeiter",
    "Monatsumsatz",
    "Projekt",
    "Projektanteil",
    "Umsatzhistorie",
]
