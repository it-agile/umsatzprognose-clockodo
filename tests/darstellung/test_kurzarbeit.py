"""Tests fuer darstellung.kurzarbeit - die Text-Berichte, aus notebooks/04_kurzarbeit.ipynb
in die Darstellungsschicht verschoben."""

from __future__ import annotations

from umsatzprognose.darstellung.kurzarbeit import kurzarbeit_bericht, kurzarbeit_hinweise_bericht
from umsatzprognose.domaene import Hinweis, Kurzarbeitsbewertung, Schwellenwerte

_SCHWELLENWERTE = Schwellenwerte(
    anteil_interne_arbeit=0.24, ueberstunden_stunden=14.0, quote_organisation=0.30
)


def test_kurzarbeit_bericht_nennt_juengsten_monat_und_status():
    ergebnisse = {
        (2026, 7): Kurzarbeitsbewertung(
            jahr=2026, monat=7, schwellenwerte=_SCHWELLENWERTE, anzahl_kurzarbeitsfaehig=1
        ),
        (2026, 8): Kurzarbeitsbewertung(
            jahr=2026,
            monat=8,
            schwellenwerte=_SCHWELLENWERTE,
            anzahl_kurzarbeitsfaehig=3,
            anzahl_scheitert_interne_arbeit=1,
        ),
    }

    text = kurzarbeit_bericht(ergebnisse)

    assert text.startswith("August 2026: ")
    assert "Voraussetzung erfüllt" in text
    assert "75.0%" in text  # Quote 3 von 4
    assert "Juli 2026" in text  # taucht in der Tabelle darunter auf


def test_kurzarbeit_bericht_mit_farbe_traegt_ansi_codes():
    ergebnisse = {
        (2026, 8): Kurzarbeitsbewertung(
            jahr=2026, monat=8, schwellenwerte=_SCHWELLENWERTE, anzahl_kurzarbeitsfaehig=1
        )
    }

    mit_farbe = kurzarbeit_bericht(ergebnisse, mit_farbe=True)
    ohne_farbe = kurzarbeit_bericht(ergebnisse, mit_farbe=False)

    assert "\033[" in mit_farbe
    assert "\033[" not in ohne_farbe
    # Reine Textbestandteile bleiben trotzdem gleich.
    assert "Voraussetzung erfüllt" in ohne_farbe


def test_kurzarbeit_bericht_ohne_quote_zeigt_keine_auswertung_moeglich():
    ergebnisse = {
        (2026, 8): Kurzarbeitsbewertung(jahr=2026, monat=8, schwellenwerte=_SCHWELLENWERTE)
    }

    text = kurzarbeit_bericht(ergebnisse)

    assert "keine Auswertung möglich (keine einbezogene Person)" in text


def test_kurzarbeit_hinweise_bericht_zeigt_hinweistext_nicht_das_objekt():
    hinweis = Hinweis("Diese Personen sind laut Rollenzuordnung ausgeschlossen", ("301", "302"))
    ergebnisse = {
        (2026, 8): Kurzarbeitsbewertung(
            jahr=2026, monat=8, schwellenwerte=_SCHWELLENWERTE, hinweise=(hinweis,)
        )
    }

    text = kurzarbeit_hinweise_bericht(ergebnisse)

    assert "August 2026:" in text
    assert "  - Diese Personen sind laut Rollenzuordnung ausgeschlossen" in text
    assert "Hinweis(" not in text


def test_kurzarbeit_hinweise_bericht_ohne_hinweise():
    ergebnisse = {
        (2026, 8): Kurzarbeitsbewertung(jahr=2026, monat=8, schwellenwerte=_SCHWELLENWERTE)
    }

    assert kurzarbeit_hinweise_bericht(ergebnisse) == "Keine Hinweise."
