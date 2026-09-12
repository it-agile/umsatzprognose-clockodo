"""Tests fuer domaene.auslastung: reine Fachlogik, ohne Netzzugriff."""

from __future__ import annotations

import numpy as np
import pytest

from umsatzprognose.domaene.auslastung import (
    Auslastungsmonat,
    Auslastungssumme,
    FakturierbareArbeitBandbreite,
    FakturierbareArbeitVerteilung,
    anteile_fakturierbarer_arbeit,
    durchschnittlicher_anteil_fakturierbarer_arbeit,
)
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


def test_anteil_fakturierbarer_arbeit_bezieht_sich_auf_gebuchte_zeit_nicht_kapazitaet() -> None:
    # 80h abrechenbar von insgesamt 100h gebuchter Zeit (20 intern + 80 abrechenbar) -
    # die verfuegbare Kapazitaet (anders als bei quote) spielt hier keine Rolle.
    anna = _mitarbeiter_mit_wochenstunden(8.0)
    monat = Auslastungsmonat(
        mitarbeiter=anna, jahr=2026, monat=9, abrechenbare_stunden=80.0, interne_stunden=20.0
    )

    assert monat.anteil_fakturierbarer_arbeit == 0.8


def test_anteil_fakturierbarer_arbeit_ohne_gebuchte_zeit_ist_none() -> None:
    anna = _mitarbeiter_mit_wochenstunden(8.0)
    monat = Auslastungsmonat(mitarbeiter=anna, jahr=2026, monat=9)

    assert monat.anteil_fakturierbarer_arbeit is None


def test_auslastungssumme_summiert_interne_stunden() -> None:
    anna = _mitarbeiter_mit_wochenstunden(8.0)
    monate = (
        Auslastungsmonat(
            mitarbeiter=anna, jahr=2026, monat=8, abrechenbare_stunden=80.0, interne_stunden=10.0
        ),
        Auslastungsmonat(
            mitarbeiter=anna, jahr=2026, monat=9, abrechenbare_stunden=80.0, interne_stunden=30.0
        ),
    )

    (summe,) = Auslastungssumme.je_mitarbeiter(monate)

    assert summe.interne_stunden == 40.0
    assert summe.anteil_fakturierbarer_arbeit == 160.0 / 200.0


def test_fakturierbare_arbeit_bandbreite_je_monat_ueber_mehrere_personen() -> None:
    anna = _mitarbeiter_mit_wochenstunden(8.0)
    bert = _mitarbeiter_mit_wochenstunden(8.0)
    monate = (
        Auslastungsmonat(
            mitarbeiter=anna, jahr=2026, monat=9, abrechenbare_stunden=90.0, interne_stunden=10.0
        ),  # 90 % fakturierbar
        Auslastungsmonat(
            mitarbeiter=bert, jahr=2026, monat=9, abrechenbare_stunden=70.0, interne_stunden=30.0
        ),  # 70 % fakturierbar
    )

    (bandbreite,) = FakturierbareArbeitBandbreite.je_monat(monate)

    assert (bandbreite.jahr, bandbreite.monat) == (2026, 9)
    assert bandbreite.minimum == 0.7
    assert bandbreite.maximum == 0.9
    assert bandbreite.durchschnitt == 0.8
    assert bandbreite.anzahl_personen == 2


def test_fakturierbare_arbeit_bandbreite_ueberspringt_personen_ohne_gebuchte_zeit() -> None:
    anna = _mitarbeiter_mit_wochenstunden(8.0)
    bert = _mitarbeiter_mit_wochenstunden(8.0)
    monate = (
        Auslastungsmonat(
            mitarbeiter=anna, jahr=2026, monat=9, abrechenbare_stunden=90.0, interne_stunden=10.0
        ),
        Auslastungsmonat(mitarbeiter=bert, jahr=2026, monat=9),  # keine gebuchte Zeit
    )

    (bandbreite,) = FakturierbareArbeitBandbreite.je_monat(monate)

    assert bandbreite.anzahl_personen == 1


def test_fakturierbare_arbeit_bandbreite_ueberspringt_ausschliesslich_interne_personen() -> None:
    anna = _mitarbeiter_mit_wochenstunden(8.0)
    bert = _mitarbeiter_mit_wochenstunden(8.0)
    monate = (
        Auslastungsmonat(
            mitarbeiter=anna, jahr=2026, monat=9, abrechenbare_stunden=90.0, interne_stunden=10.0
        ),
        # Bert hat keine abrechenbare Stunde in diesem Monat (0 % fakturierbar) - ein
        # Ausreisser, der Minimum/Maximum sonst auf 0 % ziehen wuerde.
        Auslastungsmonat(mitarbeiter=bert, jahr=2026, monat=9, interne_stunden=5.0),
    )

    (bandbreite,) = FakturierbareArbeitBandbreite.je_monat(monate)

    assert bandbreite.anzahl_personen == 1
    assert bandbreite.minimum == bandbreite.maximum == bandbreite.durchschnitt == 0.9


def test_fakturierbare_arbeit_bandbreite_laesst_monat_ganz_ohne_gebuchte_zeit_weg() -> None:
    anna = _mitarbeiter_mit_wochenstunden(8.0)
    monate = (Auslastungsmonat(mitarbeiter=anna, jahr=2026, monat=9),)

    assert FakturierbareArbeitBandbreite.je_monat(monate) == ()


def test_durchschnittlicher_anteil_fakturierbarer_arbeit_gewichtet_nach_gebuchter_zeit() -> None:
    anna = _mitarbeiter_mit_wochenstunden(8.0)
    bert = _mitarbeiter_mit_wochenstunden(8.0)
    monate = (
        # Anna: 90h fakturierbar von 100h (90 %) - viel gebuchte Zeit, soll staerker wiegen.
        Auslastungsmonat(
            mitarbeiter=anna, jahr=2026, monat=9, abrechenbare_stunden=90.0, interne_stunden=10.0
        ),
        # Bert: 2h fakturierbar von 10h (20 %) - wenig gebuchte Zeit, ein reiner
        # Durchschnitt der beiden Anteile (90 % und 20 %) waere durch diesen
        # Ausreisser verzerrt. Noch keine ausschliesslich interne Arbeit (Bert hat 2h
        # abrechenbar), zaehlt also mit - siehe den Test unten fuer den Fall ganz ohne
        # abrechenbare Stunde.
        Auslastungsmonat(
            mitarbeiter=bert, jahr=2026, monat=9, abrechenbare_stunden=2.0, interne_stunden=8.0
        ),
    )

    ergebnis = durchschnittlicher_anteil_fakturierbarer_arbeit(monate)

    assert ergebnis == 92.0 / 110.0


def test_durchschnittlicher_anteil_fakturierbarer_arbeit_ohne_gebuchte_zeit_ist_none() -> None:
    assert durchschnittlicher_anteil_fakturierbarer_arbeit(()) is None


def test_anteile_fakturierbarer_arbeit_liefert_rohwert_je_person_und_monat() -> None:
    anna = _mitarbeiter_mit_wochenstunden(8.0)
    bert = _mitarbeiter_mit_wochenstunden(8.0)
    monate = (
        Auslastungsmonat(
            mitarbeiter=anna, jahr=2026, monat=8, abrechenbare_stunden=90.0, interne_stunden=10.0
        ),  # 90 %
        Auslastungsmonat(
            mitarbeiter=bert, jahr=2026, monat=9, abrechenbare_stunden=70.0, interne_stunden=30.0
        ),  # 70 %
    )

    assert anteile_fakturierbarer_arbeit(monate) == (0.9, 0.7)


def test_anteile_fakturierbarer_arbeit_ueberspringt_nur_ohne_gebuchte_zeit() -> None:
    anna = _mitarbeiter_mit_wochenstunden(8.0)
    bert = _mitarbeiter_mit_wochenstunden(8.0)
    carla = _mitarbeiter_mit_wochenstunden(8.0)
    monate = (
        Auslastungsmonat(
            mitarbeiter=anna, jahr=2026, monat=9, abrechenbare_stunden=90.0, interne_stunden=10.0
        ),
        Auslastungsmonat(mitarbeiter=bert, jahr=2026, monat=9),  # keine gebuchte Zeit - fehlt
        # Carla hat keine abrechenbare Stunde in diesem Monat (0 % fakturierbar) -
        # anders als bei FakturierbareArbeitBandbreite/
        # durchschnittlicher_anteil_fakturierbarer_arbeit kein Ausreisser hier, bleibt
        # also enthalten (siehe Moduldocstring).
        Auslastungsmonat(mitarbeiter=carla, jahr=2026, monat=9, interne_stunden=5.0),
    )

    assert anteile_fakturierbarer_arbeit(monate) == (0.9, 0.0)


def test_durchschnittlicher_anteil_fakturierbarer_arbeit_ignoriert_ausschliesslich_interne() -> (
    None
):
    anna = _mitarbeiter_mit_wochenstunden(8.0)
    bert = _mitarbeiter_mit_wochenstunden(8.0)
    monate = (
        Auslastungsmonat(
            mitarbeiter=anna, jahr=2026, monat=9, abrechenbare_stunden=90.0, interne_stunden=10.0
        ),
        # Bert hat in diesem Monat gar keine abrechenbare Stunde - ein Ausreisser, der
        # den Durchschnitt trotz Gewichtung auf 0 % ziehen wuerde, bliebe er drin.
        Auslastungsmonat(mitarbeiter=bert, jahr=2026, monat=9, interne_stunden=5.0),
    )

    ergebnis = durchschnittlicher_anteil_fakturierbarer_arbeit(monate)

    assert ergebnis == 0.9  # nur Annas Wert, Bert vollstaendig ausgeschlossen


def test_fakturierbare_arbeit_verteilung_aus_auslastungen_nutzt_anteile_fakturierbarer_arbeit() -> (
    None
):
    anna = _mitarbeiter_mit_wochenstunden(8.0)
    monate = (
        Auslastungsmonat(
            mitarbeiter=anna, jahr=2026, monat=9, abrechenbare_stunden=90.0, interne_stunden=10.0
        ),
    )

    verteilung = FakturierbareArbeitVerteilung.aus_auslastungen(monate)

    assert verteilung.werte == (0.9,)
    assert verteilung.anzahl == 1
    assert verteilung.vorhanden


def test_fakturierbare_arbeit_verteilung_ohne_werte_ist_nicht_vorhanden() -> None:
    verteilung = FakturierbareArbeitVerteilung()

    assert verteilung.anzahl == 0
    assert not verteilung.vorhanden


def test_fakturierbare_arbeit_verteilung_ziehen_array_zieht_mit_zuruecklegen() -> None:
    verteilung = FakturierbareArbeitVerteilung(werte=(0.2,))

    gezogen = verteilung.ziehen_array((3, 4), np.random.default_rng(0))

    assert gezogen.shape == (3, 4)
    assert (gezogen == 0.2).all()


def test_fakturierbare_arbeit_verteilung_ziehen_array_aus_leerer_verteilung_wirft() -> None:
    verteilung = FakturierbareArbeitVerteilung()

    with pytest.raises(ValueError, match="leeren Verteilung"):
        verteilung.ziehen_array((1, 1), np.random.default_rng(0))
