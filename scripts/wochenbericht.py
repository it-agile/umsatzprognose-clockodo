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

Mit ``--nur-text`` gibt das Skript nur den Text des Slack-Posts auf der Kommandozeile
aus, statt ihn zu posten - weder Diagramm-Rendering noch Slack-Zugangsdaten nötig, zum
Nachlesen des Textes vor einem echten Post.

Die drei voneinander unabhängigen Datenquellen (Dashboard, Kurzarbeit-Rohdaten,
Anmeldungsverlauf) laden dabei gleichzeitig statt nacheinander - wie
``Dashboard.laden_async`` intern schon seine vier Bestandteile gleichzeitig lädt, und
wie ``webapp/app.py``s ``_vorladen()`` alle drei Caches beim Start unabhängig
voneinander anstößt. Jede Quelle trägt ihren Ladefortschritt in einer eigenen Zeile
vor (siehe ``Mehrzeilenanzeige``), ersetzt am Ende durch die fertige Statuszeile -
sowohl mit als auch ohne ``--nur-text``, und sowohl im lokalen Terminal als auch im Log
des GitHub-Actions-Laufs. Eine Leerzeile trennt den Ladebericht ("Daten geladen und
simuliert.") sichtbar vom Folgenden - dem Post-Text bei ``--nur-text``, den
Export-Balken sonst.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import tempfile
import time
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

if TYPE_CHECKING:
    from collections.abc import Sequence

    import pandas as pd
    import plotly.graph_objects as go

    from umsatzprognose.domaene import Prognose
    from umsatzprognose.domaene.anmeldung import Anmeldungsverlauf
    from umsatzprognose.util import Monat

import humanize
import plotly.io as pio
from _fortschritt import (
    Mehrzeilenanzeige,
    dashboard_melden_bauen,
    fortschrittsbalken,
    relativer_pfad,
)
from slack_sdk import WebClient

from umsatzprognose import Dashboard, SchulungenRepository
from umsatzprognose.clockodo import (
    KurzarbeitRepository,
    anzahl_ladeschritte,
    gleichzeitig,
    kurzarbeit_aktiv,
    rollenzuordnung_automatisch,
    synchron,
)
from umsatzprognose.darstellung import diagramme
from umsatzprognose.darstellung.dashboard import STANDARD_GEWINN_VERLUST_MONATE
from umsatzprognose.domaene import Kurzarbeitsbewertung, bewertungen
from umsatzprognose.domaene.umsatzhistorie import MONATSNAMEN
from umsatzprognose.domaene.zahlen import euro, prozent


class _Monatsumsatzauszug(Protocol):
    """Nur das Feld von :class:`~umsatzprognose.domaene.umsatzhistorie.Monatsumsatz`,
    das :func:`kontext_text` fuer den bereits gebuchten Betrag des laufenden Monats
    braucht. Als ``@property`` (nicht als schreibbares Attribut), damit die
    Attributzuordnung zu :class:`_Dashboardauszug` kovariant statt invariant geprueft
    wird - sonst wuerde mypy fuer ``Monatsumsatz`` (und jeden leichtgewichtigen
    Test-Stand-in) einen exakten Typ statt nur strukturelle Kompatibilitaet verlangen."""

    @property
    def umsatz(self) -> Decimal: ...


class _Umsatzhistorieauszug(Protocol):
    """Nur das Feld von :class:`~umsatzprognose.domaene.umsatzhistorie.Umsatzhistorie`,
    das :func:`kontext_text` braucht."""

    @property
    def laufender(self) -> _Monatsumsatzauszug | None: ...


class _Bestandsauszug(Protocol):
    """Nur das Feld von :class:`~umsatzprognose.domaene.bestand.Bestand`, das
    :func:`kontext_text` braucht."""

    @property
    def umsatzhistorie(self) -> _Umsatzhistorieauszug | None: ...


class _Summenquelle(Protocol):
    """Der gemeinsame Ausschnitt von :class:`~umsatzprognose.domaene.schulung.Schulungsplan`
    und :class:`~umsatzprognose.domaene.kosten.Kostenplan`, den :func:`kontext_text`
    braucht - beide summieren einen Betrag ueber eine Menge Horizontmonate.

    ``monate`` positional-only (``/``): ``Schulungsplan.summe`` nennt denselben
    Parameter ``horizontmonate``, ``Kostenplan.summe`` nennt ihn ``monate`` - ohne
    ``/`` verlangt die Protocol-Struktur denselben Namen fuer beide (siehe
    ``Fortschritt.__call__`` in ``umsatzprognose.util.fortschritt`` fuer denselben
    Kniff)."""

    def summe(self, monate: Sequence[Monat], /) -> Decimal: ...


class _Dashboardauszug(Protocol):
    """Der Ausschnitt von :class:`~umsatzprognose.darstellung.dashboard.Dashboard`, den
    dieses Skript tatsaechlich braucht - als Protocol statt der konkreten Klasse, damit
    Tests einen leichtgewichtigen Stand-in verwenden koennen (siehe
    ``tests/scripts/test_wochenbericht.py::_FakeDashboard``), ohne eine echte Simulation
    aufzusetzen."""

    @property
    def stichtag(self) -> date: ...

    prognose: Prognose

    @property
    def bestand(self) -> _Bestandsauszug: ...

    @property
    def schulungsplan(self) -> _Summenquelle: ...

    @property
    def kostenplan(self) -> _Summenquelle: ...

    def umsatzverlauf(self, *, mit_beschriftung: bool = False) -> go.Figure: ...
    def restvolumen_je_projekt(self) -> go.Figure: ...
    def gewinn_verlust_monatlich(
        self, *, monate: int | None = None, mit_beschriftung: bool = False
    ) -> go.Figure: ...
    def gewinn_verlust_je_jahr(self, *, mit_beschriftung: bool = False) -> go.Figure: ...
    def umsatzrendite_kumuliert(self, *, mit_beschriftung: bool = False) -> go.Figure: ...
    def auslastung_je_mitarbeiter(self) -> go.Figure: ...
    def umsatztabelle(self) -> pd.DataFrame: ...


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


async def _daten_laden_async(
    *,
    stichtag: date,
    horizont_monate: int,
    mit_kurzarbeit: bool,
    mit_anmeldungsverlauf: bool,
) -> tuple[Dashboard, dict[Monat, Kurzarbeitsbewertung] | None, Anmeldungsverlauf | None]:
    """Laedt Dashboard, Kurzarbeit-Rohdaten und Anmeldungsverlauf gleichzeitig statt
    nacheinander - drei voneinander unabhaengige Datenquellen (siehe CLAUDE.md), genau
    wie ``Dashboard.laden_async`` intern schon seine vier Bestandteile gleichzeitig
    laedt, und wie ``webapp/app.py``s ``_vorladen()`` alle drei Caches beim Start
    unabhaengig voneinander anstoesst statt eine der drei erst abzuwarten, ehe die
    naechste beginnt.

    Jede tragt ihren Ladefortschritt in einer eigenen Zeile vor (siehe
    :class:`Mehrzeilenanzeige`), ersetzt am Ende durch die fertige Statuszeile -
    unabhaengig davon, in welcher Reihenfolge sie tatsaechlich fertig werden.
    ``mit_kurzarbeit``/``mit_anmeldungsverlauf`` lassen die zugehoerige Zeile (und den
    Abruf) ganz entfallen, statt unnoetig zu laden: Kurzarbeit nur hinter dem
    Feature-Flag (:func:`~umsatzprognose.clockodo.kurzarbeit_aktiv`), Anmeldungsverlauf
    nur, wenn tatsaechlich Diagramme gebraucht werden (nicht bei ``--nur-text``, siehe
    :func:`main`).
    """
    namen = ["Bestand", "Schulungsplan", "Kostenplan", "Auslastung", "Simulation"]
    if mit_kurzarbeit:
        namen.append("Kurzarbeit-Rohdaten")
    if mit_anmeldungsverlauf:
        namen.append("Anmeldungsverlauf")
    anzeige = Mehrzeilenanzeige(namen)

    anmeldungsverlauf_jahre = (
        list(range(ANMELDUNGEN_AB_JAHR, stichtag.year + 1)) if mit_anmeldungsverlauf else []
    )

    async def _dashboard_laden() -> Dashboard:
        melden = dashboard_melden_bauen(anzeige)
        dashboard = await Dashboard.laden_async(
            stichtag=stichtag, horizont_monate=horizont_monate, fortschritt=melden
        )
        await dashboard.simuliere_async(monate=horizont_monate, fortschritt=melden)
        return dashboard

    async def _kurzarbeit_laden() -> dict[Monat, Kurzarbeitsbewertung] | None:
        if not mit_kurzarbeit:
            return None

        erledigt = 0
        total = anzahl_ladeschritte(stichtag, KURZARBEIT_ANZAHL_MONATE)

        def _melden(text: str) -> None:
            nonlocal erledigt
            erledigt += 1
            anzeige.aktualisieren(
                "Kurzarbeit-Rohdaten",
                f"Kurzarbeit-Rohdaten laden {fortschrittsbalken(erledigt, total)} "
                f"{erledigt}/{total}",
            )

        start = time.perf_counter()
        rohdaten = await KurzarbeitRepository.mit_automatischen_zugangsdaten().laden_async(
            stichtag=stichtag, anzahl_monate=KURZARBEIT_ANZAHL_MONATE, fortschritt=_melden
        )
        dauer = timedelta(seconds=time.perf_counter() - start)
        anzahl_personen = len({p.mitarbeiter_id for pm in rohdaten.values() for p in pm})
        anzeige.aktualisieren(
            "Kurzarbeit-Rohdaten",
            f"Kurzarbeits-Rohdaten aus {len(rohdaten)} Monate(n) von {anzahl_personen} "
            f"Person(en) geladen (in {humanize.naturaldelta(dauer)})",
        )
        return bewertungen(rohdaten, rollenzuordnung=rollenzuordnung_automatisch())

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
        # Worker-Thread blockiert er nicht den Event-Loop, in dem gleichzeitig
        # Dashboard und Kurzarbeit-Rohdaten laufen. Mehrzeilenanzeige ist threadsicher
        # (siehe dort), _melden() darf also direkt aus dem Worker-Thread aufgerufen
        # werden.
        anmeldungsverlauf = await asyncio.to_thread(
            SchulungenRepository.mit_automatischen_zugangsdaten().anmeldungsverlauf_laden,
            anmeldungsverlauf_jahre,
            fortschritt=_melden,
        )
        dauer = timedelta(seconds=time.perf_counter() - start)
        fenster = anmeldungsverlauf.letzte(monate=ANMELDUNGEN_MONATE_FENSTER, stichtag=stichtag)
        anzeige.aktualisieren(
            "Anmeldungsverlauf",
            f"{len(fenster.anmeldungen)} Anmeldungen aus {len(fenster.monate)} Monaten geladen "
            f"(in {humanize.naturaldelta(dauer)})",
        )
        return fenster

    dashboard, kurzarbeit_ergebnisse, anmeldungsverlauf_fenster = await gleichzeitig(
        _dashboard_laden(), _kurzarbeit_laden(), _anmeldungsverlauf_laden()
    )
    return dashboard, kurzarbeit_ergebnisse, anmeldungsverlauf_fenster


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

# Titel aus DIAGRAMM_ERLAEUTERUNGEN, die eine Tabelle statt eines Diagramms sind (siehe
# diagrammtitel_und_figuren) - fuer die Export-Zusammenfassung, die Diagramme und
# Tabellen getrennt zaehlt, analog zu
# scripts/diagramme_exportieren.py::_export_zusammenfassung().
TABELLEN_TITEL = {"Umsatztabelle"}


def kontext_text(dashboard: _Dashboardauszug) -> str:
    """Kurzer Fließtext vor den Grafiken: Prognosehorizont, Bandbreite und ein
    etwaiger Kapazitätsengpass in Worten statt nur in den Diagrammen.

    Zwei Kennzahlen statt einer (Kollegen-Feedback: der frühere Text zeigte nur den
    simulierten Umsatz aus dem Bestand, weder als Umsatz noch als Gewinn erkennbar
    benannt, und ohne Schulungsanmeldungen/bereits gebuchte Beträge):

    - **Umsatzprognose**: ``prognose.summe()`` (die simulierte Bandbreite über den
      Horizont, inklusive der darin je Lauf eingebetteten ``gebucht()``-Untergrenze
      künftiger Horizontmonate, siehe ``domaene/simulation.py``) plus der im
      laufenden Stichtagsmonat bereits gebuchte Betrag (``basis`` - für den simulierten
      Anteil dieses Monats *nicht* mitgezählt, siehe ``tabellen.umsatztabelle``) plus
      die Schulungsanmeldungen des Horizonts - dieselbe Summe wie in der Spalte
      "Summe" der Umsatztabelle, nur über den ganzen Horizont statt je Monat.
    - **Gewinn**: dieselbe Summe abzüglich der Kostenprognose des Horizonts.

    Beide auf den Konfidenzniveaus 95 %/50 % (siehe ``domaene.prognose.KONFIDENZNIVEAUS``
    und CLAUDE.md) - ein höheres Niveau steht für ein niedrigeres, konservativeres
    Quantil (95 % ⇒ "mindestens dieser Betrag"), 50 % für den Median.

    Umsatz- und Gewinnzeile stehen dabei bewusst je auf einer eigenen Zeile, mit
    fettem Slack-mrkdwn-Label (``*...*``) davor - Kollegen-Feedback: beides in einem
    Fließtext war nicht auf den ersten Blick auseinanderzuhalten. Der Kapazitätssatz
    (falls vorhanden) folgt als dritte, eigene Zeile.
    """
    prognose = dashboard.prognose
    if not prognose.vorhanden:
        return prognose.begruendung

    horizont = prognose.horizontmonate()
    (von_jahr, von_monat), (bis_jahr, bis_monat) = horizont[0], horizont[-1]
    zeitraum = (
        f"{MONATSNAMEN[von_monat - 1]} {von_jahr}"
        if (von_jahr, von_monat) == (bis_jahr, bis_monat)
        else f"{MONATSNAMEN[von_monat - 1]} {von_jahr} bis {MONATSNAMEN[bis_monat - 1]} {bis_jahr}"
    )
    # summe() ist die Summe über den ganzen Horizont, kein Wert je Monat (Kollegen-
    # Feedback: der frühere Text ohne "je Monat" las sich wie ein Monatswert) - durch
    # die Anzahl Horizontmonate geteilt, um genau das klarzustellen.
    anzahl_monate = len(horizont)

    historie = dashboard.bestand.umsatzhistorie
    laufender = historie.laufender if historie is not None else None
    basis = laufender.umsatz if laufender is not None else Decimal("0")
    schulung_summe = dashboard.schulungsplan.summe(horizont)
    kosten_summe = dashboard.kostenplan.summe(horizont)

    gesamtumsatz = {
        niveau: basis + wert + schulung_summe for niveau, wert in prognose.summe().items()
    }
    gewinn = {niveau: wert - kosten_summe for niveau, wert in gesamtumsatz.items()}

    text = (
        f"*Umsatzprognose je Monat* ({zeitraum}): mindestens "
        f"{euro(gesamtumsatz[0.95] / anzahl_monate)}/Monat mit 95 % Sicherheit, im Median "
        f"rund {euro(gesamtumsatz[0.50] / anzahl_monate)}/Monat.\n"
        f"*Gewinn je Monat* (nach Kostenprognose): mindestens "
        f"{euro(gewinn[0.95] / anzahl_monate)}/Monat mit 95 % Sicherheit, im Median rund "
        f"{euro(gewinn[0.50] / anzahl_monate)}/Monat."
    )

    kapazitaet_anteil = prognose.kapazitaet_limitierend_anteil()
    if kapazitaet_anteil > 0:
        text += (
            f"\nIn {prozent(kapazitaet_anteil)} der simulierten Läufe war die "
            "Personalkapazität der limitierende Faktor, nicht die Nachfrage."
        )
    return text


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
    dashboard: _Dashboardauszug,
    kurzarbeit_ergebnisse: dict[Monat, Kurzarbeitsbewertung] | None,
    anmeldungsverlauf_fenster: Anmeldungsverlauf,
    *,
    gewinn_verlust_monate: int | None,
) -> list[tuple[str, go.Figure]]:
    """Titel und Figur je Diagramm, in der Reihenfolge des Posts.

    ``kurzarbeit_ergebnisse`` ``None`` (Baustein ausgeschaltet, siehe
    ``umsatzprognose.clockodo.kurzarbeit_aktiv``) lässt den entsprechenden Eintrag
    ganz entfallen, statt eine leere Grafik zu zeigen. ``anmeldungsverlauf_fenster``
    kommt bereits fertig geladen und auf das Anzeigefenster zugeschnitten herein
    (siehe :func:`_daten_laden_async`) - diese Funktion lädt selbst nichts mehr, damit
    Dashboard, Kurzarbeit-Rohdaten und Anmeldungsverlauf gleichzeitig statt erst
    nacheinander (hier vor dem eigentlichen Rendern) geladen werden können.
    """
    # mit_beschriftung=True nur hier: ein statischer Bildexport ohne Hover-Tooltip
    # braucht die Werte als Text, Notebooks und Webapp zeigen sie interaktiv per Hover.
    eintraege: list[tuple[str, go.Figure]] = [
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
    ]
    if kurzarbeit_ergebnisse is not None:
        eintraege.append(
            (
                "Kurzarbeitsbereitschaft je Monat",
                diagramme.kurzarbeit_grafik(kurzarbeit_ergebnisse, mit_beschriftung=True),
            )
        )
    eintraege += [
        ("Anmeldungen je Monat", diagramme.anmeldungsverlauf(anmeldungsverlauf_fenster)),
        (
            "Umsatztabelle",
            diagramme.tabelle_als_grafik("Umsatz je Monat", dashboard.umsatztabelle()),
        ),
    ]
    return eintraege


def _aktive_diagrammtitel(
    kurzarbeit_ergebnisse: dict[Monat, Kurzarbeitsbewertung] | None,
) -> list[str]:
    """Titel in Post-Reihenfolge, ohne Kurzarbeit wenn ausgeschaltet - dieselbe
    Reihenfolge wie :func:`diagrammtitel_und_figuren`, hier ohne den Umweg über
    tatsaechlich gerenderte Figuren (fuer :func:`post_text`, das ganz ohne
    Diagramm-Rendering auskommt)."""
    return [
        titel
        for titel in DIAGRAMM_ERLAEUTERUNGEN
        if kurzarbeit_ergebnisse is not None or titel != "Kurzarbeitsbereitschaft je Monat"
    ]


def post_text(
    dashboard: _Dashboardauszug,
    kurzarbeit_ergebnisse: dict[Monat, Kurzarbeitsbewertung] | None,
) -> str:
    """Der vollstaendige Text des Slack-Posts, unabhaengig von Diagrammen und Upload -
    dieselbe Funktion baut ihn fuer den echten Post (:func:`posten_async`) wie fuer die
    Kommandozeilen-Ausgabe (``--nur-text``, siehe :func:`main`)."""
    erlaeuterungen = "\n".join(
        f"• {titel}: {DIAGRAMM_ERLAEUTERUNGEN[titel]}"
        for titel in _aktive_diagrammtitel(kurzarbeit_ergebnisse)
    )
    kurzarbeit_absatz = (
        f"\n\n{kurzarbeit_erlaeuterung(kurzarbeit_ergebnisse)}"
        if kurzarbeit_ergebnisse is not None
        else ""
    )
    return (
        f"Wochenbericht Zahlen, Daten, Fakten - Stand {dashboard.stichtag:%d.%m.%Y}\n\n"
        f"{kontext_text(dashboard)}{kurzarbeit_absatz}\n\n"
        f"{erlaeuterungen}"
    )


async def _bilder_exportieren_async(
    titel_figuren: list[tuple[str, go.Figure]], verzeichnis: Path
) -> list[Path]:
    """Schreibt je Diagramm ein PNG, mit einem eigenen Export-Balken pro Datei (siehe
    :class:`Mehrzeilenanzeige`) - beschriftet mit dem Dateinamen relativ zum
    Aufrufenden Verzeichnis zur Erlaeuterung, was gerade geschrieben wird. Ersetzt
    durch denselben Pfad samt Exportdauer, sobald die Datei geschrieben ist.

    Ein Batch-Aufruf statt ``figur.write_image()`` je Bild: kaleido (>=1.0) startet
    sonst fuer jedes Bild eine eigene Chromium-Instanz neu - siehe
    ``scripts/diagramme_exportieren.py`` fuer denselben Fix. ``asyncio.to_thread()``,
    weil der Aufruf selbst synchron ist - im eigenen Worker-Thread blockiert er nicht
    den Event-Loop. Da kaleido dabei keinen Zwischenstand je Datei liefert, bleibt der
    Balken bis zum Ende des Batches unveraendert (kein Zwischenfortschritt ableitbar) -
    alle Zeilen werden deshalb gemeinsam ersetzt, sobald der Batch fertig ist.
    """
    # "/" im Titel ("Gewinn/Verlust je Monat") waere im Dateinamen ein Pfadtrenner -
    # der Slack-Titel bleibt davon unberuehrt, nur der lokale Dateiname wird bereinigt.
    bilder = [verzeichnis / f"{titel.replace('/', '-')}.png" for titel, _figur in titel_figuren]
    anzeigenamen = [str(relativer_pfad(bild)) for bild in bilder]
    anzeige = Mehrzeilenanzeige(
        anzeigenamen, vorlage="{name} exportieren " + fortschrittsbalken(0, 1)
    )

    start = time.perf_counter()
    await asyncio.to_thread(
        pio.write_images,
        fig=cast("list[dict[str, object] | go.Figure]", [figur for _titel, figur in titel_figuren]),
        file=cast("list[str | Path]", bilder),
        width=1400,
        height=800,
        scale=2,
    )
    dauer = timedelta(seconds=time.perf_counter() - start)
    for anzeigename in anzeigenamen:
        anzeige.aktualisieren(
            anzeigename, f"{anzeigename} exportiert (in {humanize.naturaldelta(dauer)})"
        )
    return bilder


def _export_zusammenfassung(titel: Sequence[str]) -> str:
    """Zaehlt Diagramme und Tabellen getrennt, z. B. ``"7 Diagramm(e) und 1
    Tabelle(n)"`` - nur die Tabellen-Zaehlung dazu, wenn tatsaechlich mindestens eine
    Tabelle dabei war. Analog zu
    ``scripts/diagramme_exportieren.py::_export_zusammenfassung()``, hier ohne das dort
    angehaengte Wort "exportiert", weil der Aufrufer noch "und an Slack gepostet"
    ergaenzt."""
    anzahl_tabellen = sum(1 for t in titel if t in TABELLEN_TITEL)
    anzahl_diagramme = len(titel) - anzahl_tabellen
    if anzahl_tabellen == 0:
        return f"{anzahl_diagramme} Diagramm(e)"
    return f"{anzahl_diagramme} Diagramm(e) und {anzahl_tabellen} Tabelle(n)"


async def posten_async(
    client: WebClient,
    kanal: str,
    dashboard: _Dashboardauszug,
    kurzarbeit_ergebnisse: dict[Monat, Kurzarbeitsbewertung] | None,
    anmeldungsverlauf_fenster: Anmeldungsverlauf,
    verzeichnis: Path,
    *,
    gewinn_verlust_monate: int | None,
) -> list[str]:
    if not _CHANNEL_ID_MUSTER.match(kanal):
        raise RuntimeError(
            f"{SLACK_CHANNEL_VAR}={kanal!r} sieht nicht nach einer Channel-/Conversation-ID "
            "aus (erwartet z. B. 'C0123456789' oder 'D0123456789'). Für einen DM-Test an "
            "sich selbst die ID der DM-Konversation verwenden (Slack: Konversation öffnen, "
            "„Copy link“ - der Teil nach der letzten '/'), nicht die eigene Mitglieds-ID."
        )

    titel_figuren = diagrammtitel_und_figuren(
        dashboard,
        kurzarbeit_ergebnisse,
        anmeldungsverlauf_fenster,
        gewinn_verlust_monate=gewinn_verlust_monate,
    )
    bilder = await _bilder_exportieren_async(titel_figuren, verzeichnis)

    # file_uploads statt einer Schleife aus einzelnen files_upload_v2-Aufrufen: so
    # haengen alle Bilder gemeinsam an einer Nachricht (initial_comment), statt je Bild
    # eine eigene Unternachricht im Thread zu erzeugen.
    client.files_upload_v2(
        channel=kanal,
        initial_comment=post_text(dashboard, kurzarbeit_ergebnisse),
        file_uploads=[
            {"file": str(bild), "title": titel}
            for (titel, _figur), bild in zip(titel_figuren, bilder, strict=True)
        ],
    )
    return [titel for titel, _figur in titel_figuren]


def _argumente() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--nur-text",
        action="store_true",
        help=(
            "Nur den Text des Slack-Posts auf der Kommandozeile ausgeben, statt ihn zu "
            "posten - ohne Diagramm-Rendering, ohne Slack-Zugangsdaten."
        ),
    )
    return parser.parse_args()


def main() -> None:
    argumente = _argumente()

    horizont_monate = _optionale_ganzzahl(HORIZONT_MONATE_VAR, STANDARD_HORIZONT_MONATE)
    gewinn_verlust_monate = _optionale_ganzzahl(
        GEWINN_VERLUST_MONATE_VAR, STANDARD_GEWINN_VERLUST_MONATE
    )
    stichtag = date.today()

    dashboard, kurzarbeit_ergebnisse, anmeldungsverlauf_fenster = synchron(
        _daten_laden_async(
            stichtag=stichtag,
            horizont_monate=horizont_monate,
            mit_kurzarbeit=kurzarbeit_aktiv(),
            mit_anmeldungsverlauf=not argumente.nur_text,
        )
    )

    # Die Leerzeile trennt die (auf stderr geschriebene) Ladeanzeige sichtbar vom
    # Folgenden - dem Post-Text bei --nur-text, den Export-Balken sonst.
    print("Daten geladen und simuliert.\n")

    if argumente.nur_text:
        print(post_text(dashboard, kurzarbeit_ergebnisse))
        return

    client = WebClient(token=_umgebungsvariable(SLACK_TOKEN_VAR))
    kanal = _umgebungsvariable(SLACK_CHANNEL_VAR)

    with tempfile.TemporaryDirectory() as verzeichnis:
        assert anmeldungsverlauf_fenster is not None  # mit_anmeldungsverlauf=True oben
        titel = synchron(
            posten_async(
                client,
                kanal,
                dashboard,
                kurzarbeit_ergebnisse,
                anmeldungsverlauf_fenster,
                Path(verzeichnis),
                gewinn_verlust_monate=gewinn_verlust_monate,
            )
        )
    print(f"{_export_zusammenfassung(titel)} exportiert und an Slack gepostet")


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
