"""Die Abbildungsschicht: alles, was Clockodo weiss, weiss nur dieses Paket.

Hier steht der HTTP-Zugriff und die Uebersetzung der Antworten in Fachobjekte - und
damit auch das gesammelte Wissen ueber die Eigenheiten dieser API: welche Version
welchen Endpunkt bedient, welche Query-Parameter akzeptiert werden, welche Felder
anders heissen oder anders gemeint sind, als es aussieht. Jeder dieser Punkte ist an
einer echten Antwort geprueft, nicht aus der Doku uebernommen; ``docs.clockodo.com``
ist eine JavaScript-Anwendung und war nicht auslesbar.

Die Domaene importiert von hier **nichts**. Umgekehrt schon - die Repositories bauen
Fachobjekte.
"""

from umsatzprognose.clockodo.bestand import BestandRepository
from umsatzprognose.clockodo.client import ClockodoClient, ClockodoError
from umsatzprognose.clockodo.config import ClockodoCredentials, MissingCredentialsError, in_colab
from umsatzprognose.clockodo.kunden import KundenRepository
from umsatzprognose.clockodo.mitarbeiter import MitarbeiterRepository
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
    "in_colab",
]
