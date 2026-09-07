"""Fruehwarn-Tests fuer scripts/diagramme_exportieren.py - keine Live-API, kein
tatsaechlicher kaleido-Bildexport (nur der abhaengigkeitsfreie HTML-Pfad)."""

from __future__ import annotations

import sys
from pathlib import Path

import plotly.graph_objects as go
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
import diagramme_exportieren as script


def test_argumente_defaults():
    args = script._argumente([])

    assert args.ausgabeverzeichnis == Path("diagramme")
    assert args.format == script.STANDARD_FORMAT
    assert args.diagramme is None
    assert args.stichtag is None
    assert args.horizont_monate == 3
    assert args.monate_fenster == script.STANDARD_MONATE_FENSTER


def test_argumente_diagramm_ist_mehrfach_angebbar():
    args = script._argumente(["--diagramm", "umsatzverlauf", "--diagramm", "anmeldungsverlauf"])

    assert args.diagramme == ["umsatzverlauf", "anmeldungsverlauf"]


def test_argumente_lehnt_unbekanntes_diagramm_ab():
    with pytest.raises(SystemExit):
        script._argumente(["--diagramm", "unbekannt"])


def test_alle_diagramme_deckt_dashboard_und_anmeldungsverlauf_ab():
    assert set(script.ALLE_DIAGRAMME) == {
        *script.DIAGRAMME_DASHBOARD,
        script.DIAGRAMM_ANMELDUNGSVERLAUF,
    }


def test_mit_beschriftung_faehig_ist_teilmenge_von_diagramme_dashboard():
    assert set(script.DIAGRAMME_DASHBOARD) >= script.MIT_BESCHRIFTUNG_FAEHIG


def test_exportieren_schreibt_html_dateien_in_angegebener_reihenfolge(tmp_path):
    namen = ["umsatzverlauf", "kennzahlen"]
    figuren = {name: go.Figure() for name in namen}

    pfade = script.exportieren(figuren, namen, tmp_path, "html")

    assert pfade == [tmp_path / "umsatzverlauf.html", tmp_path / "kennzahlen.html"]
    assert all(pfad.exists() for pfad in pfade)
