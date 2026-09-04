"""Tests fuer schulungen.schulungen: Parsing und Repository, ohne Netzzugriff.

Kein Test spricht mit der echten Google Sheets API - statt eines echten
``GoogleSheetsClient`` bekommt das Repository einen Fake mit derselben
``werte()``-Schnittstelle. Alle Beispielwerte (IDs, Beträge, Jahre) sind frei erfunden.
"""

from __future__ import annotations

from datetime import date

import pytest

from umsatzprognose.schulungen.schulungen import (
    SchulungenRepository,
    _benoetigte_jahre,
    _jahr_spalte_ermitteln,
    _zeilen_zu_anmeldungen,
    _zeilen_zu_terminen,
)

KOPFZEILE = ["Schulung", "Jahr", "Monat", "Trainer", "Umsatz gesamt", "Bemerkungen"]

# Die Spalte "TN Zahl" kommt laut Spec Abschnitt 4 zweimal vor: einmal als Gesamtsumme
# direkt vor "Umsatz gesamt" (hier Index 4), einmal in der Gruppe mit "Max
# Zahl"/"Restplätze"/"Auslastung" (hier Index 7) - beide tragen laut Beobachtung am
# Jahrgang 2024 denselben Wert.
KOPFZEILE_ANMELDUNGEN = [
    "Schulung",
    "Jahr",
    "Monat",
    "Trainer",
    "TN Zahl",
    "Umsatz gesamt",
    "Bemerkungen",
    "TN Zahl",
    "Max Zahl",
    "Restplätze",
    "Auslastung",
]


class FakeClient:
    """Liefert je Spreadsheet-ID feste Zeilen, oder wirft, wenn konfiguriert."""

    def __init__(self, antworten: dict[str, list[list[str]] | Exception]) -> None:
        self._antworten = antworten

    def werte(self, spreadsheet_id: str, bereich: str = "") -> list[list[str]]:
        antwort = self._antworten[spreadsheet_id]
        if isinstance(antwort, Exception):
            raise antwort
        return antwort


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


def test_zeilen_zu_terminen_findet_kopfzeile_hinter_einer_vorausgehenden_zeile() -> None:
    """Eine Zeile ohne alle Pflichtspalten geht der eigentlichen Kopfzeile voraus - die
    Suche darf nicht bei Zeile 0 aufgeben."""
    vorausgehende_zeile = ["Übersicht", "Monat", "", "", "", ""]
    zeilen = [
        vorausgehende_zeile,
        KOPFZEILE,
        ["Python-Grundkurs", "2026", "10", "A. Beispiel", "1.500,00 €", ""],
    ]
    termine = _zeilen_zu_terminen(zeilen)
    assert [(t.jahr, t.monat, t.umsatz) for t in termine] == [(2026, 10, 1500.0)]


def test_jahr_spalte_ermitteln_nimmt_die_kopfzeilen_spalte_wenn_vorhanden() -> None:
    assert _jahr_spalte_ermitteln({"Schulung": 0, "Jahr": 1, "Monat": 2}) == 1


def test_jahr_spalte_ermitteln_faellt_ohne_kopfzeilen_spalte_auf_die_erste_spalte_zurueck() -> None:
    """Beobachtet am Jahrgang 2024: die erste Spalte trägt dort "x^" statt "Jahr"."""
    assert _jahr_spalte_ermitteln({"Monat": 1, "Schulung": 2}) == 0


def test_zeilen_zu_terminen_findet_jahr_spalte_trotz_vertipptem_kopfzeilentext() -> None:
    """Wie beim Jahrgang 2024 beobachtet: die erste Spalte trägt einen Vertipper ("x^")
    statt "Jahr" - die Jahr-Spalte gilt trotzdem als die erste Spalte des Blatts."""
    kopfzeile = ["x^", "Monat", "Schulung", "Trainer", "Datum", "Umsatz gesamt", "Bemerkungen"]
    zeilen = [kopfzeile, ["2024", "10", "Scrum Master", "A. Beispiel", "", "1.500,00 €", ""]]
    termine = _zeilen_zu_terminen(zeilen)
    assert [(t.jahr, t.monat, t.umsatz) for t in termine] == [(2024, 10, 1500.0)]


def test_zeilen_zu_anmeldungen_findet_spalten_ueber_die_kopfzeile() -> None:
    zeilen = [
        KOPFZEILE_ANMELDUNGEN,
        [
            "Scrum Master",
            "2026",
            "10",
            "A. Beispiel",
            "1",
            "1.500,00 €",
            "",
            "12",
            "15",
            "3",
            "80%",
        ],
    ]
    anmeldungen = _zeilen_zu_anmeldungen(zeilen)
    assert [(a.jahr, a.monat, a.schulungstyp, a.teilnehmerzahl) for a in anmeldungen] == [
        (2026, 10, "Scrum Master", 12),
    ]


def test_zeilen_zu_anmeldungen_nimmt_die_zuletzt_stehende_tn_zahl_spalte() -> None:
    """Erste und zweite "TN Zahl"-Spalte unterscheiden sich hier bewusst, damit der Test
    eine Verwechslung aufdeckt - in der Praxis tragen beide denselben Wert."""
    zeilen = [
        KOPFZEILE_ANMELDUNGEN,
        ["Kurs A", "2026", "10", "", "1", "0,00 €", "", "9", "10", "1", "90%"],
    ]
    [anmeldung] = _zeilen_zu_anmeldungen(zeilen)
    assert anmeldung.teilnehmerzahl == 9


def test_zeilen_zu_anmeldungen_ueberspringt_zeilen_ohne_jahr_monat_oder_teilnehmerzahl() -> None:
    zeilen = [KOPFZEILE_ANMELDUNGEN, ["Kurs A", "", "", "", "", "0,00 €", "", "", "", "", ""]]
    assert _zeilen_zu_anmeldungen(zeilen) == []


def test_zeilen_zu_anmeldungen_findet_jahr_spalte_trotz_vertipptem_kopfzeilentext() -> None:
    kopfzeile = ["x^", "Monat", "Schulung", "Trainer", "Datum", "TN Zahl", "Umsatz gesamt"]
    zeilen = [kopfzeile, ["2024", "10", "Scrum Master", "", "", "12", "1.500,00 €"]]
    [anmeldung] = _zeilen_zu_anmeldungen(zeilen)
    assert (anmeldung.jahr, anmeldung.monat, anmeldung.schulungstyp, anmeldung.teilnehmerzahl) == (
        2024,
        10,
        "Scrum Master",
        12,
    )


def test_zeilen_zu_anmeldungen_ohne_zeilen_ist_leer() -> None:
    assert _zeilen_zu_anmeldungen([]) == []


def test_zeilen_zu_anmeldungen_wirft_bei_fehlenden_spalten() -> None:
    with pytest.raises(ValueError, match="TN Zahl"):
        _zeilen_zu_anmeldungen([["Schulung", "Jahr", "Monat"]])


def test_zeilen_zu_anmeldungen_findet_kopfzeile_hinter_einer_vorausgehenden_zeile() -> None:
    vorausgehende_zeile = ["Übersicht", "Monat", "", "", "", "", "", "", "", "", ""]
    zeilen = [
        vorausgehende_zeile,
        KOPFZEILE_ANMELDUNGEN,
        ["Kurs A", "2026", "10", "", "1", "0,00 €", "", "9", "10", "1", "90%"],
    ]
    [anmeldung] = _zeilen_zu_anmeldungen(zeilen)
    assert (anmeldung.jahr, anmeldung.monat, anmeldung.teilnehmerzahl) == (2026, 10, 9)


def test_anmeldungsverlauf_laden_fuehrt_mehrere_jahre_zusammen() -> None:
    client = FakeClient(
        {
            "sheet-2022": [
                KOPFZEILE_ANMELDUNGEN,
                ["Scrum Master", "2022", "3", "", "1", "1.000,00 €", "", "4", "10", "6", "40%"],
            ],
            "sheet-2023": [
                KOPFZEILE_ANMELDUNGEN,
                ["Scrum Master", "2023", "1", "", "1", "2.000,00 €", "", "6", "10", "4", "60%"],
            ],
        }
    )
    repository = SchulungenRepository(client, {2022: "sheet-2022", 2023: "sheet-2023"})
    verlauf = repository.anmeldungsverlauf_laden([2022, 2023])

    assert verlauf.je_monat() == {(2022, 3): 4, (2023, 1): 6}
    assert verlauf.abbildungshinweise == ()


def test_anmeldungsverlauf_laden_meldet_nicht_konfiguriertes_jahr_als_hinweis() -> None:
    repository = SchulungenRepository(FakeClient({}), {})
    verlauf = repository.anmeldungsverlauf_laden([2022])

    assert verlauf.anmeldungen == ()
    assert len(verlauf.abbildungshinweise) == 1
    assert "2022" in verlauf.abbildungshinweise[0].text


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
    plan = repository.laden(stichtag=date(2026, 11, 1), horizont_monate=3)

    assert plan.umsatz_je_monat([(2026, 12), (2027, 1)]) == [1000.0, 2000.0]
    assert plan.hinweise([(2026, 12), (2027, 1)]) == ()


def test_laden_mit_leerer_datei_liefert_keine_termine_und_keinen_hinweis() -> None:
    client = FakeClient({"sheet-2026": [KOPFZEILE]})
    repository = SchulungenRepository(client, {2026: "sheet-2026"})
    plan = repository.laden(stichtag=date(2026, 9, 15), horizont_monate=1)

    assert plan.termine == ()
    assert plan.abbildungshinweise == ()


def test_laden_meldet_nicht_konfiguriertes_jahr_als_hinweis() -> None:
    repository = SchulungenRepository(FakeClient({}), {})
    plan = repository.laden(stichtag=date(2026, 9, 15), horizont_monate=1)

    assert len(plan.abbildungshinweise) == 1
    assert "2026" in plan.abbildungshinweise[0].text
    assert "KOSTEN_SHEET_IDS" in plan.abbildungshinweise[0].text


def test_laden_meldet_lesefehler_als_hinweis_statt_absturz() -> None:
    client = FakeClient({"sheet-2026": RuntimeError("kein Zugriff")})
    repository = SchulungenRepository(client, {2026: "sheet-2026"})
    plan = repository.laden(stichtag=date(2026, 9, 15), horizont_monate=1)

    assert plan.termine == ()
    assert len(plan.abbildungshinweise) == 1
    assert "2026" in plan.abbildungshinweise[0].text
