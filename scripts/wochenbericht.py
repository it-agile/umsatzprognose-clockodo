"""Wöchentlicher Slack-Post des Dashboards - Einstieg für die GitHub Action.

Lädt den Bestand wie das Notebook, rendert dieselben Diagramme als PNG (kaleido) und
postet sie in einen Slack-Kanal (Bot-Token, ``chat:write`` und ``files:write``). Kein
Teil des Pakets: Slack- und Bildexport-Abhängigkeiten gehören nicht in
``umsatzprognose`` selbst, siehe ``[project.optional-dependencies.bericht]`` in
pyproject.toml.

Zugangsdaten kommen ausschließlich aus Umgebungsvariablen (``ClockodoCredentials.
aus_umgebung()`` bzw. ``GoogleSheetsConfig.aus_umgebung()``) - in der Action als
Secrets, siehe .github/workflows/wochenbericht.yml.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import plotly.io as pio
from slack_sdk import WebClient

from umsatzprognose import Dashboard

SLACK_CHANNEL_VAR = "SLACK_CHANNEL_ID"
SLACK_TOKEN_VAR = "SLACK_BOT_TOKEN"


def diagramme(dashboard: Dashboard) -> list[tuple[str, object]]:
    """Titel und Figur je Diagramm, in der Reihenfolge des Posts."""
    return [
        ("Kennzahlen", dashboard.kennzahlen()),
        ("Umsatzverlauf", dashboard.umsatzverlauf()),
        ("Offenes Auftragsvolumen je Projekt", dashboard.restvolumen_je_projekt()),
        ("Kapazität je Mitarbeiter", dashboard.kapazitaet_je_mitarbeiter()),
        ("Kapazität je Projekt", dashboard.kapazitaet_je_projekt()),
    ]


def posten(client: WebClient, kanal: str, dashboard: Dashboard, verzeichnis: Path) -> None:
    einstieg = client.chat_postMessage(
        channel=kanal,
        text=f"Wochenbericht Umsatzprognose - Stand {dashboard.stichtag:%d.%m.%Y}",
    )
    titel_figuren = diagramme(dashboard)
    bilder = [verzeichnis / f"{titel}.png" for titel, _figur in titel_figuren]
    # Ein Batch-Aufruf statt figur.write_image() je Bild: kaleido (>=1.0) startet sonst
    # fuer jedes Bild eine eigene Chromium-Instanz neu - siehe
    # scripts/diagramme_exportieren.py fuer denselben Fix mit Zeitmessung.
    pio.write_images(
        fig=[figur for _titel, figur in titel_figuren], file=bilder, width=1400, height=800, scale=2
    )
    for (titel, _figur), bild in zip(titel_figuren, bilder, strict=True):
        client.files_upload_v2(
            channel=kanal,
            thread_ts=einstieg["ts"],
            file=str(bild),
            title=titel,
        )


def main() -> None:
    dashboard = Dashboard.laden()
    dashboard.simuliere()

    client = WebClient(token=_umgebungsvariable(SLACK_TOKEN_VAR))
    kanal = _umgebungsvariable(SLACK_CHANNEL_VAR)

    with tempfile.TemporaryDirectory() as verzeichnis:
        posten(client, kanal, dashboard, Path(verzeichnis))


def _umgebungsvariable(name: str) -> str:
    wert = os.environ.get(name, "").strip()
    if not wert:
        raise RuntimeError(f"Umgebungsvariable {name} ist nicht gesetzt.")
    return wert


if __name__ == "__main__":
    main()
