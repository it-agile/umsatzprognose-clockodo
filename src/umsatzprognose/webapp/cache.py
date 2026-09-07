"""Prozessweiter Zwischenspeicher fuer die beiden teuren Ladevorgaenge des Webapps.

**Warum ueberhaupt ein eigener Cache, obwohl es schon ``clockodo/cache.py`` gibt.**
Jener Cache betrifft nur die rohe Clockodo-Vollhistorie; hier geht es um die
*fertigen* Objekte - ein ``Dashboard`` samt Monte-Carlo-Simulation, bzw. einen
``Anmeldungsverlauf``. ``notebooks/setup.py`` haelt sie in Modulvariablen je Kernel -
ein Webserver bedient dagegen mehrere gleichzeitige Anfragen aus demselben Prozess,
ohne Kernel-Grenze dazwischen. Ein Neuladen je Anfrage waere sowohl wegen des Abrufs
als auch wegen der Simulation selbst zu langsam; stattdessen sehen alle Besucher
denselben, periodisch aktualisierten Stand - es gibt ohnehin keine Benutzertrennung
(siehe Moduldocstring von :mod:`umsatzprognose.webapp`).

**Nicht blockierend**: ``bereit()`` liefert sofort den aktuellen Wert oder ``None``,
``anstossen()`` startet einen fehlenden Ladevorgang im Hintergrund (mehrfache Aufrufe
fuer denselben Schluessel loesen keinen zweiten Ladevorgang aus). :mod:`.app` zeigt
waehrend eines laufenden Hintergrund-Ladevorgangs eine "Daten werden geladen"-Seite,
statt die Anfrage bis zum fertigen Ergebnis zu blockieren. ``fortschritt()`` liefert
dabei die bisher gemeldeten Statuszeilen desselben ``fortschritt``-Callbacks wie in
den Notebooks (siehe ``notebooks/setup.py``) - die Ladeseite zeigt sie an und holt
sie sich per Meta-Refresh alle paar Sekunden erneut, es gibt (anders als dort) keinen
dauerhaft offenen Kanal zum Browser, ueber den sie live nachgeschoben werden koennten.

**Ein Eintrag je Parameterkombination - aber nur, wenn ein engerer Wert wirklich
weniger laedt.** :class:`DashboardCache` haelt je angefragter
(``horizont_monate``, ``auslastung_monate``)-Kombination einen eigenen Eintrag vor:
ein anderer ``horizont_monate`` fragt bei Clockodo tatsaechlich ein anderes
Zeitfenster ab, ein neuer Simulationslauf ist dort auch fachlich sinnvoll, wenn der
Betrachtungszeitraum sich aendert - ein Zwischenspeichern des breiteren Laufs fuer
einen engeren Aufruf waere keine Abkuerzung, sondern eine andere (veraltete)
Simulation. :class:`AnmeldungsverlaufCache` dagegen haelt bewusst **nur einen
einzigen** Eintrag: die Google-Sheets-Dateien sind unabhaengig vom gewaehlten
``ab_jahr`` dieselben, ein engerer Beginn ist immer eine Teilmenge eines schon
geladenen weiteren Bereichs (siehe Klassendocstring) - ihn dafuer neu zu laden waere
reine Verschwendung.
"""

from __future__ import annotations

import asyncio
import os
import time
from datetime import date, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Hashable

    from umsatzprognose.util import Fortschritt

import humanize

# Aktiviert nebenbei auch die deutsche humanize-Lokalisierung fuer diesen Prozess
# (Modul-Level-Aufruf in darstellung.dashboard, humanize.i18n.activate() wirkt nur
# thread-lokal) - hier reicht das, weil ein einzelner uvicorn-Prozess alles auf
# demselben Thread ausfuehrt, anders als der Jupyter-Thread-Umweg von synchron().
from umsatzprognose import Dashboard
from umsatzprognose.clockodo import KurzarbeitRepository, rollenzuordnung_automatisch
from umsatzprognose.domaene import Anmeldungsverlauf, Kurzarbeitsbewertung, bewertungen
from umsatzprognose.schulungen import SchulungenRepository
from umsatzprognose.util import Monat

TTL_ENV = "WEBAPP_CACHE_TTL_SEKUNDEN"
STANDARD_TTL_SEKUNDEN = 60 * 60


def standard_ttl_sekunden() -> int:
    """Die konfigurierte Cache-Dauer in Sekunden - ungesetzt oder ungueltig: der Standard."""
    wert = os.environ.get(TTL_ENV)
    if wert is None:
        return STANDARD_TTL_SEKUNDEN
    try:
        return int(wert)
    except ValueError:
        return STANDARD_TTL_SEKUNDEN


class _TTLCache[K: Hashable, V]:
    """Ein Wert je Schluessel, erneuert nach Ablauf der TTL - der Kern beider Caches.

    Absichtlich ohne blockierendes "warte, bis der Wert da ist": ein Webserver soll
    eine Anfrage waehrend eines laufenden Ladevorgangs nicht offenhalten, sondern
    sofort antworten koennen (siehe Moduldocstring).
    """

    def __init__(self, *, ttl_sekunden: int | None = None) -> None:
        self._ttl = standard_ttl_sekunden() if ttl_sekunden is None else ttl_sekunden
        self._eintraege: dict[K, tuple[V, float]] = {}
        self._laeuft: dict[K, asyncio.Task[None]] = {}
        self._fortschritt: dict[K, list[str]] = {}

    def _frisch(self, schluessel: K) -> V | None:
        eintrag = self._eintraege.get(schluessel)
        if eintrag is None or (time.monotonic() - eintrag[1]) >= self._ttl:
            return None
        return eintrag[0]

    def bereit(self, schluessel: K) -> V | None:
        """Der aktuelle Wert zu ``schluessel``, wenn er existiert und frisch ist.

        ``None`` sowohl wenn noch nie geladen als auch nach Ablauf der TTL - in
        beiden Faellen muss :meth:`anstossen` aufgerufen werden, um ihn zu bekommen.
        Loest selbst nie einen Ladevorgang aus.
        """
        return self._frisch(schluessel)

    def fortschritt(self, schluessel: K) -> list[str]:
        """Die bisher gemeldeten Statuszeilen eines laufenden Ladevorgangs zu
        ``schluessel`` - leer, wenn (noch) nichts gemeldet wurde oder gerade kein
        Ladevorgang laeuft (auch schon direkt nach dessen Abschluss: die naechste
        :meth:`bereit`-Abfrage liefert dann ohnehin den fertigen Wert, siehe
        :meth:`anstossen`).
        """
        return list(self._fortschritt.get(schluessel, ()))

    def anstossen(self, schluessel: K, laden: Callable[[Fortschritt], Awaitable[V]]) -> None:
        """Startet das Laden im Hintergrund, falls noetig - ohne darauf zu warten.

        Ohne Wirkung, wenn ``schluessel`` bereits frisch ist oder gerade laedt - ruft
        z. B. jede Anfrage auf eine noch ladende Seite erneut auf, entsteht daraus
        trotzdem nur ein einziger Ladevorgang. ``laden`` bekommt einen
        ``fortschritt``-Callback uebergeben (dieselbe Form wie bei
        ``Dashboard.laden_async``) und ruft ihn nach Belieben auf - jeder Aufruf landet
        sofort in :meth:`fortschritt`.
        """
        if self._frisch(schluessel) is not None or schluessel in self._laeuft:
            return

        zeilen: list[str] = []
        self._fortschritt[schluessel] = zeilen

        async def _hintergrund() -> None:
            try:
                wert = await laden(zeilen.append)
            except Exception as fehler:
                print(f"Laden fehlgeschlagen ({schluessel}): {fehler}")
            else:
                self._eintraege[schluessel] = (wert, time.monotonic())
            finally:
                del self._laeuft[schluessel]
                del self._fortschritt[schluessel]

        self._laeuft[schluessel] = asyncio.create_task(_hintergrund())


class DashboardCache:
    """Haelt je angefragter (``horizont_monate``, ``auslastung_monate``)-Kombination
    ein geladenes ``Dashboard`` vor."""

    def __init__(self, *, ttl_sekunden: int | None = None) -> None:
        self._cache = _TTLCache[tuple[int, int], Dashboard](ttl_sekunden=ttl_sekunden)

    def bereit(self, *, horizont_monate: int, auslastung_monate: int) -> Dashboard | None:
        return self._cache.bereit((horizont_monate, auslastung_monate))

    def fortschritt(self, *, horizont_monate: int, auslastung_monate: int) -> list[str]:
        return self._cache.fortschritt((horizont_monate, auslastung_monate))

    def anstossen(self, *, horizont_monate: int, auslastung_monate: int) -> None:
        async def laden(fortschritt: Fortschritt) -> Dashboard:
            dashboard = await Dashboard.laden_async(
                stichtag=date.today(),
                horizont_monate=horizont_monate,
                auslastung_monate=auslastung_monate,
                fortschritt=fortschritt,
            )
            dashboard.simuliere(monate=horizont_monate, fortschritt=fortschritt)
            return dashboard

        self._cache.anstossen((horizont_monate, auslastung_monate), laden)


class AnmeldungsverlaufCache:
    """Haelt genau einen geladenen ``Anmeldungsverlauf`` vor, seit ``ab_jahr``.

    Anders als :class:`DashboardCache` **kein** Eintrag je angefragtem Betrachtungs-
    beginn: ``ab_jahr`` steht hier im Konstruktor fest (die frueheste Auswahl, die die
    Weboberflaeche anbietet) statt je Anfrage zu variieren. Ein engerer Beginn - "seit
    2024" statt "seit 2022" - ist immer eine Teilmenge dieses einen geladenen
    Zeitraums; :meth:`~umsatzprognose.domaene.anmeldung.Anmeldungsverlauf.ab_jahr`
    filtert dafuer nur noch in-memory, ohne die Google-Sheets-Dateien der bereits
    geladenen Jahre erneut zu lesen.
    """

    def __init__(self, *, ab_jahr: int, ttl_sekunden: int | None = None) -> None:
        self._ab_jahr = ab_jahr
        self._cache = _TTLCache[None, Anmeldungsverlauf](ttl_sekunden=ttl_sekunden)

    def bereit(self) -> Anmeldungsverlauf | None:
        return self._cache.bereit(None)

    def fortschritt(self) -> list[str]:
        return self._cache.fortschritt(None)

    def anstossen(self) -> None:
        async def laden(fortschritt: Fortschritt) -> Anmeldungsverlauf:
            jahre = range(self._ab_jahr, date.today().year + 1)
            # anmeldungsverlauf_laden() ist ein einzelner synchroner Aufruf (siehe
            # Moduldocstring von umsatzprognose.schulungen.schulungen) - kein eigener
            # fortschritt-Parameter noetig, ein Vorher/Nachher-Bericht wie bei der
            # Simulation genuegt (siehe Dashboard.simuliere).
            start = time.perf_counter()
            verlauf = SchulungenRepository.mit_automatischen_zugangsdaten().anmeldungsverlauf_laden(
                jahre
            )
            dauer = timedelta(seconds=time.perf_counter() - start)
            fortschritt(
                f"{len(verlauf.anmeldungen)} Anmeldungen aus {len(verlauf.monate)} Monaten "
                f"geladen (in {humanize.naturaldelta(dauer)})."
            )
            return verlauf

        self._cache.anstossen(None, laden)


class KurzarbeitCache:
    """Haelt je angefragter ``anzahl_monate`` eine geladene und bewertete
    Kurzarbeitsbereitschaft vor.

    Muster wie :class:`DashboardCache`, nicht wie :class:`AnmeldungsverlaufCache`:
    ein anderer ``anzahl_monate`` fragt bei Clockodo tatsaechlich ein anderes
    Zeitfenster ab (siehe
    :meth:`~umsatzprognose.clockodo.kurzarbeit.KurzarbeitRepository.laden_async`),
    ein Zwischenspeichern des breiteren Laufs fuer einen engeren Aufruf waere hier
    also keine Abkuerzung. Vollstaendig unabhaengig von :class:`DashboardCache` -
    kein Bezug zur Umsatzprognose (siehe ``spec/spec-kurzarbeit.md`` Abschnitt 2/7).
    """

    def __init__(self, *, ttl_sekunden: int | None = None) -> None:
        self._cache = _TTLCache[int, dict[Monat, Kurzarbeitsbewertung]](ttl_sekunden=ttl_sekunden)

    def bereit(self, *, anzahl_monate: int) -> dict[Monat, Kurzarbeitsbewertung] | None:
        return self._cache.bereit(anzahl_monate)

    def fortschritt(self, *, anzahl_monate: int) -> list[str]:
        return self._cache.fortschritt(anzahl_monate)

    def anstossen(self, *, anzahl_monate: int) -> None:
        async def laden(fortschritt: Fortschritt) -> dict[Monat, Kurzarbeitsbewertung]:
            start = time.perf_counter()
            rohdaten = await KurzarbeitRepository.mit_automatischen_zugangsdaten().laden_async(
                stichtag=date.today(), anzahl_monate=anzahl_monate
            )
            rollenzuordnung = rollenzuordnung_automatisch()
            ergebnisse = bewertungen(rohdaten, rollenzuordnung=rollenzuordnung)
            dauer = timedelta(seconds=time.perf_counter() - start)
            fortschritt(f"{len(ergebnisse)} Monate bewertet (in {humanize.naturaldelta(dauer)}).")
            return ergebnisse

        self._cache.anstossen(anzahl_monate, laden)
