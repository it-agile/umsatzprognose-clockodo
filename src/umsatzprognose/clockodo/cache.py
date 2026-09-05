"""Optionaler lokaler Zwischenspeicher fuer die beiden Vollhistorien-Abrufe von
``/v2/entrygroups`` (Verbrauch je Projekt, siehe :mod:`.projekte` und
:mod:`.verbrauchsverlauf`).

**Warum ueberhaupt ein Cache.** Beide Abrufe fragen die komplette Historie seit
``HISTORIE_VON`` ab, weil ``revenue`` je Projekt der *kumulierte* Verbrauch seit
Projektbeginn ist (siehe Moduldocstring von :mod:`.projekte`) - das dauert bei
Clockodo mehrere Sekunden, weil dort ueber Jahre aggregiert wird. Nach Beobachtung
aendert sich der laengst abgeschlossene Teil dieser Historie nicht mehr (Abrechnungen
aelterer Monate werden nicht nachtraeglich korrigiert); nur die letzten paar Monate
sind noch in Bewegung. Deshalb spaltet :func:`~.client.ClockodoClient` die Abfrage an
einem Cutoff (:func:`cutoff_datum`) in zwei Teile: der aeltere, stabile Teil darf lokal
zwischengespeichert werden, der juengere Teil wird immer frisch geholt und beide werden
anschliessend wieder zusammengefuehrt (siehe ``entrygroups_zusammenfuehren`` in
:mod:`.client`) - das Ergebnis bleibt exakt, es wird nur aufgeteilt, nicht gekuerzt.

**Opt-in ueber Umgebungsvariable, keine Ueberraschung im Standardfall.** Ohne
:data:`TTL_ENV` bleibt der Cache aus - das bisherige Verhalten, unveraendert. Gesetzt,
aber ohne gueltige Zahl (z. B. nur als Ein-/Aus-Schalter gedacht), gilt
:data:`STANDARD_TTL_SEKUNDEN`. Der Cutoff selbst ist ueber :data:`CUTOFF_ENV` oder je
Aufruf ueber einen Parameter einstellbar (Rangfolge in :func:`cutoff_monate`).

**Abgelegt wird ausserhalb des Repositories**, im Nutzerverzeichnis - dieselbe
Begruendung wie beim gecachten Google-OAuth-Token
(``google_sheets.client._lokale_credentials``): gelesene Werte gehoeren in keine Datei
dieses Repositories.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

import hashlib
import json
import os
import time
from datetime import date
from pathlib import Path

from umsatzprognose.util import aus_ordnung, ordnung

TTL_ENV = "CLOCKODO_CACHE_TTL_SEKUNDEN"
CUTOFF_ENV = "CLOCKODO_CACHE_CUTOFF_MONATE"

STANDARD_TTL_SEKUNDEN = 20 * 60
STANDARD_CUTOFF_MONATE = 6

VERZEICHNIS = Path.home() / ".cache" / "umsatzprognose-clockodo"


def ttl_sekunden() -> int | None:
    """Der konfigurierte Cache-Zeitraum in Sekunden - ``None`` bedeutet: kein Cache.

    Eine ungesetzte Variable schaltet den Cache aus. Gesetzt, aber keine gueltige Zahl,
    gilt :data:`STANDARD_TTL_SEKUNDEN`.
    """
    wert = os.environ.get(TTL_ENV)
    if wert is None:
        return None
    try:
        return int(wert)
    except ValueError:
        return STANDARD_TTL_SEKUNDEN


def cutoff_monate(uebersteuerung: int | None = None) -> int:
    """Wie viele Monate vor dem Abfrageende noch als 'in Bewegung' gelten.

    Rangfolge: expliziter Parameter vor :data:`CUTOFF_ENV` vor
    :data:`STANDARD_CUTOFF_MONATE`.
    """
    if uebersteuerung is not None:
        return uebersteuerung
    wert = os.environ.get(CUTOFF_ENV)
    if wert is None:
        return STANDARD_CUTOFF_MONATE
    try:
        return int(wert)
    except ValueError:
        return STANDARD_CUTOFF_MONATE


def cutoff_datum(time_until: str, *, monate: int) -> str:
    """Der erste Tag des Monats, der ``monate`` Monate vor ``time_until`` liegt.

    Gleiche Form wie ``HISTORIE_VON`` (volle ISO-Zeit, siehe :mod:`.client`) - alles
    davor gilt als abgeschlossen und darf zwischengespeichert werden, alles ab hier als
    noch in Bewegung und wird immer frisch abgefragt.
    """
    bis = date.fromisoformat(time_until[:10])
    jahr, monat = aus_ordnung(ordnung(bis.year, bis.month) - monate)
    return f"{jahr:04d}-{monat:02d}-01T00:00:00Z"


def schluessel(grouping: Sequence[str], *, time_since: str, time_until: str) -> str:
    """Dateiname-tauglicher Schluessel fuer eine bestimmte Abfrage."""
    roh = "|".join((*grouping, time_since, time_until))
    return hashlib.sha256(roh.encode()).hexdigest()


async def gecacht_oder_neu[T](schluessel: str, *, ttl: int, lader: Callable[[], Awaitable[T]]) -> T:
    """Liefert den gecachten Wert, wenn er existiert und juenger als ``ttl`` Sekunden ist.

    Sonst wird ``lader`` aufgerufen und das (JSON-faehige) Ergebnis fuer folgende
    Aufrufe abgelegt.
    """
    datei = VERZEICHNIS / f"{schluessel}.json"
    if datei.exists() and (time.time() - datei.stat().st_mtime) < ttl:
        return json.loads(datei.read_text())

    ergebnis = await lader()
    VERZEICHNIS.mkdir(parents=True, exist_ok=True)
    datei.write_text(json.dumps(ergebnis))
    return ergebnis
