"""Tests zu NochKeinePrognose"""

from __future__ import annotations

from umsatzprognose.domaene import NochKeinePrognose


def test_noch_keine_prognose_ist_nicht_vorhanden_und_traegt_eine_begruendung():
    prognose = NochKeinePrognose()

    assert not prognose.vorhanden
    assert "Bandbreite" in prognose.begruendung


def test_noch_keine_prognose_liefert_konstante_leerwerte():
    prognose = NochKeinePrognose()

    assert prognose.horizontmonate() == ()
    assert prognose.monatswerte() == {}
    assert prognose.gebucht() == []
    assert prognose.summe() == {}
    assert prognose.kapazitaet_limitierend_anteil() == 0.0
    assert prognose.kapazitaet_je_projekt() == {}


def test_noch_keine_prognose_traegt_eine_eigene_begruendung():
    prognose = NochKeinePrognose(fehlt="Kein Projekt liegt im Prognose-Scope")

    assert prognose.begruendung == "Kein Projekt liegt im Prognose-Scope"
