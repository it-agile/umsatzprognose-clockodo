"""Gemeinsame Logik zum Entfernen von Zellausgaben aus Notebook-Dateien.

Reine Standardbibliothek - genutzt sowohl vom Pre-Commit-Hook (``.githooks/pre-commit``,
läuft ohne ``uv sync --extra notebook``) als auch vom Kommandozeilen-Skript
``notebook_ausgaben_loeschen.py``. Siehe CLAUDE.md, Abschnitt "Keine gelesenen Werte im
Repository".
"""

from __future__ import annotations

import json
from pathlib import Path

NOTEBOOKS_VERZEICHNIS = Path(__file__).resolve().parent.parent / "notebooks"


def alle_notebooks() -> list[Path]:
    """Alle Notebook-Dateien im Repository, sortiert."""
    return sorted(NOTEBOOKS_VERZEICHNIS.glob("*.ipynb"))


def zellausgaben_entfernen(pfad: Path) -> bool:
    """Entfernt Ausgaben und Ausführungszähler aus einer Notebook-Datei.

    Returns:
        Ob die Datei dabei verändert wurde.
    """
    with open(pfad, encoding="utf-8") as datei:
        notebook = json.load(datei)

    veraendert = False
    for zelle in notebook.get("cells", []):
        if zelle.get("cell_type") != "code":
            continue
        if zelle.get("outputs"):
            zelle["outputs"] = []
            veraendert = True
        if zelle.get("execution_count") is not None:
            zelle["execution_count"] = None
            veraendert = True
        # Manche Jupyter-Versionen haengen hier Ausfuehrungszeiten an - kein Wert
        # fuers Repository, siehe Moduldocstring.
        if zelle.get("metadata", {}).pop("execution", None) is not None:
            veraendert = True

    if veraendert:
        with open(pfad, "w", encoding="utf-8") as datei:
            json.dump(notebook, datei, indent=1, ensure_ascii=False)
            datei.write("\n")

    return veraendert
