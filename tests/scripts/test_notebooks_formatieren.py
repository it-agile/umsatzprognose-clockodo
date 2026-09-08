"""Fruehwarn-Tests fuer scripts/notebook_ausgaben.py und
scripts/notebooks_formatieren.py.

``zellausgaben_entfernen()``/``code_zellen_einklappen()`` selbst sind schon ueber
``tests/test_pre_commit_hook.py`` gruendlich abgedeckt (der Hook importiert dieselben
Funktionen) - hier geht es um die Stellen, die dort nicht mitgetestet werden: das
Auffinden aller Notebooks, die Kommandozeilen-Schleife darueber und die beiden
Optionen ``--ausgaben-loeschen``/``--einklappen``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
import notebook_ausgaben
import notebooks_formatieren


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

    ergebnis = notebooks_formatieren.main([str(pfad)])

    assert ergebnis == 0
    assert "1 Notebook(s) bereinigt." in capsys.readouterr().out
    bereinigt = json.loads(pfad.read_text(encoding="utf-8"))
    assert bereinigt["cells"][0]["outputs"] == []
    assert bereinigt["cells"][0]["metadata"]["jupyter"]["source_hidden"] is True


def test_main_ohne_einklappen_loescht_nur_ausgaben(tmp_path):
    pfad = tmp_path / "notebook.ipynb"
    _notebook_mit_ausgabe(pfad)

    notebooks_formatieren.main(["--no-einklappen", str(pfad)])

    ergebnis = json.loads(pfad.read_text(encoding="utf-8"))
    zelle = ergebnis["cells"][0]
    assert zelle["outputs"] == []
    assert "jupyter" not in zelle["metadata"]


def test_main_ohne_ausgaben_loeschen_klappt_nur_ein(tmp_path):
    pfad = tmp_path / "notebook.ipynb"
    _notebook_mit_ausgabe(pfad)

    notebooks_formatieren.main(["--no-ausgaben-loeschen", str(pfad)])

    ergebnis = json.loads(pfad.read_text(encoding="utf-8"))
    zelle = ergebnis["cells"][0]
    assert zelle["outputs"] != []
    assert zelle["metadata"]["jupyter"]["source_hidden"] is True


def test_main_meldet_bereits_saubere_notebooks(tmp_path, capsys):
    pfad = tmp_path / "notebook.ipynb"
    pfad.write_text(
        json.dumps({"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}),
        encoding="utf-8",
    )

    ergebnis = notebooks_formatieren.main([str(pfad)])

    assert ergebnis == 0
    assert "Keine Zellausgaben oder ausgeklappten Code-Zellen gefunden." in capsys.readouterr().out


def test_main_ohne_einklappen_nennt_nur_zellausgaben_in_der_meldung(tmp_path, capsys):
    pfad = tmp_path / "notebook.ipynb"
    pfad.write_text(
        json.dumps({"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}),
        encoding="utf-8",
    )

    notebooks_formatieren.main(["--no-einklappen", str(pfad)])

    ausgabe = capsys.readouterr().out
    assert "Keine Zellausgaben gefunden." in ausgabe
    assert "Code-Zellen" not in ausgabe


def test_main_ohne_ausgaben_loeschen_nennt_nur_code_zellen_in_der_meldung(tmp_path, capsys):
    pfad = tmp_path / "notebook.ipynb"
    pfad.write_text(
        json.dumps({"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}),
        encoding="utf-8",
    )

    notebooks_formatieren.main(["--no-ausgaben-loeschen", str(pfad)])

    ausgabe = capsys.readouterr().out
    assert "Keine ausgeklappten Code-Zellen gefunden." in ausgabe
    assert "Zellausgaben" not in ausgabe


def test_main_ohne_beide_optionen_tut_nichts(tmp_path, capsys):
    pfad = tmp_path / "notebook.ipynb"
    _notebook_mit_ausgabe(pfad)
    inhalt = pfad.read_text(encoding="utf-8")

    ergebnis = notebooks_formatieren.main(["--no-ausgaben-loeschen", "--no-einklappen", str(pfad)])

    assert ergebnis == 0
    assert "Nichts zu tun" in capsys.readouterr().err
    assert pfad.read_text(encoding="utf-8") == inhalt


def test_main_meldet_fehlende_datei_und_bricht_ab(tmp_path, capsys):
    fehlend = tmp_path / "existiert-nicht.ipynb"

    ergebnis = notebooks_formatieren.main([str(fehlend)])

    assert ergebnis == 1
    assert "nicht gefunden" in capsys.readouterr().err
