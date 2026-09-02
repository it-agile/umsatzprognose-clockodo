"""Tests fuer domaene.kosten: reine Fachlogik, ohne Netzzugriff."""

from __future__ import annotations

from umsatzprognose.domaene import Hinweis
from umsatzprognose.domaene.kosten import Kostenplan, Kostenposten


def test_kosten_je_monat_summiert_je_monat() -> None:
    plan = Kostenplan(
        posten=(
            Kostenposten(2026, 1, 1000.0),
            Kostenposten(2026, 2, 1500.0),
        )
    )
    assert plan.kosten_je_monat([(2026, 1), (2026, 2), (2026, 3)]) == [1000.0, 1500.0, 0.0]


def test_kosten_je_monat_ohne_posten_ist_ueberall_null() -> None:
    plan = Kostenplan()
    assert plan.kosten_je_monat([(2026, 1), (2026, 2)]) == [0.0, 0.0]


def test_kosten_je_monat_gilt_auch_fuer_vergangene_monate() -> None:
    """Anders als der Schulungsplan filtert der Kostenplan nicht nach einem Stichtag."""
    plan = Kostenplan(posten=(Kostenposten(2025, 1, 500.0),))
    assert plan.kosten_je_monat([(2025, 1)]) == [500.0]


def test_summe_addiert_die_uebergebenen_monate() -> None:
    plan = Kostenplan(posten=(Kostenposten(2026, 1, 1000.0), Kostenposten(2026, 2, 1500.0)))
    assert plan.summe([(2026, 1), (2026, 2)]) == 2500.0


def test_hinweise_meldet_fehlende_monate() -> None:
    plan = Kostenplan(posten=(Kostenposten(2026, 1, 1000.0),))
    hinweise = plan.hinweise([(2026, 1), (2026, 2), (2026, 3)])
    assert len(hinweise) == 1
    assert "Feb 2026" in hinweise[0].betroffene
    assert "Mär 2026" in hinweise[0].betroffene
    assert "Jan 2026" not in hinweise[0].betroffene


def test_hinweise_ohne_luecke_bleibt_bei_den_abbildungshinweisen() -> None:
    abbildungshinweis = Hinweis("Die Kosten-Datei für 2026 konnte nicht gelesen werden")
    plan = Kostenplan(
        posten=(Kostenposten(2026, 1, 1000.0),), abbildungshinweise=(abbildungshinweis,)
    )
    assert plan.hinweise([(2026, 1)]) == (abbildungshinweis,)
