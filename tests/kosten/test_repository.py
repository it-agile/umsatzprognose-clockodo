"""Tests fuer kosten.kosten: Parsing und Repository, ohne Netzzugriff.

Kein Test spricht mit der echten Google Sheets API - statt eines echten
``GoogleSheetsClient`` bekommt das Repository einen Fake mit derselben
``werte()``-Schnittstelle. Alle Beispielwerte (IDs, Beträge, Jahre) sind frei erfunden.
"""

from __future__ import annotations

from datetime import date

import pytest

from umsatzprognose.domaene.kosten import Erfasst, Geschaetzt
from umsatzprognose.google_sheets import kopfzeile_finden
from umsatzprognose.kosten.kosten import (
    SPALTE_ALLGEMEINKOSTEN,
    SPALTE_GESAMTKOSTEN,
    KostenRepository,
    _monat_parsen,
    _monat_spalte_ermitteln,
    _monatsfolge,
    _zeilen_zu_posten,
)

KOSTEN_PFLICHTSPALTEN = {SPALTE_GESAMTKOSTEN, SPALTE_ALLGEMEINKOSTEN}

KOPFZEILE = ["Monat", "Gehälter", "Spesen", "Allgemeinkosten", "Gesamtkosten"]
KOPFZEILE_MIT_ERFASSUNG = [*KOPFZEILE, "Kostenerfassung"]


class FakeClient:
    """Liefert je Spreadsheet-ID feste Zeilen, oder wirft, wenn konfiguriert."""

    def __init__(self, antworten: dict[str, list[list[str]] | Exception]) -> None:
        self._antworten = antworten

    def werte(self, spreadsheet_id: str, bereich: str) -> list[list[str]]:
        antwort = self._antworten[spreadsheet_id]
        if isinstance(antwort, Exception):
            raise antwort
        return antwort


@pytest.mark.parametrize(
    ("text", "erwartet"),
    [
        ("Januar", 1),
        ("  Februar  ", 2),
        ("märz", 3),
        ("DEZEMBER", 12),
        ("Foo", None),
        ("", None),
    ],
)
def test_monat_parsen(text: str, erwartet: int | None) -> None:
    assert _monat_parsen(text) == erwartet


def test_zeilen_zu_posten_findet_spalten_ueber_die_kopfzeile() -> None:
    zeilen = [
        KOPFZEILE,
        ["Januar", "100,00 €", "800,00 €", "50,00 €", "950,00 €"],
        ["Februar", "0,00 €", "800,00 €", "0,00 €", "800,00 €"],
    ]
    posten = _zeilen_zu_posten(zeilen, 2026)
    assert [(p.jahr, p.monat, p.kosten) for p in posten] == [
        (2026, 1, 950.0),
        (2026, 2, 800.0),
    ]


def test_zeilen_zu_posten_ersetzt_nur_den_allgemeinkosten_anteil_bei_erfassung() -> None:
    zeilen = [
        KOPFZEILE_MIT_ERFASSUNG,
        # Gehälter, Spesen, Allgemeinkosten, Gesamtkosten, Kostenerfassung
        ["Januar", "100,00 €", "800,00 €", "50,00 €", "950,00 €", "120,00 €"],
        ["Februar", "0,00 €", "800,00 €", "0,00 €", "800,00 €", ""],
    ]
    posten = _zeilen_zu_posten(zeilen, 2026)
    assert [(p.pauschale, p.allgemeinkosten, p.erfassung, p.kosten) for p in posten] == [
        (950.0, 50.0, Erfasst(120.0), 1020.0),  # 950 - 50 + 120
        (800.0, 0.0, Geschaetzt(), 800.0),
    ]


def test_zeilen_zu_posten_ohne_kostenerfassung_spalte_faellt_immer_auf_die_pauschale_zurueck() -> (
    None
):
    zeilen = [KOPFZEILE, ["Januar", "100,00 €", "800,00 €", "50,00 €", "950,00 €"]]
    posten = _zeilen_zu_posten(zeilen, 2026)
    assert posten[0].erfassung == Geschaetzt()
    assert posten[0].kosten == 950.0


def test_zeilen_zu_posten_ueberspringt_zeilen_ohne_erkennbaren_monat() -> None:
    zeilen = [KOPFZEILE, ["", "", "", "", "0,00 €"], ["Irgendwas", "", "", "", "0,00 €"]]
    assert _zeilen_zu_posten(zeilen, 2026) == []


def test_zeilen_zu_posten_findet_monatsspalte_ohne_kopfzeilen_bezeichnung() -> None:
    # Kopfzeile ohne Bezeichnung fuer die erste Spalte - wie bei manchen Jahrgaengen.
    zeilen = [
        ["", "Gehälter", "Spesen", "Allgemeinkosten", "Gesamtkosten"],
        ["Januar", "", "", "50,00 €", "950,00 €"],
        ["Februar", "", "", "0,00 €", "800,00 €"],
    ]
    posten = _zeilen_zu_posten(zeilen, 2022)
    assert [(p.jahr, p.monat, p.kosten) for p in posten] == [
        (2022, 1, 950.0),
        (2022, 2, 800.0),
    ]


def test_zeilen_zu_posten_findet_monatsspalte_an_verschobener_position() -> None:
    # Der Bereich kann jahrgangsweise leicht verschoben sein - die Monatsspalte muss
    # nicht an Position 0 stehen, auch nicht ohne eigene Kopfzeilen-Bezeichnung.
    zeilen = [
        ["Notiz", "", "Allgemeinkosten", "Gesamtkosten"],
        ["frei", "Januar", "50,00 €", "950,00 €"],
        ["frei", "Februar", "0,00 €", "800,00 €"],
    ]
    posten = _zeilen_zu_posten(zeilen, 2022)
    assert [(p.jahr, p.monat, p.kosten) for p in posten] == [
        (2022, 1, 950.0),
        (2022, 2, 800.0),
    ]


def test_kopfzeile_finden_ueberspringt_vorausgehende_tabelle() -> None:
    # Manche Jahrgaenge (z.B. 2022) haben im selben Zeilenbereich vor der eigentlichen
    # Monatsuebersicht noch eine andere Tabelle - deren Kopfzeile traegt teils
    # aehnliche, aber nicht beide Pflichtspalten (hier: "Allgemeinkosten" ohne
    # "Gesamtkosten").
    zeilen = [
        ["Jahr", "Mitarbeiter", "Allgemeinkosten", "Bemerkungen"],
        ["2022", "", "0,00 €", ""],
        ["2022", "", "0,00 €", ""],
        KOPFZEILE,
    ]
    zeile_index, index = kopfzeile_finden(zeilen, KOSTEN_PFLICHTSPALTEN)
    assert zeile_index == 3
    assert index["Gesamtkosten"] == KOPFZEILE.index("Gesamtkosten")


def test_kopfzeile_finden_ohne_treffer_wirft() -> None:
    with pytest.raises(ValueError, match="Gesamtkosten"):
        kopfzeile_finden([["Monat", "Reisekosten"]], KOSTEN_PFLICHTSPALTEN)


def test_zeilen_zu_posten_findet_kopfzeile_nach_vorausgehender_tabelle() -> None:
    zeilen = [
        ["Jahr", "Mitarbeiter", "Allgemeinkosten", "Bemerkungen"],
        ["2022", "", "0,00 €", ""],
        KOPFZEILE,
        ["Januar", "", "800,00 €", "50,00 €", "950,00 €"],
    ]
    posten = _zeilen_zu_posten(zeilen, 2022)
    assert [(p.jahr, p.monat, p.kosten) for p in posten] == [(2022, 1, 950.0)]


def test_monat_spalte_ermitteln_bevorzugt_die_kopfzeile() -> None:
    zeilen = [["Allgemeinkosten", "Monat"], ["50,00 €", "Januar"]]
    index = {"Allgemeinkosten": 0, "Monat": 1}
    assert _monat_spalte_ermitteln(zeilen, index) == 1


def test_monat_spalte_ermitteln_waehlt_die_spalte_mit_den_meisten_treffern() -> None:
    zeilen = [
        ["Notiz", "x"],
        ["Januar", "kein Monat"],
        ["Februar", "Marz"],  # nur ein Treffer in Spalte 1 ("Marz" ist kein gueltiger Monatsname)
    ]
    assert _monat_spalte_ermitteln(zeilen, index={}) == 0


def test_monat_spalte_ermitteln_ohne_treffer_wirft() -> None:
    zeilen = [["Notiz"], ["nichts hier"], ["auch nicht"]]
    with pytest.raises(ValueError, match="Monatsnamen"):
        _monat_spalte_ermitteln(zeilen, index={})


def test_zeilen_zu_posten_ohne_zeilen_ist_leer() -> None:
    assert _zeilen_zu_posten([], 2026) == []


def test_zeilen_zu_posten_wirft_bei_fehlenden_spalten() -> None:
    with pytest.raises(ValueError, match="Gesamtkosten"):
        _zeilen_zu_posten([["Monat", "Reisekosten"]], 2026)


@pytest.mark.parametrize(
    ("stichtag", "horizont_monate", "erwartet"),
    [
        (date(2026, 9, 15), 3, [(2026, 9), (2026, 10), (2026, 11)]),
        (date(2026, 11, 1), 3, [(2026, 11), (2026, 12), (2027, 1)]),
        (date(2026, 12, 1), 1, [(2026, 12)]),
    ],
)
def test_monatsfolge(stichtag: date, horizont_monate: int, erwartet: list[tuple[int, int]]) -> None:
    assert _monatsfolge(stichtag, horizont_monate) == erwartet


def test_laden_deckt_historie_und_prognosehorizont_ab() -> None:
    client = FakeClient(
        {
            "sheet-2026": [
                KOPFZEILE,
                ["November", "", "", "", "500,00 €"],
                ["Dezember", "", "", "", "600,00 €"],
            ],
            "sheet-2027": [KOPFZEILE, ["Januar", "", "", "", "700,00 €"]],
        }
    )
    repository = KostenRepository(client, {2026: "sheet-2026", 2027: "sheet-2027"})
    plan = repository.laden(
        stichtag=date(2026, 12, 1), horizont_monate=2, historie_monate=[(2026, 11)]
    )

    assert plan.kosten_je_monat([(2026, 11), (2026, 12), (2027, 1)]) == [500.0, 600.0, 700.0]
    assert plan.hinweise([(2026, 11), (2026, 12), (2027, 1)]) == ()


def test_laden_ohne_historie_deckt_nur_den_horizont_ab() -> None:
    client = FakeClient({"sheet-2026": [KOPFZEILE, ["September", "", "", "", "300,00 €"]]})
    repository = KostenRepository(client, {2026: "sheet-2026"})
    plan = repository.laden(stichtag=date(2026, 9, 15), horizont_monate=1)

    assert plan.kosten_je_monat([(2026, 9)]) == [300.0]


def test_laden_meldet_nicht_konfiguriertes_jahr_als_hinweis() -> None:
    repository = KostenRepository(FakeClient({}), {})
    plan = repository.laden(stichtag=date(2026, 9, 15), horizont_monate=1)

    assert len(plan.abbildungshinweise) == 1
    assert "2026" in plan.abbildungshinweise[0].text
    assert "KOSTEN_SHEET_IDS" in plan.abbildungshinweise[0].text


def test_fruehestes_konfiguriertes_jahr_ist_das_minimum() -> None:
    repository = KostenRepository(FakeClient({}), {2024: "x", 2022: "y", 2026: "z"})
    assert repository.fruehestes_konfiguriertes_jahr == 2022


def test_fruehestes_konfiguriertes_jahr_ohne_konfiguration_ist_none() -> None:
    assert KostenRepository(FakeClient({}), {}).fruehestes_konfiguriertes_jahr is None


def test_laden_meldet_lesefehler_als_hinweis_statt_absturz() -> None:
    client = FakeClient({"sheet-2026": RuntimeError("kein Zugriff")})
    repository = KostenRepository(client, {2026: "sheet-2026"})
    plan = repository.laden(stichtag=date(2026, 9, 15), horizont_monate=1)

    assert plan.posten == ()
    assert len(plan.abbildungshinweise) == 1
    assert "2026" in plan.abbildungshinweise[0].text
    # Nicht nur der Exceptiontyp, auch die Meldung - sonst bleibt die genaue Ursache
    # (etwa welche Spalten in _zeilen_zu_posten fehlten) beim Diagnostizieren unsichtbar.
    assert "RuntimeError: kein Zugriff" in plan.abbildungshinweise[0].text


def test_laden_meldet_fehlende_spalten_mit_der_konkreten_meldung_als_hinweis() -> None:
    client = FakeClient({"sheet-2022": [["Monat", "Gesamtkosten"]]})
    repository = KostenRepository(client, {2022: "sheet-2022"})
    plan = repository.laden(stichtag=date(2022, 9, 15), horizont_monate=1)

    assert len(plan.abbildungshinweise) == 1
    text = plan.abbildungshinweise[0].text
    assert "2022" in text
    assert "Allgemeinkosten" in text
