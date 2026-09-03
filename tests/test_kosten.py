"""Tests fuer domaene.kosten: reine Fachlogik, ohne Netzzugriff."""

from __future__ import annotations

from umsatzprognose.domaene import Hinweis
from umsatzprognose.domaene.kosten import Erfasst, Kostenplan, Kostenposten


def test_kostenposten_kosten_faellt_ohne_erfassung_auf_die_pauschale_zurueck() -> None:
    posten = Kostenposten(2026, 1, pauschale=1000.0)
    assert posten.kosten == 1000.0


def test_kostenposten_kosten_ersetzt_nur_den_allgemeinkosten_anteil() -> None:
    """Gehälter und Spesen aus der Pauschale bleiben unberührt von der Erfassung."""
    posten = Kostenposten(
        2026, 1, pauschale=1000.0, allgemeinkosten=200.0, erfassung=Erfasst(350.0)
    )
    assert posten.kosten == 1150.0  # 1000 - 200 + 350


def test_kostenposten_kosten_akzeptiert_eine_erfassung_von_null() -> None:
    """Eine bewusst erfasste 0 ist ein vorliegender Wert, keine fehlende Erfassung."""
    posten = Kostenposten(2026, 1, pauschale=1000.0, allgemeinkosten=200.0, erfassung=Erfasst(0.0))
    assert posten.kosten == 800.0  # 1000 - 200 + 0


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


def test_hat_erfassung_je_monat_unterscheidet_erfasst_von_pauschale() -> None:
    plan = Kostenplan(
        posten=(
            Kostenposten(
                2026, 1, pauschale=1000.0, allgemeinkosten=200.0, erfassung=Erfasst(150.0)
            ),
            Kostenposten(2026, 2, pauschale=1500.0),
        )
    )
    assert plan.hat_erfassung_je_monat([(2026, 1), (2026, 2), (2026, 3)]) == [True, False, False]


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
