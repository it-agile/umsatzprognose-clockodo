"""Gemeinsame Ladelogik der drei Notebooks, siehe deren erste Zelle.

Kein Teil des installierten Pakets: das Colab-`pip install` in den Notebooks muss
zuerst laufen, sonst waere `umsatzprognose` beim Import dieses Moduls noch nicht da.
"""

import time
from datetime import date, timedelta

import humanize
from tqdm.auto import tqdm

from umsatzprognose import Dashboard
from umsatzprognose.domaene import Anmeldungsverlauf
from umsatzprognose.schulungen import SchulungenRepository

humanize.i18n.activate("de_DE")

_dashboard: Dashboard | None = None
_anmeldungsverlauf: Anmeldungsverlauf | None = None
_anmeldungsverlauf_dauer: timedelta | None = None

SCHRITTE_DASHBOARD_LADEN = ("Bestand", "Schulungsplan", "Kostenplan", "Auslastung")
# Ein je Schritt eindeutiger Textbaustein aus dessen fertiger Statuszeile (siehe
# Dashboard.laden_async) - daran erkennt _melden, welchem der vier Platzhalter-Balken
# eine ankommende fortschritt()-Meldung zuzuordnen ist. Verlaufscache-Meldungen (siehe
# cache.gecacht_oder_neu) passen auf keinen dieser Bausteine und werden stattdessen
# einfach als zusaetzliche Zeile ausgegeben - das ist die Vereinheitlichung von
# fortschritt und dem frueheren eigenen cache_fortschritt in Dashboard.laden().
_SCHRITT_MUSTER = {
    "Bestand": "Bestand geladen",
    "Schulungsplan": "Schulung(en) geladen",
    "Kostenplan": "Kostenprognose geladen",
    "Auslastung": "Auslastungsmonat(e) geladen",
}


def _platzhalter_balken(desc: str, *, position: int) -> tqdm:
    """Eine eigene Zeile fuer einen von mehreren gleichzeitig ausstehenden Schritten -
    Platzhalter, bis er fertig ist, siehe :func:`_balken_ersetzen`.

    Wie ``rustup update`` es fuer mehrere gleichzeitig synchronisierte Toolchains macht:
    alle ausstehenden Schritte stehen von Anfang an da, jeder in seiner eigenen Zeile;
    ihr Balken verschwindet zugunsten des fertigen Textes, sobald der jeweilige Schritt
    da ist - unabhaengig davon, ob die Schritte technisch nacheinander oder gleichzeitig
    ablaufen (siehe :func:`dashboard`).
    """
    return tqdm(total=1, desc=desc, bar_format="{desc} {bar}", position=position, leave=True)


def _balken_ersetzen(balken: tqdm, text: str) -> None:
    """Den Platzhalter-Balken eines Schritts durch seinen fertigen Text ersetzen."""
    balken.bar_format = "{desc}"
    balken.set_description_str(text)
    balken.update(1)
    balken.close()


def dashboard(
    *,
    stichtag: date | None = None,
    horizont_monate: int = 3,
    auslastung_monate: int = 12,
) -> Dashboard:
    """Laedt das Dashboard beim ersten Aufruf je Kernel, danach nur noch zurueckgegeben.

    Zeigt sofort alle vier Schritte (Bestand, Schulungsplan, Kostenplan, Auslastung),
    jeden in einer eigenen Zeile mit Platzhalter-Balken - Bestand und Schulungsplan
    laufen gleichzeitig, Kostenplan und Auslastung danach ebenfalls gleichzeitig (siehe
    ``Dashboard.laden_async``). Jede Zeile wird durch ihre fertige Statuszeile (Umfang
    und Dauer) ersetzt, sobald der jeweilige Abruf tatsaechlich fertig ist - in der
    Reihenfolge, in der die vier tatsaechlich fertig werden, nicht in der oben
    genannten. Ist der Verlaufscache aktiv (``CLOCKODO_CACHE_TTL_SEKUNDEN``), erscheint
    zusaetzlich je Cache-Zugriff eine eigene Zeile mit dessen eigener, meist sehr
    kurzer Ladezeit - ueber denselben ``fortschritt``-Callback wie die vier Schritte,
    siehe :data:`_SCHRITT_MUSTER`.

    Beim zweiten Aufruf im selben Kernel wird nicht neu geladen, die vier Zeilen
    erscheinen aber trotzdem - mit derselben Anzahl Eintraege wie beim ersten Laden,
    aber mit der tatsaechlich gemessenen (nur sehr kurzen) Dauer *dieses* Zugriffs auf
    das schon geladene Dashboard, statt faelschlich die alte, teure Original-Ladedauer
    erneut zu zeigen (siehe ``dauer`` bei
    :meth:`~umsatzprognose.darstellung.dashboard.Dashboard.schritt_berichte`).
    """
    global _dashboard
    start = time.perf_counter()
    offene_schritte = {
        name: _platzhalter_balken(f"{name} laden", position=i)
        for i, name in enumerate(SCHRITTE_DASHBOARD_LADEN)
    }

    if _dashboard is None:

        def _melden(text: str) -> None:
            for name, muster in _SCHRITT_MUSTER.items():
                if name in offene_schritte and muster in text:
                    _balken_ersetzen(offene_schritte.pop(name), text)
                    return
            tqdm.write(text)

        _dashboard = Dashboard.laden(
            stichtag=date.today() if stichtag is None else stichtag,
            horizont_monate=horizont_monate,
            auslastung_monate=auslastung_monate,
            fortschritt=_melden,
        )
    else:
        zugriffsdauer = timedelta(seconds=time.perf_counter() - start)
        berichte = _dashboard.schritt_berichte(dauer=zugriffsdauer)
        for name, text in zip(SCHRITTE_DASHBOARD_LADEN, berichte, strict=True):
            _balken_ersetzen(offene_schritte[name], text)
    return _dashboard


def simulieren(dashboard: Dashboard, *, monate: int = 3, laeufe: int = 10_000) -> None:
    """Fuehrt die Monte-Carlo-Simulation aus (siehe ``Dashboard.simuliere``) und zeigt
    dabei einen Fortschrittsbalken.

    Anders als beim Laden ein einzelner Balken statt einer Mehrzeilen-Anzeige: die
    Simulation ist eine einzige vektorisierte Rechnung ohne sinnvolle Zwischenschritte
    (siehe Docstring von ``Dashboard.simuliere``) - ein Vorher/Nachher-Bericht genuegt.
    """
    with tqdm(total=1, desc="Simulation läuft", leave=False) as fortschrittsbalken:

        def _melden(text: str) -> None:
            fortschrittsbalken.write(text)
            fortschrittsbalken.update(1)

        dashboard.simuliere(monate=monate, laeufe=laeufe, fortschritt=_melden)


def anmeldungsverlauf(*, ab_jahr: int = 2022) -> Anmeldungsverlauf:
    """Laedt den Anmeldungsverlauf beim ersten Aufruf je Kernel, danach nur noch zurueckgegeben.

    Anders als :func:`dashboard` unabhaengig vom Baustein Bestand - liest ueber
    :meth:`~umsatzprognose.schulungen.schulungen.SchulungenRepository.anmeldungsverlauf_laden`
    direkt aus der Schulungsanmeldungen-Quelle, ab dem angegebenen Jahr bis zum
    aktuellen. Beim zweiten Aufruf im selben Kernel wird nicht neu geladen, die
    Statuszeile (:func:`anmeldungsverlauf_bericht`) erscheint aber trotzdem - mit der
    tatsaechlich gemessenen (nur sehr kurzen) Dauer *dieses* Zugriffs, statt
    faelschlich die alte, teure Original-Ladedauer erneut zu zeigen.
    """
    global _anmeldungsverlauf, _anmeldungsverlauf_dauer
    start = time.perf_counter()
    with tqdm(total=1, desc="Anmeldungsverlauf laden", leave=False) as fortschrittsbalken:
        neu_geladen = _anmeldungsverlauf is None
        if neu_geladen:
            jahre = range(ab_jahr, date.today().year + 1)
            _anmeldungsverlauf = (
                SchulungenRepository.mit_automatischen_zugangsdaten().anmeldungsverlauf_laden(jahre)
            )
        zugriffsdauer = timedelta(seconds=time.perf_counter() - start)
        if neu_geladen:
            _anmeldungsverlauf_dauer = zugriffsdauer
            fortschrittsbalken.write(anmeldungsverlauf_bericht())
        else:
            fortschrittsbalken.write(anmeldungsverlauf_bericht(dauer=zugriffsdauer))
        fortschrittsbalken.update(1)
    return _anmeldungsverlauf


def anmeldungsverlauf_bericht(*, dauer: timedelta | None = None) -> str:
    """Kurzer Ladehinweis wie ``Dashboard.ladebericht()`` - Umfang und Dauer des Abrufs.

    Setzt voraus, dass :func:`anmeldungsverlauf` bereits im selben Kernel gelaufen ist.
    ``dauer``, sofern angegeben, ersetzt die gespeicherte Original-Ladedauer - fuer den
    Wiederholungsfall in :func:`anmeldungsverlauf`, siehe dort.
    """
    if _anmeldungsverlauf is None or _anmeldungsverlauf_dauer is None:
        raise ValueError("Der Anmeldungsverlauf wurde noch nicht geladen.")
    tatsaechliche_dauer = dauer if dauer is not None else _anmeldungsverlauf_dauer
    return (
        f"{len(_anmeldungsverlauf.anmeldungen)} Anmeldungen aus "
        f"{len(_anmeldungsverlauf.monate)} Monaten geladen"
        f" (in {humanize.naturaldelta(tatsaechliche_dauer)})."
    )
