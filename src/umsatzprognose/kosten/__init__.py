"""Die Abbildungsschicht fuer die Kostenprognose: alles, was vom Kosten-Tabellenblatt weiss.

Zu :mod:`umsatzprognose.schulungen` gleichrangige Quellschicht - beide lesen aus
derselben jaehrlichen Google-Sheets-Datei (unterschiedliche Tabellenblaetter), aber
haengen nicht voneinander ab. Der eigentliche Google-Sheets-Zugriff liegt gemeinsam in
:mod:`umsatzprognose.google_sheets`.
"""

from umsatzprognose.kosten.kosten import KostenRepository

__all__ = [
    "KostenRepository",
]
