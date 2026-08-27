"""Tests fuer schulungen.schulungen: Parsing und Repository, ohne Netzzugriff.

Kein Test spricht mit der echten Google Sheets API - statt eines echten
``SchulungenSheetsClient`` bekommt das Repository einen Fake mit derselben
``werte()``-Schnittstelle. Alle Beispielwerte (IDs, Beträge, Jahre) sind frei erfunden.
"""

from __future__ import annotations

from datetime import date

import pytest

from umsatzprognose.schulungen.schulungen import (
    SchulungenRepository,
    _benoetigte_jahre,
    _euro_parsen,
    _zeilen_zu_terminen,
)

KOPFZEILE = ["Schulung", "Jahr", "Monat", "Trainer", "Umsatz gesamt", "Bemerkungen"]


class FakeClient:
    """Liefert je Spreadsheet-ID feste Zeilen, oder wirft, wenn konfiguriert."""

    def __init__(self, antworten: dict[str, list[list[str]] | Exception]) -> None:
        self._antworten = antworten

    def werte(self, spreadsheet_id: str, bereich: str = "") -> list[list[str]]:
        antwort = self._antworten[spreadsheet_id]
        if isinstance(antwort, Exception):
            raise antwort
        return antwort


@pytest.mark.parametrize(
    ("text", "erwartet"),
    [
        ("12.345,67 €", 12345.67),
        ("1.234,56€", 1234.56),
        ("0 €", 0.0),
        ("500 €", 500.0),
        ("", 0.0),
    ],
)
def test_euro_parsen(text: str, erwartet: float) -> None:
    assert _euro_parsen(text) == pytest.approx(erwartet)


def test_zeilen_zu_terminen_findet_spalten_ueber_die_kopfzeile() -> None:
    zeilen = [
        KOPFZEILE,
        ["Python-Grundkurs", "2026", "10", "A. Beispiel", "1.500,00 €", ""],
        ["Python-Grundkurs", "2026", "10", "B. Beispiel", "750,00 €", "abgesagt"],
    ]
    termine = _zeilen_zu_terminen(zeilen)
    assert [(t.jahr, t.monat, t.umsatz) for t in termine] == [
        (2026, 10, 1500.0),
        (2026, 10, 750.0),
    ]


def test_zeilen_zu_terminen_ueberspringt_zeilen_ohne_jahr_oder_monat() -> None:
    zeilen = [KOPFZEILE, ["Python-Grundkurs", "", "", "", "0,00 €", ""]]
    assert _zeilen_zu_terminen(zeilen) == []


def test_zeilen_zu_terminen_ohne_zeilen_ist_leer() -> None:
    assert _zeilen_zu_terminen([]) == []


def test_zeilen_zu_terminen_wirft_bei_fehlenden_spalten() -> None:
    with pytest.raises(ValueError, match="Umsatz gesamt"):
        _zeilen_zu_terminen([["Schulung", "Jahr"]])


@pytest.mark.parametrize(
    ("stichtag", "horizont_monate", "erwartet"),
    [
        (date(2026, 9, 15), 3, (2026,)),
        (date(2026, 11, 1), 3, (2026, 2027)),
        (date(2026, 12, 1), 1, (2026,)),
    ],
)
def test_benoetigte_jahre(stichtag: date, horizont_monate: int, erwartet: tuple[int, ...]) -> None:
    assert _benoetigte_jahre(stichtag, horizont_monate) == erwartet


def test_laden_fuehrt_mehrere_jahre_zusammen() -> None:
    client = FakeClient(
        {
            "sheet-2026": [KOPFZEILE, ["Kurs A", "2026", "12", "", "1.000,00 €", ""]],
            "sheet-2027": [KOPFZEILE, ["Kurs B", "2027", "1", "", "2.000,00 €", ""]],
        }
    )
    repository = SchulungenRepository(client, {2026: "sheet-2026", 2027: "sheet-2027"})
    plan = repository.laden(date(2026, 11, 1), horizont_monate=3)

    assert plan.umsatz_je_monat([(2026, 12), (2027, 1)]) == [1000.0, 2000.0]
    assert plan.hinweise([(2026, 12), (2027, 1)]) == ()


def test_laden_mit_leerer_datei_liefert_keine_termine_und_keinen_hinweis() -> None:
    client = FakeClient({"sheet-2026": [KOPFZEILE]})
    repository = SchulungenRepository(client, {2026: "sheet-2026"})
    plan = repository.laden(date(2026, 9, 15), horizont_monate=1)

    assert plan.termine == ()
    assert plan.abbildungshinweise == ()


def test_laden_meldet_nicht_konfiguriertes_jahr_als_hinweis() -> None:
    repository = SchulungenRepository(FakeClient({}), {})
    plan = repository.laden(date(2026, 9, 15), horizont_monate=1)

    assert len(plan.abbildungshinweise) == 1
    assert "2026" in plan.abbildungshinweise[0].text
    assert "TRAINING_SHEET_ID" in plan.abbildungshinweise[0].text


def test_laden_meldet_lesefehler_als_hinweis_statt_absturz() -> None:
    client = FakeClient({"sheet-2026": RuntimeError("kein Zugriff")})
    repository = SchulungenRepository(client, {2026: "sheet-2026"})
    plan = repository.laden(date(2026, 9, 15), horizont_monate=1)

    assert plan.termine == ()
    assert len(plan.abbildungshinweise) == 1
    assert "2026" in plan.abbildungshinweise[0].text
