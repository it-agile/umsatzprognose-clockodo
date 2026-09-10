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
from umsatzprognose.domaene import (
    Anmeldungsverlauf,
    Kurzarbeitsbewertung,
    Personenmonat,
    Rollenzuordnung,
    Schwellenwerte,
    bewertungen,
)
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


# Dieselben fuenf fertigen Statuszeilen wie in scripts/wochenbericht.py/
# scripts/diagramme_exportieren.py/notebooks/setup.py (dort ``_ABSCHLUSS_MUSTER``) -
# nur sie werden an die Ladeseite durchgereicht, nicht die Zwischenschritte dazwischen
# (Bestands fuenf gleichzeitige Zweige, Kostenplans Jahr-fuer-Jahr-Meldungen,
# Verlaufscache-Meldungen). CLI/Notebooks fangen diese Zwischenschritte ueber einen
# live aktualisierten Balken ab, der am Ende durch die fertige Statuszeile ersetzt
# wird; die Weboberflaeche kennt keinen solchen Balken (kein dauerhaft offener Kanal
# zum Browser, siehe Moduldocstring) und wuerde ohne diesen Filter jeden
# Zwischenschritt als eigene, dauerhaft stehenbleibende Zeile zeigen - ausfuehrlicher
# als die bewusst zusammengefasste Anzeige dort, und damit inkonsistent zu ihr.
_ABSCHLUSS_MUSTER = (
    "Bestand geladen",
    "Schulung(en) geladen",
    "Kostenprognose geladen",
    "Auslastungsmonat(e) geladen",
    "Simulation abgeschlossen",
)


def _nur_abschluesse(fortschritt: Fortschritt) -> Fortschritt:
    """Filtert einen ``fortschritt``-Callback auf die finalen Statuszeilen aus
    :data:`_ABSCHLUSS_MUSTER` - fuer denselben Informationsstand wie die
    Fortschrittsbalken in CLI-Scripts und Notebooks, siehe dort."""

    def _gefiltert(text: str) -> None:
        if any(muster in text for muster in _ABSCHLUSS_MUSTER):
            fortschritt(text)

    return _gefiltert


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
        self._letzter_fehler: dict[K, str] = {}

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

    def fehler(self, schluessel: K) -> str | None:
        """Die Fehlermeldung des zuletzt gescheiterten Ladeversuchs zu ``schluessel``,
        ``None`` ohne einen solchen - fuer die Ladeseite (siehe ``webapp.app``), sonst
        blieb ein wiederholt scheiternder Ladevorgang bislang von aussen ununterscheidbar
        von einem echten, nur noch laufenden: beides zeigte "Daten werden geladen" ohne
        jeden Hinweis, die eigentliche Meldung landete nur auf der Server-Konsole.

        Wird geloescht, sobald ein Ladevorgang zu demselben Schluessel erfolgreich
        durchlaeuft - eine alte Fehlermeldung soll nicht neben einem frischen Ergebnis
        stehen bleiben.
        """
        return self._letzter_fehler.get(schluessel)

    def anstossen(self, schluessel: K, laden: Callable[[Fortschritt], Awaitable[V]]) -> None:
        """Startet das Laden im Hintergrund, falls noetig - ohne darauf zu warten.

        Ohne Wirkung, wenn ``schluessel`` bereits frisch ist oder gerade laedt - ruft
        z. B. jede Anfrage auf eine noch ladende Seite erneut auf, entsteht daraus
        trotzdem nur ein einziger Ladevorgang. ``laden`` bekommt einen
        ``fortschritt``-Callback uebergeben (dieselbe Form wie bei
        ``Dashboard.laden_async``) und ruft ihn nach Belieben auf - jeder Aufruf landet
        sofort in :meth:`fortschritt`. Ein vorheriger, gescheiterter Versuch zu
        demselben Schluessel haelt ``anstossen`` nicht ab - jeder Aufruf (also auch
        jeder erneute Seitenaufruf) loest einen neuen Versuch aus, siehe :meth:`fehler`.
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
                self._letzter_fehler[schluessel] = str(fehler) or type(fehler).__name__
            else:
                self._eintraege[schluessel] = (wert, time.monotonic())
                self._letzter_fehler.pop(schluessel, None)
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

    def fehler(self, *, horizont_monate: int, auslastung_monate: int) -> str | None:
        return self._cache.fehler((horizont_monate, auslastung_monate))

    def anstossen(self, *, horizont_monate: int, auslastung_monate: int) -> None:
        async def laden(fortschritt: Fortschritt) -> Dashboard:
            melden = _nur_abschluesse(fortschritt)
            dashboard = await Dashboard.laden_async(
                stichtag=date.today(),
                horizont_monate=horizont_monate,
                auslastung_monate=auslastung_monate,
                fortschritt=melden,
            )
            # simuliere_async() statt simuliere(): ein direkter, blockierender Aufruf
            # wuerde den einzigen Event-Loop-Thread des Servers fuer die Dauer der
            # Monte-Carlo-Rechnung einfrieren - saemtliche anderen gleichzeitigen
            # Anfragen (auch die der anderen beiden Caches, siehe _vorladen() in
            # webapp/app.py) muessten darauf warten, statt wirklich gleichzeitig zu
            # laufen.
            await dashboard.simuliere_async(monate=horizont_monate, fortschritt=melden)
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

    def fehler(self) -> str | None:
        return self._cache.fehler(None)

    def anstossen(self) -> None:
        async def laden(fortschritt: Fortschritt) -> Anmeldungsverlauf:
            jahre = range(self._ab_jahr, date.today().year + 1)
            # anmeldungsverlauf_laden() ist ein einzelner synchroner Aufruf (siehe
            # Moduldocstring von umsatzprognose.schulungen.schulungen) - kein eigener
            # fortschritt-Parameter noetig, ein Vorher/Nachher-Bericht wie bei der
            # Simulation genuegt (siehe Dashboard.simuliere). asyncio.to_thread() statt
            # eines direkten Aufrufs: ein Server bedient mehrere Anfragen aus demselben
            # Event-Loop-Thread - ein direkter, blockierender Google-Sheets-Aufruf
            # wuerde diesen einen Thread fuer die Dauer des Abrufs einfrieren und damit
            # auch die anderen beiden, gleichzeitig angestossenen Caches ausbremsen.
            start = time.perf_counter()
            verlauf = await asyncio.to_thread(
                SchulungenRepository.mit_automatischen_zugangsdaten().anmeldungsverlauf_laden,
                jahre,
            )
            dauer = timedelta(seconds=time.perf_counter() - start)
            fortschritt(
                f"{len(verlauf.anmeldungen)} Anmeldungen aus {len(verlauf.monate)} Monaten "
                f"geladen (in {humanize.naturaldelta(dauer)})"
            )
            return verlauf

        self._cache.anstossen(None, laden)


class KurzarbeitCache:
    """Haelt die geladenen Personenmonat-Rohdaten (und die aufgeloeste
    Rollenzuordnung) vor, ueber die maximal waehlbare Anzahl Monate
    (``maximale_monate``) - **nicht** schon die bewertete Kurzarbeitsbereitschaft.

    Muster wie :class:`AnmeldungsverlaufCache`, nicht wie :class:`DashboardCache`,
    fuer die Monatsauswahl: anders als beim vorwaerts simulierenden Dashboard haengt
    die Bewertung eines einzelnen Monats (siehe
    :mod:`umsatzprognose.domaene.kurzarbeit`) ausschliesslich von dessen eigenen
    Personenmonat-Daten ab, nicht davon, wie viele Monate insgesamt angefragt wurden -
    ein engerer Zeitraum ("3 Monate" statt "12 Monate") ist deshalb immer eine
    Teilmenge des einen, breitesten geladenen Laufs.

    Die Bewertung selbst (:func:`~umsatzprognose.domaene.kurzarbeit.bewertungen`) ist
    reine Berechnung ohne I/O - :meth:`bereit` ruft sie deshalb bei **jeder** Anfrage
    frisch mit den vom Aufruf uebergebenen ``schwellenwerte`` auf, genau wie
    ``gewinn_verlust_monate`` bei :class:`DashboardCache` nur einen anderen
    Ausschnitt derselben geladenen Historie liest. Weder ein Wechsel der
    ``anzahl_monate`` noch ein Wechsel der ``schwellenwerte`` (z. B. ueber einen
    Regler in der Weboberflaeche) loest deshalb einen neuen Ladevorgang bei Clockodo
    aus. Vollstaendig unabhaengig von :class:`DashboardCache` - kein Bezug zur
    Umsatzprognose.
    """

    def __init__(self, *, maximale_monate: int, ttl_sekunden: int | None = None) -> None:
        self._maximale_monate = maximale_monate
        self._cache = _TTLCache[
            None, tuple[dict[Monat, tuple[Personenmonat, ...]], Rollenzuordnung]
        ](ttl_sekunden=ttl_sekunden)

    def bereit(
        self, *, anzahl_monate: int, schwellenwerte: Schwellenwerte
    ) -> dict[Monat, Kurzarbeitsbewertung] | None:
        eintrag = self._cache.bereit(None)
        if eintrag is None:
            return None
        rohdaten, rollenzuordnung = eintrag
        eingeschraenkt = _juengste_monate(rohdaten, anzahl_monate)
        return bewertungen(
            eingeschraenkt, rollenzuordnung=rollenzuordnung, schwellenwerte=schwellenwerte
        )

    def fortschritt(self) -> list[str]:
        return self._cache.fortschritt(None)

    def fehler(self) -> str | None:
        return self._cache.fehler(None)

    def anstossen(self) -> None:
        async def laden(
            fortschritt: Fortschritt,
        ) -> tuple[dict[Monat, tuple[Personenmonat, ...]], Rollenzuordnung]:
            # Ohne fortschritt= an laden_async(): dessen fuenf gleichzeitige Zweige
            # und die Jahres-Abrufe sind reine Zwischenschritte (siehe
            # KurzarbeitRepository.laden_async), die CLI/Notebooks ueber einen live
            # aktualisierten Balken abfangen statt sie stehen zu lassen - hier reicht
            # die eine synthetisierte Statuszeile danach, wortgleich zu dort.
            start = time.perf_counter()
            rohdaten = await KurzarbeitRepository.mit_automatischen_zugangsdaten().laden_async(
                stichtag=date.today(), anzahl_monate=self._maximale_monate
            )
            rollenzuordnung = rollenzuordnung_automatisch()
            dauer = timedelta(seconds=time.perf_counter() - start)
            anzahl_personen = len({p.mitarbeiter_id for pm in rohdaten.values() for p in pm})
            fortschritt(
                f"Kurzarbeits-Rohdaten aus {len(rohdaten)} Monate(n) von {anzahl_personen} "
                f"Person(en) geladen (in {humanize.naturaldelta(dauer)})"
            )
            return rohdaten, rollenzuordnung

        self._cache.anstossen(None, laden)


def _juengste_monate[V](daten: dict[Monat, V], anzahl_monate: int) -> dict[Monat, V]:
    """Die juengsten ``anzahl_monate`` Eintraege aus einem breiter geladenen Ergebnis."""
    monate = sorted(daten)[-anzahl_monate:]
    return {monat: daten[monat] for monat in monate}
