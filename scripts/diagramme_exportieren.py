"""Dashboard-Diagramme über die Kommandozeile exportieren - für Aufrufer ohne Jupyter.

    uv run python scripts/diagramme_exportieren.py                            # alle, als PNG
    uv run python scripts/diagramme_exportieren.py --format html              # alle, als HTML
    uv run python scripts/diagramme_exportieren.py --diagramm umsatzverlauf --diagramm kennzahlen
    uv run python scripts/diagramme_exportieren.py -o export --horizont-monate 1

Lädt den Bestand wie die Notebooks (``Dashboard.laden()``) und schreibt dieselben
Diagramme, die dort gezeigt werden, als Dateien in ein Verzeichnis. PNG- und
SVG-Export laufen wie im Wochenbericht (``scripts/wochenbericht.py``) über
``kaleido`` (``[project.optional-dependencies.bericht]``); HTML kommt ohne
zusätzliche Abhängigkeit aus, ist dafür aber nur im Browser interaktiv statt als
eigenständige Bilddatei nutzbar.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import plotly.io as pio

from umsatzprognose import Dashboard

STANDARD_FORMAT = "png"
FORMATE = ("png", "svg", "html")

# Name auf der Kommandozeile -> Dashboard-Methode, die die Figur liefert. Deckt alle
# Grafik-Methoden aus den drei Notebooks ab (siehe deren Zellen), nicht nur die fuenf
# aus scripts/wochenbericht.py.
DIAGRAMME = {
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


def _argumente(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dashboard-Diagramme als Dateien exportieren.")
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
        choices=sorted(DIAGRAMME),
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
        help="Prognosehorizont in Monaten für die Simulation (Standard: 3).",
    )
    return parser.parse_args(argv)


def exportieren(
    dashboard: Dashboard, ausgabeverzeichnis: Path, ausgabeformat: str, namen: list[str]
) -> list[Path]:
    """Je Name aus ``DIAGRAMME`` eine Datei schreiben, gibt die geschriebenen Pfade zurück."""
    ausgabeverzeichnis.mkdir(parents=True, exist_ok=True)
    figuren = [DIAGRAMME[name](dashboard) for name in namen]
    pfade = [ausgabeverzeichnis / f"{name}.{ausgabeformat}" for name in namen]
    if ausgabeformat == "html":
        for figur, pfad in zip(figuren, pfade, strict=True):
            figur.write_html(pfad)
    else:
        # Ein Batch-Aufruf statt figur.write_image() je Diagramm: kaleido (>=1.0) startet
        # sonst für jedes einzelne Bild eine eigene Chromium-Instanz neu, was den Export
        # mehrerer Diagramme spürbar verlangsamt - hier ein gemeinsamer Browserprozess.
        pio.write_images(fig=figuren, file=pfade, width=1400, height=800, scale=2)
    return pfade


def main(argv: list[str]) -> int:
    args = _argumente(argv)

    dashboard = Dashboard.laden(stichtag=args.stichtag, horizont_monate=args.horizont_monate)
    dashboard.simuliere(monate=args.horizont_monate)

    namen = sorted(set(args.diagramme)) if args.diagramme else sorted(DIAGRAMME)
    pfade = exportieren(dashboard, args.ausgabeverzeichnis, args.format, namen)

    print(f"{len(pfade)} Diagramm(e) exportiert nach {args.ausgabeverzeichnis}:")
    for pfad in pfade:
        print(f"  {pfad}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
