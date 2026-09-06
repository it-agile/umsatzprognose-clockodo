"""Wöchentlicher Slack-Post des Dashboards - Einstieg für die GitHub Action.

Lädt den Bestand wie das Notebook, rendert dieselben Diagramme als PNG (kaleido) und
postet sie in einen Slack-Kanal (Bot-Token, ``chat:write`` und ``files:write``). Kein
Teil des Pakets: Slack- und Bildexport-Abhängigkeiten gehören nicht in
``umsatzprognose`` selbst, siehe ``[project.optional-dependencies.bericht]`` in
pyproject.toml.

Zugangsdaten kommen ausschließlich aus Umgebungsvariablen (``ClockodoCredentials.
aus_umgebung()`` bzw. ``GoogleSheetsConfig.aus_umgebung()``) - in der Action als
Secrets, siehe .github/workflows/wochenbericht.yml.

Der Post besteht aus zwei Nachrichten im selben Thread: die erste ("Zahlen, Daten,
Fakten") trägt alle Diagramme als Bilder, die zweite die Umsatztabelle als Text -
dieselben Ansichten wie in notebooks/01_dashboard.ipynb, notebooks/00_datencheck.ipynb
und notebooks/03_schulungsanmeldungen.ipynb.

``WOCHENBERICHT_HORIZONT_MONATE`` und ``WOCHENBERICHT_GEWINN_VERLUST_MONATE`` sind
optional - ohne gesetztes Secret gelten dieselben Standardwerte wie in den Notebooks
(``Dashboard.laden`` bzw. ``Dashboard.gewinn_verlust_monatlich``).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import plotly.io as pio
from slack_sdk import WebClient

from umsatzprognose import Dashboard, SchulungenRepository
from umsatzprognose.darstellung import diagramme
from umsatzprognose.darstellung.dashboard import STANDARD_GEWINN_VERLUST_MONATE

SLACK_CHANNEL_VAR = "SLACK_CHANNEL_ID"
SLACK_TOKEN_VAR = "SLACK_BOT_TOKEN"
HORIZONT_MONATE_VAR = "WOCHENBERICHT_HORIZONT_MONATE"
GEWINN_VERLUST_MONATE_VAR = "WOCHENBERICHT_GEWINN_VERLUST_MONATE"

STANDARD_HORIZONT_MONATE = 3

# Deckt sich mit "monate_fenster"/"ab_jahr" in notebooks/03_schulungsanmeldungen.ipynb -
# derselbe Betrachtungszeitraum für den Anmeldungsverlauf, hier ohne eigenes Secret,
# weil nicht angefragt.
ANMELDUNGEN_AB_JAHR = 2022
ANMELDUNGEN_MONATE_FENSTER = 13

# Deckt sich mit "KATEGORIEN" in notebooks/03_schulungsanmeldungen.ipynb und
# webapp/app.py - dieselbe, von Hand gepflegte Zuordnung Schulungstyp -> Kategorie.
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


def diagrammtitel_und_figuren(
    dashboard: Dashboard, *, gewinn_verlust_monate: int | None
) -> list[tuple[str, object]]:
    """Titel und Figur je Diagramm, in der Reihenfolge des Posts."""
    jahre = range(ANMELDUNGEN_AB_JAHR, dashboard.stichtag.year + 1)
    anmeldungsverlauf = (
        SchulungenRepository.mit_automatischen_zugangsdaten().anmeldungsverlauf_laden(jahre)
    )
    anmeldungsverlauf_fenster = anmeldungsverlauf.letzte(
        monate=ANMELDUNGEN_MONATE_FENSTER, stichtag=dashboard.stichtag
    )
    return [
        ("Umsatz je Monat", dashboard.umsatzverlauf()),
        ("Offenes Auftragsvolumen je Projekt", dashboard.restvolumen_je_projekt()),
        (
            "Gewinn/Verlust je Monat",
            dashboard.gewinn_verlust_monatlich(monate=gewinn_verlust_monate),
        ),
        ("Gewinn/Verlust je Monat und Jahr", dashboard.gewinn_verlust_je_jahr()),
        ("Kumulierte Umsatzrendite je Jahr", dashboard.umsatzrendite_kumuliert()),
        (
            "Anmeldungen je Monat",
            diagramme.anmeldungsverlauf(anmeldungsverlauf_fenster, KATEGORIEN),
        ),
    ]


def posten(
    client: WebClient,
    kanal: str,
    dashboard: Dashboard,
    verzeichnis: Path,
    *,
    gewinn_verlust_monate: int | None,
) -> None:
    einstieg = client.chat_postMessage(
        channel=kanal,
        text=f"Zahlen, Daten, Fakten - Stand {dashboard.stichtag:%d.%m.%Y}",
    )
    # chat.postMessage loest eine Nutzer-ID im DM-Fall selbst zur eigentlichen
    # Conversation-ID auf (antwortet mit "channel") - die neueren Datei-Upload-Endpunkte
    # pruefen channel_id dagegen streng gegen "^[CGDZ][A-Z0-9]{8,}$" und lehnen eine
    # Nutzer-ID ("U...") ab. Deshalb ab hier die aufgeloeste ID statt kanal verwenden.
    channel_id = einstieg["channel"]
    titel_figuren = diagrammtitel_und_figuren(
        dashboard, gewinn_verlust_monate=gewinn_verlust_monate
    )
    # "/" im Titel ("Gewinn/Verlust je Monat") waere im Dateinamen ein Pfadtrenner -
    # der Slack-Titel bleibt davon unberuehrt, nur der lokale Dateiname wird bereinigt.
    bilder = [verzeichnis / f"{titel.replace('/', '-')}.png" for titel, _figur in titel_figuren]
    # Ein Batch-Aufruf statt figur.write_image() je Bild: kaleido (>=1.0) startet sonst
    # fuer jedes Bild eine eigene Chromium-Instanz neu - siehe
    # scripts/diagramme_exportieren.py fuer denselben Fix mit Zeitmessung.
    pio.write_images(
        fig=[figur for _titel, figur in titel_figuren], file=bilder, width=1400, height=800, scale=2
    )
    for (titel, _figur), bild in zip(titel_figuren, bilder, strict=True):
        client.files_upload_v2(
            channel=channel_id,
            thread_ts=einstieg["ts"],
            file=str(bild),
            title=titel,
        )

    umsatztabelle = dashboard.umsatztabelle().to_string(index=False)
    client.chat_postMessage(
        channel=channel_id,
        thread_ts=einstieg["ts"],
        text=f"Umsatz je Monat\n```{umsatztabelle}```",
    )


def main() -> None:
    horizont_monate = _optionale_ganzzahl(HORIZONT_MONATE_VAR, STANDARD_HORIZONT_MONATE)
    gewinn_verlust_monate = _optionale_ganzzahl(
        GEWINN_VERLUST_MONATE_VAR, STANDARD_GEWINN_VERLUST_MONATE
    )

    dashboard = Dashboard.laden(horizont_monate=horizont_monate)
    dashboard.simuliere(monate=horizont_monate)

    client = WebClient(token=_umgebungsvariable(SLACK_TOKEN_VAR))
    kanal = _umgebungsvariable(SLACK_CHANNEL_VAR)

    with tempfile.TemporaryDirectory() as verzeichnis:
        posten(
            client,
            kanal,
            dashboard,
            Path(verzeichnis),
            gewinn_verlust_monate=gewinn_verlust_monate,
        )


def _umgebungsvariable(name: str) -> str:
    wert = os.environ.get(name, "").strip()
    if not wert:
        raise RuntimeError(f"Umgebungsvariable {name} ist nicht gesetzt.")
    return wert


def _optionale_ganzzahl(name: str, standard: int) -> int:
    """Wie ``standard``, aber übersteuerbar über eine optionale Umgebungsvariable."""
    wert = os.environ.get(name, "").strip()
    return int(wert) if wert else standard


if __name__ == "__main__":
    main()
