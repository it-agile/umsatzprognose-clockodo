"""Die Fachobjekte: Kunde, Projekt, Mitarbeiter, Umsatz - und der Bestand als Ganzes.

Diese Schicht kennt weder JSON noch HTTP. Wie die Clockodo-Antworten aussehen und welche
Eigenheiten sie haben, steht ausschliesslich in :mod:`umsatzprognose.clockodo`; wie die
Zahlen dargestellt werden, ausschliesslich in :mod:`umsatzprognose.darstellung`. Die
Trennung ist die Voraussetzung dafuer, dass die Fachlogik ohne Netz und ohne pandas
pruefbar bleibt - und dass Clockodos Eigenarten nicht in die Fachbegriffe sickern.
"""

from umsatzprognose.domaene.abrufquote import Abrufquote, Abrufquotenverteilung
from umsatzprognose.domaene.bestand import Bestand
from umsatzprognose.domaene.hinweis import Hinweis
from umsatzprognose.domaene.kunde import Kunde
from umsatzprognose.domaene.mitarbeiter import Mitarbeiter, Wochenarbeitszeit
from umsatzprognose.domaene.prognose import KONFIDENZNIVEAUS, NochKeinePrognose, Prognose
from umsatzprognose.domaene.projekt import OHNE_BUDGET, Budget, Projekt
from umsatzprognose.domaene.projektanteil import Projektanteil
from umsatzprognose.domaene.umsatzhistorie import Monatsumsatz, Umsatzhistorie
from umsatzprognose.domaene.verbrauchsverlauf import Verbrauchsverlauf

__all__ = [
    "KONFIDENZNIVEAUS",
    "OHNE_BUDGET",
    "Abrufquote",
    "Abrufquotenverteilung",
    "Bestand",
    "Budget",
    "Hinweis",
    "Kunde",
    "Mitarbeiter",
    "Monatsumsatz",
    "NochKeinePrognose",
    "Prognose",
    "Projekt",
    "Projektanteil",
    "Umsatzhistorie",
    "Verbrauchsverlauf",
    "Wochenarbeitszeit",
]
