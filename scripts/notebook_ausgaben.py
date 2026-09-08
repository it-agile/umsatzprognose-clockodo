"""Gemeinsame Logik zum Bereinigen von Notebook-Dateien.

Reine Standardbibliothek - genutzt sowohl vom Pre-Commit-Hook (``.githooks/pre-commit``,
läuft ohne ``uv sync --extra notebook``) als auch vom Kommandozeilen-Skript
``notebooks_formatieren.py``. Siehe CLAUDE.md, Abschnitt "Keine gelesenen Werte im
Repository".
"""

from __future__ import annotations

import json
from pathlib import Path

NOTEBOOKS_VERZEICHNIS = Path(__file__).resolve().parent.parent / "notebooks"


def alle_notebooks() -> list[Path]:
    """Alle Notebook-Dateien im Repository, sortiert."""
    return sorted(NOTEBOOKS_VERZEICHNIS.glob("*.ipynb"))


def _notebook_lesen(pfad: Path) -> dict:
    with open(pfad, encoding="utf-8") as datei:
        return json.load(datei)


def _notebook_schreiben(pfad: Path, notebook: dict) -> None:
    with open(pfad, "w", encoding="utf-8") as datei:
        json.dump(notebook, datei, indent=1, ensure_ascii=False)
        datei.write("\n")


def zellausgaben_entfernen(pfad: Path) -> bool:
    """Entfernt Ausgaben und Ausführungszähler aus einer Notebook-Datei.

    Returns:
        Ob die Datei dabei verändert wurde.
    """
    notebook = _notebook_lesen(pfad)

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
        _notebook_schreiben(pfad, notebook)

    return veraendert


def code_zellen_einklappen(pfad: Path) -> bool:
    """Klappt jede Code-Zelle ohne eingeklappte Quelltextanzeige ein.

    Notebooks in diesem Repository zeigen Fachexpert:innen grundsätzlich keinen
    Code, nur den Zell-Titel (``# @title ...``) und seine Ausgabe - das steuert die
    Zellmetadata ``jupyter.source_hidden``. Eine neue oder überschriebene Zelle ohne
    diese Metadata (z. B. nach einer Bearbeitung, die sie nicht mitführt) würde ihren
    Code offen zeigen.

    Returns:
        Ob die Datei dabei verändert wurde.
    """
    notebook = _notebook_lesen(pfad)

    veraendert = False
    for zelle in notebook.get("cells", []):
        if zelle.get("cell_type") != "code":
            continue
        jupyter_metadata = zelle.setdefault("metadata", {}).setdefault("jupyter", {})
        if jupyter_metadata.get("source_hidden") is not True:
            jupyter_metadata["source_hidden"] = True
            veraendert = True

    if veraendert:
        _notebook_schreiben(pfad, notebook)

    return veraendert
