"""Fruehwarn-Tests fuer scripts/diagramme_exportieren.py - keine Live-API, kein
tatsaechlicher kaleido-Bildexport (nur der abhaengigkeitsfreie HTML-Pfad)."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import pytest

from umsatzprognose.domaene import Anmeldungsverlauf

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


def test_alle_diagramme_deckt_dashboard_tabellen_und_anmeldungen_ab():
    assert set(script.ALLE_DIAGRAMME) == {
        *script.DIAGRAMME_DASHBOARD,
        *script.TABELLEN_DASHBOARD,
        script.DIAGRAMM_ANMELDUNGSVERLAUF,
        script.DIAGRAMM_ANMELDUNGSTABELLE,
    }


def test_mit_beschriftung_faehig_ist_teilmenge_von_diagramme_dashboard():
    assert set(script.DIAGRAMME_DASHBOARD) >= script.MIT_BESCHRIFTUNG_FAEHIG


def test_tabellen_dashboard_werte_sind_methode_und_titel():
    for methode, titel in script.TABELLEN_DASHBOARD.values():
        assert callable(methode)
        assert isinstance(titel, str) and titel


def test_figuren_exportiert_tabellen_ueber_tabelle_als_grafik(monkeypatch):
    monkeypatch.setattr(script, "_dashboard_mit_fortschritt", lambda **kw: object())
    monkeypatch.setitem(
        script.TABELLEN_DASHBOARD,
        "umsatztabelle",
        (lambda dashboard: pd.DataFrame({"Monat": ["Sep 2026"]}), "Umsatztabelle"),
    )

    figuren = script._figuren(
        ["umsatztabelle"],
        stichtag=None,
        horizont_monate=3,
        monate_fenster=script.STANDARD_MONATE_FENSTER,
        ausgabeformat="png",
    )

    assert isinstance(figuren["umsatztabelle"], go.Figure)


def test_figuren_laedt_anmeldungsverlauf_nur_einmal_fuer_verlauf_und_tabelle(monkeypatch):
    ladeaufrufe = []

    def _fake_laden(*, stichtag: date, monate_fenster: int) -> Anmeldungsverlauf:
        ladeaufrufe.append((stichtag, monate_fenster))
        return Anmeldungsverlauf()

    monkeypatch.setattr(script, "_anmeldungsverlauf_laden", _fake_laden)

    figuren = script._figuren(
        [script.DIAGRAMM_ANMELDUNGSVERLAUF, script.DIAGRAMM_ANMELDUNGSTABELLE],
        stichtag=date(2026, 9, 1),
        horizont_monate=3,
        monate_fenster=6,
        ausgabeformat="png",
    )

    assert len(ladeaufrufe) == 1
    assert isinstance(figuren[script.DIAGRAMM_ANMELDUNGSVERLAUF], go.Figure)
    assert isinstance(figuren[script.DIAGRAMM_ANMELDUNGSTABELLE], go.Figure)


def test_exportieren_schreibt_html_dateien_in_angegebener_reihenfolge(tmp_path):
    namen = ["umsatzverlauf", "kennzahlen"]
    figuren = {name: go.Figure() for name in namen}

    pfade = script.exportieren(figuren, namen, tmp_path, "html")

    assert pfade == [tmp_path / "umsatzverlauf.html", tmp_path / "kennzahlen.html"]
    assert all(pfad.exists() for pfad in pfade)
