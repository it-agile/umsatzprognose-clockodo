"""Zellausgaben aus Notebooks löschen - für alle oder einzelne mitgereichte Dateien.

    uv run python scripts/notebook_ausgaben_loeschen.py                # alle Notebooks
    uv run python scripts/notebook_ausgaben_loeschen.py notebooks/01_dashboard.ipynb

Dieselbe Bereinigung wie im Pre-Commit-Hook (``.githooks/pre-commit``), hier aber
unabhängig von einem Commit aufrufbar - etwa nach interaktivem Arbeiten in Jupyter,
bevor überhaupt etwas gestaged wurde. Braucht dafür (anders als der Hook selbst, der
bewusst ohne Zusatzpaket auskommt) das ``notebook``-Extra fürs Fortschrittsanzeige
(``tqdm``) - wer interaktiv in Jupyter arbeitet, hat es ohnehin schon synchronisiert.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent))
from notebook_ausgaben import alle_notebooks, zellausgaben_entfernen


def main(argv: list[str]) -> int:
    pfade = [Path(arg) for arg in argv] if argv else alle_notebooks()

    fehlende = [pfad for pfad in pfade if not pfad.exists()]
    if fehlende:
        for pfad in fehlende:
            print(f"{pfad}: nicht gefunden", file=sys.stderr)
        return 1

    bereinigt = []
    with tqdm(total=len(pfade), desc="Notebooks prüfen", leave=False) as balken:
        for pfad in pfade:
            balken.set_description(f"{pfad.name} prüfen")
            if zellausgaben_entfernen(pfad):
                bereinigt.append(pfad)
                # alle_notebooks() liefert absolute Pfade (siehe NOTEBOOKS_VERZEICHNIS in
                # notebook_ausgaben.py) - fuer die Anzeige genuegt der relative Pfad.
                balken.write(f"  {os.path.relpath(pfad)} bereinigt")
            balken.update(1)

    if bereinigt:
        print(f"{len(bereinigt)} Notebook(s) von Zellausgaben bereinigt.")
    else:
        print("Keine Zellausgaben gefunden.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
