"""Test fuer webapp.app - nur mit installiertem ``web``-Extra (siehe pyproject.toml).

Ohne das Extra wird der Test uebersprungen statt die gesamte Testsuite brechen zu
lassen - ``fastapi`` ist bewusst keine Basisabhaengigkeit (siehe Moduldocstring von
:mod:`umsatzprognose.webapp`).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from umsatzprognose.darstellung import Dashboard
from umsatzprognose.domaene import (
    Anmeldung,
    Anmeldungsverlauf,
    Auslastungsmonat,
    Bestand,
    Gesamtbudget,
    Hinweis,
    Kostenplan,
    Kunde,
    Kurzarbeitsbewertung,
    Mitarbeiter,
    Monatsumsatz,
    Projekt,
    Schulungsplan,
    Schulungstermin,
    Schwellenwerte,
    Umsatzhistorie,
)
from umsatzprognose.domaene.zahlen import euro

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

import umsatzprognose.webapp.app as app_modul  # noqa: E402

# Dieselbe Zuordnung, die vor der Umstellung auf SCHULUNGEN_KATEGORIEN (siehe
# schulungen.kategorien_automatisch) als Konstante in webapp/app.py stand - hier per
# Fake statt echter Umgebungsvariable, damit die Tests ohne .env laufen (siehe
# _fake_caches unten).
KATEGORIEN = {
    "Scrum": [
        "A-CSD",
        "A-CSM",
        "A-CSPO",
        "CSD",
        "CSM 2-tägig",
        "CSM 3-tägig",
        "CSP-PO",
        "CSP-SM",
        "CSPO 2-tägig",
        "CSPO 3-tägig",
        "CAL 2",
        "CAL ETO",
    ],
    "Kanban": [
        "KCP",
        "KMM",
        "KSD",
        "KSI",
        "KSI 2-tägig",
        "KSI 3-tägig",
        "SBK",
    ],
}

STICHTAG = date(2026, 8, 24)
KUNDE = Kunde(id=1, name="Testkunde")
HISTORIE = Umsatzhistorie.zum_stichtag([Monatsumsatz(2026, 8, Decimal("1000.0"), 10.0)], STICHTAG)
PROJEKTE = (
    Projekt(
        id=1,
        name="Testprojekt",
        kunde=KUNDE,
        aktiv=True,
        budget=Gesamtbudget(betrag=Decimal("5000.0")),
        verbrauchtes_volumen=Decimal("1000.0"),
        verbrauchte_stunden=10.0,
    ),
)
BESTAND = Bestand(stichtag=STICHTAG, projekte=PROJEKTE, umsatzhistorie=HISTORIE)
SCHULUNGSPLAN = Schulungsplan(
    stichtag=STICHTAG, termine=(Schulungstermin(2026, 8, Decimal("2500.0")),)
)
DASHBOARD = Dashboard(BESTAND, SCHULUNGSPLAN, Kostenplan())
DASHBOARD.simuliere(monate=1, laeufe=100)


class _FakeDashboardCache:
    """``bereit`` liefert ``ergebnis`` fest - ``None`` simuliert eine noch nicht
    gecachte Kombination, jeder andere Wert eine bereits fertig geladene."""

    def __init__(self, ergebnis: Dashboard | None = DASHBOARD) -> None:
        self.ergebnis = ergebnis
        self.anstossen_aufrufe: list[tuple[int, int]] = []
        self.fortschritt_zeilen: list[str] = []
        self.fehler_text: str | None = None

    def bereit(self, *, horizont_monate: int, auslastung_monate: int) -> Dashboard | None:
        return self.ergebnis

    def fortschritt(self, *, horizont_monate: int, auslastung_monate: int) -> list[str]:
        return self.fortschritt_zeilen

    def fehler(self, *, horizont_monate: int, auslastung_monate: int) -> str | None:
        return self.fehler_text

    def anstossen(self, *, horizont_monate: int, auslastung_monate: int) -> None:
        self.anstossen_aufrufe.append((horizont_monate, auslastung_monate))


class _FakeAnmeldungsverlaufCache:
    def __init__(self, ergebnis: Anmeldungsverlauf | None = None) -> None:
        self.ergebnis = Anmeldungsverlauf() if ergebnis is None else ergebnis
        self.anstossen_aufrufe = 0
        self.fortschritt_zeilen: list[str] = []
        self.fehler_text: str | None = None

    def bereit(self) -> Anmeldungsverlauf | None:
        return self.ergebnis

    def fortschritt(self) -> list[str]:
        return self.fortschritt_zeilen

    def fehler(self) -> str | None:
        return self.fehler_text

    def anstossen(self) -> None:
        self.anstossen_aufrufe += 1


KURZARBEIT_ERGEBNISSE = {
    (2026, 8): Kurzarbeitsbewertung(
        jahr=2026,
        monat=8,
        schwellenwerte=Schwellenwerte(),
        anzahl_kurzarbeitsfaehig=3,
        anzahl_scheitert_interne_arbeit=1,
    )
}


class _FakeKurzarbeitCache:
    def __init__(self, ergebnis: dict | None = None) -> None:
        self.ergebnis = KURZARBEIT_ERGEBNISSE if ergebnis is None else ergebnis
        self.anstossen_aufrufe = 0
        self.fortschritt_zeilen: list[str] = []
        self.fehler_text: str | None = None
        self.bereit_schwellenwerte: Schwellenwerte | None = None

    def bereit(self, *, anzahl_monate: int, schwellenwerte: Schwellenwerte) -> dict | None:
        self.bereit_schwellenwerte = schwellenwerte
        return self.ergebnis

    def fortschritt(self) -> list[str]:
        return self.fortschritt_zeilen

    def fehler(self) -> str | None:
        return self.fehler_text

    def anstossen(self) -> None:
        self.anstossen_aufrufe += 1


@pytest.fixture(autouse=True)
def _fake_caches(monkeypatch):
    dashboard_cache = _FakeDashboardCache()
    anmeldungsverlauf_cache = _FakeAnmeldungsverlaufCache()
    kurzarbeit_cache = _FakeKurzarbeitCache()
    monkeypatch.setattr(app_modul, "_dashboard_cache", dashboard_cache)
    monkeypatch.setattr(app_modul, "_anmeldungsverlauf_cache", anmeldungsverlauf_cache)
    monkeypatch.setattr(app_modul, "_kurzarbeit_cache", kurzarbeit_cache)
    # kategorien_automatisch() liest sonst SCHULUNGEN_KATEGORIEN aus der echten
    # Umgebung (siehe schulungen.kategorien_automatisch) - hier fest verdrahtet, damit
    # die Tests ohne gesetzte .env laufen.
    monkeypatch.setattr(app_modul, "kategorien_automatisch", lambda: KATEGORIEN)
    # Standardmaessig eingeschaltet, damit die bestehenden Kurzarbeit-Tests unten das
    # bisherige Verhalten pruefen - siehe die eigenen Tests weiter unten fuer den
    # ausgeschalteten Fall (KURZARBEIT_AKTIV).
    monkeypatch.setattr(app_modul, "_KURZARBEIT_AKTIV", True)
    return dashboard_cache, anmeldungsverlauf_cache, kurzarbeit_cache


def test_uebersicht_zeigt_stichtag_und_die_drei_datencheck_grafiken():
    client = TestClient(app_modul.app)

    antwort = client.get("/")

    assert antwort.status_code == 200
    assert "24.08.2026" in antwort.text
    assert "plotly" in antwort.text.lower()


def test_uebersicht_zeigt_interne_arbeit_abschlag_regler_ohne_grafik_oder_tabelle():
    client = TestClient(app_modul.app)

    antwort = client.get("/")

    assert 'name="interne_arbeit_abschlag_prozent"' in antwort.text
    assert "<h2>Anteil interner Arbeit</h2>" not in antwort.text
    # Der Regler steht vor der Verbrauchsplan-Übersteuerung im Formular.
    assert antwort.text.index("interne_arbeit_abschlag_prozent") < antwort.text.index(
        "Verbrauchsplan-Übersteuerung"
    )


def test_dashboard_seite_interne_arbeit_abschlag_regler_steht_vor_verbrauchsplan():
    client = TestClient(app_modul.app)

    antwort = client.get("/dashboard")

    assert antwort.text.index("interne_arbeit_abschlag_prozent") < antwort.text.index(
        "Verbrauchsplan-Übersteuerung"
    )
    # Die Grafik/Tabelle stehen direkt unter der Monatstabelle, vor dem
    # Restvolumen-Regler weiter unten auf der Seite.
    assert (
        antwort.text.index("Monatstabelle")
        < antwort.text.index("Anteil interner Arbeit")
        < antwort.text.index("Anzahl Projekte mit offenem Budget")
    )


def test_uebersicht_gibt_url_parameter_an_den_cache_weiter(_fake_caches):
    dashboard_cache, _, _ = _fake_caches
    dashboard_cache.ergebnis = None
    client = TestClient(app_modul.app)

    client.get("/?horizont_monate=6&gewinn_verlust_monate=24")

    assert dashboard_cache.anstossen_aufrufe == [(6, app_modul.STANDARD_AUSLASTUNG_MONATE)]


def test_uebersicht_ohne_gecachte_daten_zeigt_die_ladeseite(_fake_caches):
    dashboard_cache, _, _ = _fake_caches
    dashboard_cache.ergebnis = None
    client = TestClient(app_modul.app)

    antwort = client.get("/")

    assert antwort.status_code == 200
    assert "werden geladen" in antwort.text
    assert "plotly" not in antwort.text.lower()
    assert dashboard_cache.anstossen_aufrufe == [(3, app_modul.STANDARD_AUSLASTUNG_MONATE)]


def test_uebersicht_zeigt_fortschritt_der_ladeseite(_fake_caches):
    dashboard_cache, _, _ = _fake_caches
    dashboard_cache.ergebnis = None
    dashboard_cache.fortschritt_zeilen = ["Bestand geladen: 900 Projekt(e) (in 16 Sekunden)"]
    client = TestClient(app_modul.app)

    antwort = client.get("/")

    assert antwort.status_code == 200
    assert "Bestand geladen: 900 Projekt(e) (in 16 Sekunden)" in antwort.text


def test_uebersicht_zeigt_einen_gescheiterten_ladeversuch(_fake_caches):
    """Ohne diese Anzeige war ein wiederholt scheiternder Ladevorgang von einem noch
    laufenden nicht zu unterscheiden - beides zeigte nur "Daten werden geladen"."""
    dashboard_cache, _, _ = _fake_caches
    dashboard_cache.ergebnis = None
    dashboard_cache.fehler_text = "504 für https://my.clockodo.com/api/v2/entrygroups"
    client = TestClient(app_modul.app)

    antwort = client.get("/")

    assert antwort.status_code == 200
    assert "504 für https://my.clockodo.com/api/v2/entrygroups" in antwort.text


def test_uebersicht_ohne_fehler_zeigt_keine_fehlermeldung(_fake_caches):
    dashboard_cache, _, _ = _fake_caches
    dashboard_cache.ergebnis = None
    client = TestClient(app_modul.app)

    antwort = client.get("/")

    assert "fehlgeschlagen" not in antwort.text


def test_uebersicht_weist_ausserhalb_der_optionen_liegende_parameter_zurueck():
    client = TestClient(app_modul.app)

    antwort = client.get("/?horizont_monate=13")

    assert antwort.status_code == 422


def test_uebersicht_zeigt_die_dropdown_optionen_und_aktuelle_auswahl():
    client = TestClient(app_modul.app)

    antwort = client.get("/?horizont_monate=6&gewinn_verlust_monate=alle")

    assert 'value="6" selected' in antwort.text
    assert 'value="alle" selected' in antwort.text
    assert 'value="24"' in antwort.text  # eine der weiteren Optionen


def test_uebersicht_wechsel_der_historischen_monate_laedt_nicht_neu(_fake_caches):
    """``gewinn_verlust_monate`` schneidet nur das schon geladene Dashboard anders
    zurecht (siehe Dashboard.gewinn_verlust_monatlich) - anders als ``horizont_monate``
    ist es kein Teil des Cache-Schluessels und darf deshalb nie neu laden."""
    dashboard_cache, _, _ = _fake_caches
    client = TestClient(app_modul.app)

    client.get("/?gewinn_verlust_monate=12")
    client.get("/?gewinn_verlust_monate=24")
    client.get("/?gewinn_verlust_monate=alle")

    assert dashboard_cache.anstossen_aufrufe == []


def test_dashboard_seite_zeigt_umsatzverlauf_und_tabelle():
    client = TestClient(app_modul.app)

    antwort = client.get("/dashboard")

    assert antwort.status_code == 200
    assert "Gewinn" in antwort.text
    assert "plotly" in antwort.text.lower()


def test_dashboard_seite_restvolumen_top_slider_steuert_die_grafik():
    client = TestClient(app_modul.app)

    antwort = client.get("/dashboard?restvolumen_top=5")

    assert antwort.status_code == 200
    assert 'name="restvolumen_top"' in antwort.text
    assert 'value="5"' in antwort.text
    assert "Anzahl Projekte mit offenem Budget" in antwort.text


def test_dashboard_seite_restvolumen_top_max_ist_anzahl_projekte_ohne_budget(_fake_caches):
    """Bewusst die Anzahl der Projekte OHNE Budget, nicht die Anzahl der Projekte in
    der Grafik selbst (siehe Klärung im Plan) - zwei verschiedene Zahlen."""
    dashboard_cache, _, _ = _fake_caches
    ohne_budget_projekt = Projekt(id=99, name="Ohne Budget", kunde=KUNDE, aktiv=True)
    bestand = Bestand(
        stichtag=STICHTAG, projekte=(*PROJEKTE, ohne_budget_projekt), umsatzhistorie=HISTORIE
    )
    dashboard = Dashboard(bestand, SCHULUNGSPLAN, Kostenplan())
    dashboard.simuliere(monate=1, laeufe=10)
    dashboard_cache.ergebnis = dashboard
    client = TestClient(app_modul.app)

    antwort = client.get("/dashboard")

    assert 'max="1"' in antwort.text  # genau ein Projekt ohne Budget


def test_dashboard_seite_zeigt_projekte_ohne_budget_und_respektiert_filter(_fake_caches):
    dashboard_cache, _, _ = _fake_caches
    ohne_budget_projekt = Projekt(id=99, name="Schulungsprodukt", kunde=KUNDE, aktiv=True)
    bestand = Bestand(
        stichtag=STICHTAG, projekte=(*PROJEKTE, ohne_budget_projekt), umsatzhistorie=HISTORIE
    )
    dashboard = Dashboard(bestand, SCHULUNGSPLAN, Kostenplan())
    dashboard.simuliere(monate=1, laeufe=10)
    dashboard_cache.ergebnis = dashboard
    client = TestClient(app_modul.app)

    ohne_filter = client.get("/dashboard")
    mit_filter = client.get("/dashboard", params={"ohne_budget_filter": "Schulungsprodukt"})

    # Nicht per Substring "Schulungsprodukt" pruefen - der Filterwert selbst taucht
    # unabhaengig vom Tabelleninhalt in jedem Navigationslink wieder auf
    # (anfrage_query). Die Tabellenzeile zeigt Kunde und Projektname kombiniert.
    assert "Testkunde / Schulungsprodukt" in ohne_filter.text
    assert "Testkunde / Schulungsprodukt" not in mit_filter.text


def test_dashboard_seite_zeigt_ueberschrift_fuer_projekte_ohne_budget():
    client = TestClient(app_modul.app)

    antwort = client.get("/dashboard")

    assert "<h2>Projekte ohne Budget</h2>" in antwort.text


def test_dashboard_seite_zeigt_immer_alle_projekte_ohne_budget(_fake_caches):
    """Kein Top-N-Slider fuer diese Tabelle - alle (gefilterten) Zeilen sind immer
    sichtbar, unabhaengig von ihrer Anzahl."""
    dashboard_cache, _, _ = _fake_caches
    ohne_budget_projekte = tuple(
        Projekt(id=100 + i, name=f"Ohne Budget {i}", kunde=KUNDE, aktiv=True) for i in range(3)
    )
    bestand = Bestand(
        stichtag=STICHTAG, projekte=(*PROJEKTE, *ohne_budget_projekte), umsatzhistorie=HISTORIE
    )
    dashboard = Dashboard(bestand, SCHULUNGSPLAN, Kostenplan())
    dashboard.simuliere(monate=1, laeufe=10)
    dashboard_cache.ergebnis = dashboard
    client = TestClient(app_modul.app)

    antwort = client.get("/dashboard")

    assert "Testkunde / Ohne Budget 0" in antwort.text
    assert "Testkunde / Ohne Budget 1" in antwort.text
    assert "Testkunde / Ohne Budget 2" in antwort.text


def test_dashboard_seite_ohne_verbrauchsplan_simuliert_nicht_neu(_fake_caches, monkeypatch):
    """Ohne gesetzten Parameter bleibt es beim gecachten Dashboard - keine zusaetzliche
    Simulation je Anfrage."""
    aufrufe: list[object] = []
    original_simuliere = Dashboard.simuliere

    def _tracking_simuliere(self, *args, **kwargs):
        aufrufe.append(self)
        return original_simuliere(self, *args, **kwargs)

    monkeypatch.setattr(Dashboard, "simuliere", _tracking_simuliere)
    client = TestClient(app_modul.app)

    client.get("/dashboard")

    assert aufrufe == []


def test_dashboard_seite_verbrauchsplan_veraendert_nicht_das_gecachte_dashboard(
    _fake_caches, monkeypatch
):
    """Wichtigster Test: ein gesetzter ``verbrauchsplan``-Parameter darf das im
    ``DashboardCache`` gehaltene, von allen Besuchenden geteilte Dashboard nicht
    veraendern - sonst saehen andere Besuchende bis zum naechsten TTL-Reload dieselbe,
    von dieser einen Anfrage uebersteuerte Prognose."""
    _, _, _ = _fake_caches
    aufrufe: list[object] = []
    original_simuliere = Dashboard.simuliere

    def _tracking_simuliere(self, *args, **kwargs):
        aufrufe.append(self)
        return original_simuliere(self, *args, **kwargs)

    monkeypatch.setattr(Dashboard, "simuliere", _tracking_simuliere)
    client = TestClient(app_modul.app)

    antwort = client.get("/dashboard", params={"verbrauchsplan": "Testprojekt: 2026-12"})

    assert antwort.status_code == 200
    assert len(aufrufe) == 1


def test_interne_arbeit_abschlag_prozent_ohne_parameter_nutzt_historischen_durchschnitt():
    anna = Mitarbeiter(id=1, name="Anna", aktiv=True)
    bestand = Bestand(stichtag=STICHTAG, mitarbeiter=(anna,))
    auslastung = (
        Auslastungsmonat(
            mitarbeiter=anna, jahr=2026, monat=7, abrechenbare_stunden=80.0, interne_stunden=20.0
        ),
    )
    dashboard = Dashboard(bestand, SCHULUNGSPLAN, Kostenplan(), auslastung)

    assert app_modul._interne_arbeit_abschlag_prozent(dashboard, None) == 20  # 20/(20+80)


def test_interne_arbeit_abschlag_prozent_mit_parameter_uebersteuert_den_durchschnitt():
    assert app_modul._interne_arbeit_abschlag_prozent(DASHBOARD, 50) == 50


def test_interne_arbeit_abschlag_prozent_ohne_auslastung_ist_null():
    assert app_modul._interne_arbeit_abschlag_prozent(DASHBOARD, None) == 0


def test_dashboard_seite_zeigt_anteil_interner_arbeit_abschnitt():
    client = TestClient(app_modul.app)

    antwort = client.get("/dashboard")

    assert "<h2>Anteil interner Arbeit</h2>" in antwort.text
    assert 'name="interne_arbeit_abschlag_prozent"' in antwort.text
    assert 'name="interne_arbeit_trend_werte"' in antwort.text


def _checkbox_markup(text: str, feldname: str) -> str:
    """Das vollstaendige (mehrzeilige) <input type="checkbox">-Tag zu ``feldname``,
    ausgeschnitten zwischen seinem Namensattribut und dem naechsten '>'."""
    start = text.index(f'name="{feldname}" value="an"')
    ende = text.index(">", start)
    return text[start:ende]


def test_dashboard_seite_trendlinie_startet_angehakt():
    client = TestClient(app_modul.app)

    antwort = client.get("/dashboard")

    assert "checked" in _checkbox_markup(antwort.text, "interne_arbeit_trend_werte")


def test_dashboard_seite_trendlinie_ausgeschaltet_zeigt_keine_trendspur():
    client = TestClient(app_modul.app)

    antwort = client.get("/dashboard", params={"interne_arbeit_trend_werte": "aus"})

    assert "checked" not in _checkbox_markup(antwort.text, "interne_arbeit_trend_werte")
    assert '"Trend"' not in antwort.text


def test_dashboard_seite_interne_arbeit_abschlag_uebernimmt_historischen_durchschnitt(
    _fake_caches,
):
    dashboard_cache, _, _ = _fake_caches
    anna = Mitarbeiter(id=1, name="Anna", aktiv=True)
    bestand = Bestand(
        stichtag=STICHTAG, projekte=PROJEKTE, mitarbeiter=(anna,), umsatzhistorie=HISTORIE
    )
    auslastung = (
        Auslastungsmonat(
            mitarbeiter=anna, jahr=2026, monat=7, abrechenbare_stunden=80.0, interne_stunden=20.0
        ),
    )
    dashboard = Dashboard(bestand, SCHULUNGSPLAN, Kostenplan(), auslastung)
    dashboard.simuliere(monate=1, laeufe=10)
    dashboard_cache.ergebnis = dashboard
    client = TestClient(app_modul.app)

    antwort = client.get("/dashboard")

    assert 'value="20"' in antwort.text


def test_dashboard_seite_interne_arbeit_abschlag_veraendert_nicht_das_gecachte_dashboard(
    _fake_caches, monkeypatch
):
    """Wie test_dashboard_seite_verbrauchsplan_veraendert_nicht_das_gecachte_dashboard,
    hier fuer den Abschlag-Regler: ein gesetzter Wert loest eine Neusimulation aus,
    darf aber das im DashboardCache gehaltene, geteilte Dashboard nicht veraendern."""
    dashboard_cache, _, _ = _fake_caches
    original_prognose = DASHBOARD.prognose
    aufrufe: list[object] = []
    original_simuliere = Dashboard.simuliere

    def _tracking_simuliere(self, *args, **kwargs):
        aufrufe.append(self)
        return original_simuliere(self, *args, **kwargs)

    monkeypatch.setattr(Dashboard, "simuliere", _tracking_simuliere)
    client = TestClient(app_modul.app)

    antwort = client.get("/dashboard", params={"interne_arbeit_abschlag_prozent": "50"})

    assert antwort.status_code == 200
    assert len(aufrufe) == 1
    assert aufrufe[0] is not DASHBOARD
    assert dashboard_cache.ergebnis.prognose is original_prognose
    assert aufrufe[0] is not dashboard_cache.ergebnis
    assert dashboard_cache.ergebnis.bestand.projekte[0].verbrauchsplan_zielmonat is None


def test_dashboard_seite_ohne_gecachte_daten_zeigt_die_ladeseite(_fake_caches):
    dashboard_cache, _, _ = _fake_caches
    dashboard_cache.ergebnis = None
    client = TestClient(app_modul.app)

    antwort = client.get("/dashboard?horizont_monate=5")

    assert antwort.status_code == 200
    assert "werden geladen" in antwort.text
    assert dashboard_cache.anstossen_aufrufe == [(5, app_modul.STANDARD_AUSLASTUNG_MONATE)]


def test_schulungen_zeigt_den_anmeldungsverlauf(_fake_caches):
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen?ab_jahr=2023")

    assert antwort.status_code == 200
    assert "plotly" in antwort.text.lower()
    assert 'value="2023" selected' in antwort.text


def test_schulungen_ohne_ab_jahr_zeigt_den_dynamischen_standard(_fake_caches):
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen")

    erwartet = app_modul._standard_anzeige_ab_jahr()
    assert antwort.status_code == 200
    assert f'value="{erwartet}" selected' in antwort.text


def test_schulungen_details_abschnitt_heisst_schulungsdetails(_fake_caches):
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen")

    assert "<summary>Schulungsdetails</summary>" in antwort.text
    assert "Einzelne Schulungen" not in antwort.text


def test_schulungen_zeigt_monatssummen_in_der_aufklappbaren_kategoriezeile(
    _fake_caches,
):
    """Die Kategorie-Zeile bleibt beim Zuklappen mit ihren Monatswerten sichtbar - sie
    stehen in derselben echten Tabellenzeile, nicht in einer separaten Tabelle."""
    _, anmeldungsverlauf_cache, _ = _fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "CSM 2-tägig", 5),
            Anmeldung(2026, 9, "CSPO 2-tägig", 2),
            Anmeldung(2026, 9, "KSD", 4),
        )
    )
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen")

    tabelle = antwort.text[antwort.text.index("<tbody>") :]
    scrum_index = tabelle.index(">Scrum<")
    zeile_ende = tabelle.index("</tr>", scrum_index)
    zeile = tabelle[scrum_index:zeile_ende]
    assert "<td>7</td>" in zeile  # 5 + 2


def test_schulungen_zeigt_gesamtzeile_ueber_alle_kategorien(_fake_caches):
    _, anmeldungsverlauf_cache, _ = _fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "CSM 2-tägig", 5),
            Anmeldung(2026, 9, "KSD", 4),
            Anmeldung(2026, 9, "Ein ganz neuer Kurs", 1),
        )
    )
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen")

    gesamt_index = antwort.text.index(">Gesamt<")
    zeile_ende = antwort.text.index("</tr>", gesamt_index)
    zeile = antwort.text[gesamt_index:zeile_ende]
    assert "<td>10</td>" in zeile


def test_schulungen_basisname_ohne_variante_bleibt_einfaches_blatt(_fake_caches):
    """Ein Schulungstyp ohne Dauer-Suffix und mit nur einem Format bleibt ein
    einfaches Blatt, ohne eigenen Aufklapp-Knopf."""
    _, anmeldungsverlauf_cache, _ = _fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(Anmeldung(2026, 9, "KSD", 4),)
    )
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen")

    ksd_index = antwort.text.index(">KSD<")
    assert "kategorie-knopf" not in antwort.text[max(0, ksd_index - 300) : ksd_index]


def test_schulungen_dauer_ebene_erscheint_nur_bei_mehreren_dauer_varianten(_fake_caches):
    _, anmeldungsverlauf_cache, _ = _fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "CSPO 2-tägig", 5),
            Anmeldung(2026, 9, "CSPO 3-tägig", 2),
        )
    )
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen")

    assert ">CSPO<" in antwort.text
    assert ">2-tägig<" in antwort.text
    assert ">3-tägig<" in antwort.text


def test_schulungen_format_ebene_erscheint_nur_bei_mehreren_formaten(_fake_caches):
    _, anmeldungsverlauf_cache, _ = _fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "CSPO 2-tägig", 5, format="Präsenz"),
            Anmeldung(2026, 9, "CSPO 2-tägig", 3, format="Online"),
        )
    )
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen")

    assert ">Präsenz<" in antwort.text
    assert ">Online<" in antwort.text


def test_schulungen_format_ebene_fehlt_bei_nur_einem_format(_fake_caches):
    _, anmeldungsverlauf_cache, _ = _fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "CSPO 2-tägig", 5, format="Präsenz"),
            Anmeldung(2026, 10, "CSPO 2-tägig", 3, format="Präsenz"),
        )
    )
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen")

    tabelle = antwort.text[antwort.text.index("<tbody>") :]
    assert ">Präsenz<" not in tabelle


def test_schulungen_vier_ebenen_format_und_dauer_zusammen(_fake_caches):
    """Deckt den Fall aus der Aufgabenstellung ab: Format- und Dauer-Ebene gemeinsam
    unter einem Basisname, wenn beide tatsaechlich variieren."""
    _, anmeldungsverlauf_cache, _ = _fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "CSPO 2-tägig", 5, format="Präsenz"),
            Anmeldung(2026, 9, "CSPO 3-tägig", 2, format="Präsenz"),
            Anmeldung(2026, 9, "CSPO 2-tägig", 1, format="Online"),
            Anmeldung(2026, 9, "CSPO 3-tägig", 4, format="Online"),
        )
    )
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen")

    cspo_index = antwort.text.index(">CSPO<")
    praesenz_index = antwort.text.index(">Präsenz<", cspo_index)
    online_index = antwort.text.index(">Online<", cspo_index)
    dauer_treffer = [m for m in ("2-tägig", "3-tägig") if f">{m}<" in antwort.text]
    assert len(dauer_treffer) == 2
    assert praesenz_index > cspo_index
    assert online_index > cspo_index


def test_schulungen_filterabschnitt_bleibt_ohne_filter_zugeklappt(_fake_caches):
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen")

    assert '<details class="regler-abschnitt" open>' not in antwort.text


def test_schulungen_filterabschnitt_klappt_bei_kategorie_auswahl_auf(_fake_caches):
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen?kategorie_filter=Scrum")

    assert '<details class="regler-abschnitt" open>' in antwort.text


def test_schulungen_kategorie_und_alle_schulungen_ergeben_je_eine_farbige_reihe(
    _fake_caches,
):
    """Jede Auswahl (auch "Alle Schulungen" zusaetzlich zu einer Kategorie) erzeugt
    ihre eigene Reihe im Diagramm, keine gegenseitig exklusive Auswahl."""
    _, anmeldungsverlauf_cache, _ = _fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "CSM 2-tägig", 5),
            Anmeldung(2026, 9, "KSD", 4),
        )
    )
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen?kategorie_filter=Alle+Kategorien&kategorie_filter=Scrum")

    assert '"name":"Alle Schulungen"' in antwort.text
    assert '"name":"Scrum"' in antwort.text


def test_schulungen_schulungen_dropdown_wird_durch_kategorie_auswahl_eingeschraenkt(
    _fake_caches,
):
    _, anmeldungsverlauf_cache, _ = _fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "CSM 2-tägig", 5),
            Anmeldung(2026, 9, "KSD", 4),
        )
    )
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen?kategorie_filter=Scrum")

    assert 'value="CSM"' in antwort.text
    assert 'value="KSD"' not in antwort.text


def test_schulungen_schulungen_dropdown_fasst_dauer_varianten_zu_basisname_zusammen(
    _fake_caches,
):
    """ "CSPO 2-tägig"/"CSPO 3-tägig" erscheinen im Dropdown zusammengefasst als
    "CSPO" - wie im Tabellen-Drilldown darunter, keine eigenen Dauer-Optionen."""
    _, anmeldungsverlauf_cache, _ = _fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "CSPO 2-tägig", 5),
            Anmeldung(2026, 9, "CSPO 3-tägig", 2),
        )
    )
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen")

    ausschnitt_start = antwort.text.index('name="schulung_filter"')
    ausschnitt_ende = antwort.text.index("</div>", ausschnitt_start)
    ausschnitt = antwort.text[ausschnitt_start:ausschnitt_ende]
    assert 'value="CSPO"' in ausschnitt
    assert 'value="CSPO 2-tägig"' not in ausschnitt
    assert 'value="CSPO 3-tägig"' not in ausschnitt


def test_schulungen_schulung_filter_summiert_ueber_dauer_varianten_hinweg():
    """Auswahl "CSPO" im Schulungen-Filter erzeugt eine Reihe, die "CSPO 2-tägig" und
    "CSPO 3-tägig" gemeinsam zaehlt."""
    verlauf = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "CSPO 2-tägig", 5),
            Anmeldung(2026, 9, "CSPO 3-tägig", 2),
        )
    )

    reihen = app_modul._anmeldungsreihen(
        verlauf,
        {},
        kategorie_filter=(),
        schulung_filter=("CSPO",),
        format_filter=(),
        dauer_filter=(),
    )

    assert reihen["CSPO"] == {(2026, 9): 7}


def test_schulungen_filter_dropdowns_sind_ohne_filter_alle_vier_auf_alle_gesetzt(
    _fake_caches,
):
    """Ohne explizite Auswahl sind alle vier 'alle'-Eintraege vorausgewaehlt, aber das
    Diagramm zeigt trotzdem nur die eine Gesamtlinie und der Filterabschnitt bleibt
    zugeklappt (siehe test_schulungen_filterabschnitt_bleibt_ohne_filter_zugeklappt)."""
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen")

    for feldname, alle_wert in (
        ("kategorie_filter", "Alle Kategorien"),
        ("schulung_filter", "Alle Schulungen"),
        ("format_filter", "Alle"),
        ("dauer_filter", "Alle"),
    ):
        ausschnitt_start = antwort.text.index(f'name="{feldname}"')
        ausschnitt_ende = antwort.text.index("</div>", ausschnitt_start)
        ausschnitt = antwort.text[ausschnitt_start:ausschnitt_ende]
        assert f'value="{alle_wert}"' in ausschnitt
        assert "checked" in ausschnitt


def test_schulungen_kategorie_optionen_alphabetisch_mit_alle_kategorien_zuerst(
    _fake_caches,
):
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen")

    ausschnitt_start = antwort.text.index('name="kategorie_filter"')
    ausschnitt_ende = antwort.text.index("</div>", ausschnitt_start)
    ausschnitt = antwort.text[ausschnitt_start:ausschnitt_ende]
    reihenfolge = [
        wert for wert in ("Alle Kategorien", "Kanban", "Scrum", "Sonstige") if wert in ausschnitt
    ]
    positionen = [ausschnitt.index(f'value="{wert}"') for wert in reihenfolge]
    assert positionen == sorted(positionen)
    assert reihenfolge[0] == "Alle Kategorien"


def test_schulungen_schulung_optionen_alphabetisch_mit_alle_schulungen_zuerst(
    _fake_caches,
):
    _, anmeldungsverlauf_cache, _ = _fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "KSD", 4),
            Anmeldung(2026, 9, "A-CSD", 5),
        )
    )
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen")

    ausschnitt_start = antwort.text.index('name="schulung_filter"')
    ausschnitt_ende = antwort.text.index("</div>", ausschnitt_start)
    ausschnitt = antwort.text[ausschnitt_start:ausschnitt_ende]
    positionen = [
        ausschnitt.index(f'value="{wert}"') for wert in ("Alle Schulungen", "A-CSD", "KSD")
    ]
    assert positionen == sorted(positionen)


def test_schulungen_trendlinien_standardmaessig_an(_fake_caches):
    """Ohne Interaktion mit dem Filter-Formular soll die Trendlinie wie bisher immer
    angezeigt werden - das Kontrollkaestchen startet deshalb angehakt."""
    _, anmeldungsverlauf_cache, _ = _fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "KSD", 4),
            Anmeldung(2026, 10, "KSD", 2),
        )
    )
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen")

    assert '"name":"Alle Schulungen (Trend)"' in antwort.text


def test_schulungen_trendlinien_checkbox_ausgeschaltet_zeigt_keine_trendreihe(
    _fake_caches,
):
    _, anmeldungsverlauf_cache, _ = _fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "KSD", 4),
            Anmeldung(2026, 10, "KSD", 2),
        )
    )
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen?trendlinien_werte=aus")

    assert "(Trend)" not in antwort.text


def test_schulungen_filter_zuruecksetzen_behaelt_ab_jahr(_fake_caches):
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen?ab_jahr=2023&kategorie_filter=Scrum")

    href_index = antwort.text.index("Filter zurücksetzen")
    zeile = antwort.text[max(0, href_index - 200) : href_index]
    assert 'href="/schulungen?ab_jahr=2023"' in zeile


def test_standard_anzeige_ab_jahr_ab_dem_mindestmonat_ist_das_laufende_jahr():
    heute = date(2026, app_modul.STANDARD_ANZEIGE_MINDESTMONAT, 15)
    assert app_modul._standard_anzeige_ab_jahr(heute=heute) == 2026


def test_standard_anzeige_ab_jahr_vor_dem_mindestmonat_ist_das_vorjahr():
    heute = date(2026, app_modul.STANDARD_ANZEIGE_MINDESTMONAT - 1, 28)
    assert app_modul._standard_anzeige_ab_jahr(heute=heute) == 2025


def test_standard_anzeige_ab_jahr_faellt_nie_vor_standard_ab_jahr():
    heute = date(app_modul.STANDARD_AB_JAHR, 1, 1)
    assert app_modul._standard_anzeige_ab_jahr(heute=heute) == app_modul.STANDARD_AB_JAHR


@pytest.mark.parametrize(
    ("wert", "erwartet"),
    [
        (euro(Decimal("4000")), '<span class="gewinn-positiv">4.000,00 EUR</span>'),
        (euro(Decimal("-1000")), '<span class="gewinn-negativ">-1.000,00 EUR</span>'),
        (euro(Decimal("0")), "0,00 EUR"),
        ("", ""),
    ],
)
def test_gewinn_eingefaerbt(wert: str, erwartet: str) -> None:
    # Exakt der Vorzeichen-Bug, der zuvor uebersehen wurde: euro_parsen() waere hier
    # faelschlich immer positiv, weil es ein Minuszeichen als "unerlaubtes Zeichen"
    # entfernt - _gewinn_eingefaerbt() muss stattdessen betrag_parsen() nutzen.
    assert app_modul._gewinn_eingefaerbt(wert) == erwartet


def test_tabelle_html_hebt_summe_ohne_und_gewinn_mit_fettung_hervor():
    tabelle = pd.DataFrame(
        [
            {
                "Monat": "Mär 2026",
                "Summe": euro(Decimal("32000")),
                "Kosten": euro(Decimal("28000")),
                "Gewinn": euro(Decimal("4000")),
            }
        ]
    )

    html = app_modul._tabelle_html(tabelle, element_id="tabelle-monat")

    # Summe (Position 2) ohne, Gewinn (Position 4) mit font-weight - unabhaengig
    # davon, dass Summe hier nicht die letzte Spalte ist.
    assert "th:nth-child(2), #tabelle-monat td:nth-child(2)" in html
    regel_summe = html[html.index("nth-child(2)") : html.index("nth-child(4)")]
    assert "font-weight" not in regel_summe
    assert "th:nth-child(4), #tabelle-monat td:nth-child(4) { border-left" in html
    assert "font-weight: 600" in html
    assert 'id="tabelle-monat"' in html
    assert '<span class="gewinn-positiv">4.000,00 EUR</span>' in html


def test_tabelle_html_ohne_element_id_erzeugt_keine_zusaetzliche_style_regel():
    tabelle = pd.DataFrame([{"Monat": "Mär 2026", "Gewinn": euro(Decimal("4000"))}])

    html = app_modul._tabelle_html(tabelle)

    assert "<style>" not in html
    assert "id=" not in html


def test_tabelle_html_ohne_gewinnspalte_escaped_weiterhin_sonderzeichen():
    # escape=False gilt tabellenweit und ist nur unbedenklich, solange keine
    # Gewinn-Spalte mit injiziertem HTML vorhanden ist (siehe Kommentar in
    # _tabelle_html) - eine Tabelle ohne Gewinn-Spalte (z. B. Projekte ohne Budget,
    # mit echten Kunden-/Projektnamen) muss weiterhin escapen.
    tabelle = pd.DataFrame([{"Projekt": "Musterkunde & Co. KG", "Grund": ""}])

    html = app_modul._tabelle_html(tabelle)

    assert "Musterkunde &amp; Co. KG" in html
    assert "Musterkunde & Co. KG" not in html


def test_schulungen_wechsel_des_jahres_laedt_nicht_neu(_fake_caches):
    """``ab_jahr`` filtert nur den schon geladenen Anmeldungsverlauf anders zurecht
    (siehe Anmeldungsverlauf.ab_jahr) - ein engerer Beginn ist immer eine Teilmenge
    des einen geladenen Bereichs und darf deshalb nie neu laden."""
    _, anmeldungsverlauf_cache, _ = _fake_caches
    client = TestClient(app_modul.app)

    client.get(f"/schulungen?ab_jahr={app_modul.STANDARD_AB_JAHR}")
    client.get(f"/schulungen?ab_jahr={app_modul.STANDARD_AB_JAHR + 2}")

    assert anmeldungsverlauf_cache.anstossen_aufrufe == 0


def test_schulungen_ohne_gecachte_daten_zeigt_die_ladeseite(_fake_caches):
    _, anmeldungsverlauf_cache, _ = _fake_caches
    anmeldungsverlauf_cache.ergebnis = None
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen?ab_jahr=2023")

    assert antwort.status_code == 200
    assert "werden geladen" in antwort.text
    assert anmeldungsverlauf_cache.anstossen_aufrufe == 1


def test_schulungen_zeigt_fortschritt_der_ladeseite(_fake_caches):
    _, anmeldungsverlauf_cache, _ = _fake_caches
    anmeldungsverlauf_cache.ergebnis = None
    anmeldungsverlauf_cache.fortschritt_zeilen = ["646 Anmeldungen aus 60 Monaten geladen."]
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen?ab_jahr=2023")

    assert antwort.status_code == 200
    assert "646 Anmeldungen aus 60 Monaten geladen." in antwort.text


def test_schulungen_weist_jahr_ausserhalb_der_optionen_zurueck():
    client = TestClient(app_modul.app)

    antwort = client.get(f"/schulungen?ab_jahr={app_modul.STANDARD_AB_JAHR - 1}")

    assert antwort.status_code == 422


def test_navigation_verlinkt_alle_vier_seiten():
    client = TestClient(app_modul.app)

    antwort = client.get("/")

    for pfad in ("/", "/dashboard", "/schulungen", "/kurzarbeit"):
        assert f'href="{pfad}"' in antwort.text


def test_favicon_wird_eingebunden_und_ausgeliefert():
    client = TestClient(app_modul.app)

    seite = client.get("/")
    assert 'href="/static/favicon.png"' in seite.text

    favicon = client.get("/static/favicon.png")
    assert favicon.status_code == 200
    assert favicon.headers["content-type"] == "image/png"


def test_start_stoesst_die_standardkombination_bereits_beim_start_an(_fake_caches):
    dashboard_cache, anmeldungsverlauf_cache, kurzarbeit_cache = _fake_caches

    with TestClient(app_modul.app):
        pass

    assert dashboard_cache.anstossen_aufrufe == [
        (int(app_modul.STANDARD_HORIZONT_MONATE), app_modul.STANDARD_AUSLASTUNG_MONATE)
    ]
    assert anmeldungsverlauf_cache.anstossen_aufrufe == 1
    assert kurzarbeit_cache.anstossen_aufrufe == 1


def test_kurzarbeit_zeigt_status_und_zaehler(_fake_caches):
    client = TestClient(app_modul.app)

    antwort = client.get("/kurzarbeit")

    assert antwort.status_code == 200
    assert "August 2026" in antwort.text
    assert "Voraussetzung erfüllt" in antwort.text  # 3 kurzarbeitsfaehig, 1 scheitert -> 75%
    assert "plotly" in antwort.text.lower()


def test_kurzarbeit_faerbt_status_wie_die_grafik(_fake_caches):
    """Dieselbe (nicht wertende) Farbfamilie wie KURZARBEIT_SCHWELLE_ERREICHT/
    KURZARBEIT_SCHWELLE_NICHT_ERREICHT in der Grafik - siehe
    .status-erfuellt/.status-nicht-erfuellt in basis.html."""
    _, _, kurzarbeit_cache = _fake_caches
    kurzarbeit_cache.ergebnis = {
        (2026, 6): Kurzarbeitsbewertung(  # 75 % Quote >= 50 %-Schwelle -> erfuellt
            jahr=2026,
            monat=6,
            schwellenwerte=Schwellenwerte(quote_organisation=0.50),
            anzahl_kurzarbeitsfaehig=3,
            anzahl_scheitert_interne_arbeit=1,
        ),
        (2026, 7): Kurzarbeitsbewertung(  # 30 % Quote < 50 %-Schwelle -> nicht erfuellt
            jahr=2026,
            monat=7,
            schwellenwerte=Schwellenwerte(quote_organisation=0.50),
            anzahl_kurzarbeitsfaehig=3,
            anzahl_scheitert_interne_arbeit=7,
        ),
        (2026, 8): Kurzarbeitsbewertung(  # keine einbezogene Person -> keine Auswertung
            jahr=2026, monat=8, schwellenwerte=Schwellenwerte(), anzahl_nicht_bestimmbar=1
        ),
    }
    client = TestClient(app_modul.app)

    antwort = client.get("/kurzarbeit")

    assert '<td class="status-erfuellt">Voraussetzung erfüllt</td>' in antwort.text
    assert '<td class="status-nicht-erfuellt">Voraussetzung nicht erfüllt</td>' in antwort.text
    assert '<td class="">keine Auswertung möglich</td>' in antwort.text


def test_kurzarbeit_zeigt_beschriftete_zeitraum_optionen(_fake_caches):
    client = TestClient(app_modul.app)

    antwort = client.get("/kurzarbeit")

    assert "Zurückliegender Zeitraum:" in antwort.text
    assert "1 Monat</option>" in antwort.text
    assert "3 Monate</option>" in antwort.text
    assert "6 Monate</option>" in antwort.text
    assert "1 Jahr</option>" in antwort.text


def test_kurzarbeit_zeigt_schwellenwert_regler_mit_standardwerten(_fake_caches):
    client = TestClient(app_modul.app)

    antwort = client.get("/kurzarbeit")

    assert 'name="anteil_interne_arbeit_prozent"' in antwort.text
    assert 'name="ueberstunden_stunden"' in antwort.text
    assert 'name="quote_organisation_prozent"' in antwort.text
    assert f'value="{app_modul.STANDARD_ANTEIL_INTERNE_ARBEIT_PROZENT}"' in antwort.text
    assert f'value="{app_modul.STANDARD_UEBERSTUNDEN_STUNDEN}"' in antwort.text
    assert f'value="{app_modul.STANDARD_QUOTE_ORGANISATION_PROZENT}"' in antwort.text
    # Bei Standardwerten bleibt der Regler-Bereich zugeklappt.
    assert '<details class="regler-abschnitt" open>' not in antwort.text


def test_kurzarbeit_zuruecksetzen_link_verweist_auf_standardwerte_und_behaelt_zeitraum(
    _fake_caches,
):
    client = TestClient(app_modul.app)

    antwort = client.get(
        "/kurzarbeit?anzahl_monate=12&anteil_interne_arbeit_prozent=10&ueberstunden_stunden=5"
    )

    assert 'href="/kurzarbeit?anzahl_monate=12"' in antwort.text


def test_kurzarbeit_gibt_regler_werte_als_schwellenwerte_an_den_cache_weiter(_fake_caches):
    _, _, kurzarbeit_cache = _fake_caches
    client = TestClient(app_modul.app)

    antwort = client.get(
        "/kurzarbeit"
        "?anteil_interne_arbeit_prozent=10"
        "&ueberstunden_stunden=5"
        "&quote_organisation_prozent=40"
    )

    assert antwort.status_code == 200
    schwellenwerte = kurzarbeit_cache.bereit_schwellenwerte
    assert schwellenwerte.anteil_interne_arbeit == pytest.approx(0.10)
    assert schwellenwerte.ueberstunden_stunden == pytest.approx(5.0)
    assert schwellenwerte.quote_organisation == pytest.approx(0.40)
    assert 'value="10"' in antwort.text
    assert 'value="5"' in antwort.text
    assert 'value="40"' in antwort.text
    # Ein vom Standard abweichender Regler haelt den Bereich aufgeklappt, statt die
    # eigene Auswahl nach dem Neuladen wieder zu verstecken.
    assert '<details class="regler-abschnitt" open>' in antwort.text


def test_kurzarbeit_haelt_regler_bereich_bereits_bei_einem_einzelnen_abweichenden_wert_offen(
    _fake_caches,
):
    client = TestClient(app_modul.app)

    antwort = client.get("/kurzarbeit?ueberstunden_stunden=20")

    assert '<details class="regler-abschnitt" open>' in antwort.text


def test_kurzarbeit_weist_regler_ausserhalb_des_wertebereichs_zurueck():
    client = TestClient(app_modul.app)

    antwort = client.get("/kurzarbeit?anteil_interne_arbeit_prozent=101")

    assert antwort.status_code == 422


def test_kurzarbeit_ohne_gecachte_daten_zeigt_die_ladeseite(_fake_caches):
    _, _, kurzarbeit_cache = _fake_caches
    kurzarbeit_cache.ergebnis = None
    client = TestClient(app_modul.app)

    antwort = client.get("/kurzarbeit?anzahl_monate=12")

    assert antwort.status_code == 200
    assert "werden geladen" in antwort.text
    assert kurzarbeit_cache.anstossen_aufrufe == 1


def test_kurzarbeit_weist_ausserhalb_der_optionen_liegende_parameter_zurueck():
    client = TestClient(app_modul.app)

    antwort = client.get("/kurzarbeit?anzahl_monate=2")

    assert antwort.status_code == 422


def test_kurzarbeit_zeigt_keine_einzelwerte_je_person():
    """Aggregatzahlen ja, aber keine Personennamen oder IDs."""
    client = TestClient(app_modul.app)

    antwort = client.get("/kurzarbeit")

    assert "Anna" not in antwort.text


def test_kurzarbeit_zeigt_keine_hinweise(_fake_caches):
    """Auf der Webapp lenken die Hinweise eher ab als im Notebook - dort bleiben sie
    (Kollegen-Feedback), auf der Webapp faellt die Anzeige komplett weg."""
    _, _, kurzarbeit_cache = _fake_caches
    hinweis = Hinweis(
        "Diese Personen sind laut Rollenzuordnung ausgeschlossen", ("301", "302", "303")
    )
    kurzarbeit_cache.ergebnis = {
        (2026, 7): Kurzarbeitsbewertung(
            jahr=2026, monat=7, schwellenwerte=Schwellenwerte(), hinweise=(hinweis,)
        ),
        (2026, 8): Kurzarbeitsbewertung(
            jahr=2026, monat=8, schwellenwerte=Schwellenwerte(), hinweise=(hinweis,)
        ),
    }
    client = TestClient(app_modul.app)

    antwort = client.get("/kurzarbeit")

    assert "Diese Personen sind laut Rollenzuordnung ausgeschlossen" not in antwort.text


def test_verbrauchsplan_aus_text_parst_gueltige_zeilen_und_ueberspringt_ungueltige():
    text = (
        "Projekt A: 2026-12\n"
        "\n"
        "keine Zeile ohne Doppelpunkt\n"
        "Projekt B: nicht-JJJJ-MM\n"
        "  : 2026-01\n"
        "Projekt C:2027-03"
    )
    assert app_modul._verbrauchsplan_aus_text(text) == {
        "Projekt A": (2026, 12),
        "Projekt C": (2027, 3),
    }


def test_verbrauchsplan_aus_text_leer_liefert_leeres_dict():
    assert app_modul._verbrauchsplan_aus_text("") == {}


def test_ohne_budget_filter_aus_text_parst_eine_zeile_je_begriff():
    text = "  it-agile GmbH  \n\nÖffentliche Schulung\n   \n"
    assert app_modul._ohne_budget_filter_aus_text(text) == [
        "it-agile GmbH",
        "Öffentliche Schulung",
    ]


def test_ohne_budget_filter_aus_text_leer_liefert_leere_liste():
    assert app_modul._ohne_budget_filter_aus_text("") == []


def test_navigation_versteckt_kurzarbeit_wenn_ausgeschaltet(monkeypatch):
    monkeypatch.setattr(app_modul, "_KURZARBEIT_AKTIV", False)
    client = TestClient(app_modul.app)

    antwort = client.get("/")

    assert 'href="/kurzarbeit' not in antwort.text


def test_kurzarbeit_route_liefert_404_wenn_ausgeschaltet(monkeypatch):
    monkeypatch.setattr(app_modul, "_KURZARBEIT_AKTIV", False)
    client = TestClient(app_modul.app)

    antwort = client.get("/kurzarbeit")

    assert antwort.status_code == 404


def test_vorladen_stoesst_kurzarbeit_cache_nicht_an_wenn_ausgeschaltet(_fake_caches, monkeypatch):
    _, _, kurzarbeit_cache = _fake_caches
    monkeypatch.setattr(app_modul, "_KURZARBEIT_AKTIV", False)

    with TestClient(app_modul.app):
        pass

    assert kurzarbeit_cache.anstossen_aufrufe == 0


def test_navigationslinks_ohne_query_wenn_alle_parameter_auf_standard(_fake_caches):
    """Standardwerte sollen beim Wechseln der Ansicht nicht in der URL landen - eine
    schlanke URL statt unveraendert mitgeschleppter Standardwerte."""
    client = TestClient(app_modul.app)

    antwort = client.get("/")

    assert 'href="/"' in antwort.text
    assert 'href="/dashboard"' in antwort.text
    assert 'href="/schulungen"' in antwort.text
    assert 'href="/kurzarbeit"' in antwort.text


def test_navigationslinks_lassen_standardwert_weg_auch_wenn_explizit_in_url(_fake_caches):
    client = TestClient(app_modul.app)

    antwort = client.get(f"/?horizont_monate={app_modul.STANDARD_HORIZONT_MONATE}")

    assert 'href="/"' in antwort.text
    assert 'href="/dashboard"' in antwort.text


def test_navigationslinks_behalten_abweichenden_parameter(_fake_caches):
    client = TestClient(app_modul.app)

    antwort = client.get("/?horizont_monate=6")

    assert 'href="/?horizont_monate=6"' in antwort.text
    assert 'href="/dashboard?horizont_monate=6"' in antwort.text


def test_verbrauchsplan_zuruecksetzen_link_ohne_abweichende_parameter_zeigt_auf_schlanke_url(
    _fake_caches,
):
    client = TestClient(app_modul.app)

    antwort = client.get("/dashboard?verbrauchsplan=Testprojekt:2026-12")

    assert 'href="/dashboard">Verbrauchsplan zurücksetzen' in antwort.text


def test_verbrauchsplan_zuruecksetzen_link_behaelt_abweichenden_parameter(_fake_caches):
    client = TestClient(app_modul.app)

    antwort = client.get("/dashboard?horizont_monate=6&verbrauchsplan=Testprojekt:2026-12")

    assert 'href="/dashboard?horizont_monate=6">Verbrauchsplan zurücksetzen' in antwort.text


def test_ohne_budget_filter_zuruecksetzen_link_ohne_abweichende_parameter_zeigt_auf_schlanke_url(
    _fake_caches,
):
    client = TestClient(app_modul.app)

    antwort = client.get("/dashboard?ohne_budget_filter=Testkunde")

    assert 'href="/dashboard">Filter zurücksetzen' in antwort.text


def test_kurzarbeit_zuruecksetzen_link_laesst_standard_zeitraum_weg(_fake_caches):
    client = TestClient(app_modul.app)

    antwort = client.get(
        f"/kurzarbeit?anzahl_monate={app_modul.STANDARD_KURZARBEIT_MONATE}"
        "&anteil_interne_arbeit_prozent=10"
    )

    assert 'href="/kurzarbeit">Schwellenwerte zurücksetzen' in antwort.text
