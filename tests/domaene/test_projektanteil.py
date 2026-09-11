"""Tests zu Projektanteil"""

from __future__ import annotations

from decimal import Decimal

from umsatzprognose.domaene import Mitarbeiter, Projektanteil


def test_projektanteil_traegt_stunden_und_umsatz_der_person():
    anteil = Projektanteil(
        mitarbeiter=Mitarbeiter(id=1, name="Beispielperson"),
        stunden=120.0,
        umsatz=Decimal("9000.0"),
    )

    assert anteil.mitarbeiter.name == "Beispielperson"
    assert anteil.stunden == 120.0
    assert anteil.umsatz == Decimal("9000.0")


def test_projektanteil_ohne_umsatz_ist_null():
    anteil = Projektanteil(mitarbeiter=Mitarbeiter(id=1), stunden=40.0)

    assert anteil.umsatz == Decimal("0")
