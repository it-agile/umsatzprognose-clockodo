"""Tests zur Abrufquote-Verteilung - Spec 5.2.

Geprueft wird das, was die Spec **nicht** festlegt und was hier entschieden werden
musste: welche Monate eine Beobachtung sind. Die Rueckrechnung des Restvolumens auf einen
vergangenen Monatsbeginn steht daneben, weil sie von der Reihenfolge der Monate lebt -
und die API liefert sie nach Dauer sortiert.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from umsatzprognose.domaene import (
    Abrufquote,
    Abrufquotenverteilung,
    Budget,
    Monatsumsatz,
    Projekt,
    Verbrauchsverlauf,
)

STICHTAG = date(2026, 8, 24)


def projekt(**felder) -> Projekt:
    standard = {"id": 1, "aktiv": True, "budget": Budget(betrag=100000.0)}
    return Projekt(**{**standard, **felder})


def verlauf(*monate: tuple[int, int, float], **projektfelder) -> Verbrauchsverlauf:
    return Verbrauchsverlauf.fuer(
        projekt(**projektfelder),
        (Monatsumsatz(jahr=j, monat=m, umsatz=u) for j, m, u in monate),
    )


def test_monate_werden_chronologisch_geordnet_und_doppelte_zusammengefasst():
    # Die API liefert die Untergruppen nach Dauer absteigend; ein doppelter Monat waere
    # sonst ein still verworfener Verbrauch.
    gebaut = verlauf((2026, 7, 20000.0), (2026, 4, 30000.0), (2026, 4, 5000.0))

    assert [m.schluessel for m in gebaut.monate] == [(2026, 4), (2026, 7)]
    assert gebaut.gebucht(2026, 4) == 35000.0
    assert gebaut.verbrauch == 55000.0


def test_restvolumen_zu_monatsbeginn_wird_aus_dem_heutigen_budget_zurueckgerechnet():
    gebaut = verlauf((2026, 4, 30000.0), (2026, 5, 25000.0))

    assert gebaut.restvolumen_zu_monatsbeginn(2026, 4) == 100000.0
    assert gebaut.restvolumen_zu_monatsbeginn(2026, 5) == 70000.0
    assert gebaut.restvolumen_zu_monatsbeginn(2026, 6) == 45000.0


def test_ohne_bezifferbares_budget_gibt_es_kein_restvolumen_und_keine_quote():
    # Ein Stundenbudget (monetary=false) ist kein Euro-Gesamtbudget - Spec 5.0.
    gebaut = verlauf((2026, 4, 30000.0), budget=Budget(betrag=48.0, monetaer=False))

    assert gebaut.restvolumen_zu_monatsbeginn(2026, 4) is None
    assert gebaut.abrufquoten(STICHTAG) == ()


def test_luecke_im_fenster_ist_eine_quote_von_null():
    # 2026-06 fehlt in der Antwort - das ist ein Monat ohne Abruf und kein fehlender
    # Datensatz. Genau diese Nullen tragen die Bandbreite nach unten.
    quoten = verlauf((2026, 4, 30000.0), (2026, 6, 0.0), (2026, 7, 20000.0)).abrufquoten(STICHTAG)
    # 2026-06 kommt hier zwar vor, aber mit 0 - dasselbe Ergebnis wie ohne den Eintrag.
    ohne_eintrag = verlauf((2026, 4, 30000.0), (2026, 7, 20000.0)).abrufquoten(STICHTAG)

    assert [(q.jahr, q.monat, q.wert) for q in quoten] == [
        (2026, 4, 0.3),
        (2026, 5, 0.0),
        (2026, 6, 0.0),
        (2026, 7, 20000.0 / 70000.0),
    ]
    assert [q.wert for q in ohne_eintrag] == [q.wert for q in quoten]


def test_fenster_eines_laufenden_projekts_reicht_bis_zum_vormonat_des_stichtags():
    # Ein Projekt im Prognose-Scope, auf das seit Monaten nichts gebucht wird, liefert
    # die Nullen, die es verdient - der Stichtagsmonat selbst bleibt aussen vor, weil
    # er angebrochen ist (Spec 5.4).
    gebaut = verlauf((2026, 4, 30000.0), (2026, 8, 11661.88))

    assert gebaut.beobachtungsmonate(STICHTAG) == ((2026, 4), (2026, 5), (2026, 6), (2026, 7))
    assert [q.wert for q in gebaut.abrufquoten(STICHTAG)] == [0.3, 0.0, 0.0, 0.0]


def test_fenster_eines_beendeten_projekts_endet_mit_seiner_letzten_buchung():
    # abgeschlossen schlaegt aktiv (Spec 5.0): das Projekt ist nicht im Scope, und die
    # Monate nach seinem Ende sind keine Beobachtung - niemand ruft dort noch etwas ab.
    beendet = verlauf((2026, 4, 30000.0), (2026, 5, 25000.0), abgeschlossen=True)

    assert beendet.beobachtungsmonate(STICHTAG) == ((2026, 4), (2026, 5))


def test_buchungen_nach_dem_stichtag_zaehlen_nicht_zur_historie():
    # Sie sind laut Spec 5.4 die Untergrenze der Bandbreite und nicht Verbrauch.
    gebaut = verlauf((2026, 4, 30000.0), (2026, 9, 6000.0))

    assert gebaut.beobachtungsmonate(STICHTAG)[-1] == (2026, 7)
    assert gebaut.gebucht(2026, 9) == 6000.0
    assert all(q.schluessel <= (2026, 7) for q in gebaut.abrufquoten(STICHTAG))


def test_monate_ohne_offenes_restvolumen_sind_keine_beobachtung():
    # Ab 2026-05 ist das Budget aufgebraucht: eine Quote waere undefiniert, nicht 0.
    gebaut = verlauf((2026, 4, 120000.0), (2026, 6, 5000.0))

    assert [q.schluessel for q in gebaut.abrufquoten(STICHTAG)] == [(2026, 4)]
    assert gebaut.restvolumen_zu_monatsbeginn(2026, 6) == -20000.0


def test_quote_ueber_eins_bleibt_stehen():
    # Budgets sind weiche Grenzen (Spec 5.1). Gekappt wird erst in der Simulation.
    gebaut = verlauf((2026, 7, 120000.0))

    assert gebaut.abrufquoten(STICHTAG)[0].wert == 1.2


def test_ein_restvolumen_von_null_ist_keine_quote():
    with pytest.raises(ValueError, match="Restvolumen"):
        Abrufquote(
            projekt=projekt(), jahr=2026, monat=7, verbrauch=0.0, restvolumen_zu_monatsbeginn=0.0
        )


def test_projekt_ohne_buchung_hat_kein_beobachtungsfenster():
    leer = Verbrauchsverlauf.fuer(projekt(), ())

    assert leer.beobachtungsmonate(STICHTAG) == ()
    assert leer.abrufquoten(STICHTAG) == ()


def verteilung(*werte: float) -> Abrufquotenverteilung:
    return Abrufquotenverteilung.aus_quoten(
        Abrufquote(
            projekt=projekt(),
            jahr=2026,
            monat=1 + nummer,
            verbrauch=wert * 1000.0,
            restvolumen_zu_monatsbeginn=1000.0,
        )
        for nummer, wert in enumerate(werte)
    )


def test_verteilung_kennt_ihre_kennzahlen():
    gebaut = verteilung(0.0, 0.0, 0.5, 1.0, 1.5)

    assert gebaut.anzahl == 5
    assert gebaut.werte() == (0.0, 0.0, 0.5, 1.0, 1.5)
    assert gebaut.median == 0.5
    assert gebaut.mittelwert == 0.6
    assert gebaut.anteil_ohne_abruf == 0.4
    assert gebaut.anteil_ueber_budget == 0.2
    assert gebaut.quantil(0.0) == 0.0
    assert gebaut.quantil(1.0) == 1.5


def test_leere_verteilung_liefert_keine_zahlen_und_zieht_nicht():
    leer = Abrufquotenverteilung()

    assert not leer.vorhanden
    assert leer.median is None
    assert leer.mittelwert is None
    with pytest.raises(ValueError, match="leeren Verteilung"):
        leer.ziehen(np.random.default_rng(1))


def test_ziehung_ist_mit_zuruecklegen_und_mit_startwert_wiederholbar():
    gebaut = verteilung(0.0, 0.5, 1.0)

    erste = gebaut.ziehungen(20, np.random.default_rng(42))
    zweite = gebaut.ziehungen(20, np.random.default_rng(42))

    assert erste == zweite
    assert set(erste) <= {0.0, 0.5, 1.0}
    # Mit Zuruecklegen: 20 Ziehungen aus 3 Werten gibt es nur so.
    assert len(erste) == 20
