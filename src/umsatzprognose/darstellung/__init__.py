"""Die Darstellungsschicht: Diagramme, Tabellen und das Dashboard.

Haengt von der Domaene ab, nie umgekehrt. Hier - und nur hier - stehen plotly
(:mod:`~umsatzprognose.darstellung.diagramme`) und pandas
(:mod:`~umsatzprognose.darstellung.tabellen`); die Fachobjekte bleiben dadurch ohne
Bibliotheksabhaengigkeit und ohne Netzzugriff pruefbar.
"""

from umsatzprognose.darstellung.dashboard import Dashboard

__all__ = ["Dashboard"]
