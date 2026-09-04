"""Zellausgaben aus Notebooks löschen - für alle oder einzelne mitgereichte Dateien.

    uv run python scripts/notebook_ausgaben_loeschen.py                # alle Notebooks
    uv run python scripts/notebook_ausgaben_loeschen.py notebooks/01_dashboard.ipynb

Dieselbe Bereinigung wie im Pre-Commit-Hook (``.githooks/pre-commit``), hier aber
unabhängig von einem Commit aufrufbar - etwa nach interaktivem Arbeiten in Jupyter,
bevor überhaupt etwas gestaged wurde.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from notebook_ausgaben import alle_notebooks, zellausgaben_entfernen


def main(argv: list[str]) -> int:
    pfade = [Path(arg) for arg in argv] if argv else alle_notebooks()

    fehlende = [pfad for pfad in pfade if not pfad.exists()]
    if fehlende:
        for pfad in fehlende:
            print(f"{pfad}: nicht gefunden", file=sys.stderr)
        return 1

    bereinigt = [pfad for pfad in pfade if zellausgaben_entfernen(pfad)]

    if bereinigt:
        print("Zellausgaben entfernt aus: " + ", ".join(str(pfad) for pfad in bereinigt))
    else:
        print("Keine Zellausgaben gefunden.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
