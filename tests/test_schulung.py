"""Tests fuer den Baustein Schulungsanmeldungen: die Fachobjekte in domaene.schulung."""

from __future__ import annotations

from datetime import date

from umsatzprognose.domaene import Hinweis
from umsatzprognose.domaene.schulung import Schulungsplan, Schulungstermin

STICHTAG = date(2026, 9, 15)
HORIZONT = [(2026, 9), (2026, 10), (2026, 11)]


def test_umsatz_je_monat_summiert_mehrere_termine_desselben_monats() -> None:
    plan = Schulungsplan(
        stichtag=STICHTAG,
        termine=(
            Schulungstermin(2026, 10, 1000.0),
            Schulungstermin(2026, 10, 500.0),
        ),
    )
    assert plan.umsatz_je_monat(HORIZONT) == [0.0, 1500.0, 0.0]


def test_umsatz_je_monat_ignoriert_monate_vor_dem_stichtag() -> None:
    plan = Schulungsplan(
        stichtag=STICHTAG,
        termine=(Schulungstermin(2026, 8, 2000.0), Schulungstermin(2026, 9, 300.0)),
    )
    # August liegt vor dem Stichtagsmonat und ist bereits Ist-Umsatz (Spec 5.2).
    assert plan.umsatz_je_monat(HORIZONT) == [300.0, 0.0, 0.0]


def test_umsatz_je_monat_zaehlt_stornierte_termine_mit_null_normal() -> None:
    plan = Schulungsplan(stichtag=STICHTAG, termine=(Schulungstermin(2026, 9, 0.0),))
    assert plan.umsatz_je_monat(HORIZONT) == [0.0, 0.0, 0.0]


def test_summe_ist_die_summe_ueber_den_horizont() -> None:
    plan = Schulungsplan(
        stichtag=STICHTAG,
        termine=(Schulungstermin(2026, 9, 100.0), Schulungstermin(2026, 11, 50.0)),
    )
    assert plan.summe(HORIZONT) == 150.0


def test_hinweise_meldet_horizontmonate_ohne_termin() -> None:
    plan = Schulungsplan(stichtag=STICHTAG, termine=(Schulungstermin(2026, 9, 100.0),))
    hinweise = plan.hinweise(HORIZONT)
    assert len(hinweise) == 1
    assert hinweise[0].betroffene == ("Okt 2026", "Nov 2026")


def test_hinweise_ohne_luecken_ist_leer() -> None:
    plan = Schulungsplan(
        stichtag=STICHTAG,
        termine=tuple(Schulungstermin(jahr, monat, 1.0) for jahr, monat in HORIZONT),
    )
    assert plan.hinweise(HORIZONT) == ()


def test_hinweise_reicht_abbildungshinweise_durch() -> None:
    abbildung = Hinweis("Die Schulungs-Datei für 2027 konnte nicht gelesen werden (HttpError)")
    plan = Schulungsplan(
        stichtag=STICHTAG,
        termine=tuple(Schulungstermin(jahr, monat, 1.0) for jahr, monat in HORIZONT),
        abbildungshinweise=(abbildung,),
    )
    assert plan.hinweise(HORIZONT) == (abbildung,)
