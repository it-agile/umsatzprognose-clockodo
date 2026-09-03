"""Tests fuer domaene.auslastung: reine Fachlogik, ohne Netzzugriff."""

from __future__ import annotations

from umsatzprognose.domaene.auslastung import Auslastungsmonat, Auslastungssumme
from umsatzprognose.domaene.mitarbeiter import Mitarbeiter, Wochenarbeitszeit


def _mitarbeiter_mit_wochenstunden(stunden_je_tag: float) -> Mitarbeiter:
    from datetime import date

    arbeitszeit = Wochenarbeitszeit(
        stunden_je_wochentag=(stunden_je_tag,) * 5 + (0.0, 0.0),
        gueltig_ab=date(2020, 1, 1),
    )
    return Mitarbeiter(id=1, name="Anna", aktiv=True, arbeitszeiten=(arbeitszeit,))


def test_quote_ist_anteil_abrechenbarer_stunden_an_verfuegbarer_kapazitaet() -> None:
    anna = _mitarbeiter_mit_wochenstunden(8.0)  # September 2026: 22 Arbeitstage x 8h = 176h
    monat = Auslastungsmonat(mitarbeiter=anna, jahr=2026, monat=9, abrechenbare_stunden=88.0)

    assert monat.verfuegbare_stunden == 176.0
    assert monat.quote == 0.5


def test_quote_ist_none_ohne_verfuegbare_kapazitaet() -> None:
    ohne_arbeitszeit = Mitarbeiter(id=2, name="Bert", aktiv=True)
    monat = Auslastungsmonat(
        mitarbeiter=ohne_arbeitszeit, jahr=2026, monat=9, abrechenbare_stunden=10.0
    )

    assert monat.verfuegbare_stunden == 0.0
    assert monat.quote is None


def test_auslastungssumme_je_mitarbeiter_summiert_mehrere_monate() -> None:
    anna = _mitarbeiter_mit_wochenstunden(8.0)  # August 2026: 21 Arbeitstage, September: 22
    monate = (
        Auslastungsmonat(mitarbeiter=anna, jahr=2026, monat=8, abrechenbare_stunden=84.0),
        Auslastungsmonat(mitarbeiter=anna, jahr=2026, monat=9, abrechenbare_stunden=88.0),
    )

    (summe,) = Auslastungssumme.je_mitarbeiter(monate)

    assert summe.mitarbeiter is anna
    assert summe.abrechenbare_stunden == 172.0
    assert summe.verfuegbare_stunden == 168.0 + 176.0
    assert summe.quote == (84.0 + 88.0) / (168.0 + 176.0)


def test_auslastungssumme_je_mitarbeiter_trennt_nach_person() -> None:
    anna = _mitarbeiter_mit_wochenstunden(8.0)
    bert = Mitarbeiter(id=2, name="Bert", aktiv=True)
    monate = (
        Auslastungsmonat(mitarbeiter=anna, jahr=2026, monat=9, abrechenbare_stunden=88.0),
        Auslastungsmonat(mitarbeiter=bert, jahr=2026, monat=9, abrechenbare_stunden=10.0),
    )

    summen = {s.mitarbeiter.id: s for s in Auslastungssumme.je_mitarbeiter(monate)}

    assert summen[1].quote == 0.5
    assert summen[2].quote is None  # Bert hat keine hinterlegte Arbeitszeit
