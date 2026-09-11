"""Tests zum Verbrauchsverlauf"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from umsatzprognose.util import Monat

from datetime import date
from decimal import Decimal

from umsatzprognose.domaene import (
    Budget,
    Gesamtbudget,
    Kunde,
    Monatsumsatz,
    Projekt,
    Projektanteil,
    StundenBudget,
    Verbrauchsverlauf,
)

STICHTAG = date(2026, 8, 24)
_STANDARD_BUDGET = Gesamtbudget(betrag=Decimal("100000.0"))


def projekt(
    *,
    id: int = 1,
    name: str | None = None,
    kunde: Kunde | None = None,
    aktiv: bool = True,
    abgeschlossen: bool = False,
    budget: Budget = _STANDARD_BUDGET,
    verbrauchtes_volumen: Decimal = Decimal("0"),
    verbrauchte_stunden: float = 0.0,
    anteile: tuple[Projektanteil, ...] = (),
    stundensatz_uebersteuerung: Decimal | None = None,
    verbrauchsplan_zielmonat: Monat | None = None,
    automatischer_abschluss: date | None = None,
) -> Projekt:
    return Projekt(
        id=id,
        name=name,
        kunde=kunde,
        aktiv=aktiv,
        abgeschlossen=abgeschlossen,
        budget=budget,
        verbrauchtes_volumen=verbrauchtes_volumen,
        verbrauchte_stunden=verbrauchte_stunden,
        anteile=anteile,
        stundensatz_uebersteuerung=stundensatz_uebersteuerung,
        verbrauchsplan_zielmonat=verbrauchsplan_zielmonat,
        automatischer_abschluss=automatischer_abschluss,
    )


def verlauf(*monate: tuple[int, int, float], **projektfelder) -> Verbrauchsverlauf:
    return Verbrauchsverlauf.fuer(
        projekt(**projektfelder),
        (Monatsumsatz(jahr=j, monat=m, umsatz=Decimal(str(u))) for j, m, u in monate),
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
    # Ein Stundenbudget (monetary=false) ist kein Euro-Gesamtbudget.
    gebaut = verlauf((2026, 4, 30000.0), budget=StundenBudget(stunden=48.0))

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
    # er angebrochen ist.
    gebaut = verlauf((2026, 4, 30000.0), (2026, 8, 11661.88))

    assert gebaut.beobachtungsmonate(STICHTAG) == ((2026, 4), (2026, 5), (2026, 6), (2026, 7))
    assert [q.wert for q in gebaut.abrufquoten(STICHTAG)] == [0.3, 0.0, 0.0, 0.0]


def test_fenster_eines_beendeten_projekts_endet_mit_seiner_letzten_buchung():
    # abgeschlossen schlaegt aktiv: das Projekt ist nicht im Scope, und die
    # Monate nach seinem Ende sind keine Beobachtung - niemand ruft dort noch etwas ab.
    beendet = verlauf((2026, 4, 30000.0), (2026, 5, 25000.0), abgeschlossen=True)

    assert beendet.beobachtungsmonate(STICHTAG) == ((2026, 4), (2026, 5))


def test_buchungen_nach_dem_stichtag_zaehlen_nicht_zur_historie():
    # Sie sind die Untergrenze der Bandbreite.
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
    # Budgets sind weiche Grenzen. Gekappt wird erst in der Simulation.
    gebaut = verlauf((2026, 7, 120000.0))

    assert gebaut.abrufquoten(STICHTAG)[0].wert == 1.2


def test_projekt_ohne_buchung_hat_kein_beobachtungsfenster():
    leer = Verbrauchsverlauf.fuer(projekt(), ())

    assert leer.beobachtungsmonate(STICHTAG) == ()
    assert leer.abrufquoten(STICHTAG) == ()
