"""Fruehwarn-Tests fuer scripts/wochenbericht.py, samt der Kurzarbeit-Integration -
keine Live-API, kein Slack-Post.

Deckt genau die Art von Regression ab, die zuletzt unbemerkt blieb, bis der
woechentliche Actions-Lauf fehlschlug: eine falsche Signatur, ein vertauschter
Parameter oder ein Tippfehler in einer der reinen Funktionen dieses Skripts. Der
eigentliche Live-Ausfall (504 von Clockodo) faengt keiner dieser Tests ab - dagegen
hilft die Wiederholung in ``clockodo/client.py`` -, wohl aber ein kaputtes Skript
selbst, lange bevor der naechste Montag kommt.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pandas as pd
import plotly.graph_objects as go
import pytest

from umsatzprognose.darstellung import diagramme
from umsatzprognose.domaene import Kurzarbeitsbewertung, Schwellenwerte

if TYPE_CHECKING:
    from collections.abc import Sequence

    from slack_sdk import WebClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
import wochenbericht

# Minimale, gueltige Kurzarbeit-Rohdaten fuer Tests von diagrammtitel_und_figuren() -
# die Funktion ruft echten Code auf (diagramme.kurzarbeit_grafik()), kein Mock noetig.
_KURZARBEIT_ERGEBNISSE = {
    (2026, 8): Kurzarbeitsbewertung(
        jahr=2026, monat=8, schwellenwerte=Schwellenwerte(), anzahl_kurzarbeitsfaehig=1
    )
}


class _FakeDashboard:
    stichtag = date(2026, 9, 1)
    prognose: object = None

    def umsatzverlauf(self, *, mit_beschriftung: bool = False) -> go.Figure:
        return go.Figure()

    def restvolumen_je_projekt(self) -> go.Figure:
        return go.Figure()

    def gewinn_verlust_monatlich(
        self, *, monate: int | None = None, mit_beschriftung: bool = False
    ) -> go.Figure:
        return go.Figure()

    def gewinn_verlust_je_jahr(self, *, mit_beschriftung: bool = False) -> go.Figure:
        return go.Figure()

    def umsatzrendite_kumuliert(self, *, mit_beschriftung: bool = False) -> go.Figure:
        return go.Figure()

    def auslastung_je_mitarbeiter(self) -> go.Figure:
        return go.Figure()

    def umsatztabelle(self) -> pd.DataFrame:
        return pd.DataFrame({"Monat": ["September 2026"], "Umsatz": ["1.000,00 €"]})


class _FakeAnmeldungsverlauf:
    def letzte(self, *, monate: int, stichtag: date) -> _FakeAnmeldungsverlauf:
        return self


class _FakeSchulungenRepository:
    @classmethod
    def mit_automatischen_zugangsdaten(cls) -> _FakeSchulungenRepository:
        return cls()

    def anmeldungsverlauf_laden(self, jahre: Sequence[int]) -> _FakeAnmeldungsverlauf:
        return _FakeAnmeldungsverlauf()


def test_diagrammtitel_und_figuren_liefert_alle_neun_diagramme_in_reihenfolge(monkeypatch):
    monkeypatch.setattr(wochenbericht, "SchulungenRepository", _FakeSchulungenRepository)
    monkeypatch.setattr(diagramme, "anmeldungsverlauf", lambda *a, **kw: go.Figure())

    ergebnis = wochenbericht.diagrammtitel_und_figuren(
        _FakeDashboard(), _KURZARBEIT_ERGEBNISSE, gewinn_verlust_monate=12
    )

    assert [titel for titel, _figur in ergebnis] == [
        "Umsatz je Monat",
        "Offenes Auftragsvolumen je Projekt",
        "Gewinn/Verlust je Monat",
        "Gewinn/Verlust je Monat und Jahr",
        "Kumulierte Umsatzrendite je Jahr",
        "Auslastung je Person",
        "Kurzarbeitsbereitschaft je Monat",
        "Anmeldungen je Monat",
        "Umsatztabelle",
    ]
    assert all(isinstance(figur, go.Figure) for _titel, figur in ergebnis)


def test_diagrammtitel_und_figuren_laesst_kurzarbeit_weg_wenn_ausgeschaltet(monkeypatch):
    """``kurzarbeit_ergebnisse=None`` (Baustein ausgeschaltet, siehe
    ``umsatzprognose.clockodo.kurzarbeit_aktiv``) laesst den Eintrag entfallen, statt
    eine leere Grafik zu zeigen."""
    monkeypatch.setattr(wochenbericht, "SchulungenRepository", _FakeSchulungenRepository)
    monkeypatch.setattr(diagramme, "anmeldungsverlauf", lambda *a, **kw: go.Figure())

    ergebnis = wochenbericht.diagrammtitel_und_figuren(
        _FakeDashboard(), None, gewinn_verlust_monate=12
    )

    titel = [titel for titel, _figur in ergebnis]
    assert "Kurzarbeitsbereitschaft je Monat" not in titel
    assert len(titel) == 8


@pytest.mark.parametrize("kanal", ["C0123456789", "D0123456789", "G0123456789", "Z0123456789"])
def test_channel_id_muster_akzeptiert_gueltige_praefixe(kanal):
    assert wochenbericht._CHANNEL_ID_MUSTER.match(kanal)


@pytest.mark.parametrize("kanal", ["U0123456789", "0123456789", "C123"])
def test_channel_id_muster_lehnt_ungueltige_werte_ab(kanal):
    assert wochenbericht._CHANNEL_ID_MUSTER.match(kanal) is None


def test_posten_lehnt_ungueltige_channel_id_ab_vor_jedem_api_zugriff():
    with pytest.raises(RuntimeError, match="sieht nicht nach einer Channel"):
        wochenbericht.posten(
            client=cast("WebClient", object()),
            kanal="U0123456789",
            dashboard=object(),
            verzeichnis=Path("/tmp"),
            gewinn_verlust_monate=None,
        )


class _FakeSlackClient:
    def __init__(self) -> None:
        self.aufrufe: list[dict] = []

    def files_upload_v2(self, **kwargs: object) -> None:
        self.aufrufe.append(kwargs)


def test_posten_laesst_kurzarbeit_weg_wenn_ausgeschaltet(monkeypatch, tmp_path):
    """Ohne kurzarbeit_aktiv() weder das Diagramm noch der Absatz im Post-Text -
    kein Hinweis auf einen fehlenden Kurzarbeit-Report."""
    monkeypatch.setattr(wochenbericht, "SchulungenRepository", _FakeSchulungenRepository)
    monkeypatch.setattr(diagramme, "anmeldungsverlauf", lambda *a, **kw: go.Figure())
    monkeypatch.setattr(wochenbericht, "kurzarbeit_aktiv", lambda: False)
    monkeypatch.setattr(wochenbericht.pio, "write_images", lambda **kw: None)

    dashboard = _FakeDashboard()
    dashboard.prognose = _FakeNochKeinePrognose()
    client = _FakeSlackClient()

    wochenbericht.posten(
        cast("WebClient", client),
        "C0123456789",
        dashboard,
        tmp_path,
        gewinn_verlust_monate=None,
    )

    assert len(client.aufrufe) == 1
    titel_post = client.aufrufe[0]["initial_comment"]
    assert "Kurzarbeit" not in titel_post
    assert all(
        "Kurzarbeit" not in eintrag["title"] for eintrag in client.aufrufe[0]["file_uploads"]
    )


def test_optionale_ganzzahl_ohne_gesetzte_variable_liefert_standard(monkeypatch):
    monkeypatch.delenv("WOCHENBERICHT_TEST_UNGESETZT", raising=False)
    assert wochenbericht._optionale_ganzzahl("WOCHENBERICHT_TEST_UNGESETZT", 3) == 3


def test_optionale_ganzzahl_mit_gesetzter_variable(monkeypatch):
    monkeypatch.setenv("WOCHENBERICHT_TEST_GESETZT", "7")
    assert wochenbericht._optionale_ganzzahl("WOCHENBERICHT_TEST_GESETZT", 3) == 7


def test_umgebungsvariable_fehlt_wirft_verstaendlichen_fehler(monkeypatch):
    monkeypatch.delenv("WOCHENBERICHT_TEST_FEHLT", raising=False)
    with pytest.raises(RuntimeError, match="WOCHENBERICHT_TEST_FEHLT"):
        wochenbericht._umgebungsvariable("WOCHENBERICHT_TEST_FEHLT")


def test_umgebungsvariable_liefert_gesetzten_wert(monkeypatch):
    monkeypatch.setenv("WOCHENBERICHT_TEST_WERT", "wert")
    assert wochenbericht._umgebungsvariable("WOCHENBERICHT_TEST_WERT") == "wert"


class _FakeNochKeinePrognose:
    vorhanden = False
    begruendung = "Kein Projekt im Prognose-Scope."


class _FakePrognose:
    def __init__(
        self,
        *,
        horizontmonate: tuple[tuple[int, int], ...],
        summe: dict[float, float],
        kapazitaet_limitierend_anteil: float = 0.0,
    ) -> None:
        self.vorhanden = True
        self._horizontmonate = horizontmonate
        self._summe = summe
        self._kapazitaet_limitierend_anteil = kapazitaet_limitierend_anteil

    def horizontmonate(self) -> tuple[tuple[int, int], ...]:
        return self._horizontmonate

    def summe(self) -> dict[float, float]:
        return self._summe

    def kapazitaet_limitierend_anteil(self) -> float:
        return self._kapazitaet_limitierend_anteil


def test_kontext_text_ohne_prognose_liefert_deren_begruendung():
    dashboard = _FakeDashboard()
    dashboard.prognose = _FakeNochKeinePrognose()

    assert wochenbericht.kontext_text(dashboard) == "Kein Projekt im Prognose-Scope."


def test_kontext_text_nennt_zeitraum_und_bandbreite_je_monat():
    """summe() ist die Summe über den ganzen Horizont (Kollegen-Feedback: der frühere
    Text ohne "je Monat" las sich wie ein Monatswert) - der Text zeigt deshalb den
    Betrag geteilt durch die Anzahl Horizontmonate (100.000/3, 150.000/3)."""
    dashboard = _FakeDashboard()
    dashboard.prognose = _FakePrognose(
        horizontmonate=((2026, 9), (2026, 10), (2026, 11)),
        summe={0.95: 100_000.0, 0.85: 120_000.0, 0.50: 150_000.0},
    )

    text = wochenbericht.kontext_text(dashboard)

    assert "je Monat" in text
    assert "Sep 2026 bis Nov 2026" in text
    assert "33.333,33 EUR/Monat" in text
    assert "50.000,00 EUR/Monat" in text
    assert "Personalkapazität" not in text


def test_kontext_text_nennt_kapazitaetsengpass_wenn_vorhanden():
    dashboard = _FakeDashboard()
    dashboard.prognose = _FakePrognose(
        horizontmonate=((2026, 9),),
        summe={0.95: 10.0, 0.85: 12.0, 0.50: 15.0},
        kapazitaet_limitierend_anteil=0.42,
    )

    text = wochenbericht.kontext_text(dashboard)

    assert "Sep 2026" in text
    assert "42 %" in text
    assert "Personalkapazität" in text


def test_diagramm_erlaeuterungen_deckt_alle_diagrammtitel_ab(monkeypatch):
    monkeypatch.setattr(wochenbericht, "SchulungenRepository", _FakeSchulungenRepository)
    monkeypatch.setattr(diagramme, "anmeldungsverlauf", lambda *a, **kw: go.Figure())

    titel = {
        titel
        for titel, _figur in wochenbericht.diagrammtitel_und_figuren(
            _FakeDashboard(), _KURZARBEIT_ERGEBNISSE, gewinn_verlust_monate=12
        )
    }

    assert titel == set(wochenbericht.DIAGRAMM_ERLAEUTERUNGEN)


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
