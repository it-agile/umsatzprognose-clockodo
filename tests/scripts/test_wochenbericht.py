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

import asyncio
import sys
import time
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pandas as pd
import plotly.graph_objects as go
import pytest

from umsatzprognose.darstellung import diagramme
from umsatzprognose.domaene import (
    Kurzarbeitsbewertung,
    NochKeinePrognose,
    Prognose,
    Rollenzuordnung,
    Schwellenwerte,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from slack_sdk import WebClient

    from umsatzprognose.clockodo import Fortschritt
    from umsatzprognose.domaene.anmeldung import Anmeldungsverlauf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
import wochenbericht

# Minimale, gueltige Kurzarbeit-Rohdaten fuer Tests von diagrammtitel_und_figuren() -
# die Funktion ruft echten Code auf (diagramme.kurzarbeit_grafik()), kein Mock noetig.
_KURZARBEIT_ERGEBNISSE = {
    (2026, 8): Kurzarbeitsbewertung(
        jahr=2026, monat=8, schwellenwerte=Schwellenwerte(), anzahl_kurzarbeitsfaehig=1
    )
}


class _FakeBestand:
    """``umsatzhistorie=None`` reicht als Stand-in - ``kontext_text`` behandelt eine
    fehlende Historie wie einen laufenden Monat ohne bereits gebuchten Umsatz (0)."""

    umsatzhistorie = None


class _FakeSchulungsplan:
    def summe(self, horizontmonate: Sequence[tuple[int, int]]) -> Decimal:
        return Decimal("0")


class _FakeKostenplan:
    def summe(self, monate: Sequence[tuple[int, int]]) -> Decimal:
        return Decimal("0")


class _FakeDashboard:
    stichtag = date(2026, 9, 1)
    prognose: Prognose = NochKeinePrognose()
    bestand: wochenbericht._Bestandsauszug = _FakeBestand()
    schulungsplan: wochenbericht._Summenquelle = _FakeSchulungsplan()
    kostenplan: wochenbericht._Summenquelle = _FakeKostenplan()

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
    anmeldungen: tuple[object, ...] = ()
    monate: tuple[object, ...] = ()

    def letzte(self, *, monate: int, stichtag: date) -> _FakeAnmeldungsverlauf:
        return self


def _als_anmeldungsverlauf(fake: _FakeAnmeldungsverlauf) -> Anmeldungsverlauf:
    """``Anmeldungsverlauf`` ist eine konkrete Dataclass, kein Protocol - der Fake
    passt strukturell (siehe ``_FakeAnmeldungsverlauf``), mypy verlangt aber den
    exakten Typ. Nur fuer die Typpruefung, an der Laufzeit unveraendert derselbe Fake."""
    return cast("Anmeldungsverlauf", fake)


class _FakeSchulungenRepository:
    @classmethod
    def mit_automatischen_zugangsdaten(cls) -> _FakeSchulungenRepository:
        return cls()

    def anmeldungsverlauf_laden(
        self, jahre: Sequence[int], *, fortschritt: Fortschritt | None = None
    ) -> _FakeAnmeldungsverlauf:
        return _FakeAnmeldungsverlauf()


def test_diagrammtitel_und_figuren_liefert_alle_neun_diagramme_in_reihenfolge(monkeypatch):
    monkeypatch.setattr(diagramme, "anmeldungsverlauf", lambda *a, **kw: go.Figure())

    ergebnis = wochenbericht.diagrammtitel_und_figuren(
        _FakeDashboard(),
        _KURZARBEIT_ERGEBNISSE,
        _als_anmeldungsverlauf(_FakeAnmeldungsverlauf()),
        gewinn_verlust_monate=12,
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
    monkeypatch.setattr(diagramme, "anmeldungsverlauf", lambda *a, **kw: go.Figure())

    ergebnis = wochenbericht.diagrammtitel_und_figuren(
        _FakeDashboard(),
        None,
        _als_anmeldungsverlauf(_FakeAnmeldungsverlauf()),
        gewinn_verlust_monate=12,
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
        asyncio.run(
            wochenbericht.posten_async(
                client=cast("WebClient", object()),
                kanal="U0123456789",
                dashboard=cast("wochenbericht._Dashboardauszug", object()),
                kurzarbeit_ergebnisse=None,
                anmeldungsverlauf_fenster=cast("Anmeldungsverlauf", object()),
                verzeichnis=Path("/tmp"),
                gewinn_verlust_monate=None,
            )
        )


class _FakeSlackClient:
    def __init__(self) -> None:
        self.aufrufe: list[dict] = []

    def files_upload_v2(self, **kwargs: object) -> None:
        self.aufrufe.append(kwargs)


def test_posten_laesst_kurzarbeit_weg_wenn_ausgeschaltet(monkeypatch, tmp_path):
    """Ohne Kurzarbeit-Ergebnisse (``kurzarbeit_ergebnisse=None`` - Baustein
    ausgeschaltet oder nicht geladen, entschieden schon in :func:`main` bzw.
    :func:`_daten_laden_async`) weder das Diagramm noch der Absatz im Post-Text -
    kein Hinweis auf einen fehlenden Kurzarbeit-Report."""
    monkeypatch.setattr(diagramme, "anmeldungsverlauf", lambda *a, **kw: go.Figure())
    monkeypatch.setattr(wochenbericht.pio, "write_images", lambda **kw: None)  # type: ignore[attr-defined]

    dashboard = _FakeDashboard()
    dashboard.prognose = NochKeinePrognose()
    client = _FakeSlackClient()

    asyncio.run(
        wochenbericht.posten_async(
            cast("WebClient", client),
            "C0123456789",
            dashboard,
            None,
            _als_anmeldungsverlauf(_FakeAnmeldungsverlauf()),
            tmp_path,
            gewinn_verlust_monate=None,
        )
    )

    assert len(client.aufrufe) == 1
    titel_post = client.aufrufe[0]["initial_comment"]
    assert "Kurzarbeit" not in titel_post
    assert all(
        "Kurzarbeit" not in eintrag["title"] for eintrag in client.aufrufe[0]["file_uploads"]
    )


def test_export_zusammenfassung_zaehlt_nur_diagramme_ohne_tabellen():
    zusammenfassung = wochenbericht._export_zusammenfassung(
        ["Umsatz je Monat", "Auslastung je Person"]
    )

    assert zusammenfassung == "2 Diagramm(e)"


def test_export_zusammenfassung_zaehlt_diagramme_und_tabellen_getrennt():
    zusammenfassung = wochenbericht._export_zusammenfassung(["Umsatz je Monat", "Umsatztabelle"])

    assert zusammenfassung == "1 Diagramm(e) und 1 Tabelle(n)"


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


class _FakePrognose:
    def __init__(
        self,
        *,
        horizontmonate: tuple[tuple[int, int], ...],
        summe: dict[float, Decimal],
        kapazitaet_limitierend_anteil: float = 0.0,
    ) -> None:
        self.vorhanden = True
        self.begruendung = ""
        self._horizontmonate = horizontmonate
        self._summe = summe
        self._kapazitaet_limitierend_anteil = kapazitaet_limitierend_anteil

    def horizontmonate(self) -> tuple[tuple[int, int], ...]:
        return self._horizontmonate

    def monatswerte(self) -> dict[float, list[Decimal]]:
        return {}

    def gebucht(self) -> list[Decimal]:
        return []

    def summe(self) -> dict[float, Decimal]:
        return self._summe

    def kapazitaet_limitierend_anteil(self) -> float:
        return self._kapazitaet_limitierend_anteil

    def kapazitaet_je_projekt(self) -> dict[int, float]:
        return {}


def test_kontext_text_ohne_prognose_liefert_deren_begruendung():
    dashboard = _FakeDashboard()
    dashboard.prognose = NochKeinePrognose(fehlt="Kein Projekt im Prognose-Scope.")

    assert wochenbericht.kontext_text(dashboard) == "Kein Projekt im Prognose-Scope."


def test_kontext_text_nennt_zeitraum_und_bandbreite_je_monat():
    """summe() ist die Summe über den ganzen Horizont (Kollegen-Feedback: der frühere
    Text ohne "je Monat" las sich wie ein Monatswert) - der Text zeigt deshalb den
    Betrag geteilt durch die Anzahl Horizontmonate (100.000/3, 150.000/3). Ohne
    Schulungsanmeldungen, bereits gebuchten Betrag und Kosten (alle 0 im Fake) sind
    Umsatz- und Gewinnbetrag identisch."""
    dashboard = _FakeDashboard()
    dashboard.prognose = _FakePrognose(
        horizontmonate=((2026, 9), (2026, 10), (2026, 11)),
        summe={
            0.95: Decimal("100000.0"),
            0.85: Decimal("120000.0"),
            0.50: Decimal("150000.0"),
        },
    )

    text = wochenbericht.kontext_text(dashboard)

    assert "je Monat" in text
    assert "Umsatzprognose" in text
    assert "Gewinn" in text
    assert "Sep 2026 bis Nov 2026" in text
    assert text.count("33.333,33 EUR/Monat") == 2
    assert text.count("50.000,00 EUR/Monat") == 2
    assert "Personalkapazität" not in text


def test_kontext_text_rechnet_schulungen_gebuchten_betrag_und_kosten_ein():
    """Kollegen-Feedback: der Umsatzbetrag soll Schulungsanmeldungen und bereits in
    Clockodo gebuchte/gemeldete Beträge einschließen, der Gewinnbetrag zusätzlich die
    Kostenprognose abziehen - beide getrennt ausgewiesen."""

    class _Monatsumsatz:
        umsatz = Decimal("1000")

    class _Umsatzhistorie:
        laufender = _Monatsumsatz()

    class _Bestand:
        umsatzhistorie = _Umsatzhistorie()

    class _Schulungsplan:
        def summe(self, horizontmonate: Sequence[tuple[int, int]]) -> Decimal:
            return Decimal("500")

    class _Kostenplan:
        def summe(self, monate: Sequence[tuple[int, int]]) -> Decimal:
            return Decimal("2000")

    dashboard = _FakeDashboard()
    dashboard.bestand = _Bestand()
    dashboard.schulungsplan = _Schulungsplan()
    dashboard.kostenplan = _Kostenplan()
    dashboard.prognose = _FakePrognose(
        horizontmonate=((2026, 9),),
        summe={0.95: Decimal("10000"), 0.85: Decimal("12000"), 0.50: Decimal("15000")},
    )

    text = wochenbericht.kontext_text(dashboard)

    # Umsatz je Niveau: 1.000 (gebucht) + 500 (Schulungen) + Simulationswert.
    assert "11.500,00 EUR/Monat" in text
    assert "16.500,00 EUR/Monat" in text
    # Gewinn je Niveau: derselbe Umsatz abzüglich 2.000 Kosten.
    assert "9.500,00 EUR/Monat" in text
    assert "14.500,00 EUR/Monat" in text


def test_kontext_text_nennt_kapazitaetsengpass_wenn_vorhanden():
    dashboard = _FakeDashboard()
    dashboard.prognose = _FakePrognose(
        horizontmonate=((2026, 9),),
        summe={0.95: Decimal("10.0"), 0.85: Decimal("12.0"), 0.50: Decimal("15.0")},
        kapazitaet_limitierend_anteil=0.42,
    )

    text = wochenbericht.kontext_text(dashboard)

    assert "Sep 2026" in text
    assert "42 %" in text
    assert "Personalkapazität" in text


def test_diagramm_erlaeuterungen_deckt_alle_diagrammtitel_ab(monkeypatch):
    monkeypatch.setattr(diagramme, "anmeldungsverlauf", lambda *a, **kw: go.Figure())

    titel = {
        titel
        for titel, _figur in wochenbericht.diagrammtitel_und_figuren(
            _FakeDashboard(),
            _KURZARBEIT_ERGEBNISSE,
            _als_anmeldungsverlauf(_FakeAnmeldungsverlauf()),
            gewinn_verlust_monate=12,
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


def test_aktive_diagrammtitel_laesst_kurzarbeit_weg_wenn_ausgeschaltet():
    assert "Kurzarbeitsbereitschaft je Monat" not in wochenbericht._aktive_diagrammtitel(None)
    assert "Kurzarbeitsbereitschaft je Monat" in wochenbericht._aktive_diagrammtitel(
        _KURZARBEIT_ERGEBNISSE
    )


def test_post_text_enthaelt_titel_kontext_und_erlaeuterungen_ohne_kurzarbeit():
    """``post_text`` baut denselben Text wie ``posten`` an Slack schickt (siehe
    ``initial_comment``), hier aber ganz ohne Diagramm-Rendering oder Slack-Client -
    Grundlage fuer die ``--nur-text``-Kommandozeilenausgabe in ``main``."""
    dashboard = _FakeDashboard()
    dashboard.prognose = NochKeinePrognose(fehlt="Kein Projekt im Prognose-Scope.")

    text = wochenbericht.post_text(dashboard, None)

    assert "Wochenbericht Zahlen, Daten, Fakten" in text
    assert "Kein Projekt im Prognose-Scope." in text
    assert "• Umsatz je Monat:" in text
    assert "Kurzarbeit" not in text


def test_post_text_mit_kurzarbeit_ergebnissen_enthaelt_absatz_und_diagrammtitel():
    dashboard = _FakeDashboard()
    dashboard.prognose = NochKeinePrognose(fehlt="Kein Projekt im Prognose-Scope.")

    text = wochenbericht.post_text(dashboard, _KURZARBEIT_ERGEBNISSE)

    assert "• Kurzarbeitsbereitschaft je Monat:" in text
    assert "Kurzarbeitsbereitschaft (Aug 2026)" in text


def test_argumente_ohne_flag_liefert_nur_text_false(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["wochenbericht.py"])
    assert wochenbericht._argumente().nur_text is False


def test_argumente_mit_nur_text_flag(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["wochenbericht.py", "--nur-text"])
    assert wochenbericht._argumente().nur_text is True


class _FakeGeladenesDashboard:
    async def simuliere_async(self, *, monate: int, fortschritt: Fortschritt | None = None) -> None:
        pass


def test_daten_laden_async_laedt_alle_drei_quellen_gleichzeitig(monkeypatch):
    """Zeitmessung statt Barrier (siehe ``tests/clockodo/test_nebenlaeufig.py`` fuer
    die dortige Barrier-Variante): die per ``asyncio.to_thread`` laufende
    Anmeldungsverlauf-Ladung liegt in einem eigenen Thread, wo eine ``asyncio.Barrier``
    nicht direkt wartbar waere. Liefen Dashboard, Kurzarbeit-Rohdaten und
    Anmeldungsverlauf nacheinander statt gleichzeitig, dauerte der Aufruf mindestens
    ``3 * sleep`` statt nur knapp ``sleep``."""
    sleep = 0.2

    class _FakeDashboardKlasse:
        @staticmethod
        async def laden_async(
            *, stichtag: date, horizont_monate: int, fortschritt: Fortschritt | None = None
        ) -> _FakeGeladenesDashboard:
            await asyncio.sleep(sleep)
            if fortschritt is not None:
                fortschritt("Bestand geladen: 1 Projekt(e)")
                fortschritt("Schulung(en) geladen: 1")
                fortschritt("Kostenprognose geladen: 1")
                fortschritt("Auslastungsmonat(e) geladen: 1")
            return _FakeGeladenesDashboard()

    class _FakeKurzarbeitRepository:
        @classmethod
        def mit_automatischen_zugangsdaten(cls) -> _FakeKurzarbeitRepository:
            return cls()

        async def laden_async(
            self, *, stichtag: date, anzahl_monate: int, fortschritt: Fortschritt | None = None
        ) -> dict:
            await asyncio.sleep(sleep)
            return {}

    class _FakeSchulungenRepositoryLangsam:
        @classmethod
        def mit_automatischen_zugangsdaten(cls) -> _FakeSchulungenRepositoryLangsam:
            return cls()

        def anmeldungsverlauf_laden(
            self, jahre: Sequence[int], *, fortschritt: Fortschritt | None = None
        ) -> _FakeAnmeldungsverlauf:
            time.sleep(sleep)
            return _FakeAnmeldungsverlauf()

    monkeypatch.setattr(wochenbericht, "Dashboard", _FakeDashboardKlasse)
    monkeypatch.setattr(wochenbericht, "KurzarbeitRepository", _FakeKurzarbeitRepository)
    monkeypatch.setattr(wochenbericht, "SchulungenRepository", _FakeSchulungenRepositoryLangsam)
    monkeypatch.setattr(wochenbericht, "rollenzuordnung_automatisch", Rollenzuordnung)

    start = time.perf_counter()
    _dashboard, kurzarbeit_ergebnisse, anmeldungsverlauf_fenster = asyncio.run(
        wochenbericht._daten_laden_async(
            stichtag=date(2026, 9, 1),
            horizont_monate=3,
            mit_kurzarbeit=True,
            mit_anmeldungsverlauf=True,
        )
    )
    dauer = time.perf_counter() - start

    assert dauer < sleep * 2  # sequenziell waeren es mindestens 3 * sleep
    assert kurzarbeit_ergebnisse == {}
    assert isinstance(anmeldungsverlauf_fenster, _FakeAnmeldungsverlauf)


def test_daten_laden_async_ueberspringt_kurzarbeit_und_anmeldungsverlauf_wenn_nicht_gebraucht(
    monkeypatch,
):
    """``mit_kurzarbeit=False``/``mit_anmeldungsverlauf=False`` (siehe ``--nur-text`` in
    :func:`main`, das ohne Diagramme keinen Anmeldungsverlauf braucht) lassen den
    jeweiligen Abruf ganz entfallen, statt ihn unnoetig aufzurufen - die beiden
    Repositories bleiben hier absichtlich ohne ``mit_automatischen_zugangsdaten()``,
    ein Zugriff wuerde also mit einem ``AttributeError`` auffallen."""

    class _FakeDashboardKlasse:
        @staticmethod
        async def laden_async(
            *, stichtag: date, horizont_monate: int, fortschritt: Fortschritt | None = None
        ) -> _FakeGeladenesDashboard:
            return _FakeGeladenesDashboard()

    class _NichtAufzurufendesRepository:
        pass

    monkeypatch.setattr(wochenbericht, "Dashboard", _FakeDashboardKlasse)
    monkeypatch.setattr(wochenbericht, "KurzarbeitRepository", _NichtAufzurufendesRepository)
    monkeypatch.setattr(wochenbericht, "SchulungenRepository", _NichtAufzurufendesRepository)

    _dashboard, kurzarbeit_ergebnisse, anmeldungsverlauf_fenster = asyncio.run(
        wochenbericht._daten_laden_async(
            stichtag=date(2026, 9, 1),
            horizont_monate=3,
            mit_kurzarbeit=False,
            mit_anmeldungsverlauf=False,
        )
    )

    assert kurzarbeit_ergebnisse is None
    assert anmeldungsverlauf_fenster is None
