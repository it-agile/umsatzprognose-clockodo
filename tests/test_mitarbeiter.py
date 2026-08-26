"""Tests zur Person und ihrer vereinbarten Arbeitszeit."""

from __future__ import annotations

from datetime import date

from umsatzprognose.domaene.mitarbeiter import Abwesenheit, Feiertag, Mitarbeiter, Wochenarbeitszeit

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


def test_feiertage_bleiben_ohne_hinterlegung_leer():
    person = Mitarbeiter(id=1)
    assert person.feiertage == ()

    person_mit_feiertag = Mitarbeiter(
        id=1, feiertage=(Feiertag(datum=date(2026, 12, 24), halber_tag=True, name="Heiligabend"),)
    )
    assert person_mit_feiertag.feiertage[0].halber_tag
