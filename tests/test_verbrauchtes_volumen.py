"""Tests zum verbrauchten Volumen (Spec Abschnitt 4, ``revenue_kumuliert`` in 5.1).

Die Faelle stammen aus per curl geprueften Antworten (24.08.2026), nicht aus der
Doku - siehe Modul-Docstring von ``umsatzprognose.verbrauchtes_volumen``.
"""

from __future__ import annotations

import pytest

from umsatzprognose.verbrauchtes_volumen import revenue_je_projekt


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
