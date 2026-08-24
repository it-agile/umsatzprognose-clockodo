"""Tests zur Tabellendarstellung."""

from __future__ import annotations

import pytest

from umsatzprognose.restvolumen import ProjektRestvolumen
from umsatzprognose.tabellen import SPALTEN, restvolumen_tabelle


def test_tabelle_ist_absteigend_nach_prognosewirksamem_volumen():
    tabelle = restvolumen_tabelle(
        [
            ProjektRestvolumen(projects_id=1, budget=10_000.0, revenue_kumuliert=9_000.0),
            ProjektRestvolumen(projects_id=2, budget=50_000.0, revenue_kumuliert=0.0),
        ]
    )
    assert list(tabelle.columns) == SPALTEN
    assert list(tabelle["projects_id"]) == [2, 1]
    assert tabelle["prognosewirksam"].iloc[0] == pytest.approx(50_000.0)


def test_ueberschreitung_erscheint_roh_negativ_und_prognosewirksam_null():
    tabelle = restvolumen_tabelle(
        [ProjektRestvolumen(projects_id=3, budget=20_000.0, revenue_kumuliert=30_000.0)]
    )
    zeile = tabelle.iloc[0]
    assert zeile["restvolumen_roh"] == pytest.approx(-10_000.0)
    assert zeile["prognosewirksam"] == pytest.approx(0.0)
    assert bool(zeile["ueberschritten"])


def test_leere_eingabe_ergibt_leere_tabelle_mit_spalten():
    tabelle = restvolumen_tabelle([])
    assert list(tabelle.columns) == SPALTEN
    assert len(tabelle) == 0
