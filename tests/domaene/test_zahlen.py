"""Tests fuer domaene.zahlen: deutsche Zahlformate, ohne Netzzugriff."""

from __future__ import annotations

from decimal import Decimal

import pytest

from umsatzprognose.domaene.zahlen import betrag_parsen, euro, euro_parsen


@pytest.mark.parametrize(
    ("text", "erwartet"),
    [
        ("12.345,67 €", Decimal("12345.67")),
        ("1.234,56€", Decimal("1234.56")),
        ("0 €", Decimal("0")),
        ("500 €", Decimal("500")),
        ("", Decimal("0")),
    ],
)
def test_euro_parsen(text: str, erwartet: Decimal) -> None:
    # Exakter Vergleich statt pytest.approx: euro_parsen() geht direkt in Decimal,
    # ohne den Umweg ueber float, es gibt also keine Rundungsungenauigkeit abzufedern.
    assert euro_parsen(text) == erwartet


@pytest.mark.parametrize(
    ("text", "erwartet"),
    [
        ("12.345,67 EUR", Decimal("12345.67")),
        ("-1.234,56 EUR", Decimal("-1234.56")),
        ("0,00 EUR", Decimal("0")),
        ("", Decimal("0")),
    ],
)
def test_betrag_parsen(text: str, erwartet: Decimal) -> None:
    assert betrag_parsen(text) == erwartet


@pytest.mark.parametrize("betrag", [Decimal("729212.45"), Decimal("-729212.45"), Decimal("0")])
def test_betrag_parsen_ist_umkehrung_von_euro(betrag: Decimal) -> None:
    # Der eigentliche Zweck von betrag_parsen(): einen selbst per euro() formatierten
    # Betrag wieder einlesen, ohne dass das Vorzeichen wie bei euro_parsen() verloren
    # geht (siehe Docstring von betrag_parsen()).
    assert betrag_parsen(euro(betrag)) == betrag
