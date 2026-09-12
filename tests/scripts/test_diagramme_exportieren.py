"""Fruehwarn-Tests fuer scripts/diagramme_exportieren.py - keine Live-API, kein
tatsaechlicher kaleido-Bildexport (nur der abhaengigkeitsfreie HTML-Pfad)."""

from __future__ import annotations

import asyncio
import sys
import time
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pandas as pd
import plotly.graph_objects as go
import pytest

from umsatzprognose.domaene import Anmeldungsverlauf

if TYPE_CHECKING:
    from umsatzprognose import Dashboard

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
    monkeypatch.setitem(
        script.TABELLEN_DASHBOARD,
        "umsatztabelle",
        (lambda dashboard: pd.DataFrame({"Monat": ["Sep 2026"]}), "Umsatztabelle"),
    )

    figuren = script._figuren(
        ["umsatztabelle"],
        dashboard=cast("Dashboard", object()),
        anmeldungsverlauf_fenster=None,
        ausgabeformat="png",
    )

    assert isinstance(figuren["umsatztabelle"], go.Figure)


def test_figuren_baut_verlauf_und_tabelle_aus_demselben_fenster(monkeypatch):
    # kategorien_automatisch() liest sonst SCHULUNGEN_KATEGORIEN aus der echten Umgebung
    # (siehe schulungen.kategorien_automatisch) - hier fest verdrahtet, damit der Test
    # ohne .env/Secrets laeuft (derselbe Kniff wie in tests/webapp/test_app.py).
    monkeypatch.setattr(script, "kategorien_automatisch", dict)
    fenster = Anmeldungsverlauf()

    figuren = script._figuren(
        [script.DIAGRAMM_ANMELDUNGSVERLAUF, script.DIAGRAMM_ANMELDUNGSTABELLE],
        dashboard=None,
        anmeldungsverlauf_fenster=fenster,
        ausgabeformat="png",
    )

    assert isinstance(figuren[script.DIAGRAMM_ANMELDUNGSVERLAUF], go.Figure)
    assert isinstance(figuren[script.DIAGRAMM_ANMELDUNGSTABELLE], go.Figure)


def test_daten_laden_async_laedt_dashboard_und_anmeldungsverlauf_gleichzeitig(monkeypatch):
    """Zeitmessung statt Barrier (siehe scripts/wochenbericht.py fuer dieselbe
    Technik): liefen Dashboard und Anmeldungsverlauf nacheinander statt gleichzeitig,
    dauerte der Aufruf mindestens ``2 * sleep`` statt nur knapp ``sleep``."""
    sleep = 0.2

    class _FakeGeladenesDashboard:
        async def simuliere_async(self, *, monate, fortschritt=None):
            pass  # kein weiterer sleep - der Zeittest misst nur laden_async/anmeldungsverlauf_laden

    class _FakeDashboardKlasse:
        @staticmethod
        async def laden_async(*, stichtag, horizont_monate, fortschritt=None):
            await asyncio.sleep(sleep)
            return _FakeGeladenesDashboard()

    class _FakeSchulungenRepository:
        @classmethod
        def mit_automatischen_zugangsdaten(cls):
            return cls()

        def anmeldungsverlauf_laden(self, jahre, *, fortschritt=None):
            time.sleep(sleep)
            return Anmeldungsverlauf()

    monkeypatch.setattr(script, "Dashboard", _FakeDashboardKlasse)
    monkeypatch.setattr(script, "SchulungenRepository", _FakeSchulungenRepository)

    start = time.perf_counter()
    dashboard, anmeldungsverlauf_fenster = asyncio.run(
        script._daten_laden_async(
            mit_dashboard=True,
            mit_anmeldungsverlauf=True,
            stichtag=date(2026, 9, 1),
            horizont_monate=3,
            monate_fenster=6,
        )
    )
    dauer = time.perf_counter() - start

    assert dauer < sleep * 2  # sequenziell waeren es mindestens 2 * sleep
    assert dashboard is not None
    assert isinstance(anmeldungsverlauf_fenster, Anmeldungsverlauf)


def test_daten_laden_async_ueberspringt_anmeldungsverlauf_wenn_nicht_angefordert(monkeypatch):
    class _FakeDashboardKlasse:
        @staticmethod
        async def laden_async(*, stichtag, horizont_monate, fortschritt=None):
            raise AssertionError("haette nicht aufgerufen werden duerfen")

    class _NichtAufzurufendesRepository:
        pass

    monkeypatch.setattr(script, "Dashboard", _FakeDashboardKlasse)
    monkeypatch.setattr(script, "SchulungenRepository", _NichtAufzurufendesRepository)

    dashboard, anmeldungsverlauf_fenster = asyncio.run(
        script._daten_laden_async(
            mit_dashboard=False,
            mit_anmeldungsverlauf=False,
            stichtag=date(2026, 9, 1),
            horizont_monate=3,
            monate_fenster=6,
        )
    )

    assert dashboard is None
    assert anmeldungsverlauf_fenster is None


def test_exportieren_schreibt_html_dateien_in_angegebener_reihenfolge(tmp_path):
    namen = ["umsatzverlauf", "kennzahlen"]
    figuren = {name: go.Figure() for name in namen}

    pfade = asyncio.run(script.exportieren_async(figuren, namen, tmp_path, "html"))

    assert pfade == [tmp_path / "umsatzverlauf.html", tmp_path / "kennzahlen.html"]
    assert all(pfad.exists() for pfad in pfade)


def test_export_zusammenfassung_zaehlt_nur_diagramme_ohne_tabellen():
    zusammenfassung = script._export_zusammenfassung(["umsatzverlauf", "kennzahlen"])

    assert zusammenfassung == "2 Diagramm(e) exportiert"


def test_export_zusammenfassung_zaehlt_diagramme_und_tabellen_getrennt():
    zusammenfassung = script._export_zusammenfassung(["umsatzverlauf", "umsatztabelle"])

    assert zusammenfassung == "1 Diagramm(e) und 1 Tabelle(n) exportiert"
