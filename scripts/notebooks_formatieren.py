"""Notebooks bereinigen - für alle oder einzelne mitgereichte Dateien.

    uv run python scripts/notebooks_formatieren.py                          # alle Notebooks
    uv run python scripts/notebooks_formatieren.py notebooks/01_dashboard.ipynb
    uv run python scripts/notebooks_formatieren.py --no-einklappen          # nur Ausgaben löschen
    uv run python scripts/notebooks_formatieren.py --no-ausgaben-loeschen   # nur einklappen

Dieselbe Bereinigung wie im Pre-Commit-Hook (``.githooks/pre-commit``): Zellausgaben/
Ausführungszähler werden entfernt und Code-Zellen ohne eingeklappte Quelltextanzeige
eingeklappt (siehe ``notebook_ausgaben.py``) - beide Aktionen standardmäßig an, je
einzeln über ``--no-ausgaben-loeschen``/``--no-einklappen`` abschaltbar. Hier aber
unabhängig von einem Commit aufrufbar - etwa nach interaktivem Arbeiten in Jupyter,
bevor überhaupt etwas gestaged wurde. Braucht dafür (anders als der Hook selbst, der
bewusst ohne Zusatzpaket auskommt) das ``notebook``-Extra fürs Fortschrittsanzeige
(``tqdm``) - wer interaktiv in Jupyter arbeitet, hat es ohnehin schon synchronisiert.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent))
from notebook_ausgaben import alle_notebooks, code_zellen_einklappen, zellausgaben_entfernen


def _argumente(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Zellausgaben aus Notebooks entfernen und/oder ihre Code-Zellen einklappen."
    )
    parser.add_argument(
        "notebooks",
        nargs="*",
        type=Path,
        help="Nur diese Notebook-Dateien prüfen (Standard: alle im Repository).",
    )
    parser.add_argument(
        "--ausgaben-loeschen",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Zellausgaben und Ausführungszähler entfernen (Standard: an).",
    )
    parser.add_argument(
        "--einklappen",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Code-Zellen ohne eingeklappte Quelltextanzeige einklappen (Standard: an).",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _argumente(argv)
    if not args.ausgaben_loeschen and not args.einklappen:
        print(
            "Nichts zu tun: --no-ausgaben-loeschen und --no-einklappen sind beide gesetzt.",
            file=sys.stderr,
        )
        return 0

    pfade = args.notebooks or alle_notebooks()

    fehlende = [pfad for pfad in pfade if not pfad.exists()]
    if fehlende:
        for pfad in fehlende:
            print(f"{pfad}: nicht gefunden", file=sys.stderr)
        return 1

    bereinigt = []
    with tqdm(total=len(pfade), desc="Notebooks prüfen", leave=False) as balken:
        for pfad in pfade:
            balken.set_description(f"{pfad.name} prüfen")
            # Beide Pruefungen laufen unabhaengig vom Kurzschluss von `or` - eine
            # entfernte Zellausgabe soll das Einklappen nicht ueberspringen.
            ausgaben_entfernt = args.ausgaben_loeschen and zellausgaben_entfernen(pfad)
            eingeklappt = args.einklappen and code_zellen_einklappen(pfad)
            if ausgaben_entfernt or eingeklappt:
                bereinigt.append(pfad)
                # alle_notebooks() liefert absolute Pfade (siehe NOTEBOOKS_VERZEICHNIS in
                # notebook_ausgaben.py) - fuer die Anzeige genuegt der relative Pfad.
                balken.write(f"  {os.path.relpath(pfad)} bereinigt")
            balken.update(1)

    if bereinigt:
        print(f"{len(bereinigt)} Notebook(s) bereinigt.")
    else:
        # Nennt nur die tatsaechlich angeforderten Aktionen - sonst wuerde die Meldung
        # bei z. B. --no-einklappen faelschlich auch ausgeklappte Code-Zellen
        # ausschliessen, obwohl darauf gar nicht geprueft wurde.
        gepruefte_aktionen = [
            text
            for aktiv, text in (
                (args.ausgaben_loeschen, "Zellausgaben"),
                (args.einklappen, "ausgeklappten Code-Zellen"),
            )
            if aktiv
        ]
        print(f"Keine {' oder '.join(gepruefte_aktionen)} gefunden.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
