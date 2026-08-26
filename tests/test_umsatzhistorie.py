"""Tests zur Umsatzhistorie - vor allem zur Abgrenzung des laufenden Monats."""

from __future__ import annotations

from datetime import date

from umsatzprognose.domaene.umsatzhistorie import Monatsumsatz, Umsatzhistorie

STICHTAG = date(2026, 8, 24)


def test_fenster_umfasst_zwoelf_abgeschlossene_monate_plus_den_laufenden():
    historie = Umsatzhistorie.zum_stichtag([], STICHTAG)
    assert len(historie.monate) == 13
    assert historie.monate[0].schluessel == (2025, 8)
    assert historie.monate[-1].schluessel == (2026, 8)
    assert len(historie.abgeschlossene()) == 12


def test_fehlende_monate_werden_mit_null_aufgefuellt():
    # Monate ohne Buchungen fehlen in der Antwort. Eine Luecke im Diagramm saehe aus
    # wie ein fehlender Monat, nicht wie ein Monat ohne Umsatz.
    historie = Umsatzhistorie.zum_stichtag([Monatsumsatz(2026, 6, 300000.0)], STICHTAG)
    juli = next(m for m in historie.monate if m.schluessel == (2026, 7))
    assert juli.umsatz == 0.0
    assert len(historie.monate) == 13


def test_laufender_monat_zaehlt_nicht_in_summe_und_durchschnitt():
    # Am Stichtag ist der laufende Monat unvollstaendig; im Durchschnitt wuerde er
    # das Ergebnis nach unten ziehen.
    historie = Umsatzhistorie.zum_stichtag(
        [Monatsumsatz(2026, 7, 300000.0), Monatsumsatz(2026, 8, 150000.0)], STICHTAG
    )
    assert historie.laufender.schluessel == (2026, 8)
    assert historie.summe() == 300000.0
    assert historie.durchschnitt() == 25000.0


def test_aeltere_monate_ausserhalb_des_fensters_fallen_weg():
    historie = Umsatzhistorie.zum_stichtag([Monatsumsatz(2019, 1, 999.0)], STICHTAG)
    assert all(m.jahr >= 2025 for m in historie.monate)
    assert historie.summe() == 0.0


def test_jahreswechsel_zaehlt_richtig_zurueck():
    historie = Umsatzhistorie.zum_stichtag([], date(2026, 1, 15))
    assert historie.monate[0].schluessel == (2025, 1)
    assert historie.monate[-1].schluessel == (2026, 1)


def test_beschriftung_ist_deutsch_und_ohne_locale():
    assert Monatsumsatz(2025, 9).beschriftung == "Sep 2025"
    assert Monatsumsatz(2026, 3).beschriftung == "Mär 2026"


def test_durchschnitt_ohne_abgeschlossene_monate_ist_null():
    assert Umsatzhistorie(stichtag=STICHTAG).durchschnitt() == 0.0
