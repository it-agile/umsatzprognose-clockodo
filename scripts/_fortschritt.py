"""Gemeinsame Ladeanzeige fuer die CLI-Scripts (``scripts/wochenbericht.py``,
``scripts/diagramme_exportieren.py``) - je eine Zeile pro Datenquelle/Datei, die
waehrend eines Lade- oder Export-Vorgangs sichtbaren Fortschritt zeigt und am Ende
in-place durch die fertige Statuszeile ersetzt wird.

Frueher war dieser Code in beiden Scripts dupliziert (siehe Git-Historie) - das lief
wiederholt auseinander (z. B. eine fehlende Ladedauer oder ein abweichender Wortlaut
bei derselben Meldung in nur einem der beiden Scripts), weil eine Aenderung leicht in
nur einer der beiden Kopien landete. Beide Scripts liegen im selben Verzeichnis und
werden immer gemeinsam ausgeliefert (anders als ``notebooks/setup.py`` - das bleibt
bewusst eine einzelne, eigenstaendige Datei, weil Colab sie einzeln per ``curl``
nachlaedt, ohne den Rest des Repositories - ein Import von hier waere dort nicht
verfuegbar).

Kein Teil des installierten Pakets, wie die beiden Scripts selbst.
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from umsatzprognose.clockodo import Fortschritt


class Mehrzeilenanzeige:
    """Eine feste Anzahl Zeilen (eine je Datenquelle oder Datei), die bei jeder
    Aenderung gemeinsam neu gezeichnet werden - je eine eigene Zeile zeigt, was gerade
    laedt/exportiert wird und wie weit es ist, am Ende ersetzt durch die fertige
    Statuszeile.

    Ersetzt mehrere unabhaengige, ueber tqdms ``position=``-Parameter positionierte
    Balken (siehe Git-Historie): tqdms Positionsverwaltung geht beim Schliessen eines
    Balkens (``close()``) davon aus, dass Balken in absteigender Positionsreihenfolge
    fertig werden (wie bei verschachtelten Balken, z. B. eine aeussere und mehrere
    innere Schleifen) - sie verschiebt beim Schliessen automatisch die Positionen
    aller noch offenen Balken mit hoeherer Positionsnummer. Bei unabhaengigen,
    gleichzeitig laufenden Quellen wie hier (z. B. Bestand und Anmeldungsverlauf, die
    in beliebiger Reihenfolge und mit mehreren Zwischenschritten fertig werden) fuehrt
    das dazu, dass noch aktive Zeilen mitten im Update ploetzlich an einer anderen
    Bildschirmzeile landen - beobachtet als doppelt gedruckte oder
    durcheinandergewuerfelte Statuszeilen und ein am Ende sichtbar kaputtes Terminal.
    Diese Klasse zeichnet stattdessen bei jeder Aenderung alle Zeilen gemeinsam neu, in
    einer festen Reihenfolge, ohne jede Annahme ueber die Fertigstellungsreihenfolge -
    und ohne tqdm ueberhaupt zu benutzen.

    Threadsicher durch eine einzelne Sperre statt eines Zurueckreichens an einen
    bestimmten Thread: mehrere ``fortschritt()``-Quellen laufen nebeneinander, deren
    Berichte teils im Event-Loop-Thread ankommen (reine Coroutinen), teils in einem
    eigenen ``asyncio.to_thread``-Worker - die Sperre serialisiert die tatsaechlichen
    Zeichenvorgaenge unabhaengig davon, aus welchem Thread sie kommen.
    """

    def __init__(self, namen: Sequence[str], *, vorlage: str = "{name} laden ...") -> None:
        self._namen = list(namen)
        self._zeilen = {name: vorlage.format(name=name) for name in self._namen}
        self._sperre = threading.Lock()
        self._schon_gezeichnet = False

    def _neu_zeichnen(self) -> None:
        teile = [f"\033[{len(self._namen)}A"] if self._schon_gezeichnet else []
        teile.extend(f"\033[2K{self._zeilen[name]}\n" for name in self._namen)
        sys.stderr.write("".join(teile))
        sys.stderr.flush()
        self._schon_gezeichnet = True

    def aktualisieren(self, name: str, text: str) -> None:
        """Ersetzt die Zeile zu ``name`` durch ``text`` - fuer Zwischenstaende
        (weiterer Aufruf folgt) genauso wie fuer die fertige Statuszeile (letzter
        Aufruf zu diesem ``name``)."""
        with self._sperre:
            self._zeilen[name] = text
            self._neu_zeichnen()


# Ein je Schritt eindeutiger Textbaustein aus dessen fertiger Statuszeile (siehe
# Dashboard.laden_async), der Name entspricht der Zeile in Mehrzeilenanzeige.
ABSCHLUSS_MUSTER = {
    "Bestand": "Bestand geladen",
    "Schulungsplan": "Schulung(en) geladen",
    "Kostenplan": "Kostenprognose geladen",
    "Auslastung": "Auslastungsmonat(e) geladen",
    "Simulation": "Simulation abgeschlossen",
}
# Bestand meldet sich zusaetzlich zwischendurch, je einem seiner fuenf gleichzeitigen
# Zweige (siehe BestandRepository.laden_async) - diese Texte sind fest und bekannt,
# anders als bei Kostenplan (dort variiert die Jahreszahl).
BESTAND_ZWISCHENSCHRITTE = (
    "Kunden geladen",
    "Personen geladen",
    "Projekt-Rohdaten geladen",
    "Umsatzhistorie geladen",
    "Verbrauchsverlauf geladen",
)
# Kostenplan meldet sich ebenfalls zwischendurch, je verarbeitetem Jahr (siehe
# KostenRepository.laden) - die Jahresanzahl ist vorher nicht bekannt, deshalb ein
# Spinner statt eines Anteils von einem Gesamtwert (siehe :func:`spinner`).
KOSTENPLAN_ZWISCHENSCHRITT_MUSTER = "Kostenposten bis"

_BALKEN_BREITE = 24
_SPINNER_ZEICHEN = "|/-\\"


def fortschrittsbalken(erledigt: int, gesamt: int) -> str:
    """Ein schlichter Text-Fortschrittsbalken, z. B. ``[████████░░░░░░░░]`` - kein
    tqdm (siehe Klassendocstring von :class:`Mehrzeilenanzeige`), nur zur sichtbaren
    Untermalung des Zwischenstands, den :class:`Mehrzeilenanzeige` ohnehin schon als
    Text (``n/gesamt``) traegt."""
    anteil = min(1.0, erledigt / gesamt) if gesamt else 0.0
    gefuellt = round(_BALKEN_BREITE * anteil)
    return "[" + "█" * gefuellt + "░" * (_BALKEN_BREITE - gefuellt) + "]"


def spinner(index: int) -> str:
    """Ein rotierendes Zeichen fuer Zwischenschritte ohne bekanntes Gesamt (siehe
    :data:`KOSTENPLAN_ZWISCHENSCHRITT_MUSTER`) - zeigt "es tut sich was", wo ein
    Anteil mangels bekanntem Gesamtwert nicht sinnvoll waere."""
    return _SPINNER_ZEICHEN[index % len(_SPINNER_ZEICHEN)]


def relativer_pfad(pfad: Path) -> Path:
    """Der Pfad relativ zum aufrufenden Arbeitsverzeichnis - eine Exportzeile zeigt den
    Dateinamen so, statt absolut, auch wenn das Zielverzeichnis absolut angegeben
    wurde (oder, wie beim Wochenbericht, ausserhalb des Arbeitsverzeichnisses in einem
    ``tempfile.TemporaryDirectory()`` liegt)."""
    return Path(os.path.relpath(pfad, Path.cwd()))


def dashboard_melden_bauen(anzeige: Mehrzeilenanzeige) -> Fortschritt:
    """Baut den ``fortschritt()``-Callback fuers Dashboard-Laden/-Simulieren: eine
    Zeile je Schritt (Bestand, Schulungsplan, Kostenplan, Auslastung, Simulation),
    mit sichtbarem Zwischenstand fuer Bestand (fuenf Zweige, als Balken) und
    Kostenplan (verarbeitete Jahre, als Spinner), bis sie durch die fertige
    Statuszeile ersetzt wird."""
    bestand_erledigt = 0
    kostenplan_jahre = 0

    def _melden(text: str) -> None:
        nonlocal bestand_erledigt, kostenplan_jahre
        for name, muster in ABSCHLUSS_MUSTER.items():
            if muster in text:
                anzeige.aktualisieren(name, text)
                return
        if text in BESTAND_ZWISCHENSCHRITTE:
            bestand_erledigt += 1
            gesamt = len(BESTAND_ZWISCHENSCHRITTE)
            anzeige.aktualisieren(
                "Bestand",
                f"Bestand laden {fortschrittsbalken(bestand_erledigt, gesamt)} "
                f"{bestand_erledigt}/{gesamt}",
            )
            return
        if KOSTENPLAN_ZWISCHENSCHRITT_MUSTER in text:
            kostenplan_jahre += 1
            anzeige.aktualisieren(
                "Kostenplan",
                f"Kostenplan laden {spinner(kostenplan_jahre)} ({kostenplan_jahre} Jahr(e))",
            )
            return
        # Verlaufscache-Meldungen o.Ae. passen auf keines der bekannten Muster - ohne
        # eigene Zeile bewusst verworfen (der Verlaufscache ist per
        # CLOCKODO_CACHE_TTL_SEKUNDEN ohnehin striktes Opt-in, siehe CLAUDE.md).

    return _melden
