"""Fruehwarn-Tests fuer scripts/notebook_ausgaben.py und
scripts/notebook_ausgaben_loeschen.py.

``zellausgaben_entfernen()`` selbst ist schon ueber ``tests/test_pre_commit_hook.py``
gruendlich abgedeckt (der Hook importiert dieselbe Funktion) - hier geht es um die
beiden Stellen, die dort nicht mitgetestet werden: das Auffinden aller Notebooks und
die Kommandozeilen-Schleife darueber.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
import notebook_ausgaben
import notebook_ausgaben_loeschen


def test_alle_notebooks_findet_die_vorhandenen_notebooks():
    gefunden = notebook_ausgaben.alle_notebooks()

    assert gefunden == sorted(gefunden)
    assert any(pfad.name == "01_dashboard.ipynb" for pfad in gefunden)


def _notebook_mit_ausgabe(pfad: Path) -> None:
    notebook = {
        "cells": [
            {
                "cell_type": "code",
                "execution_count": 1,
                "outputs": [{"output_type": "stream", "name": "stdout", "text": ["x\n"]}],
                "metadata": {},
                "source": ["1 + 1"],
            }
        ],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    pfad.write_text(json.dumps(notebook), encoding="utf-8")


def test_main_bereinigt_uebergebene_notebooks(tmp_path, capsys):
    pfad = tmp_path / "notebook.ipynb"
    _notebook_mit_ausgabe(pfad)

    ergebnis = notebook_ausgaben_loeschen.main([str(pfad)])

    assert ergebnis == 0
    assert "1 Notebook(s) von Zellausgaben bereinigt." in capsys.readouterr().out
    bereinigt = json.loads(pfad.read_text(encoding="utf-8"))
    assert bereinigt["cells"][0]["outputs"] == []


def test_main_meldet_bereits_saubere_notebooks(tmp_path, capsys):
    pfad = tmp_path / "notebook.ipynb"
    pfad.write_text(
        json.dumps({"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}),
        encoding="utf-8",
    )

    ergebnis = notebook_ausgaben_loeschen.main([str(pfad)])

    assert ergebnis == 0
    assert "Keine Zellausgaben gefunden." in capsys.readouterr().out


def test_main_meldet_fehlende_datei_und_bricht_ab(tmp_path, capsys):
    fehlend = tmp_path / "existiert-nicht.ipynb"

    ergebnis = notebook_ausgaben_loeschen.main([str(fehlend)])

    assert ergebnis == 1
    assert "nicht gefunden" in capsys.readouterr().err
