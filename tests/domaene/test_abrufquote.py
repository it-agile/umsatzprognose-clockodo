"""Tests zur Abrufquote-Verteilung"""

from __future__ import annotations

from decimal import Decimal

import numpy as np
import pytest

from conftest import projekt
from umsatzprognose.domaene import Abrufquote, Abrufquotenverteilung


def test_ein_restvolumen_von_null_ist_keine_quote():
    with pytest.raises(ValueError, match="Restvolumen"):
        Abrufquote(
            projekt=projekt(),
            jahr=2026,
            monat=7,
            verbrauch=Decimal("0"),
            restvolumen_zu_monatsbeginn=Decimal("0"),
        )


def verteilung(*werte: float) -> Abrufquotenverteilung:
    return Abrufquotenverteilung.aus_quoten(
        Abrufquote(
            projekt=projekt(),
            jahr=2026,
            monat=1 + nummer,
            verbrauch=Decimal(str(wert * 1000.0)),
            restvolumen_zu_monatsbeginn=Decimal("1000.0"),
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


def test_leere_verteilung_zieht_auch_mehrere_nicht():
    leer = Abrufquotenverteilung()

    with pytest.raises(ValueError, match="leeren Verteilung"):
        leer.ziehungen(5, np.random.default_rng(1))
    with pytest.raises(ValueError, match="leeren Verteilung"):
        leer.ziehen_array((5, 2), np.random.default_rng(1))


def test_leere_verteilung_hat_keinen_anteil_ohne_abruf_oder_ueber_budget():
    leer = Abrufquotenverteilung()

    assert leer.anteil_ohne_abruf == 0.0
    assert leer.anteil_ueber_budget == 0.0


def test_verteilung_ohne_beobachtungen_zeigt_sich_als_solche():
    assert str(Abrufquotenverteilung()) == "keine Beobachtungen"
    assert "Median" in str(verteilung(0.0, 0.5, 1.0))


def test_quantil_ausserhalb_von_null_bis_eins_wirft():
    gebaut = verteilung(0.0, 0.5, 1.0)

    with pytest.raises(ValueError, match="Quantil"):
        gebaut.quantil(1.5)


def test_hoechste_liefert_die_groessten_quoten_zuerst():
    gebaut = verteilung(0.2, 0.9, 0.5)

    hoechste = gebaut.hoechste(2)

    assert [q.wert for q in hoechste] == [0.9, 0.5]


def test_abrufquote_beschriftung_und_str_zeigen_projekt_und_wert():
    quote = Abrufquote(
        projekt=projekt(name="Beispielprojekt"),
        jahr=2026,
        monat=6,
        verbrauch=Decimal("3000.0"),
        restvolumen_zu_monatsbeginn=Decimal("10000.0"),
    )

    assert quote.beschriftung == "Beispielprojekt, Jun 2026"
    assert str(quote) == "Beispielprojekt, Jun 2026: 0.300"
