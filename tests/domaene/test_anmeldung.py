"""Tests fuer den Anmeldungsverlauf: die Fachobjekte in domaene.anmeldung."""

from __future__ import annotations

from datetime import date

import pytest

from umsatzprognose.domaene import Hinweis
from umsatzprognose.domaene.anmeldung import (
    KATEGORIE_SONSTIGE,
    Anmeldung,
    Anmeldungsverlauf,
    _basisname_und_dauer,
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


def test_summe_je_typ_summiert_ueber_alle_monate() -> None:
    verlauf = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "Scrum Master", 5),
            Anmeldung(2026, 10, "Scrum Master", 3),
            Anmeldung(2026, 9, "Requirements Engineering", 2),
        )
    )
    assert verlauf.summe_je_typ() == {"Scrum Master": 8, "Requirements Engineering": 2}


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


def test_basisname_und_dauer_trennt_erkannten_dauer_suffix_ab() -> None:
    assert _basisname_und_dauer("CSPO 2-tägig") == ("CSPO", "2-tägig")
    assert _basisname_und_dauer("CSPO 3-tägig") == ("CSPO", "3-tägig")


def test_basisname_und_dauer_ohne_suffix_ist_der_ganze_name_ohne_dauer() -> None:
    assert _basisname_und_dauer("KSD") == ("KSD", None)


def test_gliederung_je_kategorie_ohne_variante_ist_einfaches_blatt() -> None:
    """Ein Schulungstyp ohne Dauer-Suffix und mit nur einem Format bleibt ein
    einfacher Blatt-Knoten, ohne Kinder."""
    verlauf = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "KSD", 4),
            Anmeldung(2026, 10, "KSD", 2),
        )
    )
    [knoten] = verlauf.gliederung_je_kategorie(KATEGORIEN)["Kanban"]
    assert knoten.name == "KSD"
    assert knoten.monate == {(2026, 9): 4, (2026, 10): 2}
    assert knoten.kinder == ()


def test_gliederung_je_kategorie_dauer_variante_ohne_format_vielfalt() -> None:
    """Zwei Dauer-Varianten ohne Format-Vielfalt - die Format-Ebene entfaellt, die
    Dauer-Kinder haengen direkt am Basisname-Knoten."""
    kategorien = {"Scrum": ["CSPO 2-tägig", "CSPO 3-tägig"]}
    verlauf = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "CSPO 2-tägig", 5),
            Anmeldung(2026, 9, "CSPO 3-tägig", 2),
        )
    )
    [knoten] = verlauf.gliederung_je_kategorie(kategorien)["Scrum"]
    assert knoten.name == "CSPO"
    assert knoten.monate == {(2026, 9): 7}
    assert {kind.name for kind in knoten.kinder} == {"2-tägig", "3-tägig"}


def test_gliederung_je_kategorie_format_variante_ohne_dauer_vielfalt() -> None:
    """Zwei Formate ohne Dauer-Vielfalt - die Dauer-Ebene entfaellt, die Format-Kinder
    sind direkt Blaetter."""
    kategorien = {"Scrum": ["CSPO 2-tägig"]}
    verlauf = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "CSPO 2-tägig", 5, format="Präsenz"),
            Anmeldung(2026, 9, "CSPO 2-tägig", 3, format="Online"),
        )
    )
    [knoten] = verlauf.gliederung_je_kategorie(kategorien)["Scrum"]
    assert knoten.name == "CSPO"
    assert {kind.name for kind in knoten.kinder} == {"Präsenz", "Online"}
    for kind in knoten.kinder:
        assert kind.kinder == ()


def test_gliederung_je_kategorie_format_und_dauer_gemeinsam() -> None:
    """Format- und Dauer-Vielfalt gemeinsam - Format-Knoten mit je eigenen
    Dauer-Kindern darunter (das CSPO-Beispiel aus der Aufgabenstellung)."""
    kategorien = {"Scrum": ["CSPO 2-tägig", "CSPO 3-tägig"]}
    verlauf = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "CSPO 2-tägig", 5, format="Präsenz"),
            Anmeldung(2026, 9, "CSPO 3-tägig", 2, format="Präsenz"),
            Anmeldung(2026, 9, "CSPO 2-tägig", 1, format="Online"),
            Anmeldung(2026, 9, "CSPO 3-tägig", 4, format="Online"),
        )
    )
    [knoten] = verlauf.gliederung_je_kategorie(kategorien)["Scrum"]
    assert knoten.name == "CSPO"
    assert knoten.monate == {(2026, 9): 12}
    format_namen = {kind.name for kind in knoten.kinder}
    assert format_namen == {"Präsenz", "Online"}
    for format_knoten in knoten.kinder:
        dauer_namen = {kind.name for kind in format_knoten.kinder}
        assert dauer_namen == {"2-tägig", "3-tägig"}


def test_gliederung_je_kategorie_sortiert_basisnamen_alphabetisch_nicht_nach_anmeldezahl() -> None:
    """Im Tabellen-Drilldown soll man einen bekannten Namen alphabetisch
    wiederfinden - hier bewusst mit gegenlaeufiger Teilnehmerzahl, damit ein
    Ruecksprung auf absteigende Teilnehmerzahl auffiele."""
    kategorien = {"Scrum": ["Zertifizierung 2-tägig", "Auffrischung 2-tägig"]}
    verlauf = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "Zertifizierung 2-tägig", 9),
            Anmeldung(2026, 9, "Auffrischung 2-tägig", 1),
        )
    )
    knoten = verlauf.gliederung_je_kategorie(kategorien)["Scrum"]
    assert [k.name for k in knoten] == ["Auffrischung", "Zertifizierung"]


def test_gliederung_je_kategorie_sortiert_format_alphabetisch_nicht_nach_anmeldezahl() -> None:
    kategorien = {"Scrum": ["CSPO 2-tägig"]}
    verlauf = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "CSPO 2-tägig", 5, format="Präsenz"),
            Anmeldung(2026, 9, "CSPO 2-tägig", 1, format="Online"),
        )
    )
    [knoten] = verlauf.gliederung_je_kategorie(kategorien)["Scrum"]
    assert [kind.name for kind in knoten.kinder] == ["Online", "Präsenz"]


def test_gliederung_je_kategorie_sortiert_dauer_alphabetisch_nicht_nach_anmeldezahl() -> None:
    kategorien = {"Scrum": ["CSPO 5-tägig", "CSPO 2-tägig"]}
    verlauf = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "CSPO 5-tägig", 9),
            Anmeldung(2026, 9, "CSPO 2-tägig", 1),
        )
    )
    [knoten] = verlauf.gliederung_je_kategorie(kategorien)["Scrum"]
    assert [kind.name for kind in knoten.kinder] == ["2-tägig", "5-tägig"]


def test_gliederung_je_kategorie_unsuffigierte_variante_behaelt_vollen_namen() -> None:
    """Eine Variante ohne erkannten Dauer-Suffix (z. B. "KSI" neben "KSI 2-tägig")
    behaelt ihren vollen Namen als Label statt eines erfundenen Platzhalters."""
    kategorien = {"Kanban": ["KSI", "KSI 2-tägig"]}
    verlauf = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "KSI", 3),
            Anmeldung(2026, 9, "KSI 2-tägig", 5),
        )
    )
    [knoten] = verlauf.gliederung_je_kategorie(kategorien)["Kanban"]
    assert knoten.name == "KSI"
    dauer_namen = {kind.name for kind in knoten.kinder}
    assert dauer_namen == {"KSI", "2-tägig"}


def test_gliederung_je_kategorie_basisname_ohne_teilnehmende_wird_ausgeblendet() -> None:
    """Ein Basisname ganz ohne Teilnehmende in diesem Zeitraum taucht gar nicht erst
    als eigene Zeile auf, statt leer angezeigt zu werden."""
    kategorien = {"Scrum": ["CSPO 2-tägig", "CSM 2-tägig"]}
    verlauf = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "CSPO 2-tägig", 5),
            Anmeldung(2026, 9, "CSM 2-tägig", 0),
        )
    )
    knoten = verlauf.gliederung_je_kategorie(kategorien)["Scrum"]
    assert [k.name for k in knoten] == ["CSPO"]


def test_gliederung_je_kategorie_format_ohne_teilnehmende_wird_ausgeblendet() -> None:
    """Ein Format ganz ohne Teilnehmende faellt aus den Kindern heraus - bleibt danach
    nur noch ein Format uebrig, entfaellt die Format-Ebene komplett."""
    kategorien = {"Scrum": ["CSPO 2-tägig"]}
    verlauf = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "CSPO 2-tägig", 5, format="Präsenz"),
            Anmeldung(2026, 9, "CSPO 2-tägig", 0, format="Online"),
        )
    )
    [knoten] = verlauf.gliederung_je_kategorie(kategorien)["Scrum"]
    assert knoten.name == "CSPO"
    assert knoten.kinder == ()


def test_gliederung_je_kategorie_dauer_ohne_teilnehmende_wird_ausgeblendet() -> None:
    kategorien = {"Scrum": ["CSPO 2-tägig", "CSPO 3-tägig"]}
    verlauf = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "CSPO 2-tägig", 5),
            Anmeldung(2026, 9, "CSPO 3-tägig", 0),
        )
    )
    [knoten] = verlauf.gliederung_je_kategorie(kategorien)["Scrum"]
    assert knoten.name == "CSPO"
    assert knoten.kinder == ()


def test_gliederung_je_kategorie_sammelt_unbekannte_typen_unter_sonstige() -> None:
    verlauf = Anmeldungsverlauf(anmeldungen=(Anmeldung(2026, 9, "Ein ganz neuer Kurs", 1),))
    [knoten] = verlauf.gliederung_je_kategorie(KATEGORIEN)[KATEGORIE_SONSTIGE]
    assert knoten.name == "Ein ganz neuer Kurs"


def test_gliederung_je_kategorie_enthaelt_alle_kategorien_auch_ohne_anmeldung() -> None:
    verlauf = Anmeldungsverlauf(anmeldungen=(Anmeldung(2026, 9, "CSM 2-tägig", 5),))
    ergebnis = verlauf.gliederung_je_kategorie(KATEGORIEN)
    assert list(ergebnis) == ["Scrum", "Kanban", KATEGORIE_SONSTIGE]
    assert ergebnis["Kanban"] == ()
    assert ergebnis[KATEGORIE_SONSTIGE] == ()


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
        Anmeldungsverlauf().letzte(13, stichtag=date(2026, 9, 15))  # type: ignore


def test_letzte_behaelt_abbildungshinweise() -> None:
    hinweis = Hinweis("Die Schulungs-Datei für 2022 konnte nicht gelesen werden (HttpError)")
    verlauf = Anmeldungsverlauf(
        anmeldungen=(Anmeldung(2026, 9, "KSD", 1),), abbildungshinweise=(hinweis,)
    )
    fenster = verlauf.letzte(monate=12, stichtag=date(2026, 9, 15))
    assert fenster.abbildungshinweise == (hinweis,)


def test_ab_jahr_behaelt_nur_anmeldungen_ab_dem_angegebenen_jahr() -> None:
    verlauf = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2022, 12, "KSD", 1),
            Anmeldung(2023, 1, "KSD", 2),
            Anmeldung(2024, 6, "KSD", 3),
        )
    )
    gefiltert = verlauf.ab_jahr(2023)
    assert gefiltert.monate == ((2023, 1), (2024, 6))
    assert gefiltert.je_monat() == {(2023, 1): 2, (2024, 6): 3}


def test_ab_jahr_behaelt_abbildungshinweise() -> None:
    hinweis = Hinweis("Die Schulungs-Datei für 2022 konnte nicht gelesen werden (HttpError)")
    verlauf = Anmeldungsverlauf(
        anmeldungen=(Anmeldung(2024, 9, "KSD", 1),), abbildungshinweise=(hinweis,)
    )
    gefiltert = verlauf.ab_jahr(2023)
    assert gefiltert.abbildungshinweise == (hinweis,)


def test_formate_sortiert_nach_absteigender_gesamtteilnehmerzahl_und_ohne_leere() -> None:
    verlauf = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "CSPO 2-tägig", 2, format="Online"),
            Anmeldung(2026, 9, "CSM 2-tägig", 5, format="Präsenz"),
            Anmeldung(2026, 9, "Unbekannt", 9),
        )
    )
    assert verlauf.formate == ("Präsenz", "Online")


def test_je_monat_und_format_beschraenkt_auf_ein_format() -> None:
    verlauf = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "CSPO 2-tägig", 5, format="Präsenz"),
            Anmeldung(2026, 9, "CSM 2-tägig", 2, format="Online"),
            Anmeldung(2026, 10, "CSPO 2-tägig", 3, format="Präsenz"),
        )
    )
    assert verlauf.je_monat_und_format("Präsenz") == {(2026, 9): 5, (2026, 10): 3}


def test_dauern_sortiert_nach_absteigender_gesamtteilnehmerzahl_und_ohne_unsuffigierte() -> None:
    verlauf = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "CSPO 2-tägig", 2),
            Anmeldung(2026, 9, "CSM 3-tägig", 5),
            Anmeldung(2026, 9, "KSD", 9),
        )
    )
    assert verlauf.dauern == ("3-tägig", "2-tägig")


def test_je_monat_und_dauer_beschraenkt_auf_eine_dauer() -> None:
    verlauf = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "CSPO 2-tägig", 5),
            Anmeldung(2026, 9, "CSM 3-tägig", 2),
            Anmeldung(2026, 10, "KSI 2-tägig", 3),
        )
    )
    assert verlauf.je_monat_und_dauer("2-tägig") == {(2026, 9): 5, (2026, 10): 3}


def test_schulungstypen_je_kategorie_gruppiert_nach_absteigender_gesamtteilnehmerzahl() -> None:
    verlauf = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "CSM 2-tägig", 2),
            Anmeldung(2026, 9, "CSPO 3-tägig", 5),
            Anmeldung(2026, 9, "KSD", 4),
        )
    )
    ergebnis = verlauf.schulungstypen_je_kategorie(KATEGORIEN)
    assert ergebnis["Scrum"] == ("CSPO 3-tägig", "CSM 2-tägig")
    assert ergebnis["Kanban"] == ("KSD",)


def test_schulungstypen_je_kategorie_enthaelt_alle_kategorien_auch_ohne_anmeldung() -> None:
    verlauf = Anmeldungsverlauf(anmeldungen=(Anmeldung(2026, 9, "CSM 2-tägig", 5),))
    ergebnis = verlauf.schulungstypen_je_kategorie(KATEGORIEN)
    assert list(ergebnis) == ["Scrum", "Kanban", KATEGORIE_SONSTIGE]
    assert ergebnis["Kanban"] == ()


def test_basisnamen_fasst_dauer_varianten_zu_einem_namen_zusammen() -> None:
    verlauf = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "CSPO 2-tägig", 5),
            Anmeldung(2026, 9, "CSPO 3-tägig", 2),
            Anmeldung(2026, 9, "KSD", 4),
        )
    )
    assert verlauf.basisnamen == ("CSPO", "KSD")


def test_je_monat_und_basisname_summiert_ueber_dauer_varianten_hinweg() -> None:
    verlauf = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "CSPO 2-tägig", 5),
            Anmeldung(2026, 9, "CSPO 3-tägig", 2),
            Anmeldung(2026, 10, "CSPO 2-tägig", 3),
        )
    )
    assert verlauf.je_monat_und_basisname("CSPO") == {(2026, 9): 7, (2026, 10): 3}


def test_basisnamen_je_kategorie_gruppiert_und_fasst_dauer_varianten_zusammen() -> None:
    verlauf = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "CSM 2-tägig", 2),
            Anmeldung(2026, 9, "CSPO 3-tägig", 5),
            Anmeldung(2026, 9, "KSD", 4),
        )
    )
    ergebnis = verlauf.basisnamen_je_kategorie(KATEGORIEN)
    assert ergebnis["Scrum"] == ("CSPO", "CSM")
    assert ergebnis["Kanban"] == ("KSD",)


def test_basisnamen_je_kategorie_enthaelt_alle_kategorien_auch_ohne_anmeldung() -> None:
    verlauf = Anmeldungsverlauf(anmeldungen=(Anmeldung(2026, 9, "CSM 2-tägig", 5),))
    ergebnis = verlauf.basisnamen_je_kategorie(KATEGORIEN)
    assert list(ergebnis) == ["Scrum", "Kanban", KATEGORIE_SONSTIGE]
    assert ergebnis["Kanban"] == ()
