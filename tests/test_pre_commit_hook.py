"""Tests fuer den pre-commit-Hook, der Zellausgaben aus Notebooks entfernt.

`.githooks/pre-commit` hat keine `.py`-Endung (Git verlangt den exakten Dateinamen
``pre-commit``) und wird deshalb ueber ``importlib`` statt eines normalen ``import``
geladen. Die Git-Interaktion (``staged_notebooks()``, ``main()``) wird hier nicht
getestet - dafuer bräuchte es ein echtes Git-Repository als Fixture; geprueft wird die
eigentliche Kernlogik, ``zellausgaben_entfernen()``.
"""

from __future__ import annotations

import importlib.util
import json
from importlib.machinery import SourceFileLoader
from pathlib import Path

HOOK_PFAD = Path(__file__).resolve().parent.parent / ".githooks" / "pre-commit"

# Kein `.py`-Suffix (Git verlangt den exakten Dateinamen `pre-commit`) - deshalb der
# Loader explizit statt der ueblichen Suffix-Erkennung von spec_from_file_location.
_loader = SourceFileLoader("pre_commit_hook", str(HOOK_PFAD))
_spec = importlib.util.spec_from_loader(_loader.name, _loader)
assert _spec is not None, f"Kein Modul-Spec fuer {HOOK_PFAD}"
_hook = importlib.util.module_from_spec(_spec)
_loader.exec_module(_hook)


def _notebook(zellen: list[dict]) -> dict:
    return {"cells": zellen, "metadata": {}, "nbformat": 4, "nbformat_minor": 5}


def _code_zelle(*, execution_count=None, outputs=None, metadata=None) -> dict:
    return {
        "cell_type": "code",
        "execution_count": execution_count,
        "outputs": outputs or [],
        "metadata": metadata or {},
        "source": ["1 + 1"],
    }


def test_entfernt_ausgaben_und_ausfuehrungszaehler(tmp_path):
    pfad = tmp_path / "notebook.ipynb"
    notebook = _notebook(
        [
            _code_zelle(
                execution_count=3,
                outputs=[{"output_type": "stream", "name": "stdout", "text": ["12345\n"]}],
            )
        ]
    )
    pfad.write_text(json.dumps(notebook), encoding="utf-8")

    veraendert = _hook.zellausgaben_entfernen(str(pfad))

    assert veraendert is True
    ergebnis = json.loads(pfad.read_text(encoding="utf-8"))
    zelle = ergebnis["cells"][0]
    assert zelle["outputs"] == []
    assert zelle["execution_count"] is None


def test_entfernt_ausfuehrungszeit_aus_der_zellmetadata(tmp_path):
    pfad = tmp_path / "notebook.ipynb"
    notebook = _notebook(
        [_code_zelle(metadata={"execution": {"iopub.execute_input": "2026-08-27T10:00:00Z"}})]
    )
    pfad.write_text(json.dumps(notebook), encoding="utf-8")

    veraendert = _hook.zellausgaben_entfernen(str(pfad))

    assert veraendert is True
    ergebnis = json.loads(pfad.read_text(encoding="utf-8"))
    assert "execution" not in ergebnis["cells"][0]["metadata"]


def test_bereits_saubere_datei_bleibt_unveraendert(tmp_path):
    pfad = tmp_path / "notebook.ipynb"
    notebook = _notebook([_code_zelle(), {"cell_type": "markdown", "source": ["# Titel"]}])
    inhalt = json.dumps(notebook)
    pfad.write_text(inhalt, encoding="utf-8")

    veraendert = _hook.zellausgaben_entfernen(str(pfad))

    assert veraendert is False
    assert pfad.read_text(encoding="utf-8") == inhalt


def test_markdown_zellen_bleiben_unangetastet(tmp_path):
    pfad = tmp_path / "notebook.ipynb"
    notebook = _notebook(
        [
            {"cell_type": "markdown", "source": ["# Titel"]},
            _code_zelle(
                execution_count=1,
                outputs=[{"output_type": "stream", "name": "stdout", "text": ["x\n"]}],
            ),
        ]
    )
    pfad.write_text(json.dumps(notebook), encoding="utf-8")

    _hook.zellausgaben_entfernen(str(pfad))

    ergebnis = json.loads(pfad.read_text(encoding="utf-8"))
    assert ergebnis["cells"][0] == {"cell_type": "markdown", "source": ["# Titel"]}
