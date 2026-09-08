"""Die Abbildungsschicht: Zugriff auf die Clockodo API.

Hier steht der HTTP-Zugriff und die Uebersetzung der Antworten in Fachobjekte.

Die Domaene importiert von hier **nichts**. Umgekehrt schon - die Repositories bauen
Fachobjekte.

Die Abrufe sind nebenlaeufig: :class:`ClockodoClient` besteht aus Coroutinen, die
Repositories faechern die voneinander unabhaengigen Endpunkte auf und setzen erst die
Antworten zusammen. Ihre ``laden``-Methoden bleiben gewoehnliche Funktionen - was
dahinter noetig ist, steht in :mod:`umsatzprognose.clockodo.nebenlaeufig`.
"""

from umsatzprognose.clockodo.auslastung import AuslastungRepository
from umsatzprognose.clockodo.bestand import BestandRepository
from umsatzprognose.clockodo.client import ClockodoClient, ClockodoError
from umsatzprognose.clockodo.config import ClockodoCredentials, MissingCredentialsError
from umsatzprognose.clockodo.fortschritt import Fortschritt
from umsatzprognose.clockodo.kunden import KundenRepository
from umsatzprognose.clockodo.kurzarbeit import (
    KurzarbeitRepository,
    anzahl_ladeschritte,
    kurzarbeit_aktiv,
    rollenzuordnung_automatisch,
)
from umsatzprognose.clockodo.mitarbeiter import MitarbeiterRepository
from umsatzprognose.clockodo.nebenlaeufig import gleichzeitig, synchron
from umsatzprognose.clockodo.projekte import ProjektRepository
from umsatzprognose.clockodo.umsatz import UmsatzRepository
from umsatzprognose.clockodo.verbrauchsverlauf import VerbrauchsverlaufRepository

__all__ = [
    "AuslastungRepository",
    "BestandRepository",
    "ClockodoClient",
    "ClockodoCredentials",
    "ClockodoError",
    "Fortschritt",
    "KundenRepository",
    "KurzarbeitRepository",
    "MissingCredentialsError",
    "MitarbeiterRepository",
    "ProjektRepository",
    "UmsatzRepository",
    "VerbrauchsverlaufRepository",
    "anzahl_ladeschritte",
    "gleichzeitig",
    "kurzarbeit_aktiv",
    "rollenzuordnung_automatisch",
    "synchron",
]
