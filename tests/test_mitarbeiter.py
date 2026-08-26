"""Tests zur Person und ihrer vereinbarten Arbeitszeit."""

from __future__ import annotations

from datetime import date

from umsatzprognose.domaene import Mitarbeiter, Wochenarbeitszeit
from umsatzprognose.domaene.mitarbeiter import Abwesenheit, Feiertag

SIEBEN_STUNDEN = (7.0, 7.0, 7.0, 7.0, 7.0, 0.0, 0.0)
ACHT_STUNDEN = (8.0, 8.0, 8.0, 8.0, 8.0, 0.0, 0.0)


def test_wochenstunden_sind_die_summe_der_wochentage():
    assert Wochenarbeitszeit(SIEBEN_STUNDEN, gueltig_ab=date(2023, 6, 14)).wochenstunden == 35.0


def test_gueltigkeit_beachtet_beide_grenzen():
    alt = Wochenarbeitszeit(ACHT_STUNDEN, date(2020, 1, 1), date(2023, 6, 13))
    assert alt.gilt_am(date(2023, 6, 13))
    assert not alt.gilt_am(date(2023, 6, 14))
    assert not alt.gilt_am(date(2019, 12, 31))


def test_die_am_stichtag_gueltige_vereinbarung_gewinnt():
    person = Mitarbeiter(
        id=1,
        arbeitszeiten=(
            Wochenarbeitszeit(ACHT_STUNDEN, date(2020, 1, 1), date(2023, 6, 13)),
            Wochenarbeitszeit(SIEBEN_STUNDEN, date(2023, 6, 14)),
        ),
    )
    assert person.wochenstunden(date(2026, 8, 24)) == 35.0
    assert person.wochenstunden(date(2021, 5, 1)) == 40.0


def test_bei_ueberlappung_gilt_die_zuletzt_begonnene():
    # In dieser Installation kam der Fall nicht vor, die Reihenfolge der Antwort darf
    # aber nicht entscheiden, welche Sollzeit gilt.
    person = Mitarbeiter(
        id=1,
        arbeitszeiten=(
            Wochenarbeitszeit(SIEBEN_STUNDEN, date(2024, 1, 1)),
            Wochenarbeitszeit(ACHT_STUNDEN, date(2020, 1, 1)),
        ),
    )
    assert person.wochenstunden(date(2026, 8, 24)) == 35.0


def test_ohne_hinterlegte_sollzeit_bleibt_es_bei_none():
    assert Mitarbeiter(id=1).wochenstunden(date(2026, 8, 24)) is None


def test_genehmigt_ist_nur_status_approved():
    # AbsenceStatus laut clocodo-api.yaml: 0 Enquired, 1 Approved, 2 Declined,
    # 3 ApprovalCancelled, 4 Cancelled.
    genehmigt = Abwesenheit(
        mitarbeiter_id=1, beginnt=date(2026, 9, 1), endet=date(2026, 9, 1), typ=1, status=1
    )
    unbestaetigt = Abwesenheit(
        mitarbeiter_id=1, beginnt=date(2026, 9, 1), endet=date(2026, 9, 1), typ=1, status=0
    )

    assert genehmigt.genehmigt
    assert not unbestaetigt.genehmigt


def _abwesenheit(typ: int) -> Abwesenheit:
    return Abwesenheit(
        mitarbeiter_id=1, beginnt=date(2026, 9, 1), endet=date(2026, 9, 1), typ=typ, status=1
    )


def test_gilt_als_abwesend_ist_nur_urlaub_und_krankheit():
    # AbsenceType laut clocodo-api.yaml: 1 RegularHoliday (Urlaub), 4 SickSelf,
    # 5 SickChild, 11 SickSelfUnpaid, 12 SickChildUnpaid, 15 SickSelfWithCertificate -
    # alle fuenf Krankheitsvarianten zaehlen laut Entscheidung 26.08.2026 als Krankheit.
    for urlaub_oder_krankheit in (1, 4, 5, 11, 12, 15):
        assert _abwesenheit(urlaub_oder_krankheit).gilt_als_abwesend

    # Sonderurlaub, Ueberstundenabbau, Home office, Quarantaene zaehlen nach dieser
    # Entscheidung ausdruecklich nicht, auch wenn das fachlich diskutabel ist.
    for anderer_typ in (2, 3, 8, 9, 13):
        assert not _abwesenheit(anderer_typ).gilt_als_abwesend


def test_feiertage_bleiben_ohne_hinterlegung_leer():
    person = Mitarbeiter(id=1)
    assert person.feiertage == ()

    person_mit_feiertag = Mitarbeiter(
        id=1, feiertage=(Feiertag(datum=date(2026, 12, 24), halber_tag=True, name="Heiligabend"),)
    )
    assert person_mit_feiertag.feiertage[0].halber_tag


def test_feiertagsstunden_ignoriert_den_halben_tag():
    # Entscheidung 26.08.2026: ein halber Feiertag zaehlt wie ein ganzer, siehe
    # Modul-Docstring - die Kollegen nehmen den Rest in aller Regel als Urlaub.
    person = Mitarbeiter(
        id=1,
        arbeitszeiten=(Wochenarbeitszeit(SIEBEN_STUNDEN, date(2020, 1, 1)),),
        feiertage=(
            Feiertag(datum=date(2026, 10, 1), halber_tag=False, name="Ganzer Feiertag"),
            Feiertag(datum=date(2026, 12, 24), halber_tag=True, name="Heiligabend"),
        ),
    )
    assert person.feiertagsstunden(2026, 10) == 7.0
    assert person.feiertagsstunden(2026, 12) == 7.0


def test_feiertag_am_wochenende_wirkt_von_selbst_nicht():
    # 2026-10-03 (Tag der Deutschen Einheit) faellt auf einen Samstag - dort steht
    # ohnehin keine Sollstunde, es gibt also nichts abzuziehen.
    person = Mitarbeiter(
        id=1,
        arbeitszeiten=(Wochenarbeitszeit(SIEBEN_STUNDEN, date(2020, 1, 1)),),
        feiertage=(Feiertag(datum=date(2026, 10, 3), halber_tag=False),),
    )
    assert person.feiertagsstunden(2026, 10) == 0.0


def test_feiertagsstunden_ohne_sollzeit_bleibt_null():
    person = Mitarbeiter(id=1, feiertage=(Feiertag(datum=date(2026, 10, 1), halber_tag=False),))
    assert person.feiertagsstunden(2026, 10) == 0.0


def test_feiertage_ausserhalb_des_monats_zaehlen_nicht():
    person = Mitarbeiter(
        id=1,
        arbeitszeiten=(Wochenarbeitszeit(SIEBEN_STUNDEN, date(2020, 1, 1)),),
        feiertage=(Feiertag(datum=date(2026, 10, 1), halber_tag=False),),
    )
    assert person.feiertagsstunden(2026, 11) == 0.0


def _urlaub_mit_status(status: int) -> Abwesenheit:
    return Abwesenheit(
        mitarbeiter_id=1, beginnt=date(2026, 9, 1), endet=date(2026, 9, 1), typ=1, status=status
    )


def test_zaehlt_als_kapazitaetsabzug_beachtet_typ_und_status():
    # Entscheidung 26.08.2026: der Status zaehlt schon ab "beantragt" (Enquired), nicht
    # erst ab "genehmigt" (Approved) - Declined/ApprovalCancelled/Cancelled nicht mehr.
    assert _urlaub_mit_status(0).zaehlt_als_kapazitaetsabzug  # Enquired
    assert _urlaub_mit_status(1).zaehlt_als_kapazitaetsabzug  # Approved
    assert not _urlaub_mit_status(2).zaehlt_als_kapazitaetsabzug  # Declined
    assert not _urlaub_mit_status(3).zaehlt_als_kapazitaetsabzug  # ApprovalCancelled
    assert not _urlaub_mit_status(4).zaehlt_als_kapazitaetsabzug  # Cancelled

    # Passender Status, aber ein Typ, der nicht als Abwesenheit zaehlt (Home office).
    home_office = Abwesenheit(
        mitarbeiter_id=1, beginnt=date(2026, 9, 1), endet=date(2026, 9, 1), typ=8, status=1
    )
    assert not home_office.zaehlt_als_kapazitaetsabzug


def test_verfuegbare_kapazitaet_ohne_feiertage_und_abwesenheit():
    # Oktober 2026: 22 Wochentage Montag-Freitag a 7 Stunden.
    person = Mitarbeiter(id=1, arbeitszeiten=(Wochenarbeitszeit(SIEBEN_STUNDEN, date(2020, 1, 1)),))
    assert person.verfuegbare_kapazitaet(2026, 10) == 22 * 7.0


def test_verfuegbare_kapazitaet_zieht_feiertage_ab():
    person = Mitarbeiter(
        id=1,
        arbeitszeiten=(Wochenarbeitszeit(SIEBEN_STUNDEN, date(2020, 1, 1)),),
        feiertage=(Feiertag(datum=date(2026, 10, 1), halber_tag=False),),  # Donnerstag
    )
    assert person.verfuegbare_kapazitaet(2026, 10) == 22 * 7.0 - 7.0


def test_verfuegbare_kapazitaet_zieht_geplante_abwesenheit_ab():
    person = Mitarbeiter(
        id=1,
        arbeitszeiten=(Wochenarbeitszeit(SIEBEN_STUNDEN, date(2020, 1, 1)),),
        abwesenheiten=(
            # Mo 05.10. bis Fr 09.10., fuenf Wochentage, genehmigter Urlaub.
            Abwesenheit(
                mitarbeiter_id=1,
                beginnt=date(2026, 10, 5),
                endet=date(2026, 10, 9),
                typ=1,
                status=1,
            ),
        ),
    )
    assert person.verfuegbare_kapazitaet(2026, 10) == 22 * 7.0 - 5 * 7.0


def test_verfuegbare_kapazitaet_ignoriert_nicht_zaehlende_abwesenheit():
    person = Mitarbeiter(
        id=1,
        arbeitszeiten=(Wochenarbeitszeit(SIEBEN_STUNDEN, date(2020, 1, 1)),),
        abwesenheiten=(
            # Abgelehnter Urlaub - zaehlt nicht, siehe zaehlt_als_kapazitaetsabzug.
            Abwesenheit(
                mitarbeiter_id=1,
                beginnt=date(2026, 10, 5),
                endet=date(2026, 10, 9),
                typ=1,
                status=2,
            ),
        ),
    )
    assert person.verfuegbare_kapazitaet(2026, 10) == 22 * 7.0


def test_verfuegbare_kapazitaet_zaehlt_einen_ueberschneidenden_tag_nur_einmal():
    # Urlaub ueber Weihnachten (21.-31.12.), der den Feiertag am 25.12. einschliesst -
    # ein realistischer Fall, kein Sonderfall. Drei getrennte Abzuege (Sollstunden minus
    # Feiertage minus Abwesenheit) wuerden den 25.12. doppelt abziehen; taggenau gerechnet
    # zaehlt er nur einmal.
    person = Mitarbeiter(
        id=1,
        arbeitszeiten=(Wochenarbeitszeit(SIEBEN_STUNDEN, date(2020, 1, 1)),),
        feiertage=(Feiertag(datum=date(2026, 12, 25), halber_tag=False, name="1. Weihnachtstag"),),
        abwesenheiten=(
            Abwesenheit(
                mitarbeiter_id=1,
                beginnt=date(2026, 12, 21),
                endet=date(2026, 12, 31),
                typ=1,
                status=1,
            ),
        ),
    )
    # Dezember 2026: 23 Wochentage a 7h = 161h, davon 9 Wochentage (21.-31.12., inkl.
    # Feiertag am 25.) durch den Urlaub belegt = 63h Abzug, nicht 63h + 7h.
    assert person.verfuegbare_kapazitaet(2026, 12) == 23 * 7.0 - 9 * 7.0


def test_verfuegbare_kapazitaet_kappt_abwesenheit_an_monatsgrenzen():
    # Abwesenheit reicht vom 28.11. bis 03.12. - fuer Dezember zaehlen nur die drei Tage
    # ab dem 1., die zwei Novembertage nicht.
    person = Mitarbeiter(
        id=1,
        arbeitszeiten=(Wochenarbeitszeit(SIEBEN_STUNDEN, date(2020, 1, 1)),),
        abwesenheiten=(
            Abwesenheit(
                mitarbeiter_id=1,
                beginnt=date(2026, 11, 28),
                endet=date(2026, 12, 3),
                typ=1,
                status=1,
            ),
        ),
    )
    # 01.-03.12.2026 sind Dienstag bis Donnerstag, drei Wochentage.
    assert person.verfuegbare_kapazitaet(2026, 12) == 23 * 7.0 - 3 * 7.0


def test_feiertagsstunden_nutzt_die_am_feiertag_gueltige_sollzeit():
    # Ein Wechsel mitten im Monat: der Feiertag am 1. zaehlt noch mit der alten
    # Sollzeit, der am 15. schon mit der neuen - je Feiertag einzeln nachgeschlagen,
    # nicht einmal fuer den ganzen Monat.
    person = Mitarbeiter(
        id=1,
        arbeitszeiten=(
            Wochenarbeitszeit(ACHT_STUNDEN, date(2020, 1, 1), date(2026, 10, 14)),
            Wochenarbeitszeit(SIEBEN_STUNDEN, date(2026, 10, 15)),
        ),
        feiertage=(
            Feiertag(datum=date(2026, 10, 1), halber_tag=False),
            Feiertag(datum=date(2026, 10, 15), halber_tag=False),
        ),
    )
    assert person.feiertagsstunden(2026, 10) == 8.0 + 7.0
