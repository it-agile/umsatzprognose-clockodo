"""``Fortschritt`` liegt in :mod:`umsatzprognose.util` (dependenzfrei), damit sowohl
``clockodo`` als auch ``domaene`` ihn nutzen koennen - ``domaene`` darf ``clockodo``
nicht importieren (siehe Moduldocstring von :mod:`umsatzprognose.domaene.simulation`).

Re-Export hier, damit bestehender Code (``from umsatzprognose.clockodo import
Fortschritt`` bzw. ``from .fortschritt import Fortschritt`` innerhalb dieses Pakets)
unveraendert weiter funktioniert.
"""

from __future__ import annotations

from umsatzprognose.util.fortschritt import Fortschritt

__all__ = ["Fortschritt"]
