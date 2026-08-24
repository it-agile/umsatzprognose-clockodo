"""Tests zur Extraktion aus den Clockodo-Antworten.

Die Faelle stammen aus per curl geprueften Antworten (24.08.2026), nicht aus der
Doku - siehe Modul-Docstring von ``umsatzprognose.extraktion``.
"""

from __future__ import annotations

import pytest

from umsatzprognose.extraktion import budgets_je_projekt, projekt_id, revenue_je_projekt


def projekt(pid, *, active=True, budget=None):
    """Ein Projekt in der Form, die ``/v4/projects`` liefert."""
    return {"id": pid, "active": active, "budget": budget}


def euro_budget(amount, **abweichungen):
    """Ein Euro-Gesamtbudget, wie es in dieser Installation vorkommt."""
    return {
        "monetary": True,
        "hard": False,
        "from_subprojects": False,
        "interval": None,
        "amount": amount,
        "subprojects_budget_total": 0,
    } | abweichungen


def test_projekt_id_nimmt_id_und_faellt_auf_projects_id_zurueck():
    assert projekt_id({"id": "4013678"}) == 4013678
    assert projekt_id({"projects_id": 42}) == 42
    with pytest.raises(KeyError):
        projekt_id({"name": "ohne ID"})


def test_nur_aktive_projekte_zaehlen_standardmaessig():
    projekte = [projekt(1), projekt(2, active=False)]
    assert set(budgets_je_projekt(projekte).budgets) == {1}
    assert set(budgets_je_projekt(projekte, nur_aktive=False).budgets) == {1, 2}


def test_budget_null_bedeutet_kein_budget():
    # budget ist immer als Schluessel vorhanden, aber oft null.
    auszug = budgets_je_projekt([projekt(1, budget=None)])
    assert auszug.budgets == {1: None}
    assert auszug.unbenutzbar == []


def test_euro_budget_wird_uebernommen():
    auszug = budgets_je_projekt([projekt(1, budget=euro_budget(11_300))])
    assert auszug.budgets == {1: pytest.approx(11_300.0)}


def test_stundenbudget_wird_nicht_als_euro_gelesen():
    # monetary=false: in amount steht eine Stundenzahl. Als Euro waere das falsch.
    auszug = budgets_je_projekt([projekt(1, budget=euro_budget(48, monetary=False))])
    assert auszug.budgets == {1: None}
    assert auszug.nicht_monetaer == [1]
    assert auszug.unbenutzbar == [1]


def test_intervallbudget_ist_kein_gesamtbudget():
    auszug = budgets_je_projekt([projekt(1, budget=euro_budget(5_000, interval="monthly"))])
    assert auszug.budgets == {1: None}
    assert auszug.mit_intervall == [1]


def test_budget_aus_teilprojekten_wird_gemeldet():
    budget = euro_budget(0, from_subprojects=True, subprojects_budget_total=9_000)
    auszug = budgets_je_projekt([projekt(1, budget=budget)])
    assert auszug.budgets == {1: None}
    assert auszug.aus_teilprojekten == [1]


def test_projekt_id_der_entrygroup_kommt_als_string():
    revenue, ohne_projekt = revenue_je_projekt([{"group": "1375839", "revenue": 1_132_440.7}])
    assert revenue == {1375839: pytest.approx(1_132_440.7)}
    assert ohne_projekt == []


def test_buchungen_ohne_projekt_werden_ausgesondert():
    # group == 0 sind Buchungen auf einen Kunden ohne Projekt - sonst entstuende
    # daraus ein Phantom-Projekt 0.
    gruppen = [{"group": 0, "revenue": 500.0}, {"group": "7", "revenue": 100.0}]
    revenue, ohne_projekt = revenue_je_projekt(gruppen)
    assert revenue == {7: pytest.approx(100.0)}
    assert ohne_projekt == [gruppen[0]]


def test_revenue_null_zaehlt_als_null_euro():
    revenue, _ = revenue_je_projekt([{"group": "7", "revenue": None}])
    assert revenue == {7: pytest.approx(0.0)}


def test_mehrere_gruppen_je_projekt_werden_summiert():
    revenue, _ = revenue_je_projekt(
        [{"group": "7", "revenue": 100.0}, {"group": "7", "revenue": 50.0}]
    )
    assert revenue == {7: pytest.approx(150.0)}
