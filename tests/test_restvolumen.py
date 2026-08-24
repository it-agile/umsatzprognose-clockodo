"""Tests zu Spec Abschnitt 5.1."""

from __future__ import annotations

import pytest

from umsatzprognose.restvolumen import (
    ProjektRestvolumen,
    restvolumen_je_projekt,
    summe_prognosewirksam,
)


def test_restvolumen_ist_budget_minus_verbrauch():
    r = ProjektRestvolumen(projects_id=1, budget=100_000.0, revenue_kumuliert=40_000.0)
    assert r.roh == pytest.approx(60_000.0)
    assert r.prognosewirksam == pytest.approx(60_000.0)
    assert not r.ueberschritten


def test_budgetueberschreitung_bleibt_im_rohwert_sichtbar():
    # budget.hard ist false, der Verbrauch kann das Budget uebersteigen.
    r = ProjektRestvolumen(projects_id=2, budget=50_000.0, revenue_kumuliert=62_500.0)
    assert r.roh == pytest.approx(-12_500.0)
    assert r.ueberschritten
    # Abrufbar ist daraus nichts mehr.
    assert r.prognosewirksam == pytest.approx(0.0)


def test_projekt_ohne_buchungen_hat_volles_budget_als_restvolumen():
    ergebnisse, ohne_budget = restvolumen_je_projekt(
        budgets={7: 80_000.0},
        revenue_kumuliert={},
    )
    assert ohne_budget == []
    assert [r.projects_id for r in ergebnisse] == [7]
    assert ergebnisse[0].prognosewirksam == pytest.approx(80_000.0)


def test_projekte_ohne_budget_werden_separat_gemeldet():
    ergebnisse, ohne_budget = restvolumen_je_projekt(
        budgets={1: 10_000.0, 2: None, 3: None},
        revenue_kumuliert={1: 2_500.0, 2: 9_000.0},
    )
    assert ohne_budget == [2, 3]
    assert [r.projects_id for r in ergebnisse] == [1]
    assert ergebnisse[0].roh == pytest.approx(7_500.0)


def test_summe_ignoriert_ueberschreitungen():
    restvolumina = [
        ProjektRestvolumen(projects_id=1, budget=100_000.0, revenue_kumuliert=25_000.0),
        ProjektRestvolumen(projects_id=2, budget=20_000.0, revenue_kumuliert=30_000.0),
    ]
    # 75.000 aus Projekt 1, Projekt 2 steuert 0 bei (nicht -10.000).
    assert summe_prognosewirksam(restvolumina) == pytest.approx(75_000.0)
