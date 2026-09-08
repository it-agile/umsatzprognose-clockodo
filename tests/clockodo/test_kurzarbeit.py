"""Tests zur Abbildung der Rohdaten fuer den Baustein Kurzarbeitsbereitschaft.

Frei erfundene IDs, Namen und Betraege - siehe Moduldocstring von ``conftest.py``.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from umsatzprognose.clockodo.client import EntryGroupV2

from conftest import client_mit_routen
from umsatzprognose.clockodo.kurzarbeit import (
    KURZARBEIT_AKTIV_VAR,
    KurzarbeitRepository,
    _abgeschlossene_monate,
    anzahl_ladeschritte,
    kurzarbeit_aktiv,
)

STICHTAG = date(2026, 9, 24)


def test_kurzarbeit_aktiv_ist_ohne_gesetzte_variable_aus(monkeypatch):
    monkeypatch.delenv(KURZARBEIT_AKTIV_VAR, raising=False)
    # use_dotenv=False: isoliert vom lokalen .env dieses Klons (siehe
    # ClockodoCredentials.aus_umgebung()-Tests fuer dasselbe Muster).
    assert kurzarbeit_aktiv(use_dotenv=False) is False


def test_kurzarbeit_aktiv_ist_bei_true_an(monkeypatch):
    monkeypatch.setenv(KURZARBEIT_AKTIV_VAR, "true")
    assert kurzarbeit_aktiv(use_dotenv=False) is True


def test_kurzarbeit_aktiv_laedt_env_datei(monkeypatch, tmp_path):
    monkeypatch.delenv(KURZARBEIT_AKTIV_VAR, raising=False)
    (tmp_path / ".env").write_text(f"{KURZARBEIT_AKTIV_VAR}=true\n")
    monkeypatch.chdir(tmp_path)

    assert kurzarbeit_aktiv() is True


def _benutzer_antwort() -> dict:
    return {
        "paging": {"current_page": 1, "count_pages": 1, "count_items": 2},
        "data": [
            {"id": 301, "name": "Anna Beispiel", "active": True},
            {"id": 302, "name": "Bert Muster", "active": True},
        ],
    }


def _entrygroups_person_monat(person_id: str, monat: str, *, duration: int, revenue: float) -> dict:
    return {
        "groups": [
            {
                "group": person_id,
                "name": "…",
                "duration": duration,
                "revenue": revenue,
                "grouped_by": "users_id",
                "sub_groups": [
                    {
                        "group": monat,
                        "name": monat,
                        "duration": duration,
                        "revenue": revenue,
                        "grouped_by": "month",
                    }
                ],
            }
        ]
    }


def _userreports_antwort(*, overtime_carryover: float, month_details: list[dict]) -> dict:
    return {
        "userreports": [
            {
                "users_id": 301,
                "overtime_carryover": overtime_carryover,
                "month_details": month_details,
            }
        ]
    }


def test_abgeschlossene_monate_schliesst_stichtagsmonat_aus():
    monate = _abgeschlossene_monate(date(2026, 9, 24), 3)

    assert monate == [(2026, 6), (2026, 7), (2026, 8)]


def test_anzahl_ladeschritte_ohne_jahreswechsel_im_horizont():
    # Juni bis August 2026 - ein einziges Kalenderjahr, also fuenf feste Zweige plus
    # ein /userreports-Abruf.
    assert anzahl_ladeschritte(date(2026, 9, 24), 3) == 5 + 1


def test_anzahl_ladeschritte_mit_jahreswechsel_im_horizont():
    # November/Dezember 2025 plus Januar 2026 - zwei Kalenderjahre, also fuenf feste
    # Zweige plus zwei /userreports-Abrufe.
    assert anzahl_ladeschritte(date(2026, 2, 15), 3) == 5 + 2


def test_abbilden_faellt_intern_extern_und_gesamt_stunden_zusammen():
    intern: list[EntryGroupV2] = [
        {
            "group": "301", "name": "…", "duration": 3600 * 40, "revenue": 0.0,
            "grouped_by": "users_id",
            "sub_groups": [
                {"group": "202608", "name": "202608", "duration": 3600 * 40,
                 "revenue": 0.0, "grouped_by": "month"},
            ],
        },
    ]  # fmt: skip
    ergebnis = KurzarbeitRepository.abbilden(
        [{"id": 301, "name": "Anna Beispiel", "active": True}],
        intern=intern,
        extern={(301, (2026, 8)): 120.0},
        gesamt={(301, (2026, 8)): 160.0},
        userreports_nach_jahr={},
        monate=[(2026, 8)],
    )

    (person,) = ergebnis[(2026, 8)]
    assert person.mitarbeiter_id == 301
    assert person.name == "Anna Beispiel"
    assert person.interne_stunden == 40.0
    assert person.externe_stunden == 120.0
    assert person.gesamt_stunden == 160.0
    assert person.unklassifizierte_stunden == 0.0


def test_abbilden_erzeugt_personenmonat_auch_ohne_gebuchte_stunde():
    # "keine gebuchte Stunde" muss von "keine Person" unterscheidbar bleiben.
    ergebnis = KurzarbeitRepository.abbilden(
        [{"id": 301, "name": "Anna Beispiel", "active": True}],
        intern=[],
        extern={},
        gesamt={},
        userreports_nach_jahr={},
        monate=[(2026, 8)],
    )

    (person,) = ergebnis[(2026, 8)]
    assert person.interne_stunden == 0.0
    assert person.gesamt_stunden == 0.0
    assert person.ueberstundenstand is None


def test_ueberstundenstand_wird_aus_carryover_und_kumulierter_monatssumme_gebildet():
    # overtime_carryover=5, Monat 1: +2 -> 7, Monat 2: -3 -> 4 (kumuliert zum Monatsende)
    userreports_nach_jahr = {
        2026: _userreports_antwort(
            overtime_carryover=5.0,
            month_details=[{"nr": 1, "diff": 2.0}, {"nr": 2, "diff": -3.0}],
        )["userreports"]
    }
    ergebnis = KurzarbeitRepository.abbilden(
        [{"id": 301, "name": "Anna Beispiel", "active": True}],
        intern=[],
        extern={},
        gesamt={},
        userreports_nach_jahr=userreports_nach_jahr,
        monate=[(2026, 1), (2026, 2)],
    )

    januar = next(p for p in ergebnis[(2026, 1)] if p.mitarbeiter_id == 301)
    februar = next(p for p in ergebnis[(2026, 2)] if p.mitarbeiter_id == 301)
    assert januar.ueberstundenstand == 7.0
    assert februar.ueberstundenstand == 4.0


def test_person_ohne_userreport_hat_keinen_ueberstundenstand():
    ergebnis = KurzarbeitRepository.abbilden(
        [{"id": 301, "name": "Anna Beispiel", "active": True}],
        intern=[],
        extern={},
        gesamt={},
        userreports_nach_jahr={2026: []},
        monate=[(2026, 1)],
    )

    (person,) = ergebnis[(2026, 1)]
    assert person.ueberstundenstand is None


def test_laden_ruft_die_erwarteten_endpunkte_gleichzeitig_ab():
    def entrygroups(request):
        billable = request.url.params.get("filter[billable]")
        gruppierung = tuple(request.url.params.get_list("grouping[]"))
        if gruppierung == ("users_id", "month") and billable is None:
            return _entrygroups_person_monat("301", "202608", duration=3600 * 160, revenue=0.0)
        antworten = {
            "0": _entrygroups_person_monat("301", "202608", duration=3600 * 40, revenue=0.0),
            "1": _entrygroups_person_monat("301", "202608", duration=3600 * 100, revenue=0.0),
            "2": _entrygroups_person_monat("301", "202608", duration=3600 * 20, revenue=0.0),
        }
        return antworten[billable]

    client, requests = client_mit_routen(
        {
            "/v3/users": _benutzer_antwort(),
            "/v2/entrygroups": entrygroups,
            "/userreports": _userreports_antwort(
                overtime_carryover=0.0, month_details=[{"nr": 8, "diff": 3.0}]
            ),
        }
    )

    ergebnis = KurzarbeitRepository(client).laden(stichtag=STICHTAG, anzahl_monate=1)

    august = ergebnis[(2026, 8)]
    anna = next(p for p in august if p.mitarbeiter_id == 301)
    assert anna.interne_stunden == 40.0
    assert anna.externe_stunden == 120.0  # 100 (abrechenbar) + 20 (fakturiert)
    assert anna.gesamt_stunden == 160.0
    assert anna.ueberstundenstand == 3.0
    bert = next(p for p in august if p.mitarbeiter_id == 302)
    assert bert.interne_stunden == 0.0  # keine Buchungen fuer Bert in den Fixtures

    aufgerufene_pfade = [r.url.path for r in requests]
    assert aufgerufene_pfade.count("/api/v2/entrygroups") == 4  # intern, 2x extern, ungefiltert
    assert aufgerufene_pfade.count("/api/userreports") == 1


def test_laden_meldet_fortschritt_je_zweig_statt_nur_am_ende():
    def entrygroups(request):
        billable = request.url.params.get("filter[billable]")
        gruppierung = tuple(request.url.params.get_list("grouping[]"))
        if gruppierung == ("users_id", "month") and billable is None:
            return _entrygroups_person_monat("301", "202608", duration=3600 * 160, revenue=0.0)
        antworten = {
            "0": _entrygroups_person_monat("301", "202608", duration=3600 * 40, revenue=0.0),
            "1": _entrygroups_person_monat("301", "202608", duration=3600 * 100, revenue=0.0),
            "2": _entrygroups_person_monat("301", "202608", duration=3600 * 20, revenue=0.0),
        }
        return antworten[billable]

    client, _requests = client_mit_routen(
        {
            "/v3/users": _benutzer_antwort(),
            "/v2/entrygroups": entrygroups,
            "/userreports": _userreports_antwort(
                overtime_carryover=0.0, month_details=[{"nr": 8, "diff": 3.0}]
            ),
        }
    )
    gemeldet: list[str] = []

    KurzarbeitRepository(client).laden(
        stichtag=STICHTAG, anzahl_monate=1, fortschritt=gemeldet.append
    )

    assert set(gemeldet) == {
        "Personen geladen",
        "Interne Stunden geladen",
        "Abrechenbare Stunden geladen",
        "Fakturierte Stunden geladen",
        "Gesamtstunden geladen",
        "Überstundenstand 2026 geladen",
    }
