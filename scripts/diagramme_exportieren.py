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
über denselben Weg (``exportieren()`` unterscheidet nicht zwischen Diagramm- und
Tabellen-Figuren, beides ist am Ende ein ``go.Figure``).

Der Anmeldungsverlauf und die Anmeldungstabelle (``notebooks/03_schulungsanmeldungen.
ipynb``) hängen anders als die übrigen Diagramme/Tabellen nicht am ``Dashboard`` der
Umsatzprognose, sondern laden eigenständig über ``SchulungenRepository`` - deshalb ein
eigener Ladepfad (:func:`_anmeldungsverlauf_laden`) statt eines Eintrags in
``DIAGRAMME_DASHBOARD``/``TABELLEN_DASHBOARD``, nur geladen, wenn eines von beiden
tatsächlich angefordert ist. ``KATEGORIEN`` deckt sich mit derselben, von Hand
gepflegten Zuordnung in ``webapp/app.py``/``notebooks/03_schulungsanmeldungen.ipynb``
(siehe CLAUDE.md) - frei konfigurierbar, deshalb bewusst hier dupliziert statt im Paket.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    import pandas as pd
    import plotly.graph_objects as go

    from umsatzprognose.domaene.anmeldung import Anmeldungsverlauf

import plotly.io as pio
from tqdm import tqdm

from umsatzprognose import Dashboard
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


def _anmeldungsverlauf_laden(*, stichtag: date, monate_fenster: int) -> Anmeldungsverlauf:
    """Laedt den Anmeldungsverlauf eigenstaendig (siehe Moduldocstring), auf das
    angefragte Fenster zugeschnitten - fuer sowohl den Anmeldungsverlauf als auch die
    Anmeldungstabelle, ohne die Jahrgaenge zweimal zu laden, wenn beide angefordert sind.

    Die benoetigten Jahrgaenge ergeben sich aus ``stichtag`` und ``monate_fenster`` -
    genau wie ``schulungen._benoetigte_jahre`` fuer den Prognosehorizont, hier nur
    rueckwaerts statt vorwaerts gezaehlt. Der Balken fuellt sich dabei sichtbar ueber
    echte Zwischenschritte, ein Jahr nach dem anderen (siehe Docstring von
    ``anmeldungsverlauf_laden``), ohne dafuer je Jahr eine eigene Zeile zu hinterlassen.
    """
    ende = ordnung(stichtag.year, stichtag.month)
    start_jahr = aus_ordnung(ende - (monate_fenster - 1))[0]
    jahre = list(range(start_jahr, stichtag.year + 1))
    with tqdm(total=len(jahre), desc="Anmeldungsverlauf laden", leave=False) as balken:

        def _melden(text: str) -> None:
            balken.update(1)

        verlauf = SchulungenRepository.mit_automatischen_zugangsdaten().anmeldungsverlauf_laden(
            jahre, fortschritt=_melden
        )
    return verlauf.letzte(monate=monate_fenster, stichtag=stichtag)


SCHRITTE_DASHBOARD_LADEN = ("Bestand", "Schulungsplan", "Kostenplan", "Auslastung")
# Ein je Schritt eindeutiger Textbaustein aus dessen fertiger Statuszeile (siehe
# Dashboard.laden_async) - daran erkennt _melden, welchem der vier Platzhalter-Balken
# eine ankommende fortschritt()-Meldung zuzuordnen ist. Verlaufscache-Meldungen (siehe
# cache.gecacht_oder_neu) passen auf keinen dieser Bausteine und werden stattdessen
# einfach als zusaetzliche Zeile ausgegeben - das ist die Vereinheitlichung von
# fortschritt und dem frueheren eigenen cache_fortschritt in Dashboard.laden().
_SCHRITT_MUSTER = {
    "Bestand": "Bestand geladen",
    "Schulungsplan": "Schulung(en) geladen",
    "Kostenplan": "Kostenprognose geladen",
    "Auslastung": "Auslastungsmonat(e) geladen",
}

# Bestand meldet sich zusaetzlich zwischendurch, je einem seiner fuenf gleichzeitigen
# Zweige (siehe BestandRepository.laden_async) - ein Tick je Zweig auf dem eigenen
# Platzhalter-Balken (total=6: fuenf Zwischenschritte plus der Abschluss durch
# _balken_ersetzen) statt einer eigenen Zeile je Zwischenschritt.
_BESTAND_ZWISCHENSCHRITTE = frozenset(
    {
        "Kunden geladen",
        "Personen geladen",
        "Projekt-Rohdaten geladen",
        "Umsatzhistorie geladen",
        "Verbrauchsverlauf geladen",
    }
)
_SCHRITT_TOTAL = {"Bestand": len(_BESTAND_ZWISCHENSCHRITTE) + 1, "Kostenplan": 1}

# Kostenplan meldet sich ebenfalls zwischendurch, je verarbeitetem Jahr (siehe
# KostenRepository.laden) - die Jahresanzahl ist vorher nicht bekannt, deshalb nur die
# Beschreibung des Platzhalter-Balkens statt eines echten Prozentanteils.
_KOSTENPLAN_ZWISCHENSCHRITT_MUSTER = "Kostenposten bis"


def _platzhalter_balken(desc: str, *, position: int, total: int = 1) -> tqdm:
    """Eine eigene Zeile fuer einen von mehreren gleichzeitig ausstehenden Schritten -
    Platzhalter, bis er fertig ist, siehe :func:`_balken_ersetzen`.

    Wie ``rustup update`` es fuer mehrere gleichzeitig synchronisierte Toolchains macht:
    alle ausstehenden Schritte stehen von Anfang an da, jeder in seiner eigenen Zeile;
    ihr Balken verschwindet zugunsten des fertigen Textes, sobald der jeweilige Schritt
    da ist - unabhaengig davon, ob die Schritte technisch nacheinander oder gleichzeitig
    ablaufen (siehe Aufrufer). ``total`` > 1 nur fuer Bestand - sichtbarer Fortschritt
    durch dessen fuenf Zwischenschritte, siehe :data:`_SCHRITT_TOTAL`.
    """
    return tqdm(total=total, desc=desc, bar_format="{desc} {bar}", position=position, leave=True)


def _balken_ersetzen(balken: tqdm, text: str) -> None:
    """Den Platzhalter-Balken eines Schritts durch seinen fertigen Text ersetzen."""
    balken.bar_format = "{desc}"
    balken.set_description_str(text)
    balken.update(1)
    balken.close()


def _dashboard_mit_fortschritt(*, stichtag: date | None, horizont_monate: int) -> Dashboard:
    """Laedt das Dashboard und simuliert direkt danach, mit denselben vier
    Platzhalterbalken wie ``notebooks/setup.py`` (siehe dort) - eigene Funktion, damit
    ``_figuren()`` nur noch entscheidet, was gebaut wird, nicht wie geladen wird.

    Bestand und Schulungsplan laufen in ``Dashboard.laden_async()`` gleichzeitig,
    Kostenplan und Auslastung danach ebenfalls gleichzeitig (siehe dort). Alle vier
    stehen hier trotzdem von Anfang an als ausstehende Schritte da (siehe
    ``_platzhalter_balken``), damit sichtbar ist, was insgesamt noch kommt - jede Zeile
    wird ersetzt, sobald ihr Schritt tatsaechlich fertig ist, unabhaengig von der
    Reihenfolge. ``fortschritt`` traegt zusaetzlich die Verlaufscache-Meldungen
    (Vereinheitlichung statt eines eigenen ``cache_fortschritt``) sowie die
    Abschlussmeldung der Simulation - ``_melden`` erkennt sie daran, dass ihr Text zu
    keinem der vier bekannten Muster passt, und gibt sie einfach als Zeile aus.
    """
    offene_schritte = {
        name: _platzhalter_balken(f"{name} laden", position=i, total=_SCHRITT_TOTAL.get(name, 1))
        for i, name in enumerate(SCHRITTE_DASHBOARD_LADEN)
    }

    def _melden(text: str) -> None:
        for name, muster in _SCHRITT_MUSTER.items():
            if name in offene_schritte and muster in text:
                _balken_ersetzen(offene_schritte.pop(name), text)
                return
        if "Bestand" in offene_schritte and text in _BESTAND_ZWISCHENSCHRITTE:
            offene_schritte["Bestand"].update(1)
            return
        if "Kostenplan" in offene_schritte and _KOSTENPLAN_ZWISCHENSCHRITT_MUSTER in text:
            offene_schritte["Kostenplan"].set_description_str(f"Kostenplan laden: {text}")
            return
        tqdm.write(text)

    dashboard = Dashboard.laden(
        stichtag=stichtag,
        horizont_monate=horizont_monate,
        fortschritt=_melden,
    )
    dashboard.simuliere(monate=horizont_monate, fortschritt=_melden)
    return dashboard


def _figuren(
    namen: list[str],
    *,
    stichtag: date | None,
    horizont_monate: int,
    monate_fenster: int,
    ausgabeformat: str,
) -> dict[str, go.Figure]:
    """Je angefordertem Namen die fertige Figur - laedt Dashboard bzw. Anmeldungsverlauf
    nur, wenn tatsaechlich ein Diagramm oder eine Tabelle der jeweiligen Quelle
    angefordert ist.

    ``html`` bleibt interaktiv (Hover zeigt den Wert), ``png``/``svg`` sind statische
    Bilder ohne Hover - wie im Wochenbericht (``scripts/wochenbericht.py``) bekommen die
    dafuer geeigneten Diagramme dort zusaetzlich den Wert als Text. Tabellen
    (``TABELLEN_DASHBOARD``, ``anmeldungstabelle``) zeigen ihre Werte ohnehin schon als
    Text in der Tabelle - ``mit_beschriftung`` betrifft nur Diagramme.
    """
    figuren: dict[str, go.Figure] = {}
    mit_beschriftung = ausgabeformat != "html"

    dashboard_namen = [name for name in namen if name in DIAGRAMME_DASHBOARD]
    tabellen_namen = [name for name in namen if name in TABELLEN_DASHBOARD]
    if dashboard_namen or tabellen_namen:
        dashboard = _dashboard_mit_fortschritt(stichtag=stichtag, horizont_monate=horizont_monate)
        for name in dashboard_namen:
            kwargs = (
                {"mit_beschriftung": mit_beschriftung} if name in MIT_BESCHRIFTUNG_FAEHIG else {}
            )
            figuren[name] = DIAGRAMME_DASHBOARD[name](dashboard, **kwargs)
        for name in tabellen_namen:
            methode, titel = TABELLEN_DASHBOARD[name]
            figuren[name] = diagramme.tabelle_als_grafik(titel, methode(dashboard))

    anmeldungs_namen = [
        name for name in (DIAGRAMM_ANMELDUNGSVERLAUF, DIAGRAMM_ANMELDUNGSTABELLE) if name in namen
    ]
    if anmeldungs_namen:
        fenster = _anmeldungsverlauf_laden(
            stichtag=stichtag or date.today(), monate_fenster=monate_fenster
        )
        if DIAGRAMM_ANMELDUNGSVERLAUF in anmeldungs_namen:
            figuren[DIAGRAMM_ANMELDUNGSVERLAUF] = diagramme.anmeldungsverlauf(fenster)
        if DIAGRAMM_ANMELDUNGSTABELLE in anmeldungs_namen:
            figuren[DIAGRAMM_ANMELDUNGSTABELLE] = diagramme.tabelle_als_grafik(
                "Anmeldungen je Monat und Kategorie",
                tabellen.anmeldungstabelle(fenster, KATEGORIEN),
            )

    return figuren


def exportieren(
    figuren: dict[str, go.Figure], namen: list[str], ausgabeverzeichnis: Path, ausgabeformat: str
) -> list[Path]:
    """Je Name aus ``namen`` eine Datei schreiben, gibt die geschriebenen Pfade zurück.

    Zeigt vorne an, welche Datei gerade geschrieben wird. Bei ``html`` geschieht das
    Schreiben der Reihe nach - ein einzelner Balken genuegt, seine Beschriftung wechselt
    vor jeder Datei. Bei ``png``/``svg`` schreibt kaleido dagegen alle Bilder in einem
    gemeinsamen Batch-Aufruf zugleich (siehe Kommentar unten) und liefert dabei keinen
    Zwischenstand je Datei - stattdessen bekommt jede Datei ihre eigene Zeile, zunaechst
    als Platzhalter, nach dem Batch durch ihren fertigen Pfad ersetzt (wie ``rustup
    update`` es fuer mehrere gleichzeitig synchronisierte Toolchains zeigt).
    """
    ausgabeverzeichnis.mkdir(parents=True, exist_ok=True)
    geordnete_figuren = [figuren[name] for name in namen]
    pfade = [ausgabeverzeichnis / f"{name}.{ausgabeformat}" for name in namen]

    if ausgabeformat == "html":
        with tqdm(total=len(pfade), desc="Diagramme exportieren", leave=False) as balken:
            for figur, pfad in zip(geordnete_figuren, pfade, strict=True):
                balken.set_description(f"{pfad.name} schreiben")
                figur.write_html(pfad)
                balken.write(f"  {pfad}")
                balken.update(1)
    else:
        # Ein Batch-Aufruf statt figur.write_image() je Diagramm: kaleido (>=1.0) startet
        # sonst für jedes einzelne Bild eine eigene Chromium-Instanz neu, was den Export
        # mehrerer Diagramme spürbar verlangsamt - hier ein gemeinsamer Browserprozess.
        datei_balken = [
            _platzhalter_balken(f"  {pfad}", position=i) for i, pfad in enumerate(pfade)
        ]
        pio.write_images(fig=geordnete_figuren, file=pfade, width=1400, height=800, scale=2)
        for balken, pfad in zip(datei_balken, pfade, strict=True):
            _balken_ersetzen(balken, f"  {pfad}")
    return pfade


def main(argv: list[str]) -> int:
    args = _argumente(argv)

    namen = sorted(set(args.diagramme)) if args.diagramme else ALLE_DIAGRAMME
    figuren = _figuren(
        namen,
        stichtag=args.stichtag,
        horizont_monate=args.horizont_monate,
        monate_fenster=args.monate_fenster,
        ausgabeformat=args.format,
    )
    print("Daten geladen.")

    print("\nDiagramm(e) exportieren:")
    pfade = exportieren(figuren, namen, args.ausgabeverzeichnis, args.format)

    print(f"{len(pfade)} Diagramm(e) exportiert nach {args.ausgabeverzeichnis}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
