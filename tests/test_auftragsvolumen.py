"""Tests zum Auftragsvolumen (Spec Abschnitt 4).

Die Faelle stammen aus per curl geprueften Antworten (24.08.2026), nicht aus der
Doku - siehe Modul-Docstring von ``umsatzprognose.auftragsvolumen``.
"""

from __future__ import annotations

import pytest

from umsatzprognose.auftragsvolumen import budgets_je_projekt, projekt_id


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
