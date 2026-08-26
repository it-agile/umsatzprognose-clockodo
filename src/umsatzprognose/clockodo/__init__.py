"""Die Abbildungsschicht: alles, was Clockodo weiss, weiss nur dieses Paket.

Hier steht der HTTP-Zugriff und die Uebersetzung der Antworten in Fachobjekte - und
damit auch das gesammelte Wissen ueber die Eigenheiten dieser API: welche Version
welchen Endpunkt bedient, welche Query-Parameter akzeptiert werden, welche Felder
anders heissen oder anders gemeint sind, als es aussieht. Jeder dieser Punkte ist an
einer echten Antwort geprueft, nicht aus der Doku uebernommen; ``docs.clockodo.com``
ist eine JavaScript-Anwendung und war nicht auslesbar.

Die Domaene importiert von hier **nichts**. Umgekehrt schon - die Repositories bauen
Fachobjekte.

Die Abrufe sind nebenlaeufig: :class:`ClockodoClient` besteht aus Coroutinen, die
Repositories faechern die voneinander unabhaengigen Endpunkte auf und setzen erst die
Antworten zusammen. Ihre ``laden``-Methoden bleiben gewoehnliche Funktionen - was
dahinter noetig ist, steht in :mod:`umsatzprognose.clockodo.nebenlaeufig`.
"""

from umsatzprognose.clockodo.bestand import BestandRepository
from umsatzprognose.clockodo.client import ClockodoClient, ClockodoError
from umsatzprognose.clockodo.config import ClockodoCredentials, MissingCredentialsError, in_colab
from umsatzprognose.clockodo.kunden import KundenRepository
from umsatzprognose.clockodo.mitarbeiter import MitarbeiterRepository
from umsatzprognose.clockodo.nebenlaeufig import gleichzeitig, synchron
from umsatzprognose.clockodo.projekte import ProjektRepository
from umsatzprognose.clockodo.umsatz import UmsatzRepository

__all__ = [
    "BestandRepository",
    "ClockodoClient",
    "ClockodoCredentials",
    "ClockodoError",
    "KundenRepository",
    "MissingCredentialsError",
    "MitarbeiterRepository",
    "ProjektRepository",
    "UmsatzRepository",
    "gleichzeitig",
    "in_colab",
    "synchron",
]
