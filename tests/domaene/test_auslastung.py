"""Tests fuer domaene.auslastung: reine Fachlogik, ohne Netzzugriff."""

from __future__ import annotations

from umsatzprognose.domaene.auslastung import (
    Auslastungsmonat,
    Auslastungssumme,
    InterneArbeitBandbreite,
    durchschnittlicher_anteil_interner_arbeit,
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


def test_anteil_interner_arbeit_bezieht_sich_auf_gebuchte_zeit_nicht_kapazitaet() -> None:
    # 20h intern von insgesamt 100h gebuchter Zeit (20 intern + 80 abrechenbar) - die
    # verfuegbare Kapazitaet (anders als bei quote) spielt hier keine Rolle.
    anna = _mitarbeiter_mit_wochenstunden(8.0)
    monat = Auslastungsmonat(
        mitarbeiter=anna, jahr=2026, monat=9, abrechenbare_stunden=80.0, interne_stunden=20.0
    )

    assert monat.anteil_interner_arbeit == 0.2


def test_anteil_interner_arbeit_ohne_gebuchte_zeit_ist_none() -> None:
    anna = _mitarbeiter_mit_wochenstunden(8.0)
    monat = Auslastungsmonat(mitarbeiter=anna, jahr=2026, monat=9)

    assert monat.anteil_interner_arbeit is None


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
    assert summe.anteil_interner_arbeit == 40.0 / 200.0


def test_interne_arbeit_bandbreite_je_monat_ueber_mehrere_personen() -> None:
    anna = _mitarbeiter_mit_wochenstunden(8.0)
    bert = _mitarbeiter_mit_wochenstunden(8.0)
    monate = (
        Auslastungsmonat(
            mitarbeiter=anna, jahr=2026, monat=9, abrechenbare_stunden=90.0, interne_stunden=10.0
        ),  # 10%
        Auslastungsmonat(
            mitarbeiter=bert, jahr=2026, monat=9, abrechenbare_stunden=70.0, interne_stunden=30.0
        ),  # 30%
    )

    (bandbreite,) = InterneArbeitBandbreite.je_monat(monate)

    assert (bandbreite.jahr, bandbreite.monat) == (2026, 9)
    assert bandbreite.minimum == 0.1
    assert bandbreite.maximum == 0.3
    assert bandbreite.durchschnitt == 0.2
    assert bandbreite.anzahl_personen == 2


def test_interne_arbeit_bandbreite_ueberspringt_personen_ohne_gebuchte_zeit() -> None:
    anna = _mitarbeiter_mit_wochenstunden(8.0)
    bert = _mitarbeiter_mit_wochenstunden(8.0)
    monate = (
        Auslastungsmonat(
            mitarbeiter=anna, jahr=2026, monat=9, abrechenbare_stunden=90.0, interne_stunden=10.0
        ),
        Auslastungsmonat(mitarbeiter=bert, jahr=2026, monat=9),  # keine gebuchte Zeit
    )

    (bandbreite,) = InterneArbeitBandbreite.je_monat(monate)

    assert bandbreite.anzahl_personen == 1


def test_interne_arbeit_bandbreite_ueberspringt_ausschliesslich_interne_personen() -> None:
    anna = _mitarbeiter_mit_wochenstunden(8.0)
    bert = _mitarbeiter_mit_wochenstunden(8.0)
    monate = (
        Auslastungsmonat(
            mitarbeiter=anna, jahr=2026, monat=9, abrechenbare_stunden=90.0, interne_stunden=10.0
        ),
        # Bert hat keine abrechenbare Stunde in diesem Monat (100% intern) - ein
        # Ausreisser, der Minimum/Maximum sonst auf 100% ziehen wuerde.
        Auslastungsmonat(mitarbeiter=bert, jahr=2026, monat=9, interne_stunden=5.0),
    )

    (bandbreite,) = InterneArbeitBandbreite.je_monat(monate)

    assert bandbreite.anzahl_personen == 1
    assert bandbreite.minimum == bandbreite.maximum == bandbreite.durchschnitt == 0.1


def test_interne_arbeit_bandbreite_laesst_monat_ganz_ohne_gebuchte_zeit_weg() -> None:
    anna = _mitarbeiter_mit_wochenstunden(8.0)
    monate = (Auslastungsmonat(mitarbeiter=anna, jahr=2026, monat=9),)

    assert InterneArbeitBandbreite.je_monat(monate) == ()


def test_durchschnittlicher_anteil_interner_arbeit_gewichtet_nach_gebuchter_zeit() -> None:
    anna = _mitarbeiter_mit_wochenstunden(8.0)
    bert = _mitarbeiter_mit_wochenstunden(8.0)
    monate = (
        # Anna: 10h intern von 100h (10%) - viel gebuchte Zeit, soll staerker wiegen.
        Auslastungsmonat(
            mitarbeiter=anna, jahr=2026, monat=9, abrechenbare_stunden=90.0, interne_stunden=10.0
        ),
        # Bert: 8h intern von 10h (80%) - wenig gebuchte Zeit, ein reiner Durchschnitt
        # der beiden Anteile (10% und 80%) waere durch diesen Ausreisser verzerrt. Noch
        # keine ausschliesslich interne Arbeit (Bert hat 2h abrechenbar), zaehlt also
        # mit - siehe den Test unten fuer den Fall ganz ohne abrechenbare Stunde.
        Auslastungsmonat(
            mitarbeiter=bert, jahr=2026, monat=9, abrechenbare_stunden=2.0, interne_stunden=8.0
        ),
    )

    ergebnis = durchschnittlicher_anteil_interner_arbeit(monate)

    assert ergebnis == 18.0 / 110.0


def test_durchschnittlicher_anteil_interner_arbeit_ohne_gebuchte_zeit_ist_none() -> None:
    assert durchschnittlicher_anteil_interner_arbeit(()) is None


def test_durchschnittlicher_anteil_interner_arbeit_ignoriert_ausschliesslich_interne() -> None:
    anna = _mitarbeiter_mit_wochenstunden(8.0)
    bert = _mitarbeiter_mit_wochenstunden(8.0)
    monate = (
        Auslastungsmonat(
            mitarbeiter=anna, jahr=2026, monat=9, abrechenbare_stunden=90.0, interne_stunden=10.0
        ),
        # Bert hat in diesem Monat gar keine abrechenbare Stunde - ein Ausreisser, der
        # den Durchschnitt trotz Gewichtung auf 100% ziehen wuerde, bliebe er drin.
        Auslastungsmonat(mitarbeiter=bert, jahr=2026, monat=9, interne_stunden=5.0),
    )

    ergebnis = durchschnittlicher_anteil_interner_arbeit(monate)

    assert ergebnis == 0.1  # nur Annas Wert, Bert vollstaendig ausgeschlossen
