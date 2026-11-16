"""Tests fuer domaene.kosten: reine Fachlogik, ohne Netzzugriff."""

from __future__ import annotations

from decimal import Decimal

from umsatzprognose.domaene import Hinweis
from umsatzprognose.domaene.kosten import Kostenplan, Kostenposten


def test_kosten_je_monat_summiert_je_monat() -> None:
    plan = Kostenplan(
        posten=(
            Kostenposten(2026, 1, Decimal("1000.0")),
            Kostenposten(2026, 2, Decimal("1500.0")),
        ),
    )
    assert plan.kosten_je_monat([(2026, 1), (2026, 2), (2026, 3)]) == [
        Decimal("1000.0"),
        Decimal("1500.0"),
        Decimal("0"),
    ]


def test_kosten_je_monat_ohne_posten_ist_ueberall_null() -> None:
    plan = Kostenplan()
    assert plan.kosten_je_monat([(2026, 1), (2026, 2)]) == [Decimal("0"), Decimal("0")]


def test_kosten_je_monat_gilt_auch_fuer_vergangene_monate() -> None:
    """Anders als der Schulungsplan filtert der Kostenplan nicht nach einem Stichtag."""
    plan = Kostenplan(posten=(Kostenposten(2025, 1, Decimal("500.0")),))
    assert plan.kosten_je_monat([(2025, 1)]) == [Decimal("500.0")]


def test_kostenstatus_je_monat_gilt_rueckwaertsblickend_ab_dem_letzten_nicht_pauschalen_monat() -> (
    None
):
    plan = Kostenplan(
        posten=(
            Kostenposten(2026, 1, Decimal("1000.0"), entspricht_pauschale=True),
            Kostenposten(2026, 2, Decimal("1100.0")),
            Kostenposten(2026, 3, Decimal("1200.0"), entspricht_pauschale=True),
            Kostenposten(2026, 4, Decimal("1300.0")),
            Kostenposten(2026, 5, Decimal("1400.0"), entspricht_pauschale=True),
        ),
    )
    monate = [(2025, 12), (2026, 1), (2026, 2), (2026, 3), (2026, 4), (2026, 5), (2026, 6)]
    assert plan.kostenstatus_je_monat(monate) == [
        "unbekannt",
        "gesichert",
        "gesichert",
        "gesichert",
        "gesichert",
        "pauschale",
        "unbekannt",
    ]


def test_kostenstatus_je_monat_ohne_nicht_pauschalen_monat_ist_alles_pauschale() -> None:
    plan = Kostenplan(posten=(Kostenposten(2026, 1, Decimal("1000.0"), entspricht_pauschale=True),))
    assert plan.kostenstatus_je_monat([(2026, 1)]) == ["pauschale"]


def test_summe_addiert_die_uebergebenen_monate() -> None:
    plan = Kostenplan(
        posten=(Kostenposten(2026, 1, Decimal("1000.0")), Kostenposten(2026, 2, Decimal("1500.0"))),
    )
    assert plan.summe([(2026, 1), (2026, 2)]) == Decimal("2500.0")


def test_hinweise_meldet_fehlende_monate() -> None:
    plan = Kostenplan(posten=(Kostenposten(2026, 1, Decimal("1000.0")),))
    hinweise = plan.hinweise([(2026, 1), (2026, 2), (2026, 3)])
    assert len(hinweise) == 1
    assert "Feb 2026" in hinweise[0].betroffene
    assert "Mär 2026" in hinweise[0].betroffene
    assert "Jan 2026" not in hinweise[0].betroffene


def test_hinweise_ohne_luecke_bleibt_bei_den_abbildungshinweisen() -> None:
    abbildungshinweis = Hinweis("Die Kosten-Datei für 2026 konnte nicht gelesen werden")
    plan = Kostenplan(
        posten=(Kostenposten(2026, 1, Decimal("1000.0")),),
        abbildungshinweise=(abbildungshinweis,),
    )
    assert plan.hinweise([(2026, 1)]) == (abbildungshinweis,)
