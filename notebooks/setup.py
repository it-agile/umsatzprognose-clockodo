"""Gemeinsame Ladelogik der drei Notebooks, siehe deren erste Zelle.

Kein Teil des installierten Pakets: das Colab-`pip install` in den Notebooks muss
zuerst laufen, sonst waere `umsatzprognose` beim Import dieses Moduls noch nicht da.
"""

from datetime import date

from umsatzprognose import Dashboard

_dashboard: Dashboard | None = None


def dashboard(
    *,
    stichtag: date | None = None,
    abgeschlossene_monate: int = 12,
    horizont_monate: int = 3,
    auslastung_monate: int = 12,
) -> Dashboard:
    """Laedt das Dashboard beim ersten Aufruf je Kernel, danach nur noch zurueckgegeben."""
    global _dashboard
    if _dashboard is None:
        _dashboard = Dashboard.laden(
            stichtag=date.today() if stichtag is None else stichtag,
            abgeschlossene_monate=abgeschlossene_monate,
            horizont_monate=horizont_monate,
            auslastung_monate=auslastung_monate,
        )
    return _dashboard
