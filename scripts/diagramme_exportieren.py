"""Diagramme über die Kommandozeile exportieren - für Aufrufer ohne Jupyter.

    uv run python scripts/diagramme_exportieren.py                            # alle, als PNG
    uv run python scripts/diagramme_exportieren.py --format html              # alle, als HTML
    uv run python scripts/diagramme_exportieren.py --diagramm umsatzverlauf --diagramm kennzahlen
    uv run python scripts/diagramme_exportieren.py -o export --horizont-monate 1
    uv run python scripts/diagramme_exportieren.py --diagramm anmeldungsverlauf --monate-fenster 6

Lädt den Bestand wie die Notebooks (``Dashboard.laden()``) und schreibt dieselben
Diagramme, die dort gezeigt werden, als Dateien in ein Verzeichnis. PNG- und
SVG-Export laufen wie im Wochenbericht (``scripts/wochenbericht.py``) über
``kaleido`` (``[project.optional-dependencies.bericht]``); HTML kommt ohne
zusätzliche Abhängigkeit aus, ist dafür aber nur im Browser interaktiv statt als
eigenständige Bilddatei nutzbar.

Der Anmeldungsverlauf (``notebooks/03_schulungsanmeldungen.ipynb``) hängt anders als
die übrigen Diagramme nicht am ``Dashboard`` der Umsatzprognose, sondern lädt
eigenständig über ``SchulungenRepository`` - deshalb ein eigener Ladepfad
(:func:`_anmeldungsverlauf_figur`) statt eines Eintrags in ``DIAGRAMME_DASHBOARD``, nur
geladen, wenn ``anmeldungsverlauf`` tatsächlich angefordert ist.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import plotly.graph_objects as go

import plotly.io as pio
from tqdm import tqdm

from umsatzprognose import Dashboard
from umsatzprognose.darstellung import diagramme
from umsatzprognose.schulungen import SchulungenRepository
from umsatzprognose.util import aus_ordnung, ordnung

STANDARD_FORMAT = "png"
FORMATE = ("png", "svg", "html")
STANDARD_MONATE_FENSTER = 13  # wie notebooks/03_schulungsanmeldungen.ipynb

DIAGRAMM_ANMELDUNGSVERLAUF = "anmeldungsverlauf"

# Dieselbe Standard-Zuordnung wie in notebooks/03_schulungsanmeldungen.ipynb - dort ist
# sie die eigentlich vorgesehene Stelle zum Anpassen, hier nur ein Startwert fuer den
# Kommandozeilen-Export ohne Notebook.
STANDARD_KATEGORIEN: dict[str, list[str]] = {
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
        "AI for Scrum Masters",
    ],
    "Kanban": [
        "KCP",
        "KMM",
        "KSD",
        "KSI",
        "KSI 2-tägig",
        "KSI 3-tägig",
        "SBK",  # "Scrum better with Kanban"
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

# Diese vier kennen "mit_beschriftung" (siehe deren Dashboard-Methoden) - die uebrigen
# (kennzahlen, restvolumen-je-projekt, kapazitaet-*, auslastung-je-mitarbeiter) haben
# den Wert entweder schon fest eingezeichnet oder brauchen ihn nicht.
MIT_BESCHRIFTUNG_FAEHIG = {
    "umsatzverlauf",
    "gewinn-verlust-monatlich",
    "gewinn-verlust-je-jahr",
    "umsatzrendite-kumuliert",
}

ALLE_DIAGRAMME = sorted({*DIAGRAMME_DASHBOARD, DIAGRAMM_ANMELDUNGSVERLAUF})


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
            f"'{DIAGRAMM_ANMELDUNGSVERLAUF}' (Standard: {STANDARD_MONATE_FENSTER})."
        ),
    )
    return parser.parse_args(argv)


def _anmeldungsverlauf_figur(*, stichtag: date, monate_fenster: int) -> go.Figure:
    """Laedt den Anmeldungsverlauf eigenstaendig (siehe Moduldocstring) und liefert die Figur.

    Die benoetigten Jahrgaenge ergeben sich aus ``stichtag`` und ``monate_fenster`` -
    genau wie ``schulungen._benoetigte_jahre`` fuer den Prognosehorizont, hier nur
    rueckwaerts statt vorwaerts gezaehlt.
    """
    ende = ordnung(stichtag.year, stichtag.month)
    start_jahr = aus_ordnung(ende - (monate_fenster - 1))[0]
    verlauf = SchulungenRepository.mit_automatischen_zugangsdaten().anmeldungsverlauf_laden(
        range(start_jahr, stichtag.year + 1)
    )
    fenster = verlauf.letzte(monate=monate_fenster, stichtag=stichtag)
    return diagramme.anmeldungsverlauf(fenster, STANDARD_KATEGORIEN)


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


def _platzhalter_balken(desc: str, *, position: int) -> tqdm:
    """Eine eigene Zeile fuer einen von mehreren gleichzeitig ausstehenden Schritten -
    Platzhalter, bis er fertig ist, siehe :func:`_balken_ersetzen`.

    Wie ``rustup update`` es fuer mehrere gleichzeitig synchronisierte Toolchains macht:
    alle ausstehenden Schritte stehen von Anfang an da, jeder in seiner eigenen Zeile;
    ihr Balken verschwindet zugunsten des fertigen Textes, sobald der jeweilige Schritt
    da ist - unabhaengig davon, ob die Schritte technisch nacheinander oder gleichzeitig
    ablaufen (siehe Aufrufer).
    """
    return tqdm(total=1, desc=desc, bar_format="{desc} {bar}", position=position, leave=True)


def _balken_ersetzen(balken: tqdm, text: str) -> None:
    """Den Platzhalter-Balken eines Schritts durch seinen fertigen Text ersetzen."""
    balken.bar_format = "{desc}"
    balken.set_description_str(text)
    balken.update(1)
    balken.close()


def _figuren(
    namen: list[str],
    *,
    stichtag: date | None,
    horizont_monate: int,
    monate_fenster: int,
    ausgabeformat: str,
) -> dict[str, go.Figure]:
    """Je angefordertem Namen die fertige Figur - laedt Dashboard bzw. Anmeldungsverlauf
    nur, wenn tatsaechlich ein Diagramm der jeweiligen Quelle angefordert ist.

    ``html`` bleibt interaktiv (Hover zeigt den Wert), ``png``/``svg`` sind statische
    Bilder ohne Hover - wie im Wochenbericht (``scripts/wochenbericht.py``) bekommen die
    dafuer geeigneten Diagramme dort zusaetzlich den Wert als Text.
    """
    figuren: dict[str, go.Figure] = {}
    mit_beschriftung = ausgabeformat != "html"

    dashboard_namen = [name for name in namen if name in DIAGRAMME_DASHBOARD]
    if dashboard_namen:
        # Bestand und Schulungsplan laufen in Dashboard.laden_async() gleichzeitig,
        # Kostenplan und Auslastung danach ebenfalls gleichzeitig (siehe dort). Alle vier
        # stehen hier trotzdem von Anfang an als ausstehende Schritte da (siehe
        # _platzhalter_balken), damit sichtbar ist, was insgesamt noch kommt - jede Zeile
        # wird ersetzt, sobald ihr Schritt tatsaechlich fertig ist, unabhaengig von der
        # Reihenfolge. ``fortschritt`` traegt zusaetzlich die Verlaufscache-Meldungen
        # (Vereinheitlichung statt eines eigenen cache_fortschritt) sowie die
        # Abschlussmeldung der Simulation - _melden erkennt sie daran, dass ihr Text zu
        # keinem der vier bekannten Muster passt, und gibt sie einfach als Zeile aus.
        offene_schritte = {
            name: _platzhalter_balken(f"{name} laden", position=i)
            for i, name in enumerate(SCHRITTE_DASHBOARD_LADEN)
        }

        def _melden(text: str) -> None:
            for name, muster in _SCHRITT_MUSTER.items():
                if name in offene_schritte and muster in text:
                    _balken_ersetzen(offene_schritte.pop(name), text)
                    return
            tqdm.write(text)

        dashboard = Dashboard.laden(
            stichtag=stichtag,
            horizont_monate=horizont_monate,
            fortschritt=_melden,
        )
        dashboard.simuliere(monate=horizont_monate, fortschritt=_melden)
        for name in dashboard_namen:
            kwargs = (
                {"mit_beschriftung": mit_beschriftung} if name in MIT_BESCHRIFTUNG_FAEHIG else {}
            )
            figuren[name] = DIAGRAMME_DASHBOARD[name](dashboard, **kwargs)

    if DIAGRAMM_ANMELDUNGSVERLAUF in namen:
        figuren[DIAGRAMM_ANMELDUNGSVERLAUF] = _anmeldungsverlauf_figur(
            stichtag=stichtag or date.today(), monate_fenster=monate_fenster
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
