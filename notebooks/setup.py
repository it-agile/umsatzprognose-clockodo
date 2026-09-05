"""Gemeinsame Ladelogik der drei Notebooks, siehe deren erste Zelle.

Kein Teil des installierten Pakets: das Colab-`pip install` in den Notebooks muss
zuerst laufen, sonst waere `umsatzprognose` beim Import dieses Moduls noch nicht da.
"""

import time
from datetime import date, timedelta

import humanize

from umsatzprognose import Dashboard
from umsatzprognose.domaene import Anmeldungsverlauf
from umsatzprognose.schulungen import SchulungenRepository

humanize.i18n.activate("de_DE")

_dashboard: Dashboard | None = None
_anmeldungsverlauf: Anmeldungsverlauf | None = None
_anmeldungsverlauf_dauer: timedelta | None = None


def dashboard(
    *,
    stichtag: date | None = None,
    horizont_monate: int = 3,
    auslastung_monate: int = 12,
) -> Dashboard:
    """Laedt das Dashboard beim ersten Aufruf je Kernel, danach nur noch zurueckgegeben."""
    global _dashboard
    if _dashboard is None:
        _dashboard = Dashboard.laden(
            stichtag=date.today() if stichtag is None else stichtag,
            horizont_monate=horizont_monate,
            auslastung_monate=auslastung_monate,
        )
    return _dashboard


def anmeldungsverlauf(*, ab_jahr: int = 2022) -> Anmeldungsverlauf:
    """Laedt den Anmeldungsverlauf beim ersten Aufruf je Kernel, danach nur noch zurueckgegeben.

    Anders als :func:`dashboard` unabhaengig vom Baustein Bestand - liest ueber
    :meth:`~umsatzprognose.schulungen.schulungen.SchulungenRepository.anmeldungsverlauf_laden`
    direkt aus der Schulungsanmeldungen-Quelle, ab dem angegebenen Jahr bis zum
    aktuellen.
    """
    global _anmeldungsverlauf, _anmeldungsverlauf_dauer
    if _anmeldungsverlauf is None:
        jahre = range(ab_jahr, date.today().year + 1)
        start = time.perf_counter()
        _anmeldungsverlauf = (
            SchulungenRepository.mit_automatischen_zugangsdaten().anmeldungsverlauf_laden(jahre)
        )
        _anmeldungsverlauf_dauer = timedelta(seconds=time.perf_counter() - start)
    return _anmeldungsverlauf


def anmeldungsverlauf_bericht() -> str:
    """Kurzer Ladehinweis wie ``Dashboard.ladebericht()`` - Umfang und Dauer des Abrufs.

    Setzt voraus, dass :func:`anmeldungsverlauf` bereits im selben Kernel gelaufen ist.
    """
    if _anmeldungsverlauf is None or _anmeldungsverlauf_dauer is None:
        raise ValueError("Der Anmeldungsverlauf wurde noch nicht geladen.")
    return (
        f"{len(_anmeldungsverlauf.anmeldungen)} Anmeldungen aus "
        f"{len(_anmeldungsverlauf.monate)} Monaten geladen"
        f" (in {humanize.naturaldelta(_anmeldungsverlauf_dauer)})."
    )
