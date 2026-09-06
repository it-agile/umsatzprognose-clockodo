"""Tests fuer den Anmeldungsverlauf: die Fachobjekte in domaene.anmeldung."""

from __future__ import annotations

from datetime import date

import pytest

from umsatzprognose.domaene import Hinweis
from umsatzprognose.domaene.anmeldung import (
    KATEGORIE_SONSTIGE,
    Anmeldung,
    Anmeldungsverlauf,
    _kategorie_zuordnung,
)

KATEGORIEN = {
    "Scrum": ["CSM 2-tägig", "CSPO 3-tägig"],
    "Kanban": ["KSD", "SBK"],
}


def test_monate_liefert_chronologische_duplikatfreie_liste() -> None:
    verlauf = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 10, "Scrum Master", 5),
            Anmeldung(2026, 9, "Scrum Master", 3),
            Anmeldung(2026, 10, "Requirements Engineering", 2),
        )
    )
    assert verlauf.monate == ((2026, 9), (2026, 10))


def test_schulungstypen_sortiert_nach_absteigender_gesamtteilnehmerzahl() -> None:
    verlauf = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "Requirements Engineering", 2),
            Anmeldung(2026, 10, "Scrum Master", 5),
            Anmeldung(2026, 11, "Scrum Master", 4),
        )
    )
    assert verlauf.schulungstypen == ("Scrum Master", "Requirements Engineering")


def test_je_monat_summiert_ueber_alle_schulungstypen() -> None:
    verlauf = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "Scrum Master", 5),
            Anmeldung(2026, 9, "Requirements Engineering", 2),
            Anmeldung(2026, 10, "Scrum Master", 3),
        )
    )
    assert verlauf.je_monat() == {(2026, 9): 7, (2026, 10): 3}


def test_je_monat_und_typ_beschraenkt_auf_einen_schulungstyp() -> None:
    verlauf = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "Scrum Master", 5),
            Anmeldung(2026, 9, "Requirements Engineering", 2),
            Anmeldung(2026, 10, "Scrum Master", 3),
        )
    )
    assert verlauf.je_monat_und_typ("Scrum Master") == {(2026, 9): 5, (2026, 10): 3}


def test_ohne_anmeldungen_ist_alles_leer() -> None:
    verlauf = Anmeldungsverlauf()
    assert verlauf.monate == ()
    assert verlauf.schulungstypen == ()
    assert verlauf.je_monat() == {}


def test_abbildungshinweise_werden_unveraendert_gehalten() -> None:
    hinweis = Hinweis("Die Schulungs-Datei für 2022 konnte nicht gelesen werden (HttpError)")
    verlauf = Anmeldungsverlauf(abbildungshinweise=(hinweis,))
    assert verlauf.abbildungshinweise == (hinweis,)


def test_kategorie_zuordnung_kehrt_kategorie_zu_typen_zuordnung_um() -> None:
    assert _kategorie_zuordnung(KATEGORIEN) == {
        "CSM 2-tägig": "Scrum",
        "CSPO 3-tägig": "Scrum",
        "KSD": "Kanban",
        "SBK": "Kanban",
    }


def test_je_monat_und_kategorie_summiert_alle_typen_dieser_kategorie() -> None:
    verlauf = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "CSM 2-tägig", 5),
            Anmeldung(2026, 9, "CSPO 3-tägig", 2),
            Anmeldung(2026, 9, "KSD", 4),
            Anmeldung(2026, 10, "CSM 2-tägig", 3),
        )
    )
    ergebnis = verlauf.je_monat_und_kategorie(KATEGORIEN)
    assert ergebnis["Scrum"] == {(2026, 9): 7, (2026, 10): 3}
    assert ergebnis["Kanban"] == {(2026, 9): 4}


def test_je_monat_und_kategorie_sammelt_unbekannte_typen_unter_sonstige() -> None:
    verlauf = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "CSM 2-tägig", 5),
            Anmeldung(2026, 9, "Ein ganz neuer Kurs", 2),
        )
    )
    ergebnis = verlauf.je_monat_und_kategorie(KATEGORIEN)
    assert ergebnis[KATEGORIE_SONSTIGE] == {(2026, 9): 2}


def test_je_monat_und_kategorie_enthaelt_alle_kategorien_auch_ohne_anmeldung() -> None:
    verlauf = Anmeldungsverlauf(anmeldungen=(Anmeldung(2026, 9, "CSM 2-tägig", 5),))
    ergebnis = verlauf.je_monat_und_kategorie(KATEGORIEN)
    assert list(ergebnis) == ["Scrum", "Kanban", KATEGORIE_SONSTIGE]
    assert ergebnis["Kanban"] == {}
    assert ergebnis[KATEGORIE_SONSTIGE] == {}


def test_je_monat_und_kategorie_ohne_konfiguration_landet_alles_unter_sonstige() -> None:
    verlauf = Anmeldungsverlauf(anmeldungen=(Anmeldung(2026, 9, "CSM 2-tägig", 5),))
    ergebnis = verlauf.je_monat_und_kategorie({})
    assert ergebnis == {KATEGORIE_SONSTIGE: {(2026, 9): 5}}


def test_letzte_beschraenkt_auf_die_angegebene_monatsanzahl_bis_zum_stichtag() -> None:
    verlauf = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2025, 8, "KSD", 1),
            Anmeldung(2025, 9, "KSD", 2),
            Anmeldung(2026, 8, "KSD", 3),
            Anmeldung(2026, 9, "KSD", 4),
        )
    )
    fenster = verlauf.letzte(monate=2, stichtag=date(2026, 9, 15))
    assert fenster.monate == ((2026, 8), (2026, 9))
    assert fenster.je_monat() == {(2026, 8): 3, (2026, 9): 4}


def test_letzte_verlangt_monate_als_keyword() -> None:
    """``monate`` ist keyword-only, damit an der Aufrufstelle lesbar bleibt, was die
    Zahl bedeutet - eine nackte ``13`` waere sonst leicht mit einem Jahr zu verwechseln."""
    with pytest.raises(TypeError):
        Anmeldungsverlauf().letzte(13, stichtag=date(2026, 9, 15))  # type: ignore[call-arg]


def test_letzte_behaelt_abbildungshinweise() -> None:
    hinweis = Hinweis("Die Schulungs-Datei für 2022 konnte nicht gelesen werden (HttpError)")
    verlauf = Anmeldungsverlauf(
        anmeldungen=(Anmeldung(2026, 9, "KSD", 1),), abbildungshinweise=(hinweis,)
    )
    fenster = verlauf.letzte(monate=12, stichtag=date(2026, 9, 15))
    assert fenster.abbildungshinweise == (hinweis,)
