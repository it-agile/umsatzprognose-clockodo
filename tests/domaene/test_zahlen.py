"""Tests fuer domaene.zahlen: deutsche Zahlformate, ohne Netzzugriff."""

from __future__ import annotations

from decimal import Decimal

import pytest

from umsatzprognose.domaene.zahlen import euro_parsen


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
