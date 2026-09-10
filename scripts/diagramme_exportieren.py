"""Diagramme über die Kommandozeile exportieren - für Aufrufer ohne Jupyter.

    uv run python scripts/diagramme_exportieren.py                            # alle, als PNG
    uv run python scripts/diagramme_exportieren.py --format html              # alle, als HTML
    uv run python scripts/diagramme_exportieren.py --diagramm umsatzverlauf --diagramm kennzahlen
    uv run python scripts/diagramme_exportieren.py -o export --horizont-monate 1
    uv run python scripts/diagramme_exportieren.py --diagramm anmeldungsverlauf --monate-fenster 6
    uv run python scripts/diagramme_exportieren.py --diagramm umsatztabelle

Lädt den Bestand wie die Notebooks (``Dashboard.laden()``) und schreibt dieselben
Diagramme, die dort gezeigt werden, als Dateien in ein Verzeichnis. PNG- und
SVG-Export laufen wie im Wochenbericht (``scripts/wochenbericht.py``) über
``kaleido`` (``[project.optional-dependencies.bericht]``); HTML kommt ohne
zusätzliche Abhängigkeit aus, ist dafür aber nur im Browser interaktiv statt als
eigenständige Bilddatei nutzbar.

**Tabellen genauso exportierbar wie Diagramme** (``TABELLEN_DASHBOARD``,
``anmeldungstabelle``): pandas-Tabellen kennen kein PNG/SVG - analog zur
Umsatztabelle im Wochenbericht macht :func:`~umsatzprognose.darstellung.diagramme.
tabelle_als_grafik` daraus dieselbe Art plotly-Figur wie ein Diagramm, exportierbar
über denselben Weg (``exportieren_async()`` unterscheidet nicht zwischen Diagramm- und
Tabellen-Figuren, beides ist am Ende ein ``go.Figure``).

Der Anmeldungsverlauf und die Anmeldungstabelle (``notebooks/03_schulungsanmeldungen.
ipynb``) hängen anders als die übrigen Diagramme/Tabellen nicht am ``Dashboard`` der
Umsatzprognose, sondern laden eigenständig über ``SchulungenRepository`` - deshalb ein
eigener Ladepfad (die innere ``_anmeldungsverlauf_laden``-Coroutine in
:func:`_daten_laden_async`) statt eines Eintrags in
``DIAGRAMME_DASHBOARD``/``TABELLEN_DASHBOARD``, nur geladen, wenn eines von beiden
tatsächlich angefordert ist. ``KATEGORIEN`` deckt sich mit derselben, von Hand
gepflegten Zuordnung in ``webapp/app.py``/``notebooks/03_schulungsanmeldungen.ipynb``
(siehe CLAUDE.md) - frei konfigurierbar, deshalb bewusst hier dupliziert statt im Paket.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Callable

    import pandas as pd
    import plotly.graph_objects as go

    from umsatzprognose.domaene.anmeldung import Anmeldungsverlauf

import humanize
import plotly.io as pio
from _fortschritt import (
    Mehrzeilenanzeige,
    dashboard_melden_bauen,
    fortschrittsbalken,
    relativer_pfad,
)

from umsatzprognose import Dashboard
from umsatzprognose.clockodo import gleichzeitig, synchron
from umsatzprognose.darstellung import diagramme, tabellen
from umsatzprognose.schulungen import SchulungenRepository
from umsatzprognose.util import aus_ordnung, ordnung

STANDARD_FORMAT = "png"
FORMATE = ("png", "svg", "html")
STANDARD_MONATE_FENSTER = 13  # wie notebooks/03_schulungsanmeldungen.ipynb

DIAGRAMM_ANMELDUNGSVERLAUF = "anmeldungsverlauf"
DIAGRAMM_ANMELDUNGSTABELLE = "anmeldungstabelle"

# Deckt sich mit "KATEGORIEN" in webapp/app.py und notebooks/03_schulungsanmeldungen.ipynb -
# dieselbe, von Hand gepflegte Zuordnung Schulungstyp -> Kategorie, nur fuer
# anmeldungstabelle gebraucht (der Anmeldungsverlauf zeigt nur die Gesamtzahl, siehe
# diagramme.anmeldungsverlauf).
KATEGORIEN: dict[str, list[str]] = {
    "Scrum": [
        "A-CSD",
        "A-CSM",
        "A-CSPO",
        "CSD",
        "CSM 2-tägig",
        "CSM 3-tägig",
        "CSP-PO",
        "CSP-SM",
        "CSPO 2-tägig",
        "CSPO 3-tägig",
        "CAL 2",
        "CAL ETO",
    ],
    "Kanban": [
        "KCP",
        "KMM",
        "KSD",
        "KSI",
        "KSI 2-tägig",
        "KSI 3-tägig",
        "SBK",
    ],
}

# Name auf der Kommandozeile -> Dashboard-Methode, die die Figur liefert. Deckt alle
# Grafik-Methoden aus den drei Bestand-Notebooks ab (siehe deren Zellen), nicht nur die
# fuenf aus scripts/wochenbericht.py. Der Anmeldungsverlauf steht bewusst nicht hier,
# siehe Moduldocstring.
DIAGRAMME_DASHBOARD = {
    "kennzahlen": Dashboard.kennzahlen,
    "umsatzverlauf": Dashboard.umsatzverlauf,
    "gewinn-verlust-monatlich": Dashboard.gewinn_verlust_monatlich,
    "gewinn-verlust-je-jahr": Dashboard.gewinn_verlust_je_jahr,
    "umsatzrendite-kumuliert": Dashboard.umsatzrendite_kumuliert,
    "restvolumen-je-projekt": Dashboard.restvolumen_je_projekt,
    "kapazitaet-je-mitarbeiter": Dashboard.kapazitaet_je_mitarbeiter,
    "kapazitaet-je-projekt": Dashboard.kapazitaet_je_projekt,
    "auslastung-je-mitarbeiter": Dashboard.auslastung_je_mitarbeiter,
}

# Name auf der Kommandozeile -> (Dashboard-Methode, Bildtitel). Anders als
# DIAGRAMME_DASHBOARD liefert die Methode ein pd.DataFrame statt einer fertigen Figur -
# diagramme.tabelle_als_grafik() macht daraus eine bildexportfaehige plotly-Tabelle,
# siehe Moduldocstring.
TABELLEN_DASHBOARD: dict[str, tuple[Callable[[Dashboard], pd.DataFrame], str]] = {
    "umsatztabelle": (Dashboard.umsatztabelle, "Umsatztabelle"),
    "projekttabelle": (Dashboard.projekttabelle, "Projekttabelle"),
}

# Diese vier kennen "mit_beschriftung" (siehe deren Dashboard-Methoden) - die uebrigen
# (kennzahlen, restvolumen-je-projekt, kapazitaet-*, auslastung-je-mitarbeiter) haben
# den Wert entweder schon fest eingezeichnet oder brauchen ihn nicht.
MIT_BESCHRIFTUNG_FAEHIG = {
    "umsatzverlauf",
    "gewinn-verlust-monatlich",
    "gewinn-verlust-je-jahr",
    "umsatzrendite-kumuliert",
}

ALLE_DIAGRAMME = sorted(
    {
        *DIAGRAMME_DASHBOARD,
        *TABELLEN_DASHBOARD,
        DIAGRAMM_ANMELDUNGSVERLAUF,
        DIAGRAMM_ANMELDUNGSTABELLE,
    }
)


def _argumente(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Diagramme als Dateien exportieren.")
    parser.add_argument(
        "--ausgabeverzeichnis",
        "-o",
        type=Path,
        default=Path("diagramme"),
        help="Zielverzeichnis für die exportierten Dateien (Standard: ./diagramme).",
    )
    parser.add_argument(
        "--format",
        choices=FORMATE,
        default=STANDARD_FORMAT,
        help=f"Ausgabeformat je Diagramm (Standard: {STANDARD_FORMAT}).",
    )
    parser.add_argument(
        "--diagramm",
        action="append",
        choices=ALLE_DIAGRAMME,
        dest="diagramme",
        help="Nur dieses Diagramm exportieren (mehrfach angebbar). Ohne Angabe: alle.",
    )
    parser.add_argument(
        "--stichtag",
        type=date.fromisoformat,
        default=None,
        help="Stichtag im Format JJJJ-MM-TT (Standard: heute).",
    )
    parser.add_argument(
        "--horizont-monate",
        type=int,
        default=3,
        help=(
            "Prognosehorizont in Monaten für die Simulation "
            "(Standard: 3, nur für Dashboard-Diagramme)."
        ),
    )
    parser.add_argument(
        "--monate-fenster",
        type=int,
        default=STANDARD_MONATE_FENSTER,
        help=(
            "Betrachtungszeitraum in Monaten bis zum Stichtag für "
            f"'{DIAGRAMM_ANMELDUNGSVERLAUF}' und '{DIAGRAMM_ANMELDUNGSTABELLE}' "
            f"(Standard: {STANDARD_MONATE_FENSTER})."
        ),
    )
    return parser.parse_args(argv)


async def _daten_laden_async(
    *,
    mit_dashboard: bool,
    mit_anmeldungsverlauf: bool,
    stichtag: date | None,
    horizont_monate: int,
    monate_fenster: int,
) -> tuple[Dashboard | None, Anmeldungsverlauf | None]:
    """Laedt Dashboard und Anmeldungsverlauf gleichzeitig statt nacheinander, wenn
    beide gebraucht werden - zwei voneinander unabhaengige Datenquellen (siehe
    Moduldocstring), dasselbe Muster wie ``scripts/wochenbericht.py``. Wird nur eine
    der beiden angefordert (z. B. ``--diagramm umsatzverlauf`` ohne
    ``anmeldungsverlauf``), laeuft nur ihr eigener Ladevorgang, ohne den anderen
    unnoetig anzustossen. Jede tragt ihren Ladefortschritt in einer eigenen Zeile vor
    (siehe :class:`Mehrzeilenanzeige`), ersetzt am Ende durch die fertige
    Statuszeile - unabhaengig davon, in welcher Reihenfolge sie tatsaechlich fertig
    werden.
    """
    aufgeloester_stichtag = stichtag or date.today()
    anmeldungsverlauf_jahre: list[int] = []
    if mit_anmeldungsverlauf:
        ende = ordnung(aufgeloester_stichtag.year, aufgeloester_stichtag.month)
        start_jahr = aus_ordnung(ende - (monate_fenster - 1))[0]
        anmeldungsverlauf_jahre = list(range(start_jahr, aufgeloester_stichtag.year + 1))

    namen = []
    if mit_dashboard:
        namen += ["Bestand", "Schulungsplan", "Kostenplan", "Auslastung", "Simulation"]
    if mit_anmeldungsverlauf:
        namen.append("Anmeldungsverlauf")
    anzeige = Mehrzeilenanzeige(namen)

    async def _dashboard_laden() -> Dashboard | None:
        if not mit_dashboard:
            return None

        melden = dashboard_melden_bauen(anzeige)
        dashboard = await Dashboard.laden_async(
            stichtag=stichtag, horizont_monate=horizont_monate, fortschritt=melden
        )
        await dashboard.simuliere_async(monate=horizont_monate, fortschritt=melden)
        return dashboard

    async def _anmeldungsverlauf_laden() -> Anmeldungsverlauf | None:
        if not mit_anmeldungsverlauf:
            return None

        erledigt = 0
        gesamt = len(anmeldungsverlauf_jahre)

        def _melden(text: str) -> None:
            nonlocal erledigt
            erledigt += 1
            anzeige.aktualisieren(
                "Anmeldungsverlauf",
                f"Anmeldungsverlauf laden {fortschrittsbalken(erledigt, gesamt)} "
                f"{erledigt}/{gesamt}",
            )

        start = time.perf_counter()
        # asyncio.to_thread(): anmeldungsverlauf_laden() ist ein synchroner Aufruf
        # (siehe Moduldocstring von umsatzprognose.schulungen.schulungen) - im eigenen
        # Worker-Thread blockiert er nicht den Event-Loop, in dem gleichzeitig das
        # Dashboard laedt. Mehrzeilenanzeige ist threadsicher (siehe dort), _melden()
        # darf also direkt aus dem Worker-Thread aufgerufen werden.
        verlauf = await asyncio.to_thread(
            SchulungenRepository.mit_automatischen_zugangsdaten().anmeldungsverlauf_laden,
            anmeldungsverlauf_jahre,
            fortschritt=_melden,
        )
        dauer = timedelta(seconds=time.perf_counter() - start)
        fenster = verlauf.letzte(monate=monate_fenster, stichtag=aufgeloester_stichtag)
        anzeige.aktualisieren(
            "Anmeldungsverlauf",
            f"{len(fenster.anmeldungen)} Anmeldungen aus {len(fenster.monate)} Monaten geladen "
            f"(in {humanize.naturaldelta(dauer)})",
        )
        return fenster

    dashboard, anmeldungsverlauf_fenster = await gleichzeitig(
        _dashboard_laden(), _anmeldungsverlauf_laden()
    )
    return dashboard, anmeldungsverlauf_fenster


def _figuren(
    namen: list[str],
    *,
    dashboard: Dashboard | None,
    anmeldungsverlauf_fenster: Anmeldungsverlauf | None,
    ausgabeformat: str,
) -> dict[str, go.Figure]:
    """Je angefordertem Namen die fertige Figur, aus bereits geladenen Daten.

    ``dashboard``/``anmeldungsverlauf_fenster`` kommen fertig geladen herein (siehe
    :func:`_daten_laden_async`, das beide bei Bedarf gleichzeitig laedt) - diese
    Funktion laedt selbst nichts mehr, sie entscheidet nur, was aus den schon
    geladenen Daten gebaut wird. ``None`` bedeutet, dass die jeweilige Quelle nicht
    angefordert war.

    ``html`` bleibt interaktiv (Hover zeigt den Wert), ``png``/``svg`` sind statische
    Bilder ohne Hover - wie im Wochenbericht (``scripts/wochenbericht.py``) bekommen die
    dafuer geeigneten Diagramme dort zusaetzlich den Wert als Text. Tabellen
    (``TABELLEN_DASHBOARD``, ``anmeldungstabelle``) zeigen ihre Werte ohnehin schon als
    Text in der Tabelle - ``mit_beschriftung`` betrifft nur Diagramme.
    """
    figuren: dict[str, go.Figure] = {}
    mit_beschriftung = ausgabeformat != "html"

    if dashboard is not None:
        for name in (name for name in namen if name in DIAGRAMME_DASHBOARD):
            kwargs = (
                {"mit_beschriftung": mit_beschriftung} if name in MIT_BESCHRIFTUNG_FAEHIG else {}
            )
            figuren[name] = DIAGRAMME_DASHBOARD[name](dashboard, **kwargs)
        for name in (name for name in namen if name in TABELLEN_DASHBOARD):
            methode, titel = TABELLEN_DASHBOARD[name]
            figuren[name] = diagramme.tabelle_als_grafik(titel, methode(dashboard))

    if anmeldungsverlauf_fenster is not None:
        if DIAGRAMM_ANMELDUNGSVERLAUF in namen:
            figuren[DIAGRAMM_ANMELDUNGSVERLAUF] = diagramme.anmeldungsverlauf(
                anmeldungsverlauf_fenster
            )
        if DIAGRAMM_ANMELDUNGSTABELLE in namen:
            figuren[DIAGRAMM_ANMELDUNGSTABELLE] = diagramme.tabelle_als_grafik(
                "Anmeldungen je Monat und Kategorie",
                tabellen.anmeldungstabelle(anmeldungsverlauf_fenster, KATEGORIEN),
            )

    return figuren


async def exportieren_async(
    figuren: dict[str, go.Figure], namen: list[str], ausgabeverzeichnis: Path, ausgabeformat: str
) -> list[Path]:
    """Je Name aus ``namen`` eine Datei schreiben, gibt die geschriebenen Pfade zurück.

    Jede Datei bekommt einen eigenen Export-Balken (siehe :class:`Mehrzeilenanzeige`)
    - beschriftet mit dem Dateinamen relativ zum Aufrufenden Verzeichnis zur
    Erlaeuterung, was gerade geschrieben wird. Ersetzt durch denselben Pfad samt
    Exportdauer, sobald die Datei geschrieben ist. Bei ``html`` laeuft das Schreiben
    gleichzeitig fuer alle Dateien (``asyncio.to_thread()`` je Datei, ueber
    :func:`~umsatzprognose.clockodo.gleichzeitig`) - jede meldet sich individuell,
    sobald sie fertig ist. Bei ``png``/``svg`` schreibt kaleido dagegen alle Bilder in
    einem gemeinsamen Batch-Aufruf zugleich (siehe Kommentar unten) und liefert dabei
    keinen Zwischenstand je Datei - der Balken bleibt bis zum Ende des Batches
    unveraendert (kein Zwischenfortschritt ableitbar), alle Zeilen werden deshalb
    gemeinsam ersetzt, sobald der Batch fertig ist.
    """
    ausgabeverzeichnis.mkdir(parents=True, exist_ok=True)
    geordnete_figuren = [figuren[name] for name in namen]
    pfade = [ausgabeverzeichnis / f"{name}.{ausgabeformat}" for name in namen]
    anzeigenamen = [str(relativer_pfad(pfad)) for pfad in pfade]
    anzeige = Mehrzeilenanzeige(
        anzeigenamen, vorlage="{name} exportieren " + fortschrittsbalken(0, 1)
    )

    if ausgabeformat == "html":

        async def _schreiben(figur: go.Figure, pfad: Path, anzeigename: str) -> None:
            start = time.perf_counter()
            await asyncio.to_thread(figur.write_html, pfad)
            dauer = timedelta(seconds=time.perf_counter() - start)
            anzeige.aktualisieren(
                anzeigename, f"{anzeigename} exportiert (in {humanize.naturaldelta(dauer)})"
            )

        await gleichzeitig(
            *(
                _schreiben(figur, pfad, anzeigename)
                for figur, pfad, anzeigename in zip(
                    geordnete_figuren, pfade, anzeigenamen, strict=True
                )
            )
        )
    else:
        # Ein Batch-Aufruf statt figur.write_image() je Diagramm: kaleido (>=1.0) startet
        # sonst für jedes einzelne Bild eine eigene Chromium-Instanz neu, was den Export
        # mehrerer Diagramme spürbar verlangsamt - hier ein gemeinsamer Browserprozess.
        # asyncio.to_thread(): der Aufruf selbst ist synchron, im eigenen Worker-Thread
        # blockiert er nicht den Event-Loop.
        start = time.perf_counter()
        await asyncio.to_thread(
            pio.write_images,
            fig=cast("list[dict[str, object] | go.Figure]", geordnete_figuren),
            file=cast("list[str | Path]", pfade),
            width=1400,
            height=800,
            scale=2,
        )
        dauer = timedelta(seconds=time.perf_counter() - start)
        for anzeigename in anzeigenamen:
            anzeige.aktualisieren(
                anzeigename, f"{anzeigename} exportiert (in {humanize.naturaldelta(dauer)})"
            )
    return pfade


def _export_zusammenfassung(namen: list[str]) -> str:
    """Zaehlt Diagramme und Tabellen getrennt, z. B. ``"3 Diagramm(e) exportiert"``
    oder ``"3 Diagramm(e) und 1 Tabelle(n) exportiert"`` - nur die Tabellen-Zaehlung
    dazu, wenn tatsaechlich mindestens eine Tabelle exportiert wurde."""
    tabellen_namen = {*TABELLEN_DASHBOARD, DIAGRAMM_ANMELDUNGSTABELLE}
    anzahl_tabellen = sum(1 for name in namen if name in tabellen_namen)
    anzahl_diagramme = len(namen) - anzahl_tabellen
    if anzahl_tabellen == 0:
        return f"{anzahl_diagramme} Diagramm(e) exportiert"
    return f"{anzahl_diagramme} Diagramm(e) und {anzahl_tabellen} Tabelle(n) exportiert"


def main(argv: list[str]) -> int:
    args = _argumente(argv)

    namen = sorted(set(args.diagramme)) if args.diagramme else ALLE_DIAGRAMME
    mit_dashboard = any(name in DIAGRAMME_DASHBOARD or name in TABELLEN_DASHBOARD for name in namen)
    mit_anmeldungsverlauf = any(
        name in (DIAGRAMM_ANMELDUNGSVERLAUF, DIAGRAMM_ANMELDUNGSTABELLE) for name in namen
    )
    dashboard, anmeldungsverlauf_fenster = synchron(
        _daten_laden_async(
            mit_dashboard=mit_dashboard,
            mit_anmeldungsverlauf=mit_anmeldungsverlauf,
            stichtag=args.stichtag,
            horizont_monate=args.horizont_monate,
            monate_fenster=args.monate_fenster,
        )
    )
    figuren = _figuren(
        namen,
        dashboard=dashboard,
        anmeldungsverlauf_fenster=anmeldungsverlauf_fenster,
        ausgabeformat=args.format,
    )
    # Die Leerzeile trennt die (auf stderr geschriebene) Ladeanzeige sichtbar von den
    # nachfolgenden Export-Balken.
    print("Daten geladen.\n")

    synchron(exportieren_async(figuren, namen, args.ausgabeverzeichnis, args.format))

    print(f"{_export_zusammenfassung(namen)} nach {args.ausgabeverzeichnis}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
