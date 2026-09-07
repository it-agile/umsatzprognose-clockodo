"""Wöchentlicher Slack-Post des Dashboards - Einstieg für die GitHub Action.

Lädt den Bestand wie das Notebook, rendert dieselben Diagramme als PNG (kaleido) und
postet sie in einen Slack-Kanal (Bot-Token, ``chat:write`` und ``files:write``). Kein
Teil des Pakets: Slack- und Bildexport-Abhängigkeiten gehören nicht in
``umsatzprognose`` selbst, siehe ``[project.optional-dependencies.bericht]`` in
pyproject.toml.

Zugangsdaten kommen ausschließlich aus Umgebungsvariablen (``ClockodoCredentials.
aus_umgebung()`` bzw. ``GoogleSheetsConfig.aus_umgebung()``) - in der Action als
Secrets, siehe .github/workflows/wochenbericht.yml.

Ein einziger Post ("Wochenbericht Zahlen, Daten, Fakten") trägt alle Diagramme als Bilder,
einschließlich der Umsatztabelle als gerendertes Bild statt als Text - dieselben
Ansichten wie in notebooks/01_dashboard.ipynb, notebooks/00_datencheck.ipynb und
notebooks/03_schulungsanmeldungen.ipynb. Ein einzelner Slack-API-Aufruf
(``files_upload_v2`` mit ``file_uploads``) hängt dabei alle Bilder gemeinsam an
dieselbe Nachricht, statt je Bild eine eigene Unternachricht zu erzeugen.

``WOCHENBERICHT_HORIZONT_MONATE`` und ``WOCHENBERICHT_GEWINN_VERLUST_MONATE`` sind
optional - ohne gesetztes Secret gelten dieselben Standardwerte wie in den Notebooks
(``Dashboard.laden`` bzw. ``Dashboard.gewinn_verlust_monatlich``).
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

    from umsatzprognose.util import Monat

import plotly.graph_objects as go
import plotly.io as pio
from slack_sdk import WebClient

from umsatzprognose import Dashboard, SchulungenRepository
from umsatzprognose.clockodo import KurzarbeitRepository, rollenzuordnung_automatisch
from umsatzprognose.darstellung import diagramme
from umsatzprognose.darstellung.dashboard import STANDARD_GEWINN_VERLUST_MONATE
from umsatzprognose.darstellung.gestaltung import FLAECHE, SCHRIFT, SERIE, TINTE, figur
from umsatzprognose.domaene import Kurzarbeitsbewertung, bewertungen
from umsatzprognose.domaene.umsatzhistorie import MONATSNAMEN
from umsatzprognose.domaene.zahlen import euro, prozent

SLACK_CHANNEL_VAR = "SLACK_CHANNEL_ID"
SLACK_TOKEN_VAR = "SLACK_BOT_TOKEN"
HORIZONT_MONATE_VAR = "WOCHENBERICHT_HORIZONT_MONATE"
GEWINN_VERLUST_MONATE_VAR = "WOCHENBERICHT_GEWINN_VERLUST_MONATE"

STANDARD_HORIZONT_MONATE = 3

# Slacks Datei-Upload-Endpunkt (anders als chat.postMessage, das eine Nutzer-ID beim
# DM-Versand selbst zur Conversation-ID aufloest) verlangt bereits eine echte
# Channel-/Conversation-ID. Wer zu Testzwecken an sich selbst postet, braucht deshalb
# die ID der DM-Konversation (Slack-Client: Konversation oeffnen, "Copy link" - der
# "D..."-Teil der URL), nicht die eigene Mitglieds-ID ("U...").
_CHANNEL_ID_MUSTER = re.compile(r"^[CGDZ][A-Z0-9]{8,}$")

# Deckt sich mit "anzahl_monate" in notebooks/04_kurzarbeit.ipynb und
# STANDARD_KURZARBEIT_MONATE in webapp/app.py - hier ohne eigenes Secret, weil nicht
# angefragt.
KURZARBEIT_ANZAHL_MONATE = 6

# Deckt sich mit "monate_fenster"/"ab_jahr" in notebooks/03_schulungsanmeldungen.ipynb -
# derselbe Betrachtungszeitraum für den Anmeldungsverlauf, hier ohne eigenes Secret,
# weil nicht angefragt.
ANMELDUNGEN_AB_JAHR = 2022
ANMELDUNGEN_MONATE_FENSTER = 13


def umsatztabelle_grafik(tabelle: pd.DataFrame) -> go.Figure:
    """Dieselbe Monatstabelle als Bild statt als Text.

    Slack kann eine eingebettete Tabelle nicht darstellen - ein monospace-Codeblock
    (die vorige Lösung) ist auf Mobilgeräten und bei vielen Spalten kaum lesbar. Kein
    Teil von :mod:`umsatzprognose.darstellung.tabellen`/``diagramme`` (dort bewusst
    pandas bzw. plotly getrennt, siehe deren Modul-Docstrings) - dieses Skript steht
    ohnehin schon außerhalb des Pakets, siehe Moduldocstring oben.
    """
    zeilenhoehe = 26
    fig = figur("Umsatz je Monat", hoehe=70 + zeilenhoehe * (len(tabelle) + 1))
    ausrichtung = ["left"] + ["right"] * (len(tabelle.columns) - 1)
    fig.add_trace(
        go.Table(
            header={
                "values": [f"<b>{spalte}</b>" for spalte in tabelle.columns],
                "fill_color": SERIE,
                "font": {"color": "#ffffff", "family": SCHRIFT, "size": 13},
                "align": ausrichtung,
                "height": 30,
            },
            cells={
                "values": [tabelle[spalte] for spalte in tabelle.columns],
                "fill_color": FLAECHE,
                "font": {"color": TINTE, "family": SCHRIFT, "size": 12},
                "align": ausrichtung,
                "height": zeilenhoehe,
            },
        )
    )
    fig.update_layout(margin={"l": 12, "r": 12, "t": 40, "b": 12})
    return fig


# Eine Zeile Kontext je Grafik (Kollegen-Feedback: "etwas mehr Kontext als nur die
# Grafiken") - dieselben Titel wie in diagrammtitel_und_figuren(), hier als
# Bildunterschriften im Post statt nur als Bild-Titel im Slack-Anhang.
DIAGRAMM_ERLAEUTERUNGEN: dict[str, str] = {
    "Umsatz je Monat": (
        "Historischer und prognostizierter Umsatz, inklusive Schulungsanmeldungen "
        "und Kostenprognose."
    ),
    "Offenes Auftragsvolumen je Projekt": "Restvolumen der größten Projekte im Prognose-Scope.",
    "Gewinn/Verlust je Monat": "Umsatz minus Kosten je Monat im gezeigten Betrachtungsfenster.",
    "Gewinn/Verlust je Monat und Jahr": "Dieselbe Differenz, gruppiert nach Kalenderjahr.",
    "Kumulierte Umsatzrendite je Jahr": "Gewinn in Prozent des Umsatzes, kumuliert über das Jahr.",
    "Auslastung je Person": (
        "Anteil abrechenbarer Stunden an der verfügbaren Kapazität je Person, über "
        "die geladenen Monate."
    ),
    "Kurzarbeitsbereitschaft je Monat": (
        "Rückblickend je Monat, ob die Organisation die Voraussetzungen für "
        "Kurzarbeit erfüllt hätte - unabhängig von der Umsatzprognose."
    ),
    "Anmeldungen je Monat": "Teilnehmerzahl öffentlicher Schulungen je Monat, insgesamt.",
    "Umsatztabelle": "Dieselben Monatswerte aus dem Umsatzverlauf als Tabelle.",
}


def kontext_text(dashboard: Dashboard) -> str:
    """Kurzer Fließtext vor den Grafiken: Prognosehorizont, Bandbreite und ein
    etwaiger Kapazitätsengpass in Worten statt nur in den Diagrammen.

    ``summe()`` ist auf den Konfidenzniveaus 95 %/85 %/50 % ausgewiesen (siehe
    ``domaene.prognose.KONFIDENZNIVEAUS`` und CLAUDE.md) - ein höheres Niveau steht für
    ein niedrigeres, konservativeres Quantil (95 % ⇒ "mindestens dieser Betrag"), 50 %
    für den Median.
    """
    prognose = dashboard.prognose
    if not prognose.vorhanden:
        return prognose.begruendung

    (von_jahr, von_monat), (bis_jahr, bis_monat) = (
        prognose.horizontmonate()[0],
        prognose.horizontmonate()[-1],
    )
    zeitraum = (
        f"{MONATSNAMEN[von_monat - 1]} {von_jahr}"
        if (von_jahr, von_monat) == (bis_jahr, bis_monat)
        else f"{MONATSNAMEN[von_monat - 1]} {von_jahr} bis {MONATSNAMEN[bis_monat - 1]} {bis_jahr}"
    )

    summe = prognose.summe()
    text = (
        f"Prognose für {zeitraum}: mindestens {euro(summe[0.95])} mit 95 % Sicherheit, "
        f"im Median rund {euro(summe[0.50])}."
    )

    kapazitaet_anteil = prognose.kapazitaet_limitierend_anteil()
    if kapazitaet_anteil > 0:
        text += (
            f" In {prozent(kapazitaet_anteil)} der simulierten Läufe war die "
            "Personalkapazität der limitierende Faktor, nicht die Nachfrage."
        )
    return text


def kurzarbeit_laden(dashboard: Dashboard) -> dict[Monat, Kurzarbeitsbewertung]:
    """Laedt die Kurzarbeit-Rohdaten und bewertet sie - eigenstaendig, unabhaengig vom
    Bestand (Spec Abschnitt 2/7, siehe ``notebooks/04_kurzarbeit.ipynb``).

    Synchron statt ``laden_async``: dieses Skript laeuft ausserhalb eines Event-Loops,
    genau der Fall, fuer den ``KurzarbeitRepository.laden`` gedacht ist.
    """
    rohdaten = KurzarbeitRepository.mit_automatischen_zugangsdaten().laden(
        stichtag=dashboard.stichtag, anzahl_monate=KURZARBEIT_ANZAHL_MONATE
    )
    return bewertungen(rohdaten, rollenzuordnung=rollenzuordnung_automatisch())


def kurzarbeit_erlaeuterung(ergebnisse: dict[Monat, Kurzarbeitsbewertung]) -> str:
    """Ein Satz zum juengsten bewerteten Monat - die Erläuterung neben der Grafik."""
    jahr, monat_nr = sorted(ergebnisse)[-1]
    bewertung = ergebnisse[(jahr, monat_nr)]
    monatsname = f"{MONATSNAMEN[monat_nr - 1]} {jahr}"
    if bewertung.vorbereitet is None:
        return f"Kurzarbeitsbereitschaft ({monatsname}): keine Auswertung möglich."
    status = "Voraussetzung erfüllt" if bewertung.vorbereitet else "Voraussetzung nicht erfüllt"
    quote = f"{bewertung.quote:.0%}" if bewertung.quote is not None else "n/a"
    # Slack-mrkdwn kennt keine Textfarbe (anders als die Grafik mit
    # ERGEBNIS_POSITIV/ERGEBNIS_NEGATIV) - Fettung ist die naheliegende Entsprechung
    # fuer denselben Zweck: erfuellt/nicht erfuellt auf den ersten Blick unterscheiden.
    return (
        f"Kurzarbeitsbereitschaft ({monatsname}): *{status}* (Quote {quote}, Schwelle "
        f"{bewertung.schwellenwerte.quote_organisation:.0%})."
    )


def diagrammtitel_und_figuren(
    dashboard: Dashboard,
    kurzarbeit_ergebnisse: dict[Monat, Kurzarbeitsbewertung],
    *,
    gewinn_verlust_monate: int | None,
) -> list[tuple[str, object]]:
    """Titel und Figur je Diagramm, in der Reihenfolge des Posts."""
    jahre = range(ANMELDUNGEN_AB_JAHR, dashboard.stichtag.year + 1)
    anmeldungsverlauf = (
        SchulungenRepository.mit_automatischen_zugangsdaten().anmeldungsverlauf_laden(jahre)
    )
    anmeldungsverlauf_fenster = anmeldungsverlauf.letzte(
        monate=ANMELDUNGEN_MONATE_FENSTER, stichtag=dashboard.stichtag
    )
    # mit_beschriftung=True nur hier: ein statischer Bildexport ohne Hover-Tooltip
    # braucht die Werte als Text, Notebooks und Webapp zeigen sie interaktiv per Hover.
    return [
        ("Umsatz je Monat", dashboard.umsatzverlauf(mit_beschriftung=True)),
        ("Offenes Auftragsvolumen je Projekt", dashboard.restvolumen_je_projekt()),
        (
            "Gewinn/Verlust je Monat",
            dashboard.gewinn_verlust_monatlich(monate=gewinn_verlust_monate, mit_beschriftung=True),
        ),
        (
            "Gewinn/Verlust je Monat und Jahr",
            dashboard.gewinn_verlust_je_jahr(mit_beschriftung=True),
        ),
        (
            "Kumulierte Umsatzrendite je Jahr",
            dashboard.umsatzrendite_kumuliert(mit_beschriftung=True),
        ),
        ("Auslastung je Person", dashboard.auslastung_je_mitarbeiter()),
        (
            "Kurzarbeitsbereitschaft je Monat",
            diagramme.kurzarbeit_grafik(kurzarbeit_ergebnisse, mit_beschriftung=True),
        ),
        ("Anmeldungen je Monat", diagramme.anmeldungsverlauf(anmeldungsverlauf_fenster)),
        ("Umsatztabelle", umsatztabelle_grafik(dashboard.umsatztabelle())),
    ]


def posten(
    client: WebClient,
    kanal: str,
    dashboard: Dashboard,
    verzeichnis: Path,
    *,
    gewinn_verlust_monate: int | None,
) -> None:
    if not _CHANNEL_ID_MUSTER.match(kanal):
        raise RuntimeError(
            f"{SLACK_CHANNEL_VAR}={kanal!r} sieht nicht nach einer Channel-/Conversation-ID "
            "aus (erwartet z. B. 'C0123456789' oder 'D0123456789'). Für einen DM-Test an "
            "sich selbst die ID der DM-Konversation verwenden (Slack: Konversation öffnen, "
            "„Copy link“ - der Teil nach der letzten '/'), nicht die eigene Mitglieds-ID."
        )

    kurzarbeit_ergebnisse = kurzarbeit_laden(dashboard)
    titel_figuren = diagrammtitel_und_figuren(
        dashboard, kurzarbeit_ergebnisse, gewinn_verlust_monate=gewinn_verlust_monate
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

    # file_uploads statt einer Schleife aus einzelnen files_upload_v2-Aufrufen: so
    # haengen alle Bilder gemeinsam an einer Nachricht (initial_comment), statt je Bild
    # eine eigene Unternachricht im Thread zu erzeugen. Deshalb auch die
    # Bildunterschriften als Aufzaehlung in derselben Nachricht statt je Bild einer
    # eigenen - Slacks file_uploads kennt keinen Kommentar je Datei.
    erlaeuterungen = "\n".join(
        f"• {titel}: {DIAGRAMM_ERLAEUTERUNGEN[titel]}"
        for titel, _figur in titel_figuren
        if titel in DIAGRAMM_ERLAEUTERUNGEN
    )
    titel_post = (
        f"Wochenbericht Zahlen, Daten, Fakten - Stand {dashboard.stichtag:%d.%m.%Y}\n\n"
        f"{kontext_text(dashboard)}\n\n{kurzarbeit_erlaeuterung(kurzarbeit_ergebnisse)}\n\n"
        f"{erlaeuterungen}"
    )
    client.files_upload_v2(
        channel=kanal,
        initial_comment=titel_post,
        file_uploads=[
            {"file": str(bild), "title": titel}
            for (titel, _figur), bild in zip(titel_figuren, bilder, strict=True)
        ],
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
