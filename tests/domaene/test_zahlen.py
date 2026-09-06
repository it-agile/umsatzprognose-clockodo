"""Tests fuer domaene.zahlen: deutsche Zahlformate, ohne Netzzugriff."""

from __future__ import annotations

import pytest

from umsatzprognose.domaene.zahlen import euro_parsen


@pytest.mark.parametrize(
    ("text", "erwartet"),
    [
        ("12.345,67 €", 12345.67),
        ("1.234,56€", 1234.56),
        ("0 €", 0.0),
        ("500 €", 500.0),
        ("", 0.0),
    ],
)
def test_euro_parsen(text: str, erwartet: float) -> None:
    assert euro_parsen(text) == pytest.approx(erwartet)
