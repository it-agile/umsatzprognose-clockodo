"""Tests zu den lesbaren Bezeichnungen je Projekt.

Die Beispielformen entsprechen den am 24.08.2026 geprueften Antworten von
``/v4/projects`` und ``/v3/customers``.
"""

from __future__ import annotations

from umsatzprognose.stammdaten import (
    ProjektBezeichnung,
    bezeichnungen_je_projekt,
    kundennamen,
)

KUNDEN = [
    {"id": 1480229, "name": "//Seibert/Media GmbH", "active": True},
    {"id": 2014785, "name": "cosinex GmbH", "active": True},
]

PROJEKTE = [
    {"id": 3713470, "customers_id": 2014785, "name": "Agile Coaching 2026", "active": True},
    {"id": 1375839, "customers_id": 1480229, "name": "Schulung", "active": False},
]


def test_kunde_und_projektname_werden_zugeordnet():
    bezeichnungen = bezeichnungen_je_projekt(PROJEKTE, KUNDEN)
    assert bezeichnungen[3713470] == ProjektBezeichnung(
        kunde="cosinex GmbH", projekt="Agile Coaching 2026"
    )


def test_auch_inaktive_projekte_werden_beschriftet():
    # Die Zuordnung filtert nicht auf ``active``, damit sie fuer jede Auswahl taugt.
    assert bezeichnungen_je_projekt(PROJEKTE, KUNDEN)[1375839].kunde == "//Seibert/Media GmbH"


def test_kundennamen_kommen_mit_ganzzahliger_id():
    assert kundennamen(KUNDEN)[2014785] == "cosinex GmbH"


def test_unbekannter_kunde_bleibt_none_statt_zu_scheitern():
    bezeichnung = bezeichnungen_je_projekt(
        [{"id": 42, "customers_id": 999, "name": "Projekt ohne Kunde"}], KUNDEN
    )[42]
    assert bezeichnung == ProjektBezeichnung(kunde=None, projekt="Projekt ohne Kunde")


def test_fehlende_felder_bleiben_none():
    bezeichnung = bezeichnungen_je_projekt([{"id": 42}], KUNDEN)[42]
    assert bezeichnung == ProjektBezeichnung(kunde=None, projekt=None)
