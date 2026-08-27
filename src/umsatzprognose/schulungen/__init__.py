"""Die Abbildungsschicht fuer die Schulungs-Sheets: alles, was von ihnen weiss.

Zweite, zu :mod:`umsatzprognose.clockodo` gleichrangige Quellschicht - beide bilden
externe Daten auf die Fachobjekte in :mod:`umsatzprognose.domaene` ab, ohne dass die
Domaene etwas von Google Sheets oder Clockodo wuesste, und ohne dass diese Schicht
Wissen ueber die jeweils andere Quelle braucht.
"""

from umsatzprognose.schulungen.client import SchulungenSheetsClient
from umsatzprognose.schulungen.config import MissingCredentialsError, SchulungenConfig, in_colab
from umsatzprognose.schulungen.schulungen import SchulungenRepository

__all__ = [
    "MissingCredentialsError",
    "SchulungenConfig",
    "SchulungenRepository",
    "SchulungenSheetsClient",
    "in_colab",
]
