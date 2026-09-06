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
statt die Anfrage bis zum fertigen Ergebnis zu blockieren.

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
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Hashable

from umsatzprognose import Dashboard
from umsatzprognose.domaene import Anmeldungsverlauf
from umsatzprognose.schulungen import SchulungenRepository

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

    def anstossen(self, schluessel: K, laden: Callable[[], Awaitable[V]]) -> None:
        """Startet das Laden im Hintergrund, falls noetig - ohne darauf zu warten.

        Ohne Wirkung, wenn ``schluessel`` bereits frisch ist oder gerade laedt - ruft
        z. B. jede Anfrage auf eine noch ladende Seite erneut auf, entsteht daraus
        trotzdem nur ein einziger Ladevorgang.
        """
        if self._frisch(schluessel) is not None or schluessel in self._laeuft:
            return

        async def _hintergrund() -> None:
            try:
                wert = await laden()
            except Exception as fehler:
                print(f"Laden fehlgeschlagen ({schluessel}): {fehler}")
            else:
                self._eintraege[schluessel] = (wert, time.monotonic())
            finally:
                del self._laeuft[schluessel]

        self._laeuft[schluessel] = asyncio.create_task(_hintergrund())


class DashboardCache:
    """Haelt je angefragter (``horizont_monate``, ``auslastung_monate``)-Kombination
    ein geladenes ``Dashboard`` vor."""

    def __init__(self, *, ttl_sekunden: int | None = None) -> None:
        self._cache = _TTLCache[tuple[int, int], Dashboard](ttl_sekunden=ttl_sekunden)

    def bereit(self, *, horizont_monate: int, auslastung_monate: int) -> Dashboard | None:
        return self._cache.bereit((horizont_monate, auslastung_monate))

    def anstossen(self, *, horizont_monate: int, auslastung_monate: int) -> None:
        async def laden() -> Dashboard:
            dashboard = await Dashboard.laden_async(
                stichtag=date.today(),
                horizont_monate=horizont_monate,
                auslastung_monate=auslastung_monate,
            )
            dashboard.simuliere(monate=horizont_monate)
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

    def anstossen(self) -> None:
        async def laden() -> Anmeldungsverlauf:
            jahre = range(self._ab_jahr, date.today().year + 1)
            return SchulungenRepository.mit_automatischen_zugangsdaten().anmeldungsverlauf_laden(
                jahre
            )

        self._cache.anstossen(None, laden)
