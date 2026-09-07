"""Gemeinsame Ladelogik der drei Notebooks, siehe deren erste Zelle.

Kein Teil des installierten Pakets: das Colab-`pip install` in den Notebooks muss
zuerst laufen, sonst waere `umsatzprognose` beim Import dieses Moduls noch nicht da.
"""

import time
from datetime import date, timedelta

import humanize
from tqdm.auto import tqdm

from umsatzprognose import Dashboard
from umsatzprognose.clockodo import KurzarbeitRepository
from umsatzprognose.domaene import Anmeldungsverlauf, Personenmonat
from umsatzprognose.schulungen import SchulungenRepository
from umsatzprognose.util import Monat

humanize.i18n.activate("de_DE")

_dashboard: Dashboard | None = None
_anmeldungsverlauf: Anmeldungsverlauf | None = None
_anmeldungsverlauf_dauer: timedelta | None = None
_kurzarbeit_rohdaten: dict[Monat, tuple[Personenmonat, ...]] | None = None
_kurzarbeit_rohdaten_dauer: timedelta | None = None

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

# Bestand meldet sich zusaetzlich zwischendurch, je einem seiner fuenf gleichzeitigen
# Zweige (siehe BestandRepository.laden_async) - diese Texte sind fest und bekannt,
# anders als bei Kostenplan (dort variiert die Jahreszahl). Ein Tick je Zweig auf dem
# eigenen Platzhalter-Balken (total=6: fuenf Zwischenschritte plus der Abschluss durch
# _balken_ersetzen) statt einer eigenen Zeile - sonst waere der Output wie in einem
# frueheren Anlauf mit einer eigenen Zeile je Zwischenschritt ueberladen.
_BESTAND_ZWISCHENSCHRITTE = frozenset(
    {
        "Kunden geladen",
        "Personen geladen",
        "Projekt-Rohdaten geladen",
        "Umsatzhistorie geladen",
        "Verbrauchsverlauf geladen",
    }
)
_SCHRITT_TOTAL = {"Bestand": len(_BESTAND_ZWISCHENSCHRITTE) + 1, "Kostenplan": 1}

# Kostenplan meldet sich ebenfalls zwischendurch, je verarbeitetem Jahr (siehe
# KostenRepository.laden) - anders als bei Bestand ist die Anzahl Jahre vorher nicht
# bekannt (haengt von der geladenen Historie ab), ein Balken mit echtem Prozentanteil
# waere hier nur geraten. Die Beschreibung zeigt den jeweils juengsten Zwischenstand
# stattdessen nur voruebergehend an, ohne eine eigene Zeile zu hinterlassen.
_KOSTENPLAN_ZWISCHENSCHRITT_MUSTER = "Kostenposten bis"


def _platzhalter_balken(desc: str, *, position: int, total: int = 1) -> tqdm:
    """Eine eigene Zeile fuer einen von mehreren gleichzeitig ausstehenden Schritten -
    Platzhalter, bis er fertig ist, siehe :func:`_balken_ersetzen`.

    Wie ``rustup update`` es fuer mehrere gleichzeitig synchronisierte Toolchains macht:
    alle ausstehenden Schritte stehen von Anfang an da, jeder in seiner eigenen Zeile;
    ihr Balken verschwindet zugunsten des fertigen Textes, sobald der jeweilige Schritt
    da ist - unabhaengig davon, ob die Schritte technisch nacheinander oder gleichzeitig
    ablaufen (siehe :func:`dashboard`). ``total`` > 1 nur fuer Bestand - sichtbarer
    Fortschritt durch dessen fuenf Zwischenschritte, siehe :data:`_SCHRITT_TOTAL`.
    """
    return tqdm(total=total, desc=desc, bar_format="{desc} {bar}", position=position, leave=True)


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
    genannten. Bestands Balken fuellt sich zusaetzlich sichtbar ueber dessen fuenf
    gleichzeitige Zweige (Kunden, Personen, Projekt-Rohdaten, Umsatzhistorie,
    Verbrauchsverlauf), Kostenplans Beschriftung zeigt waehrenddessen den juengsten
    Jahrgang - beides ohne eine eigene Zeile je Zwischenschritt zu hinterlassen (siehe
    :data:`_BESTAND_ZWISCHENSCHRITTE`/:data:`_KOSTENPLAN_ZWISCHENSCHRITT_MUSTER`). Ist
    der Verlaufscache aktiv (``CLOCKODO_CACHE_TTL_SEKUNDEN``), erscheint zusaetzlich je
    Cache-Zugriff eine eigene Zeile mit dessen eigener, meist sehr kurzer Ladezeit -
    ueber denselben ``fortschritt``-Callback wie die vier Schritte.

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
        name: _platzhalter_balken(f"{name} laden", position=i, total=_SCHRITT_TOTAL.get(name, 1))
        for i, name in enumerate(SCHRITTE_DASHBOARD_LADEN)
    }

    if _dashboard is None:

        def _melden(text: str) -> None:
            for name, muster in _SCHRITT_MUSTER.items():
                if name in offene_schritte and muster in text:
                    _balken_ersetzen(offene_schritte.pop(name), text)
                    return
            if "Bestand" in offene_schritte and text in _BESTAND_ZWISCHENSCHRITTE:
                offene_schritte["Bestand"].update(1)
                return
            if "Kostenplan" in offene_schritte and _KOSTENPLAN_ZWISCHENSCHRITT_MUSTER in text:
                offene_schritte["Kostenplan"].set_description_str(f"Kostenplan laden: {text}")
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
    aktuellen. Der Balken fuellt sich dabei sichtbar ueber echte Zwischenschritte, ein
    Jahr nach dem anderen (siehe Docstring von ``anmeldungsverlauf_laden``), statt nur
    am Ende fertig zu sein - ohne dafuer je Jahr eine eigene Zeile zu hinterlassen; am
    Ende steht nur die eine Statuszeile aus :func:`anmeldungsverlauf_bericht`. Beim
    zweiten Aufruf im selben Kernel wird nicht neu geladen, die
    Statuszeile (:func:`anmeldungsverlauf_bericht`) erscheint aber trotzdem - mit der
    tatsaechlich gemessenen (nur sehr kurzen) Dauer *dieses* Zugriffs, statt
    faelschlich die alte, teure Original-Ladedauer erneut zu zeigen.
    """
    global _anmeldungsverlauf, _anmeldungsverlauf_dauer
    start = time.perf_counter()
    jahre = list(range(ab_jahr, date.today().year + 1))
    with tqdm(total=len(jahre), desc="Anmeldungsverlauf laden", leave=False) as fortschrittsbalken:
        neu_geladen = _anmeldungsverlauf is None
        if neu_geladen:

            def _melden(text: str) -> None:
                fortschrittsbalken.update(1)

            _anmeldungsverlauf = (
                SchulungenRepository.mit_automatischen_zugangsdaten().anmeldungsverlauf_laden(
                    jahre, fortschritt=_melden
                )
            )
        else:
            fortschrittsbalken.update(len(jahre))
        zugriffsdauer = timedelta(seconds=time.perf_counter() - start)
        if neu_geladen:
            _anmeldungsverlauf_dauer = zugriffsdauer
            fortschrittsbalken.write(anmeldungsverlauf_bericht())
        else:
            fortschrittsbalken.write(anmeldungsverlauf_bericht(dauer=zugriffsdauer))
    return _anmeldungsverlauf


def kurzarbeit_rohdaten(
    *, stichtag: date | None = None, anzahl_monate: int = 6
) -> dict[Monat, tuple[Personenmonat, ...]]:
    """Laedt die Personenmonat-Rohdaten fuer den Baustein Kurzarbeitsbereitschaft beim
    ersten Aufruf je Kernel, danach nur noch zurueckgegeben.

    Komplett unabhaengig von :func:`dashboard` - eigener Baustein, kein Bezug zur
    Umsatzprognose (siehe ``spec/spec-kurzarbeit.md`` Abschnitt 2/7). Liefert bewusst
    nur die Rohdaten, nicht schon eine :class:`~umsatzprognose.domaene.
    kurzarbeit.Kurzarbeitsbewertung` - die Bewertung mit Rollenzuordnung und
    Schwellenwerten ist eine reine, sofortige Rechnung
    (:func:`~umsatzprognose.domaene.kurzarbeit.bewertungen`) und braucht deshalb keinen
    eigenen Ladevorgang; sie steht im Notebook selbst, damit Schwellenwerte dort ohne
    Neuabruf geaendert werden koennen.

    Der Balken fuellt sich dabei sichtbar ueber echte Zwischenschritte (fuenf
    gleichzeitige Zweige plus ein ``/userreports``-Abruf je Jahr, siehe Docstring von
    ``KurzarbeitRepository.laden_async``), ohne dafuer eine eigene Zeile zu
    hinterlassen. ``total=None`` statt einer festen Zahl, weil die Anzahl der
    Jahres-Abrufe vorher nicht bekannt ist (haengt von ``anzahl_monate`` ab).
    """
    global _kurzarbeit_rohdaten, _kurzarbeit_rohdaten_dauer
    start = time.perf_counter()
    with tqdm(total=None, desc="Kurzarbeit-Rohdaten laden", leave=False) as fortschrittsbalken:
        neu_geladen = _kurzarbeit_rohdaten is None
        if neu_geladen:

            def _melden(text: str) -> None:
                fortschrittsbalken.update(1)

            _kurzarbeit_rohdaten = KurzarbeitRepository.mit_automatischen_zugangsdaten().laden(
                stichtag=date.today() if stichtag is None else stichtag,
                anzahl_monate=anzahl_monate,
                fortschritt=_melden,
            )
        else:
            fortschrittsbalken.update(1)
        zugriffsdauer = timedelta(seconds=time.perf_counter() - start)
        if neu_geladen:
            _kurzarbeit_rohdaten_dauer = zugriffsdauer
            fortschrittsbalken.write(kurzarbeit_rohdaten_bericht())
        else:
            fortschrittsbalken.write(kurzarbeit_rohdaten_bericht(dauer=zugriffsdauer))
    return _kurzarbeit_rohdaten


def kurzarbeit_rohdaten_bericht(*, dauer: timedelta | None = None) -> str:
    """Kurzer Ladehinweis, analog zu :func:`anmeldungsverlauf_bericht`.

    Setzt voraus, dass :func:`kurzarbeit_rohdaten` bereits im selben Kernel gelaufen ist.
    """
    if _kurzarbeit_rohdaten is None or _kurzarbeit_rohdaten_dauer is None:
        raise ValueError("Die Kurzarbeit-Rohdaten wurden noch nicht geladen.")
    tatsaechliche_dauer = dauer if dauer is not None else _kurzarbeit_rohdaten_dauer
    anzahl_personen = len({p.mitarbeiter_id for pm in _kurzarbeit_rohdaten.values() for p in pm})
    return (
        f"{len(_kurzarbeit_rohdaten)} Monate, {anzahl_personen} Personen geladen"
        f" (in {humanize.naturaldelta(tatsaechliche_dauer)})."
    )


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
