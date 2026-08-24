"""Tests zur Tabellendarstellung."""

from __future__ import annotations

import pytest

from umsatzprognose.restvolumen import ProjektRestvolumen
from umsatzprognose.stammdaten import ProjektBezeichnung
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


def test_kunde_und_projekt_werden_beschriftet():
    tabelle = restvolumen_tabelle(
        [ProjektRestvolumen(projects_id=7, budget=10_000.0, revenue_kumuliert=0.0)],
        {7: ProjektBezeichnung(kunde="cosinex GmbH", projekt="Agile Coaching 2026")},
    )
    zeile = tabelle.iloc[0]
    assert zeile["kunde"] == "cosinex GmbH"
    assert zeile["projekt"] == "Agile Coaching 2026"


def test_ohne_bezeichnungen_bleiben_die_spalten_leer_und_die_zahlen_gleich():
    restvolumina = [ProjektRestvolumen(projects_id=7, budget=10_000.0, revenue_kumuliert=2_000.0)]
    ohne = restvolumen_tabelle(restvolumina)
    mit = restvolumen_tabelle(restvolumina, {7: ProjektBezeichnung(kunde="K", projekt="P")})
    assert list(ohne.columns) == SPALTEN
    assert ohne["kunde"].iloc[0] is None
    assert ohne["prognosewirksam"].iloc[0] == mit["prognosewirksam"].iloc[0]


def test_projekt_ohne_bezeichnung_bleibt_in_der_tabelle():
    tabelle = restvolumen_tabelle(
        [ProjektRestvolumen(projects_id=7, budget=10_000.0, revenue_kumuliert=0.0)],
        {8: ProjektBezeichnung(kunde="K", projekt="P")},
    )
    assert list(tabelle["projects_id"]) == [7]
    assert tabelle["projekt"].iloc[0] is None
