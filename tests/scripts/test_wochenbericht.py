"""Fruehwarn-Tests fuer scripts/wochenbericht.py - keine Live-API, kein Slack-Post.

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
from umsatzprognose.domaene import NochKeinePrognose, Prognose

if TYPE_CHECKING:
    from collections.abc import Sequence

    from slack_sdk import WebClient

    from umsatzprognose.clockodo import Fortschritt
    from umsatzprognose.domaene.anmeldung import Anmeldungsverlauf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
import wochenbericht


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

    def umsatzrendite_kumuliert(self, *, mit_beschriftung: bool = False) -> go.Figure:
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
        self,
        jahre: Sequence[int],
        *,
        fortschritt: Fortschritt | None = None,
    ) -> _FakeAnmeldungsverlauf:
        return _FakeAnmeldungsverlauf()


def test_diagrammtitel_und_figuren_liefert_alle_vier_diagramme_in_reihenfolge(monkeypatch):
    monkeypatch.setattr(diagramme, "anmeldungsverlauf", lambda *a, **kw: go.Figure())

    ergebnis = wochenbericht.diagrammtitel_und_figuren(
        _FakeDashboard(),
        _als_anmeldungsverlauf(_FakeAnmeldungsverlauf()),
    )

    assert [titel for titel, _figur in ergebnis] == [
        "Umsatz je Monat",
        "Umsatztabelle",
        "Kumulierte Umsatzrendite je Jahr",
        "Schulungsteilnehmende je Monat",
    ]
    assert all(isinstance(figur, go.Figure) for _titel, figur in ergebnis)


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
                anmeldungsverlauf_fenster=cast("Anmeldungsverlauf", object()),
                verzeichnis=Path("/tmp"),
            ),
        )


class _FakeSlackClient:
    def __init__(self) -> None:
        self.aufrufe: list[dict] = []

    def files_upload_v2(self, **kwargs: object) -> None:
        self.aufrufe.append(kwargs)


def test_posten_haengt_alle_vier_bilder_an_einen_einzigen_post(monkeypatch, tmp_path):
    """Ein einzelner ``files_upload_v2``-Aufruf traegt alle vier Bilder gemeinsam an
    einer Nachricht (``file_uploads``), statt je Bild eine eigene Unternachricht zu
    erzeugen (siehe Moduldocstring)."""
    monkeypatch.setattr(diagramme, "anmeldungsverlauf", lambda *a, **kw: go.Figure())
    monkeypatch.setattr(wochenbericht.pio, "write_images", lambda **kw: None)  # type: ignore[attr-defined]

    dashboard = _FakeDashboard()
    dashboard.prognose = NochKeinePrognose()
    client = _FakeSlackClient()

    titel = asyncio.run(
        wochenbericht.posten_async(
            cast("WebClient", client),
            "C0123456789",
            dashboard,
            _als_anmeldungsverlauf(_FakeAnmeldungsverlauf()),
            tmp_path,
        ),
    )

    assert titel == list(wochenbericht.DIAGRAMM_ERLAEUTERUNGEN)
    assert len(client.aufrufe) == 1
    assert [eintrag["title"] for eintrag in client.aufrufe[0]["file_uploads"]] == titel


def test_export_zusammenfassung_zaehlt_nur_diagramme_ohne_tabellen():
    zusammenfassung = wochenbericht._export_zusammenfassung(
        ["Umsatz je Monat", "Kumulierte Umsatzrendite je Jahr"],
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
            _als_anmeldungsverlauf(_FakeAnmeldungsverlauf()),
        )
    }

    assert titel == set(wochenbericht.DIAGRAMM_ERLAEUTERUNGEN)


def test_post_text_enthaelt_titel_kontext_und_erlaeuterungen():
    """``post_text`` baut denselben Text wie ``posten`` an Slack schickt (siehe
    ``initial_comment``), hier aber ganz ohne Diagramm-Rendering oder Slack-Client -
    Grundlage fuer die ``--nur-text``-Kommandozeilenausgabe in ``main``."""
    dashboard = _FakeDashboard()
    dashboard.prognose = NochKeinePrognose(fehlt="Kein Projekt im Prognose-Scope.")

    text = wochenbericht.post_text(dashboard)

    assert text.startswith("(automatisch generiert)\n")
    assert "Wochenbericht Zahlen, Daten, Fakten" in text
    assert "Kein Projekt im Prognose-Scope." in text
    assert "• Umsatz je Monat:" in text


def test_argumente_ohne_flag_liefert_nur_text_false(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["wochenbericht.py"])
    assert wochenbericht._argumente().nur_text is False


def test_argumente_mit_nur_text_flag(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["wochenbericht.py", "--nur-text"])
    assert wochenbericht._argumente().nur_text is True


class _FakeGeladenesDashboard:
    async def simuliere_async(self, *, monate: int, fortschritt: Fortschritt | None = None) -> None:
        pass


def test_daten_laden_async_laedt_beide_quellen_gleichzeitig(monkeypatch):
    """Zeitmessung statt Barrier (siehe ``tests/clockodo/test_nebenlaeufig.py`` fuer
    die dortige Barrier-Variante): die per ``asyncio.to_thread`` laufende
    Anmeldungsverlauf-Ladung liegt in einem eigenen Thread, wo eine ``asyncio.Barrier``
    nicht direkt wartbar waere. Liefen Dashboard und Anmeldungsverlauf nacheinander
    statt gleichzeitig, dauerte der Aufruf mindestens ``2 * sleep`` statt nur knapp
    ``sleep``. Keine Kurzarbeit-Rohdaten mehr: der Bericht zeigt seit der Abspeckung
    auf vier Diagramme/Tabellen keinen Kurzarbeit-Inhalt mehr (siehe
    ``DIAGRAMM_ERLAEUTERUNGEN``)."""
    sleep = 0.2

    class _FakeDashboardKlasse:
        @staticmethod
        async def laden_async(
            *,
            stichtag: date,
            horizont_monate: int,
            fortschritt: Fortschritt | None = None,
        ) -> _FakeGeladenesDashboard:
            await asyncio.sleep(sleep)
            if fortschritt is not None:
                fortschritt("Bestand geladen: 1 Projekt(e)")
                fortschritt("Schulung(en) geladen: 1")
                fortschritt("Kostenprognose geladen: 1")
                fortschritt("Auslastungsmonat(e) geladen: 1")
            return _FakeGeladenesDashboard()

    class _FakeSchulungenRepositoryLangsam:
        @classmethod
        def mit_automatischen_zugangsdaten(cls) -> _FakeSchulungenRepositoryLangsam:
            return cls()

        def anmeldungsverlauf_laden(
            self,
            jahre: Sequence[int],
            *,
            fortschritt: Fortschritt | None = None,
        ) -> _FakeAnmeldungsverlauf:
            time.sleep(sleep)
            return _FakeAnmeldungsverlauf()

    monkeypatch.setattr(wochenbericht, "Dashboard", _FakeDashboardKlasse)
    monkeypatch.setattr(wochenbericht, "SchulungenRepository", _FakeSchulungenRepositoryLangsam)

    start = time.perf_counter()
    _dashboard, anmeldungsverlauf_fenster = asyncio.run(
        wochenbericht._daten_laden_async(
            stichtag=date(2026, 9, 1),
            horizont_monate=3,
            mit_anmeldungsverlauf=True,
        ),
    )
    dauer = time.perf_counter() - start

    assert dauer < sleep * 2  # sequenziell waeren es mindestens 2 * sleep
    assert isinstance(anmeldungsverlauf_fenster, _FakeAnmeldungsverlauf)


def test_daten_laden_async_ueberspringt_anmeldungsverlauf_wenn_nicht_gebraucht(monkeypatch):
    """``mit_anmeldungsverlauf=False`` (siehe ``--nur-text`` in :func:`main`, das ohne
    Diagramme keinen Anmeldungsverlauf braucht) laesst den Abruf ganz entfallen, statt
    ihn unnoetig aufzurufen - das Repository bleibt hier absichtlich ohne
    ``mit_automatischen_zugangsdaten()``, ein Zugriff wuerde also mit einem
    ``AttributeError`` auffallen."""

    class _FakeDashboardKlasse:
        @staticmethod
        async def laden_async(
            *,
            stichtag: date,
            horizont_monate: int,
            fortschritt: Fortschritt | None = None,
        ) -> _FakeGeladenesDashboard:
            return _FakeGeladenesDashboard()

    class _NichtAufzurufendesRepository:
        pass

    monkeypatch.setattr(wochenbericht, "Dashboard", _FakeDashboardKlasse)
    monkeypatch.setattr(wochenbericht, "SchulungenRepository", _NichtAufzurufendesRepository)

    _dashboard, anmeldungsverlauf_fenster = asyncio.run(
        wochenbericht._daten_laden_async(
            stichtag=date(2026, 9, 1),
            horizont_monate=3,
            mit_anmeldungsverlauf=False,
        ),
    )

    assert anmeldungsverlauf_fenster is None
