"""Tests zu Kunde"""

from __future__ import annotations

from umsatzprognose.domaene import Kunde


def test_kunde_mit_namen_zeigt_den_namen():
    assert str(Kunde(id=7, name="Musterkunde GmbH")) == "Musterkunde GmbH"


def test_kunde_ohne_namen_zeigt_die_id():
    assert str(Kunde(id=7)) == "Kunde 7"
