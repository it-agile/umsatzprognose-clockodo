"""Die Abbildungsschicht fuer die Schulungs-Sheets: alles, was von ihnen weiss.

Zweite, zu :mod:`umsatzprognose.clockodo` gleichrangige Quellschicht - beide bilden
externe Daten auf die Fachobjekte in :mod:`umsatzprognose.domaene` ab, ohne dass die
Domaene etwas von Google Sheets oder Clockodo wuesste, und ohne dass diese Schicht
Wissen ueber die jeweils andere Quelle braucht. Der eigentliche Google-Sheets-Zugriff
(Zugangsdaten, HTTP-Client) liegt in :mod:`umsatzprognose.google_sheets` - gemeinsam
mit :mod:`umsatzprognose.kosten` genutzt, die dieselben jaehrlichen Dateien lesen, aber
ein anderes Tabellenblatt.
"""

from umsatzprognose.schulungen.schulungen import SchulungenRepository

__all__ = [
    "SchulungenRepository",
]
