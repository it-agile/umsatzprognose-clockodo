"""Tests zu Hinweis"""

from __future__ import annotations

from umsatzprognose.domaene import Hinweis


def test_hinweis_ohne_betroffene_hat_anzahl_null_und_zeigt_nur_den_text():
    hinweis = Hinweis(text="Ein Budget wird in Stunden statt in Euro gefuehrt")

    assert hinweis.anzahl == 0
    assert str(hinweis) == "Ein Budget wird in Stunden statt in Euro gefuehrt"


def test_hinweis_mit_betroffenen_zeigt_text_und_anzahl():
    hinweis = Hinweis(
        text="Aktive Projekte ohne Budget fallen aus der Prognose",
        betroffene=("101", "102", "103"),
    )

    assert hinweis.anzahl == 3
    assert str(hinweis) == "Aktive Projekte ohne Budget fallen aus der Prognose (3)"
