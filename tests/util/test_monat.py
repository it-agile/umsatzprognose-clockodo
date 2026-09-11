"""Tests zur Monat-Arithmetik (ordnung/aus_ordnung/vormonat/monatsfolge)"""

from __future__ import annotations

from umsatzprognose.util import aus_ordnung, monatsfolge, ordnung, vormonat


def test_ordnung_und_aus_ordnung_sind_zueinander_umkehrbar():
    for jahr, monat in [(2025, 1), (2025, 6), (2025, 12), (2026, 1)]:
        assert aus_ordnung(ordnung(jahr, monat)) == (jahr, monat)


def test_ordnung_waechst_ueber_die_jahresgrenze_hinweg():
    assert ordnung(2025, 12) + 1 == ordnung(2026, 1)


def test_vormonat_innerhalb_des_jahres():
    assert vormonat(2025, 6) == (2025, 5)


def test_vormonat_ueber_die_jahresgrenze_hinweg():
    assert vormonat(2026, 1) == (2025, 12)


def test_monatsfolge_liefert_die_angeforderte_anzahl_aufeinanderfolgender_monate():
    assert monatsfolge((2025, 10), 3) == [(2025, 10), (2025, 11), (2025, 12)]


def test_monatsfolge_ueber_die_jahresgrenze_hinweg():
    assert monatsfolge((2025, 11), 4) == [(2025, 11), (2025, 12), (2026, 1), (2026, 2)]


def test_monatsfolge_mit_null_ist_leer():
    assert monatsfolge((2025, 6), 0) == []
