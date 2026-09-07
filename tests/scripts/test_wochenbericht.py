"""Tests fuer die Kurzarbeit-Integration in scripts/wochenbericht.py - keine Live-API,
kein Slack-Post."""

from __future__ import annotations

import sys
from pathlib import Path

from umsatzprognose.domaene import Kurzarbeitsbewertung, Schwellenwerte

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
import wochenbericht


def test_kurzarbeit_erlaeuterung_nennt_status_und_quote_des_juengsten_monats():
    ergebnisse = {
        (2026, 7): Kurzarbeitsbewertung(
            jahr=2026, monat=7, schwellenwerte=Schwellenwerte(quote_organisation=0.30)
        ),
        (2026, 8): Kurzarbeitsbewertung(
            jahr=2026,
            monat=8,
            schwellenwerte=Schwellenwerte(quote_organisation=0.30),
            anzahl_kurzarbeitsfaehig=3,
            anzahl_scheitert_interne_arbeit=1,
        ),
    }

    text = wochenbericht.kurzarbeit_erlaeuterung(ergebnisse)

    assert "Aug 2026" in text
    assert "*Voraussetzung erfüllt*" in text  # Slack-mrkdwn kennt keine Textfarbe
    assert "75%" in text
    assert "Schwelle 30%" in text


def test_kurzarbeit_erlaeuterung_ohne_quote_meldet_keine_auswertung_moeglich():
    ergebnisse = {
        (2026, 8): Kurzarbeitsbewertung(jahr=2026, monat=8, schwellenwerte=Schwellenwerte())
    }

    text = wochenbericht.kurzarbeit_erlaeuterung(ergebnisse)

    assert text == "Kurzarbeitsbereitschaft (Aug 2026): keine Auswertung möglich."
