"""Tests zum Modell fuer Projekte ohne Budget (Auswahl, Fenster, Historie, Reservierung)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import numpy as np
import pytest

from umsatzprognose.domaene import (
    Bestand,
    Gesamtbudget,
    Kunde,
    Mitarbeiter,
    Monatsumsatz,
    OhneBudgetModell,
    Projekt,
    Projektanteil,
    Verbrauchsverlauf,
)

STICHTAG = date(2026, 9, 15)
KUNDE = Kunde(id=1, name="Musterkunde GmbH")
ANNA = Mitarbeiter(id=1, name="Anna", aktiv=True)
BERT = Mitarbeiter(id=2, name="Bert", aktiv=True)

MODELL = OhneBudgetModell(ausschluss=("Intern",), schulung=("Schulung",), historie_monate=3)


def projekt(identifier: int, name: str, **felder) -> Projekt:
    return Projekt(id=identifier, name=name, kunde=KUNDE, aktiv=True, **felder)


COACHING = projekt(1, "Coaching")
INTERN = projekt(2, "Intern Verwaltung")
SCHULUNG = projekt(
    3,
    "Schulung CSM",
    anteile=(Projektanteil(ANNA, stunden=30.0), Projektanteil(BERT, stunden=10.0)),
)
MIT_BUDGET = projekt(4, "Mit Budget", budget=Gesamtbudget(betrag=Decimal("1000")))
BEENDET = projekt(5, "Beendet", abgeschlossen=True)
INAKTIV = Projekt(id=6, name="Inaktiv", kunde=KUNDE, aktiv=False)


def bestand(*verlaeufe: Verbrauchsverlauf) -> Bestand:
    return Bestand(
        stichtag=STICHTAG,
        projekte=(COACHING, INTERN, SCHULUNG, MIT_BUDGET, BEENDET, INAKTIV),
        verbrauchsverlaeufe=verlaeufe,
    )


def test_historie_monate_muss_mindestens_eins_sein():
    with pytest.raises(ValueError, match="historie_monate"):
        OhneBudgetModell(historie_monate=0)


def test_projekte_enthaelt_nur_aktive_offene_ohne_budget_und_nicht_ausgeschlossene():
    assert MODELL.projekte(bestand()) == (COACHING,)


def test_schulungsprojekte_gelten_als_ausgeschlossen():
    assert MODELL.ist_schulung(SCHULUNG)
    assert MODELL.ist_ausgeschlossen(SCHULUNG)
    assert not MODELL.ist_schulung(INTERN)
    assert MODELL.ist_ausgeschlossen(INTERN)


def test_fenster_sind_die_letzten_abgeschlossenen_monate_aelteste_zuerst():
    assert MODELL.fenster(bestand()) == ((2026, 6), (2026, 7), (2026, 8))


def test_fenster_geht_ueber_den_jahreswechsel():
    januar = Bestand(stichtag=date(2026, 1, 10))
    assert MODELL.fenster(januar) == ((2025, 10), (2025, 11), (2025, 12))


def test_umsatz_historie_fuellt_monate_ohne_buchung_mit_null():
    verlauf = Verbrauchsverlauf.fuer(
        COACHING,
        [Monatsumsatz(2026, 6, Decimal("500")), Monatsumsatz(2026, 8, Decimal("700"))],
    )
    b = bestand(verlauf)

    historie = MODELL.umsatz_historie(b, MODELL.projekte(b))

    assert historie.tolist() == [[500.0, 0.0, 700.0]]


def test_umsatz_historie_ohne_verlauf_ist_null_und_ohne_projekte_leer():
    b = bestand()
    assert MODELL.umsatz_historie(b, (COACHING,)).tolist() == [[0.0, 0.0, 0.0]]
    assert MODELL.umsatz_historie(b, ()).shape == (0, 3)
    assert isinstance(MODELL.umsatz_historie(b, ()), np.ndarray)


def test_reservierte_stunden_verteilen_das_fenstermittel_nach_personenanteil():
    verlauf = Verbrauchsverlauf.fuer(
        SCHULUNG,
        [
            Monatsumsatz(2026, 6, Decimal("0"), stunden=40.0),
            Monatsumsatz(2026, 8, Decimal("0"), stunden=80.0),
            # ausserhalb des Fensters, zaehlt nicht
            Monatsumsatz(2026, 1, Decimal("0"), stunden=999.0),
        ],
    )

    reserviert = MODELL.reservierte_stunden(bestand(verlauf))

    # 120 Stunden im 3-Monats-Fenster, Anna 75 %, Bert 25 %, gemittelt ueber 3 Monate.
    assert reserviert == {1: pytest.approx(30.0), 2: pytest.approx(10.0)}


def test_ohne_schulungsmuster_wird_nichts_reserviert():
    verlauf = Verbrauchsverlauf.fuer(SCHULUNG, [Monatsumsatz(2026, 8, Decimal("0"), stunden=40.0)])
    assert OhneBudgetModell().reservierte_stunden(bestand(verlauf)) == {}
