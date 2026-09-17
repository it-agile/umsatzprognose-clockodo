"""Test fuer webapp.app - nur mit installiertem ``web``-Extra (siehe pyproject.toml).

Ohne das Extra wird der Test uebersprungen statt die gesamte Testsuite brechen zu
lassen - ``fastapi`` ist bewusst keine Basisabhaengigkeit (siehe Moduldocstring von
:mod:`umsatzprognose.webapp`).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import cast

import pandas as pd
import pytest

from umsatzprognose.darstellung import Dashboard
from umsatzprognose.domaene import (
    Anmeldung,
    Anmeldungsknoten,
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
    WeibullFakturierbareArbeit,
)
from umsatzprognose.domaene.zahlen import euro

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

import umsatzprognose.webapp.app as app_modul  # noqa: E402

# Dieselbe Zuordnung, die vor der Umstellung auf SCHULUNGEN_KATEGORIEN (siehe
# schulungen.kategorien_automatisch) als Konstante in webapp/app.py stand - hier per
# Fake statt echter Umgebungsvariable, damit die Tests ohne .env laufen (siehe
# fake_caches unten).
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
def fake_caches(monkeypatch):
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


def test_uebersicht_zeigt_interne_arbeit_regler_ohne_grafik_oder_tabelle():
    client = TestClient(app_modul.app)

    antwort = client.get("/")

    assert 'name="interne_arbeit_modus"' in antwort.text
    assert "<h2>Anteil fakturierbarer Arbeit</h2>" not in antwort.text
    # Der Regler steht vor der Verbrauchsplan-Übersteuerung im Formular.
    assert antwort.text.index("interne_arbeit_modus") < antwort.text.index(
        "Verbrauchsplan-Übersteuerung"
    )


def test_dashboard_seite_interne_arbeit_regler_steht_vor_verbrauchsplan():
    client = TestClient(app_modul.app)

    antwort = client.get("/dashboard")

    assert antwort.text.index("interne_arbeit_modus") < antwort.text.index(
        "Verbrauchsplan-Übersteuerung"
    )
    # Die Grafik/Tabelle stehen direkt unter der Monatstabelle, vor dem
    # Restvolumen-Regler weiter unten auf der Seite.
    assert (
        antwort.text.index("Monatstabelle")
        < antwort.text.index("Anteil fakturierbarer Arbeit")
        < antwort.text.index("Anzahl Projekte mit offenem Budget")
    )


@pytest.mark.parametrize("pfad", ["/", "/dashboard"])
def test_prognosehorizont_und_laeufe_stehen_im_simulations_parameter_abschnitt_vor_der_verteilung(
    pfad,
):
    """Prognosehorizont und Anzahl Simulationsläufe gehören zur Simulation wie der
    Anteil fakturierbarer Arbeit und stehen deshalb ganz oben im selben, gemeinsam
    eingeklappten Abschnitt "Simulations-Parameter", vor der Verteilungsauswahl
    (Pauschal/Weibull/Gauss)."""
    client = TestClient(app_modul.app)

    antwort = client.get(pfad)

    assert (
        antwort.text.index("Simulations-Parameter")
        < antwort.text.index("Prognosehorizont")
        < antwort.text.index("Anzahl Simulationsläufe")
        < antwort.text.index("interne_arbeit_modus")
    )


@pytest.mark.parametrize("pfad", ["/", "/dashboard"])
def test_laeufe_regler_zeigt_standardwert_und_wertebereich(pfad):
    client = TestClient(app_modul.app)

    antwort = client.get(pfad)

    assert 'name="laeufe"' in antwort.text
    assert 'min="1" max="1000000"' in antwort.text
    assert 'value="10000"' in antwort.text
    assert "10.000" in antwort.text  # Anzeige mit deutschem Tausendertrennzeichen
    # Das Zahlenfeld neben dem Regler ist editierbar, ohne selbst einen eigenen
    # Namen (und damit Submit-Bezug) zu tragen - siehe _regler.html.
    assert '<input type="number"' in antwort.text


@pytest.mark.parametrize("pfad", ["/", "/dashboard"])
def test_laeufe_ausserhalb_des_wertebereichs_wird_zurueckgewiesen(pfad):
    client = TestClient(app_modul.app)

    assert client.get(pfad, params={"laeufe": 0}).status_code == 422
    assert client.get(pfad, params={"laeufe": 1_000_001}).status_code == 422
    assert client.get(pfad, params={"laeufe": 1}).status_code == 200
    assert client.get(pfad, params={"laeufe": 1_000_000}).status_code == 200


@pytest.mark.parametrize("pfad", ["/", "/dashboard"])
def test_laeufe_abweichend_vom_standard_haelt_den_abschnitt_offen(pfad):
    client = TestClient(app_modul.app)

    antwort = client.get(pfad, params={"laeufe": 500})

    assert '<details class="regler-abschnitt" open>' in antwort.text
    assert "500 Läufe" in antwort.text


@pytest.mark.parametrize("pfad", ["/", "/dashboard"])
def test_laeufe_zuruecksetzen_link_entfernt_den_parameter(pfad):
    client = TestClient(app_modul.app)

    antwort = client.get(pfad, params={"laeufe": 500, "horizont_monate": "6"})

    # Der Zuruecksetzen-Link behaelt andere abweichende Parameter (hier
    # horizont_monate) bei und entfernt nur laeufe, das dadurch auf seinen
    # Standardwert zurueckfaellt.
    assert f'href="{pfad}?horizont_monate=6">Auf Standardwert zurücksetzen' in antwort.text


@pytest.mark.parametrize("pfad", ["/", "/dashboard"])
def test_simulations_parameter_und_verteilungs_parameter_sind_optisch_getrennt(pfad):
    """Prognosehorizont/Anzahl Simulationsläufe stehen in einer eigenen Reglergruppe,
    optisch abgesetzt (.regler-trenner) von der Verteilungsauswahl darunter."""
    client = TestClient(app_modul.app)

    antwort = client.get(pfad)

    assert '<div class="regler-gruppe regler-trenner">' in antwort.text
    assert antwort.text.index("Anzahl Simulationsläufe") < antwort.text.index(
        '<div class="regler-gruppe regler-trenner">'
    )


@pytest.mark.parametrize("pfad", ["/", "/dashboard"])
def test_zusammenfassung_zeigt_weibull_parameter_im_zugeklappten_zustand(pfad, fake_caches):
    dashboard_cache, _, _ = fake_caches
    anna = Mitarbeiter(id=1, name="Anna", aktiv=True)
    bestand = Bestand(
        stichtag=STICHTAG, projekte=PROJEKTE, mitarbeiter=(anna,), umsatzhistorie=HISTORIE
    )
    auslastung = (
        Auslastungsmonat(
            mitarbeiter=anna, jahr=2026, monat=7, abrechenbare_stunden=80.0, interne_stunden=20.0
        ),
        Auslastungsmonat(
            mitarbeiter=anna, jahr=2026, monat=6, abrechenbare_stunden=90.0, interne_stunden=10.0
        ),
    )
    dashboard = Dashboard(bestand, SCHULUNGSPLAN, Kostenplan(), auslastung)
    dashboard.simuliere(monate=1, laeufe=10)
    dashboard_cache.ergebnis = dashboard
    client = TestClient(app_modul.app)

    antwort = client.get(pfad, params={"interne_arbeit_modus": "weibull"})

    assert "Weibull (k=" in antwort.text
    assert "λ=" in antwort.text


@pytest.mark.parametrize("pfad", ["/", "/dashboard"])
def test_zusammenfassung_zeigt_gauss_parameter_im_zugeklappten_zustand(pfad, fake_caches):
    dashboard_cache, _, _ = fake_caches
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

    antwort = client.get(pfad, params={"interne_arbeit_modus": "gauss"})

    assert "Gauss (μ=" in antwort.text
    assert "σ=" in antwort.text


def test_uebersicht_gibt_url_parameter_an_den_cache_weiter(fake_caches):
    dashboard_cache, _, _ = fake_caches
    dashboard_cache.ergebnis = None
    client = TestClient(app_modul.app)

    client.get("/?horizont_monate=6&gewinn_verlust_monate=24")

    assert dashboard_cache.anstossen_aufrufe == [(6, app_modul.STANDARD_AUSLASTUNG_MONATE)]


def test_uebersicht_ohne_gecachte_daten_zeigt_die_ladeseite(fake_caches):
    dashboard_cache, _, _ = fake_caches
    dashboard_cache.ergebnis = None
    client = TestClient(app_modul.app)

    antwort = client.get("/")

    assert antwort.status_code == 200
    assert "werden geladen" in antwort.text
    assert "plotly" not in antwort.text.lower()
    assert dashboard_cache.anstossen_aufrufe == [(3, app_modul.STANDARD_AUSLASTUNG_MONATE)]


def test_uebersicht_zeigt_fortschritt_der_ladeseite(fake_caches):
    dashboard_cache, _, _ = fake_caches
    dashboard_cache.ergebnis = None
    dashboard_cache.fortschritt_zeilen = ["Bestand geladen: 900 Projekt(e) (in 16 Sekunden)"]
    client = TestClient(app_modul.app)

    antwort = client.get("/")

    assert antwort.status_code == 200
    assert "Bestand geladen: 900 Projekt(e) (in 16 Sekunden)" in antwort.text


def test_uebersicht_zeigt_einen_gescheiterten_ladeversuch(fake_caches):
    """Ohne diese Anzeige war ein wiederholt scheiternder Ladevorgang von einem noch
    laufenden nicht zu unterscheiden - beides zeigte nur "Daten werden geladen"."""
    dashboard_cache, _, _ = fake_caches
    dashboard_cache.ergebnis = None
    dashboard_cache.fehler_text = "504 für https://my.clockodo.com/api/v2/entrygroups"
    client = TestClient(app_modul.app)

    antwort = client.get("/")

    assert antwort.status_code == 200
    assert "504 für https://my.clockodo.com/api/v2/entrygroups" in antwort.text


def test_uebersicht_ohne_fehler_zeigt_keine_fehlermeldung(fake_caches):
    dashboard_cache, _, _ = fake_caches
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


def test_uebersicht_wechsel_der_historischen_monate_laedt_nicht_neu(fake_caches):
    """``gewinn_verlust_monate`` schneidet nur das schon geladene Dashboard anders
    zurecht (siehe Dashboard.gewinn_verlust_monatlich) - anders als ``horizont_monate``
    ist es kein Teil des Cache-Schluessels und darf deshalb nie neu laden."""
    dashboard_cache, _, _ = fake_caches
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


def test_dashboard_seite_restvolumen_top_max_ist_anzahl_projekte_ohne_budget(fake_caches):
    """Bewusst die Anzahl der Projekte OHNE Budget, nicht die Anzahl der Projekte in
    der Grafik selbst (siehe Klärung im Plan) - zwei verschiedene Zahlen."""
    dashboard_cache, _, _ = fake_caches
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


def test_dashboard_seite_zeigt_projekte_ohne_budget_und_respektiert_filter(fake_caches):
    dashboard_cache, _, _ = fake_caches
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


def test_dashboard_seite_zeigt_immer_alle_projekte_ohne_budget(fake_caches):
    """Kein Top-N-Slider fuer diese Tabelle - alle (gefilterten) Zeilen sind immer
    sichtbar, unabhaengig von ihrer Anzahl."""
    dashboard_cache, _, _ = fake_caches
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


def test_dashboard_seite_ohne_verbrauchsplan_simuliert_nicht_neu(monkeypatch):
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
    fake_caches, monkeypatch
):
    """Wichtigster Test: ein gesetzter ``verbrauchsplan``-Parameter darf das im
    ``DashboardCache`` gehaltene, von allen Besuchenden geteilte Dashboard nicht
    veraendern - sonst saehen andere Besuchende bis zum naechsten TTL-Reload dieselbe,
    von dieser einen Anfrage uebersteuerte Prognose."""
    _, _, _ = fake_caches
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


def test_interne_arbeit_regler_werte_ohne_uebersteuerung_nutzt_historischen_durchschnitt():
    """Ohne eigenen Pauschalwert kommt der Vorschlag aus
    ``Dashboard.durchschnittlicher_anteil_fakturierbarer_arbeit()``, kaufmaennisch
    auf volle Prozent gerundet."""
    anna = Mitarbeiter(id=1, name="Anna", aktiv=True)
    bestand = Bestand(stichtag=STICHTAG, mitarbeiter=(anna,))
    auslastung = (
        Auslastungsmonat(
            mitarbeiter=anna, jahr=2026, monat=7, abrechenbare_stunden=80.0, interne_stunden=20.0
        ),
    )
    dashboard = Dashboard(bestand, SCHULUNGSPLAN, Kostenplan(), auslastung)

    regler = app_modul._interne_arbeit_regler_werte(
        dashboard,
        anteil_fakturierbar_prozent=None,
        weibull_formparameter=None,
        weibull_skalenparameter_prozent=None,
        gauss_mittelwert_prozent=None,
        gauss_standardabweichung=None,
    )

    assert regler.aktuell.pauschal_prozent == 80  # 80/(20+80)


def test_interne_arbeit_regler_werte_pauschal_uebersteuerung_gewinnt_gegen_die_historie():
    regler = app_modul._interne_arbeit_regler_werte(
        DASHBOARD,
        anteil_fakturierbar_prozent=42,
        weibull_formparameter=None,
        weibull_skalenparameter_prozent=None,
        gauss_mittelwert_prozent=None,
        gauss_standardabweichung=None,
    )

    assert regler.aktuell.pauschal_prozent == 42


def test_interne_arbeit_regler_werte_weibull_ohne_uebersteuerung_nutzt_die_historie():
    anna = Mitarbeiter(id=1, name="Anna", aktiv=True)
    bestand = Bestand(stichtag=STICHTAG, mitarbeiter=(anna,))
    auslastung = (
        Auslastungsmonat(
            mitarbeiter=anna, jahr=2026, monat=7, abrechenbare_stunden=80.0, interne_stunden=20.0
        ),
        Auslastungsmonat(
            mitarbeiter=anna, jahr=2026, monat=6, abrechenbare_stunden=90.0, interne_stunden=10.0
        ),
    )
    dashboard = Dashboard(bestand, SCHULUNGSPLAN, Kostenplan(), auslastung)

    regler = app_modul._interne_arbeit_regler_werte(
        dashboard,
        anteil_fakturierbar_prozent=None,
        weibull_formparameter=None,
        weibull_skalenparameter_prozent=None,
        gauss_mittelwert_prozent=None,
        gauss_standardabweichung=None,
    )

    erwartet = WeibullFakturierbareArbeit.aus_stichprobe(
        dashboard.fakturierbare_arbeit_verteilung().werte
    )
    assert regler.weibull.formparameter == pytest.approx(erwartet.formparameter)
    assert regler.weibull.skalenparameter == pytest.approx(erwartet.skalenparameter)


def test_interne_arbeit_regler_werte_gauss_uebersteuerung_gewinnt_gegen_die_historie():
    regler = app_modul._interne_arbeit_regler_werte(
        DASHBOARD,
        anteil_fakturierbar_prozent=None,
        weibull_formparameter=None,
        weibull_skalenparameter_prozent=None,
        gauss_mittelwert_prozent=42,
        gauss_standardabweichung=0.07,
    )

    assert regler.gauss.mittelwert == pytest.approx(0.42)
    assert regler.gauss.standardabweichung == pytest.approx(0.07)
    assert regler.aktuell.gauss_mittelwert_prozent == pytest.approx(42)
    assert regler.aktuell.gauss_standardabweichung == pytest.approx(0.07)


def test_interne_arbeit_regler_werte_ohne_historie_faellt_neutral_zurueck():
    """DASHBOARD (Modulkonstante) hat keine geladene Auslastung - die Weibull-
    Momentenmethode braucht aber mindestens zwei Beobachtungen, siehe
    WeibullFakturierbareArbeit.aus_stichprobe()."""
    regler = app_modul._interne_arbeit_regler_werte(
        DASHBOARD,
        anteil_fakturierbar_prozent=None,
        weibull_formparameter=None,
        weibull_skalenparameter_prozent=None,
        gauss_mittelwert_prozent=None,
        gauss_standardabweichung=None,
    )

    # ohne Historie: volle Kapazitaet als neutraler Vorschlag
    assert regler.aktuell.pauschal_prozent == 100
    assert regler.weibull.formparameter == 1.0
    assert regler.weibull.skalenparameter == 0.0
    assert regler.gauss.mittelwert == 0.0
    assert regler.gauss.standardabweichung == 0.0


def test_dashboard_seite_zeigt_anteil_fakturierbarer_arbeit_abschnitt():
    client = TestClient(app_modul.app)

    antwort = client.get("/dashboard")

    assert "<h2>Anteil fakturierbarer Arbeit</h2>" in antwort.text
    assert 'name="interne_arbeit_modus"' in antwort.text
    assert 'name="interne_arbeit_trend_werte"' in antwort.text
    assert "<h3>Verteilung über Personen-Monate</h3>" in antwort.text
    assert 'name="interne_arbeit_verteilung_min_prozent"' in antwort.text
    assert 'name="interne_arbeit_verteilung_max_prozent"' in antwort.text


def test_dashboard_seite_interne_arbeit_verteilung_regler_blenden_ausreisser_aus(fake_caches):
    dashboard_cache, _, _ = fake_caches
    anna = Mitarbeiter(id=1, name="Anna", aktiv=True)
    bert = Mitarbeiter(id=2, name="Bert", aktiv=True)
    bestand = Bestand(
        stichtag=STICHTAG, projekte=PROJEKTE, mitarbeiter=(anna, bert), umsatzhistorie=HISTORIE
    )
    auslastung = (
        Auslastungsmonat(
            mitarbeiter=anna, jahr=2026, monat=7, abrechenbare_stunden=95.0, interne_stunden=5.0
        ),  # 5%
        Auslastungsmonat(
            mitarbeiter=bert, jahr=2026, monat=7, abrechenbare_stunden=70.0, interne_stunden=30.0
        ),  # 30%
    )
    dashboard = Dashboard(bestand, SCHULUNGSPLAN, Kostenplan(), auslastung)
    dashboard.simuliere(monate=1, laeufe=10)
    dashboard_cache.ergebnis = dashboard
    client = TestClient(app_modul.app)

    antwort = client.get(
        "/dashboard",
        params={
            "interne_arbeit_verteilung_min_prozent": "10",
            "interne_arbeit_verteilung_max_prozent": "50",
        },
    )

    assert antwort.status_code == 200
    assert 'value="10"' in antwort.text
    assert 'value="50"' in antwort.text


def test_dashboard_seite_interne_arbeit_verteilung_regler_erzwingt_mindestbreite():
    client = TestClient(app_modul.app)

    antwort = client.get(
        "/dashboard",
        params={
            "interne_arbeit_verteilung_min_prozent": "80",
            "interne_arbeit_verteilung_max_prozent": "20",
        },
    )

    assert antwort.status_code == 200
    assert 'value="80"' in antwort.text  # Minimum unveraendert uebernommen
    assert 'value="81"' in antwort.text  # Maximum auf Minimum + 1 angehoben


def _checkbox_markup(text: str, feldname: str) -> str:
    """Das vollstaendige (mehrzeilige) <input type="checkbox">-Tag zu ``feldname``,
    ausgeschnitten zwischen seinem Namensattribut und dem naechsten '>' - das
    onchange-Attribut (enthaelt "this.checked" als JavaScript-Ausdruck) wird dabei
    herausgeschnitten, damit ein reiner Substring-Test auf das HTML-Attribut
    "checked" nicht faelschlich auf "this.checked" anschlaegt."""
    start = text.index(f'name="{feldname}" value="an"')
    ende = text.index(">", start)
    markup = text[start:ende]
    onchange_start = markup.index("onchange=")
    return markup[:onchange_start]


def test_dashboard_seite_trendlinie_startet_angehakt():
    client = TestClient(app_modul.app)

    antwort = client.get("/dashboard")

    assert "checked" in _checkbox_markup(antwort.text, "interne_arbeit_trend_werte")


def test_dashboard_seite_trendlinie_ausgeschaltet_zeigt_keine_trendspur():
    client = TestClient(app_modul.app)

    antwort = client.get("/dashboard", params={"interne_arbeit_trend_werte": "aus"})

    assert "checked" not in _checkbox_markup(antwort.text, "interne_arbeit_trend_werte")
    assert '"Trend"' not in antwort.text


def test_dashboard_seite_trendlinie_verstecktes_feld_deaktiviert_wenn_angehakt():
    """Regression: dasselbe versteckte-Feld-Muster wie bei /schulungen (siehe dortigen
    Test) - deaktiviert, sobald die Checkbox angehakt ist, sonst zwei Werte auf einmal."""
    client = TestClient(app_modul.app)

    angehakt = client.get("/dashboard")
    abgehakt = client.get("/dashboard", params={"interne_arbeit_trend_werte": "aus"})

    def aus_feld_markup(text: str) -> str:
        start = text.index('name="interne_arbeit_trend_werte" value="aus"')
        return text[start : text.index(">", start)]

    assert "disabled" in aus_feld_markup(angehakt.text)
    assert "disabled" not in aus_feld_markup(abgehakt.text)


def test_dashboard_seite_gauss_modus_uebernimmt_historischen_mittelwert(fake_caches):
    dashboard_cache, _, _ = fake_caches
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

    antwort = client.get("/dashboard", params={"interne_arbeit_modus": "gauss"})

    assert 'value="80.0"' in antwort.text  # 80/(20+80) als Prozent, aus der einen Beobachtung


def test_dashboard_seite_weibull_skalenparameter_uebersteuerung_wirkt_als_prozent(fake_caches):
    dashboard_cache, _, _ = fake_caches
    anna = Mitarbeiter(id=1, name="Anna", aktiv=True)
    bestand = Bestand(
        stichtag=STICHTAG, projekte=PROJEKTE, mitarbeiter=(anna,), umsatzhistorie=HISTORIE
    )
    dashboard = Dashboard(bestand, SCHULUNGSPLAN, Kostenplan())
    dashboard.simuliere(monate=1, laeufe=10)
    dashboard_cache.ergebnis = dashboard
    client = TestClient(app_modul.app)

    antwort = client.get(
        "/dashboard",
        params={
            "interne_arbeit_modus": "weibull",
            "interne_arbeit_weibull_skalenparameter_prozent": "75",
        },
    )

    assert 'name="interne_arbeit_weibull_skalenparameter_prozent"' in antwort.text
    assert 'value="75.0"' in antwort.text


def test_dashboard_seite_gauss_standardabweichung_bleibt_fliesskommazahl(fake_caches):
    """Anders als Mittelwert/Skalenparameter ist die Standardabweichung kein Anteilswert
    und bleibt deshalb eine reine Fliesskommazahl, kein ``_prozent``-Parameter."""
    dashboard_cache, _, _ = fake_caches
    anna = Mitarbeiter(id=1, name="Anna", aktiv=True)
    bestand = Bestand(
        stichtag=STICHTAG, projekte=PROJEKTE, mitarbeiter=(anna,), umsatzhistorie=HISTORIE
    )
    dashboard = Dashboard(bestand, SCHULUNGSPLAN, Kostenplan())
    dashboard.simuliere(monate=1, laeufe=10)
    dashboard_cache.ergebnis = dashboard
    client = TestClient(app_modul.app)

    antwort = client.get(
        "/dashboard",
        params={"interne_arbeit_modus": "gauss", "interne_arbeit_gauss_standardabweichung": "0.12"},
    )

    assert 'name="interne_arbeit_gauss_standardabweichung"' in antwort.text
    assert "interne_arbeit_gauss_standardabweichung_prozent" not in antwort.text
    assert 'value="0.120"' in antwort.text


def test_dashboard_seite_zeigt_historischen_vorschlag_je_modus(fake_caches):
    """Der historische Vorschlagswert steht direkt in der Regler-Beschriftung, egal ob
    der aktuelle Wert davon abweicht - Orientierung beim manuellen Einstellen."""
    dashboard_cache, _, _ = fake_caches
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

    pauschal = client.get(
        "/dashboard",
        params={"interne_arbeit_modus": "pauschal", "anteil_fakturierbar_prozent": "10"},
    )
    assert "historischer Durchschnitt" in pauschal.text
    assert "80 %" in pauschal.text  # historischer Wert, unabhaengig vom uebersteuerten Regler

    weibull = client.get(
        "/dashboard",
        params={
            "interne_arbeit_modus": "weibull",
            "interne_arbeit_weibull_skalenparameter_prozent": "5",
        },
    )
    assert "historischer Vorschlag" in weibull.text

    gauss = client.get(
        "/dashboard",
        params={
            "interne_arbeit_modus": "gauss",
            "interne_arbeit_gauss_mittelwert_prozent": "5",
        },
    )
    assert "historischer Mittelwert" in gauss.text
    assert "80 %" in gauss.text  # historischer Mittelwert, unabhaengig vom uebersteuerten Regler


def test_dashboard_seite_interne_arbeit_abschlag_veraendert_nicht_das_gecachte_dashboard(
    fake_caches, monkeypatch
):
    """Wie test_dashboard_seite_verbrauchsplan_veraendert_nicht_das_gecachte_dashboard,
    hier fuer den Abschlag-Regler: ein gesetzter Wert loest eine Neusimulation aus,
    darf aber das im DashboardCache gehaltene, geteilte Dashboard nicht veraendern."""
    dashboard_cache, _, _ = fake_caches
    original_prognose = DASHBOARD.prognose
    aufrufe: list[object] = []
    original_simuliere = Dashboard.simuliere

    def _tracking_simuliere(self, *args, **kwargs):
        aufrufe.append(self)
        return original_simuliere(self, *args, **kwargs)

    monkeypatch.setattr(Dashboard, "simuliere", _tracking_simuliere)
    client = TestClient(app_modul.app)

    antwort = client.get("/dashboard", params={"interne_arbeit_modus": "weibull"})

    assert antwort.status_code == 200
    assert len(aufrufe) == 1
    assert aufrufe[0] is not DASHBOARD
    assert dashboard_cache.ergebnis.prognose is original_prognose
    assert aufrufe[0] is not dashboard_cache.ergebnis
    assert dashboard_cache.ergebnis.bestand.projekte[0].verbrauchsplan_zielmonat is None


def test_dashboard_seite_laeufe_veraendert_nicht_das_gecachte_dashboard(fake_caches, monkeypatch):
    """Wie test_dashboard_seite_interne_arbeit_abschlag_veraendert_nicht_das_gecachte_dashboard,
    hier fuer den Laeufe-Regler: ein von STANDARD_LAEUFE abweichender Wert loest eine
    Neusimulation mit genau dieser Laeufe-Anzahl aus, darf aber das im DashboardCache
    gehaltene, geteilte Dashboard nicht veraendern."""
    dashboard_cache, _, _ = fake_caches
    original_prognose = DASHBOARD.prognose
    aufrufe: list[tuple[object, int]] = []
    original_simuliere = Dashboard.simuliere

    def _tracking_simuliere(self, *, laeufe=10_000, **kwargs):
        aufrufe.append((self, laeufe))
        return original_simuliere(self, laeufe=laeufe, **kwargs)

    monkeypatch.setattr(Dashboard, "simuliere", _tracking_simuliere)
    client = TestClient(app_modul.app)

    antwort = client.get("/dashboard", params={"laeufe": 500})

    assert antwort.status_code == 200
    assert len(aufrufe) == 1
    assert aufrufe[0] == (aufrufe[0][0], 500)
    assert aufrufe[0][0] is not DASHBOARD
    assert dashboard_cache.ergebnis.prognose is original_prognose


def test_dashboard_seite_ohne_gecachte_daten_zeigt_die_ladeseite(fake_caches):
    dashboard_cache, _, _ = fake_caches
    dashboard_cache.ergebnis = None
    client = TestClient(app_modul.app)

    antwort = client.get("/dashboard?horizont_monate=5")

    assert antwort.status_code == 200
    assert "werden geladen" in antwort.text
    assert dashboard_cache.anstossen_aufrufe == [(5, app_modul.STANDARD_AUSLASTUNG_MONATE)]


def test_schulungen_zeigt_den_anmeldungsverlauf():
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen?ab_jahr=2023")

    assert antwort.status_code == 200
    assert "plotly" in antwort.text.lower()


def test_schulungen_ohne_ab_jahr_zeigt_den_dynamischen_standard(fake_caches):
    """ "Anmeldungen ab Jahr" erscheint nur in der Ansicht "Jahresvergleich" (siehe
    test_schulungen_ab_jahr_dropdown_erscheint_nur_bei_jahresvergleich) - die Daten
    muessen deshalb ueber den dynamischen Standard hinaus mindestens zwei Jahre
    umfassen, sonst bliebe der Ansicht-Umschalter selbst schon verborgen."""
    _, anmeldungsverlauf_cache, _ = fake_caches
    erwartet = app_modul._standard_anzeige_ab_jahr()
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(erwartet, 3, "KSD", 3),
            Anmeldung(erwartet + 1, 3, "KSD", 5),
        )
    )
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen?ansicht=jahresvergleich")

    assert antwort.status_code == 200
    assert f'value="{erwartet}" selected' in antwort.text


def test_schulungen_details_abschnitt_heisst_schulungsdetails():
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen")

    assert "<summary>Schulungsdetails</summary>" in antwort.text
    assert "Einzelne Schulungen" not in antwort.text


def test_schulungen_details_tabelle_traegt_das_quartalsraster():
    """Grundlage fuer die CSS-Regel in basis.html, die vor Januar/April/Juli/Oktober
    eine Quartalsgrenze zieht (siehe dortiger Kommentar zu .quartalsraster)."""
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen")

    start = antwort.text.index('<table class="tabelle')
    tabelle_tag = antwort.text[start : antwort.text.index(">", start) + 1]
    assert "quartalsraster" in tabelle_tag


def test_schulungen_details_tabelle_traegt_die_fixierte_erste_spalte():
    """Grundlage fuer die CSS-Regel in basis.html, die die erste Spalte (Kategorie/
    Jahr/Schulungen) beim horizontalen Scrollen sichtbar haelt."""
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen")

    start = antwort.text.index('<table class="tabelle')
    tabelle_tag = antwort.text[start : antwort.text.index(">", start) + 1]
    assert "tabelle-fixierte-erste-spalte" in tabelle_tag


def test_schulungen_zeigt_monatssummen_in_der_aufklappbaren_kategoriezeile(
    fake_caches,
):
    """Die Kategorie-Zeile bleibt beim Zuklappen mit ihren Monatswerten sichtbar - sie
    stehen in derselben echten Tabellenzeile, nicht in einer separaten Tabelle."""
    _, anmeldungsverlauf_cache, _ = fake_caches
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


def test_schulungen_zeigt_gesamtzeile_ueber_alle_kategorien(fake_caches):
    _, anmeldungsverlauf_cache, _ = fake_caches
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


def test_schulungen_basisname_ohne_variante_bleibt_einfaches_blatt(fake_caches):
    """Ein Schulungstyp ohne Dauer-Suffix und mit nur einem Format bleibt ein
    einfaches Blatt, ohne eigenen Aufklapp-Knopf."""
    _, anmeldungsverlauf_cache, _ = fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(Anmeldung(2026, 9, "KSD", 4),)
    )
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen")

    ksd_index = antwort.text.index(">KSD<")
    assert "kategorie-knopf" not in antwort.text[max(0, ksd_index - 300) : ksd_index]


def test_schulungen_dauer_ebene_erscheint_nur_bei_mehreren_dauer_varianten(fake_caches):
    _, anmeldungsverlauf_cache, _ = fake_caches
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


def test_schulungen_format_ebene_erscheint_nur_bei_mehreren_formaten(fake_caches):
    _, anmeldungsverlauf_cache, _ = fake_caches
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


def test_schulungen_format_ebene_fehlt_bei_nur_einem_format(fake_caches):
    _, anmeldungsverlauf_cache, _ = fake_caches
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


def test_schulungen_vier_ebenen_format_und_dauer_zusammen(fake_caches):
    """Deckt den Fall aus der Aufgabenstellung ab: Format- und Dauer-Ebene gemeinsam
    unter einem Basisname, wenn beide tatsaechlich variieren."""
    _, anmeldungsverlauf_cache, _ = fake_caches
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


def test_schulungen_zeigt_jahr_zeilen_bei_mehreren_jahren_im_zeitraum(fake_caches):
    """Umfasst der Zeitraum mehrere Jahre, bekommt ein Knoten zusaetzliche,
    ausklappbare Jahr-Zeilen mit demselben Januar-Dezember-Monatsraster wie seine
    eigene, ueber alle Jahre kombinierte Zeile - Grundlage fuer den Jahresvergleich
    Monat fuer Monat, ohne dass die Tabelle mit der Anzahl betrachteter Jahre in die
    Breite waechst (feste 14 Spalten: Kategorie, Januar-Dezember, Summe)."""
    _, anmeldungsverlauf_cache, _ = fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2025, 3, "KSD", 3),
            Anmeldung(2026, 3, "KSD", 5),
            Anmeldung(2026, 7, "KSD", 2),
        )
    )
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen?ab_jahr=2025")

    kopf = antwort.text[antwort.text.index("<thead>") : antwort.text.index("</thead>")]
    assert kopf.count('<th scope="col">') == 14
    assert ">Jan<" in kopf
    assert ">Dez<" in kopf

    tabelle = antwort.text[antwort.text.index("<tbody>") :]
    ksd_index = tabelle.index(">KSD<")
    assert "kategorie-knopf" in tabelle[max(0, ksd_index - 300) : ksd_index]
    ksd_zeile_ende = tabelle.index("</tr>", ksd_index)
    ksd_zeile = tabelle[ksd_index:ksd_zeile_ende]
    assert "<td>8</td>" in ksd_zeile  # März kombiniert: 3 (2025) + 5 (2026)
    assert "<td>10</td>" in ksd_zeile  # Summe ueber beide Jahre

    zeile_2025_index = tabelle.index(">2025<", ksd_index)
    zeile_2025_ende = tabelle.index("</tr>", zeile_2025_index)
    assert "<td>3</td>" in tabelle[zeile_2025_index:zeile_2025_ende]

    zeile_2026_index = tabelle.index(">2026<", ksd_index)
    zeile_2026_ende = tabelle.index("</tr>", zeile_2026_index)
    zeile_2026 = tabelle[zeile_2026_index:zeile_2026_ende]
    assert "<td>5</td>" in zeile_2026
    assert "<td>2</td>" in zeile_2026
    assert "<td>7</td>" in zeile_2026


def test_schulungen_tabelle_ordnet_und_kennzeichnet_nach_juengstem_jahr(fake_caches):
    """Jahr-Zeilen sind absteigend sortiert; ein Basisname mit Anmeldungen nur in
    einem von mehreren im Zeitraum vorkommenden Jahren traegt sein Jahr im Namen und
    steht unterhalb der Basisnamen des juengsten Jahres (siehe Docstring von
    app_modul._knoten_flach und Anmeldungsverlauf.gliederung_je_kategorie)."""
    _, anmeldungsverlauf_cache, _ = fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2025, 3, "KSD", 3),
            Anmeldung(2026, 3, "KSD", 5),
            Anmeldung(2025, 6, "KMM", 2),
        )
    )
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen?ab_jahr=2025")

    tabelle = antwort.text[antwort.text.index("<tbody>") :]
    ksd_index = tabelle.index(">KSD<")
    kmm_index = tabelle.index("KMM (2025)")
    assert ksd_index < kmm_index  # juengeres Jahr (2026, KSD) zuerst

    ksd_zeile_ende = tabelle.index("</tr>", ksd_index)
    jahr_2026_index = tabelle.index(">2026<", ksd_zeile_ende)
    jahr_2025_index = tabelle.index(">2025<", ksd_zeile_ende)
    assert jahr_2026_index < jahr_2025_index


def test_schulungen_jahr_filter_erscheint_nicht_bei_nur_einem_jahr(fake_caches):
    """ "Ansicht" bleibt anders als "Jahre" auch bei nur einem Jahr sichtbar - ein
    Umschalter, der mal da ist und mal nicht, waere verwirrender als eine wenig
    aussagekraeftige Jahresvergleich-Ansicht mit nur einer Linie."""
    _, anmeldungsverlauf_cache, _ = fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(Anmeldung(2026, 3, "KSD", 4),)
    )
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen?ab_jahr=2026")

    assert 'name="jahr_filter"' not in antwort.text
    assert 'name="ansicht"' in antwort.text


def test_schulungen_jahr_filter_erscheint_bei_mehreren_jahren(fake_caches):
    _, anmeldungsverlauf_cache, _ = fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2025, 3, "KSD", 3),
            Anmeldung(2026, 3, "KSD", 5),
        )
    )
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen?ab_jahr=2025&ansicht=jahresvergleich")

    assert 'name="ansicht"' in antwort.text
    ausschnitt_start = antwort.text.index('name="jahr_filter"')
    ausschnitt_ende = antwort.text.index("</div>", ausschnitt_start)
    ausschnitt = antwort.text[ausschnitt_start:ausschnitt_ende]
    positionen = [ausschnitt.index(f'value="{wert}"') for wert in ("Alle Jahre", "2026", "2025")]
    assert positionen == sorted(positionen)


def test_schulungen_jahr_filter_checkboxen_tragen_die_javascript_synchronisation(fake_caches):
    """ "Alle Jahre" und die einzelnen Jahre schliessen sich nicht aus, sondern
    bedingen sich gegenseitig - siehe jahrFilterAlleUmschalten()/
    jahrFilterEinzelnUmschalten() in schulungen.html."""
    _, anmeldungsverlauf_cache, _ = fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2025, 3, "KSD", 3),
            Anmeldung(2026, 3, "KSD", 5),
        )
    )
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen?ab_jahr=2025&ansicht=jahresvergleich")

    ausschnitt_start = antwort.text.index('name="jahr_filter"')
    ausschnitt_ende = antwort.text.index("</div>", ausschnitt_start)
    ausschnitt = antwort.text[ausschnitt_start:ausschnitt_ende]
    assert 'class="jahr-filter-alle"' in ausschnitt
    assert 'onclick="jahrFilterAlleUmschalten(this)"' in ausschnitt
    assert ausschnitt.count('class="jahr-filter-einzeln"') == 2
    assert ausschnitt.count('onclick="jahrFilterEinzelnUmschalten(this)"') == 2


def test_schulungen_jahr_filter_hakt_einzelne_jahre_bei_alle_jahre_vor(fake_caches):
    """Ohne explizite Auswahl ist "Alle Jahre" voreingestellt - dann muessen auch die
    einzelnen Jahre bereits angehakt sein, sonst wirkt "Alle Jahre" beim ersten
    Aufklappen inkonsistent zu jahrFilterAlleUmschalten() (das beim Anklicken
    genau dasselbe herstellen wuerde)."""
    _, anmeldungsverlauf_cache, _ = fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2025, 3, "KSD", 3),
            Anmeldung(2026, 3, "KSD", 5),
        )
    )
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen?ab_jahr=2025&ansicht=jahresvergleich")

    ausschnitt_start = antwort.text.index('name="jahr_filter"')
    ausschnitt_ende = antwort.text.index("</div>", ausschnitt_start)
    ausschnitt = antwort.text[ausschnitt_start:ausschnitt_ende]
    for label in ausschnitt.split("<label>")[1:]:
        assert "checked" in label.split("</label>")[0]


def test_schulungen_jahr_filter_hakt_nicht_alle_einzelnen_jahre_bei_expliziter_auswahl(
    fake_caches,
):
    """Waehlt man explizit nur ein Jahr, bleibt "Alle Jahre" (und das jeweils andere
    Jahr) unangehakt - die Vorauswahl oben gilt nur fuer den unberuehrten
    Standardzustand."""
    _, anmeldungsverlauf_cache, _ = fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2025, 3, "KSD", 3),
            Anmeldung(2026, 3, "KSD", 5),
        )
    )
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen?ab_jahr=2025&ansicht=jahresvergleich&jahr_filter=2026")

    ausschnitt_start = antwort.text.index('name="jahr_filter"')
    ausschnitt_ende = antwort.text.index("</div>", ausschnitt_start)
    ausschnitt = antwort.text[ausschnitt_start:ausschnitt_ende]
    alle_label, jahr_2026_label, jahr_2025_label = (
        teil.split("</label>")[0] for teil in ausschnitt.split("<label>")[1:]
    )
    assert "checked" not in alle_label
    assert "checked" in jahr_2026_label
    assert "checked" not in jahr_2025_label


def test_schulungen_ansicht_wechsel_sendet_das_formular_sofort_ab(fake_caches):
    """Wie "Anmeldungen ab Jahr" wendet ein Wechsel der Ansicht sich sofort an, ohne
    dass "Anwenden" erst gedrueckt werden muss."""
    _, anmeldungsverlauf_cache, _ = fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2025, 3, "KSD", 3),
            Anmeldung(2026, 3, "KSD", 5),
        )
    )
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen?ab_jahr=2025")

    ausschnitt_start = antwort.text.index('name="ansicht"')
    ausschnitt_ende = antwort.text.index(">", ausschnitt_start)
    assert 'onchange="this.form.requestSubmit()"' in antwort.text[ausschnitt_start:ausschnitt_ende]


def test_schulungen_trendlinien_checkbox_sendet_das_formular_sofort_ab():
    """Ein Umsetzen des Trendlinien-Kontrollkaestchens wendet sich sofort an, ohne
    dass "Anwenden" erst gedrueckt werden muss - wie der Ansicht-Umschalter."""
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen")

    verstecktes_feld = antwort.text.index('name="trendlinien_werte"')
    ausschnitt_start = antwort.text.index('name="trendlinien_werte"', verstecktes_feld + 1)
    ausschnitt_ende = antwort.text.index(">", ausschnitt_start)
    assert "this.form.requestSubmit()" in antwort.text[ausschnitt_start:ausschnitt_ende]


def test_schulungen_trendlinien_verstecktes_feld_deaktiviert_wenn_angehakt():
    """Regression: das versteckte "aus"-Begleitfeld muss deaktiviert sein, sobald
    Trendlinien angehakt sind - sonst sendet ein erneutes Absenden (z. B. durch einen
    anderen Regler) sowohl "aus" als auch "an" gleichzeitig, weil ein deaktiviertes
    Formularfeld anders als ein aktives beim Absenden ausgelassen wird."""
    client = TestClient(app_modul.app)

    angehakt = client.get("/schulungen")
    abgehakt = client.get("/schulungen?trendlinien_werte=aus")

    def aus_feld_markup(text: str) -> str:
        # Erstes Vorkommen: das versteckte Feld steht im Markup vor der Checkbox.
        start = text.index('name="trendlinien_werte"')
        return text[start : text.index(">", start)]

    assert "disabled" in aus_feld_markup(angehakt.text)
    assert "disabled" not in aus_feld_markup(abgehakt.text)


def test_schulungen_formular_traegt_die_bereinigungsfunktion_beim_absenden():
    """Vor dem Absenden werden Mehrfachauswahl-Filter im Standardzustand deaktiviert
    (schulungenFormBereinigen(), siehe dortigen Kommentar) - sonst wuerde jede Anfrage
    unveraendert saemtliche Standardfilter als (kommagetrennte) Query-Parameter
    mitschleppen."""
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen")

    formular_start = antwort.text.index('id="schulungen-form"')
    formular_ende = antwort.text.index(">", formular_start)
    assert 'onsubmit="schulungenFormBereinigen()"' in antwort.text[formular_start:formular_ende]
    assert "function schulungenFormBereinigen()" in antwort.text


def test_schulungen_data_standard_markiert_die_alle_option_bei_format_und_dauer(fake_caches):
    """Format/Dauer: nur die jeweilige "Alle"-Option ist als Standard markiert (siehe
    data-standard-Attribut, ausgewertet von schulungenFormBereinigen())."""
    _, anmeldungsverlauf_cache, _ = fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "CSPO 2-tägig", 5, format="Online"),
            Anmeldung(2026, 9, "CSPO 2-tägig", 3, format="Präsenz"),
        )
    )
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen")

    ausschnitt_start = antwort.text.index('name="format_filter"')
    ausschnitt_ende = antwort.text.index("</div>", ausschnitt_start)
    ausschnitt = antwort.text[ausschnitt_start:ausschnitt_ende]
    # Genau eine Option ("Alle") ist als Standard markiert, die beiden echten Formate
    # nicht.
    assert ausschnitt.count('data-standard="true"') == 1
    alle_label, format_a_label, format_b_label = (
        teil.split("</label>")[0] for teil in ausschnitt.split("<label>")[1:4]
    )
    assert 'data-standard="true"' in alle_label
    assert 'data-standard="false"' in format_a_label
    assert 'data-standard="false"' in format_b_label


def test_schulungen_data_standard_markiert_alle_jahre_checkboxen_als_standard(fake_caches):
    """Bei "Jahre" ist der Standardzustand "alles angehakt" (siehe jahr_dropdown()) -
    entsprechend traegt dort jedes Kontrollkaestchen data-standard="true"."""
    _, anmeldungsverlauf_cache, _ = fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2025, 3, "KSD", 3),
            Anmeldung(2026, 3, "KSD", 5),
        )
    )
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen?ab_jahr=2025&ansicht=jahresvergleich")

    ausschnitt_start = antwort.text.index('name="jahr_filter"')
    ausschnitt_ende = antwort.text.index("</div>", ausschnitt_start)
    ausschnitt = antwort.text[ausschnitt_start:ausschnitt_ende]
    assert ausschnitt.count('data-standard="true"') == 3
    assert 'data-standard="false"' not in ausschnitt


def test_schulungen_data_standard_markiert_nur_alle_schulungen_als_standard(fake_caches):
    _, anmeldungsverlauf_cache, _ = fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "CSM 2-tägig", 5),
            Anmeldung(2026, 9, "KSD", 4),
        )
    )
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen")

    ausschnitt_start = antwort.text.index('name="schulung_filter"')
    ausschnitt_ende = antwort.text.index("</div>", ausschnitt_start)
    ausschnitt = antwort.text[ausschnitt_start:ausschnitt_ende]
    assert ausschnitt.count('data-standard="true"') == 1
    assert ausschnitt.count('data-standard="false"') == 2


def test_schulungen_ansicht_steht_vor_dem_einklappbaren_filterbereich(fake_caches):
    """ "Ansicht" steht dauerhaft sichtbar vor dem einklappbaren Filterbereich, nicht
    mehr darin - anders als die uebrigen, seltener gebrauchten Filter (Jahre/
    Schulungen/Format/Dauer) muss man dafuer nicht erst aufklappen. "Trendlinien"
    bleibt als einziger verbleibender Anzeige-Umschalter dort in eigener, per
    .regler-trenner abgesetzter erster Zeile."""
    _, anmeldungsverlauf_cache, _ = fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2025, 3, "KSD", 3),
            Anmeldung(2026, 3, "KSD", 5),
        )
    )
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen?ab_jahr=2025&ansicht=jahresvergleich")

    regler_start = antwort.text.index('<details class="regler-abschnitt"')
    vor_regler = antwort.text[:regler_start]
    erste_zeile_start = antwort.text.index('<div class="filter-spalten">')
    zweite_zeile_start = antwort.text.index('<div class="filter-spalten regler-trenner">')
    erste_zeile = antwort.text[erste_zeile_start:zweite_zeile_start]
    zweite_zeile = antwort.text[zweite_zeile_start:]

    assert 'name="ansicht"' in vor_regler
    assert 'name="ansicht"' not in erste_zeile
    assert 'name="trendlinien_werte"' in erste_zeile
    assert 'name="jahr_filter"' not in erste_zeile
    assert 'name="schulung_filter"' not in erste_zeile

    assert 'name="jahr_filter"' in zweite_zeile
    assert 'name="schulung_filter"' in zweite_zeile


def test_schulungen_zeitraum_dropdown_erscheint_statt_ab_jahr_bei_zeitverlauf():
    """Ohne Jahresvergleich (Standardansicht) zeigt der Kopfbereich das Zeitraum-
    Dropdown fuer die Ruecklick-Laenge des rollierenden Fensters, nicht "Anmeldungen
    ab Jahr" - das waere ohnehin wirkungslos (siehe Route-Docstring)."""
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen")

    assert '<select name="zeitraum"' in antwort.text
    assert '<select name="ab_jahr"' not in antwort.text


def test_schulungen_ab_jahr_dropdown_erscheint_nur_bei_jahresvergleich(fake_caches):
    """Erst mit ausgewaehltem Jahresvergleich (und mehr als einem Jahr im Zeitraum,
    siehe zeige_ansicht_umschalter) ersetzt "Anmeldungen ab Jahr" das Zeitraum-
    Dropdown - ein Kalenderjahresvergleich braucht einen Startjahrgang, kein
    rollierendes Monatsfenster."""
    _, anmeldungsverlauf_cache, _ = fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2025, 3, "KSD", 3),
            Anmeldung(2026, 3, "KSD", 5),
        )
    )
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen?ab_jahr=2025&ansicht=jahresvergleich")

    assert '<select name="ab_jahr"' in antwort.text
    assert '<select name="zeitraum"' not in antwort.text


def test_schulungen_zeitraum_verkuerzt_das_rollierende_fenster(fake_caches):
    """Die Ruecklick-Laenge des Diagramm-Standardfensters ist ueber "zeitraum"
    waehlbar (siehe STANDARD_MONATE_VORSCHAU/STANDARD_SCHULUNGEN_ZEITRAUM) - ein 13
    Monate vor dem laufenden Monat abgeschlossener Monat faellt beim Standard (12
    Monate) heraus, bleibt bei 24 Monaten aber sichtbar."""
    _, anmeldungsverlauf_cache, _ = fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2025, 7, "KSD", 3),
            Anmeldung(2026, 9, "KSD", 5),
        )
    )
    client = TestClient(app_modul.app)

    antwort_standard = client.get("/schulungen")
    antwort_24 = client.get("/schulungen?zeitraum=24")

    assert "Jul 2025" not in antwort_standard.text
    assert "Jul 2025" in antwort_24.text


def test_schulungen_zeitraum_ignoriert_ab_jahr(fake_caches):
    """Regression: "ab_jahr" ist in der "zeitverlauf"-Ansicht gar nicht sichtbar/
    waehlbar (siehe Template) und darf das rollierende Fenster deshalb nicht
    einschraenken - ein dynamischer Standard wie 2026 ab Juni
    (_standard_anzeige_ab_jahr()) hat sonst frueherer Monate unsichtbar aus dem
    Rueckblick herausgeschnitten, obwohl "zeitraum" sie eigentlich zeigen sollte."""
    _, anmeldungsverlauf_cache, _ = fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2025, 9, "KSD", 3),
            Anmeldung(2026, 9, "KSD", 5),
        )
    )
    client = TestClient(app_modul.app)

    # ab_jahr=2026 wuerde verlauf_ab_jahr auf 2026 begrenzen - das rollierende Fenster
    # (12 Monate: September Vorjahr bis September laufend) muss trotzdem Sep 2025 zeigen.
    antwort = client.get("/schulungen?ab_jahr=2026")

    assert "Sep 2025" in antwort.text


def test_schulungen_zeitraum_alle_zeigt_den_gesamten_geladenen_zeitraum(fake_caches):
    """ "alle" haengt das rollierende Fenster aus und zeigt den gesamten geladenen
    Zeitraum, unabhaengig von "ab_jahr" (siehe test_schulungen_zeitraum_ignoriert_ab_jahr)."""
    _, anmeldungsverlauf_cache, _ = fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2023, 1, "KSD", 3),
            Anmeldung(2026, 9, "KSD", 5),
        )
    )
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen?ab_jahr=2026&zeitraum=alle")

    assert "Jan 2023" in antwort.text


def test_schulungen_ab_jahr_bleibt_bei_zeitverlauf_als_verstecktes_feld_erhalten(fake_caches):
    """Regression: ohne dieses versteckte Feld ging die zuletzt gewaehlte
    "Anmeldungen ab Jahr"-Auswahl beim Wechsel zu "Zeitverlauf" verloren - ein
    GET-Formular sendet beim Absenden nur die gerade sichtbaren Felder, und
    "Anmeldungen ab Jahr" ist in dieser Ansicht durch "Zeitraum" ersetzt. Ein
    anschliessender Wechsel zurueck zu "Jahresvergleich" fiel dadurch auf den
    dynamischen Standard zurueck, was je nach Datenlage sogar den Ansicht-
    Umschalter selbst verschwinden lassen konnte ("kommt nicht mehr zurueck")."""
    _, anmeldungsverlauf_cache, _ = fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2023, 3, "KSD", 3),
            Anmeldung(2026, 3, "KSD", 5),
        )
    )
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen?ansicht=zeitverlauf&ab_jahr=2023")

    assert 'name="zeitraum"' in antwort.text
    assert 'type="hidden" name="ab_jahr" value="2023"' in antwort.text


def test_schulungen_zeitraum_bleibt_bei_jahresvergleich_als_verstecktes_feld_erhalten(fake_caches):
    """Gegenstueck zu test_schulungen_ab_jahr_bleibt_bei_zeitverlauf_als_verstecktes_feld_erhalten
    fuer die umgekehrte Richtung: die zuletzt gewaehlte "Zeitraum"-Auswahl bleibt beim
    Wechsel zu "Jahresvergleich" ueber ein verstecktes Feld erhalten."""
    _, anmeldungsverlauf_cache, _ = fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2025, 3, "KSD", 3),
            Anmeldung(2026, 3, "KSD", 5),
        )
    )
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen?ansicht=jahresvergleich&ab_jahr=2025&zeitraum=24")

    assert 'name="ab_jahr"' in antwort.text
    assert 'type="hidden" name="zeitraum" value="24"' in antwort.text


def test_schulungen_jahr_filter_wirkt_nur_auf_das_diagramm_nicht_auf_die_tabelle(fake_caches):
    """Anders als ``ab_jahr`` bleibt die Schulungsdetails-Tabelle von ``jahr_filter``
    unberuehrt - nur das Diagramm blendet die abgewaehlten Jahre aus (siehe Docstring
    der Route)."""
    _, anmeldungsverlauf_cache, _ = fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2025, 3, "KSD", 3),
            Anmeldung(2026, 3, "KSD", 5),
        )
    )
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen?ab_jahr=2025&jahr_filter=2026")

    assert "Mär 2025" not in antwort.text
    assert "Mär 2026" in antwort.text
    # "Ansicht" bleibt trotzdem sichtbar, obwohl "jahr_filter" das Diagramm auf nur
    # noch ein Jahr einschraenkt - die Tabelle zeigt weiterhin beide Jahre.
    assert 'name="ansicht"' in antwort.text

    tabelle = antwort.text[antwort.text.index("<tbody>") :]
    assert ">2025<" in tabelle
    assert ">2026<" in tabelle


def test_schulungen_jahresvergleich_zeigt_eine_farbige_linie_je_jahr(fake_caches):
    _, anmeldungsverlauf_cache, _ = fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2025, 3, "KSD", 3),
            Anmeldung(2026, 3, "KSD", 5),
        )
    )
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen?ab_jahr=2025&ansicht=jahresvergleich")

    assert '"name":"2025"' in antwort.text
    assert '"name":"2026"' in antwort.text
    assert "Jahresvergleich" in antwort.text


def test_schulungen_jahresvergleich_zeigt_trendlinien_je_jahr(fake_caches):
    """Die Trendlinien-Checkbox wirkte bisher nur im Zeitverlauf-Diagramm, nicht im
    Jahresvergleich - beide Ansichten unterstuetzen sie jetzt gleichermassen."""
    _, anmeldungsverlauf_cache, _ = fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2025, 3, "KSD", 3),
            Anmeldung(2026, 3, "KSD", 5),
        )
    )
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen?ab_jahr=2025&ansicht=jahresvergleich")
    assert '"name":"2025 (Trend)"' in antwort.text
    assert '"name":"2026 (Trend)"' in antwort.text

    ohne_trend = client.get(
        "/schulungen?ab_jahr=2025&ansicht=jahresvergleich&trendlinien_werte=aus"
    )
    assert "(Trend)" not in ohne_trend.text


def test_schulungen_dropdown_zuruecksetzen_ist_ein_rein_clientseitiger_knopf(fake_caches):
    """Der "Auswahl zurücksetzen"-Knopf im Schulungen-Dropdown ist bewusst kein Link
    (kein Seiten-Neuladen, keine sofortige Anwendung) - er hakt per JavaScript
    (schulungFilterZuruecksetzen(), siehe schulungen.html) nur die Kontrollkaestchen
    dort wieder ab, angewandt wird das erst durch den "Anwenden"-Knopf. Das
    "Alle Schulungen"-Kontrollkaestchen traegt dafuer eine feste ID, an der das
    Skript es wiedererkennt."""
    _, anmeldungsverlauf_cache, _ = fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(Anmeldung(2026, 9, "CSM 2-tägig", 5),)
    )
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen?schulung_filter=CSM&format_filter=Online")

    knopf_index = antwort.text.index("Auswahl zurücksetzen")
    tag_start = antwort.text.rindex("<button", 0, knopf_index)
    tag = antwort.text[tag_start:knopf_index]
    assert 'onclick="schulungFilterZuruecksetzen(this)"' in tag
    assert "href=" not in tag
    assert 'id="schulung-filter-alle"' in antwort.text


def test_zukuenftige_monate_markiert_ab_einschliesslich_dem_laufenden_monat():
    """Der laufende Monat gilt selbst noch als nicht abgeschlossen - eine darin
    terminierte Schulung kann noch neue Anmeldungen bekommen."""
    zukuenftig = app_modul._zukuenftige_monate(2026, laufender_monat=(2026, 9))
    assert zukuenftig[7] is False  # August
    assert zukuenftig[8] is True  # September (laufender Monat)
    assert zukuenftig[9] is True  # Oktober


def test_knoten_flach_markiert_kombinierte_zeile_nur_bei_genau_einem_jahr():
    """Bei mehreren Jahren im Zeitraum vermengt die kombinierte Zeile Monate
    verschiedener Jahre unter derselben Spalte - dort bleibt sie unmarkiert, nur die
    eindeutigen Jahr-Zeilen bekommen echte Markierungen (siehe Docstring von
    :func:`app_modul._knoten_flach`)."""
    einzeljahr = Anmeldungsknoten("KSD", {(2026, 9): 4})
    [zeile] = app_modul._knoten_flach(
        einzeljahr, laufender_monat=(2026, 9), mehrere_jahre_insgesamt=False
    )
    assert cast("list[bool]", zeile["zukuenftige_monate"])[8] is True

    mehrjaehrig = Anmeldungsknoten("KSD", {(2025, 9): 3, (2026, 9): 4})
    zeilen = app_modul._knoten_flach(
        mehrjaehrig, laufender_monat=(2026, 9), mehrere_jahre_insgesamt=True
    )
    kombiniert = zeilen[0]
    assert kombiniert["zukuenftige_monate"] == [False] * 12

    jahr_2026 = next(z for z in zeilen if z["name"] == "2026")
    assert cast("list[bool]", jahr_2026["zukuenftige_monate"])[8] is True
    jahr_2025 = next(z for z in zeilen if z["name"] == "2025")
    assert cast("list[bool]", jahr_2025["zukuenftige_monate"])[8] is False


def test_knoten_flach_sortiert_jahr_zeilen_absteigend():
    knoten = Anmeldungsknoten("KSD", {(2024, 9): 1, (2026, 9): 4, (2025, 9): 3})
    zeilen = app_modul._knoten_flach(
        knoten, laufender_monat=(2026, 9), mehrere_jahre_insgesamt=True
    )
    jahr_zeilen = [z for z in zeilen if z.get("ist_jahr")]
    assert [z["name"] for z in jahr_zeilen] == ["2026", "2025", "2024"]


def test_knoten_flach_haengt_jahr_an_namen_wenn_nur_ein_jahr_von_mehreren_betroffen():
    """Traegt der gesamte Tabellenzeitraum mehrere Jahre, aber ein einzelner Knoten nur
    eines davon, waere sonst nirgends an dieser Zeile ablesbar, um welches Jahr es
    sich handelt - der Name traegt es deshalb selbst (siehe Docstring von
    app_modul._knoten_flach)."""
    nur_2025 = Anmeldungsknoten("CSM", {(2025, 3): 5})
    [zeile] = app_modul._knoten_flach(
        nur_2025, laufender_monat=(2026, 9), mehrere_jahre_insgesamt=True
    )
    assert zeile["name"] == "CSM (2025)"

    # Ohne mehrere Jahre im gesamten Zeitraum bleibt der Name unveraendert - hier ist
    # das Jahr ohnehin unmissverstaendlich.
    [zeile_ohne_mehrdeutigkeit] = app_modul._knoten_flach(
        nur_2025, laufender_monat=(2026, 9), mehrere_jahre_insgesamt=False
    )
    assert zeile_ohne_mehrdeutigkeit["name"] == "CSM"


def test_knoten_flach_ignoriert_jahr_ohne_jegliche_anmeldung() -> None:
    """Ein Jahr, in dem dieser Knoten nur einen Termin mit 0 Anmeldungen hatte (z. B.
    ein abgesagter Kurs), zaehlt nicht als eigenes Jahr - sonst bekaeme der Knoten eine
    komplett leere Jahr-Zeile und faelschlich einen Ausklapp-Pfeil, obwohl effektiv nur
    ein einziges Jahr Daten traegt (beobachtet an "A-CSM" > "Präsenz" mit einem
    einzelnen 0-Anmeldungen-Termin in 2025 neben echten Anmeldungen in 2023/2024/2026)."""
    knoten = Anmeldungsknoten("A-CSM", {(2024, 5): 6, (2025, 2): 0})
    [zeile] = app_modul._knoten_flach(
        knoten, laufender_monat=(2026, 9), mehrere_jahre_insgesamt=True
    )
    assert zeile["hat_kinder"] is False
    assert zeile["name"] == "A-CSM (2024)"


def test_schulungen_hebt_noch_offene_schulungstermine_in_der_tabelle_ab(fake_caches):
    """Ein bereits terminierter, aber noch in der Zukunft liegender Schulungstermin
    bekommt in der Schulungsdetails-Tabelle dieselbe abgehobene Markierung wie im
    Diagramm darueber - hier absichtlich mit weit auseinanderliegenden Jahren, damit
    der Test unabhaengig vom tatsaechlichen Tagesdatum eindeutig bleibt."""
    _, anmeldungsverlauf_cache, _ = fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(Anmeldung(2022, 3, "KSD", 4),)
    )
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen?ab_jahr=2022")

    tabelle = antwort.text[antwort.text.index("<tbody>") :]
    ksd_index = tabelle.index(">KSD<")
    zeile_ende = tabelle.index("</tr>", ksd_index)
    zeile = tabelle[ksd_index:zeile_ende]
    assert 'class="zelle-zukunft"' not in zeile


def test_schulungen_markiert_noch_offene_zukuenftige_schulungstermine(fake_caches):
    """Gegenstueck zu :func:`test_schulungen_hebt_noch_offene_schulungstermine_in_der_tabelle_ab`
    mit einem weit in der Zukunft liegenden, bereits terminierten Schulungstermin."""
    _, anmeldungsverlauf_cache, _ = fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(Anmeldung(2099, 3, "KSD", 4),)
    )
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen?ab_jahr=2099")

    tabelle = antwort.text[antwort.text.index("<tbody>") :]
    ksd_index = tabelle.index(">KSD<")
    zeile_ende = tabelle.index("</tr>", ksd_index)
    zeile = tabelle[ksd_index:zeile_ende]
    assert 'class="zelle-zukunft"' in zeile


def test_schulungen_filterabschnitt_bleibt_ohne_filter_zugeklappt():
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen")

    assert '<details class="regler-abschnitt" open>' not in antwort.text


def test_schulungen_filterabschnitt_klappt_bei_schulung_auswahl_auf():
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen?schulung_filter=CSM")

    assert '<details class="regler-abschnitt" open>' in antwort.text


def test_schulungen_alle_schulungen_und_basisname_ergeben_je_eine_farbige_reihe(
    fake_caches,
):
    """Jede Auswahl im Schulungen-Dropdown (auch "Alle Schulungen" zusaetzlich zu
    einem Basisnamen) erzeugt ihre eigene Reihe im Diagramm, keine gegenseitig
    exklusive Auswahl."""
    _, anmeldungsverlauf_cache, _ = fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "CSM 2-tägig", 5),
            Anmeldung(2026, 9, "KSD", 4),
        )
    )
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen?schulung_filter=Alle+Schulungen,CSM")

    assert '"name":"Alle Schulungen"' in antwort.text
    assert '"name":"CSM"' in antwort.text


def test_schulungen_schulung_dropdown_gruppiert_nach_kategorie(fake_caches):
    """Der Kategorie-Filter ist entfallen - stattdessen ist der Schulungen-Filter
    selbst nach Kategorien unterteilt (siehe app._schulung_gruppen)."""
    _, anmeldungsverlauf_cache, _ = fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "CSM 2-tägig", 5),
            Anmeldung(2026, 9, "KSD", 4),
        )
    )
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen")

    ausschnitt_start = antwort.text.index('name="schulung_filter"')
    ausschnitt_ende = antwort.text.index("</div>", ausschnitt_start)
    ausschnitt = antwort.text[ausschnitt_start:ausschnitt_ende]
    scrum_index = ausschnitt.index(">Scrum<")
    kanban_index = ausschnitt.index(">Kanban<")
    csm_index = ausschnitt.index('value="CSM"')
    ksd_index = ausschnitt.index('value="KSD"')
    assert scrum_index < csm_index < kanban_index < ksd_index


def test_schulungen_kein_kategorie_filter_mehr():
    """Der Kategorie-Filter ist vollstaendig entfallen (siehe Docstring von
    app._schulung_gruppen) - weder als eigenes Dropdown noch als Query-Parameter."""
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen")

    assert 'name="kategorie_filter"' not in antwort.text


def test_schulungen_schulungen_dropdown_fasst_dauer_varianten_zu_basisname_zusammen(
    fake_caches,
):
    """ "CSPO 2-tägig"/"CSPO 3-tägig" erscheinen im Dropdown zusammengefasst als
    "CSPO" - wie im Tabellen-Drilldown darunter, keine eigenen Dauer-Optionen."""
    _, anmeldungsverlauf_cache, _ = fake_caches
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
        schulung_filter=("CSPO",),
        format_filter=(),
        dauer_filter=(),
    )

    assert reihen["CSPO"] == {(2026, 9): 7}


def test_anmeldungsreihen_kreuzt_schulung_und_dauer_statt_nur_additiv_zu_sein():
    """Schulung "CSPO" zusammen mit Dauer "2-tägig" und "3-tägig" ergibt zwei
    kombinierte Reihen ("CSPO 2-tägig", "CSPO 3-tägig") statt einer gemeinsamen
    "CSPO"- und einer gemeinsamen Dauer-Reihe."""
    verlauf = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "CSPO 2-tägig", 5),
            Anmeldung(2026, 9, "CSPO 3-tägig", 2),
            Anmeldung(2026, 9, "KSD", 9),
        )
    )

    reihen = app_modul._anmeldungsreihen(
        verlauf,
        schulung_filter=("CSPO",),
        format_filter=(),
        dauer_filter=("2-tägig", "3-tägig"),
    )

    assert set(reihen) == {"CSPO 2-tägig", "CSPO 3-tägig"}
    assert reihen["CSPO 2-tägig"] == {(2026, 9): 5}
    assert reihen["CSPO 3-tägig"] == {(2026, 9): 2}


def test_anmeldungsreihen_zusaetzlich_alle_in_derselben_achse_ergibt_dritte_reihe():
    """Zusaetzlich "Alle" im Dauer-Filter neben "2-tägig"/"3-tägig" erzeugt eine dritte
    Reihe fuer "CSPO" ueber alle Dauern hinweg, neben den beiden Dauer-Varianten."""
    verlauf = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "CSPO 2-tägig", 5),
            Anmeldung(2026, 9, "CSPO 3-tägig", 2),
        )
    )

    reihen = app_modul._anmeldungsreihen(
        verlauf,
        schulung_filter=("CSPO",),
        format_filter=(),
        dauer_filter=(app_modul.ALLE, "2-tägig", "3-tägig"),
    )

    assert set(reihen) == {"CSPO", "CSPO 2-tägig", "CSPO 3-tägig"}
    assert reihen["CSPO"] == {(2026, 9): 7}


def test_anmeldungsreihen_format_kreuzt_wie_dauer():
    """Dieselbe Kreuzprodukt-Logik gilt fuer den Format-Filter (Online/Präsenz)."""
    verlauf = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "CSPO 2-tägig", 5, format="Online"),
            Anmeldung(2026, 9, "CSPO 2-tägig", 3, format="Präsenz"),
        )
    )

    reihen = app_modul._anmeldungsreihen(
        verlauf,
        schulung_filter=("CSPO",),
        format_filter=("Online", "Präsenz"),
        dauer_filter=(),
    )

    assert set(reihen) == {"CSPO Online", "CSPO Präsenz"}
    assert reihen["CSPO Online"] == {(2026, 9): 5}
    assert reihen["CSPO Präsenz"] == {(2026, 9): 3}


def test_anmeldungsreihen_alle_drei_filter_leer_ergibt_kein_diagramm():
    """Sind alle drei Filter-Dropdowns vollstaendig abgewaehlt, gibt es keine einzige
    Reihe - anders als frueher faellt das nicht mehr automatisch auf die Gesamtzahl
    zurueck (siehe test_schulungen_alle_filter_abwaehlen_leert_das_diagramm)."""
    verlauf = Anmeldungsverlauf(anmeldungen=(Anmeldung(2026, 9, "CSPO 2-tägig", 5),))

    reihen = app_modul._anmeldungsreihen(
        verlauf,
        schulung_filter=(),
        format_filter=(),
        dauer_filter=(),
    )

    assert reihen == {}


def test_schulungen_alle_filter_abwaehlen_leert_das_diagramm(fake_caches):
    """Wird in allen drei Dropdowns eine leere Auswahl uebermittelt (kommagetrennter
    Parameter als leere Zeichenkette, siehe _liste_aus_kommagetrennt), also keine
    einzige Checkbox angehakt, faellt das nicht mehr auf den Query-Default ("Alle
    Schulungen" & Co.) zurueck - die Anmeldedaten-Meldung statt einer Linie
    erscheint."""
    _, anmeldungsverlauf_cache, _ = fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(Anmeldung(2026, 9, "CSM 2-tägig", 5),)
    )
    client = TestClient(app_modul.app)

    antwort = client.get(
        "/schulungen?schulung_filter=&format_filter=&dauer_filter=",
    )

    assert '"name":"Alle Schulungen"' not in antwort.text
    assert "Keine Anmeldedaten" in antwort.text


def test_schulungen_filter_dropdowns_sind_ohne_filter_alle_drei_auf_alle_gesetzt():
    """Ohne explizite Auswahl sind alle drei 'alle'-Eintraege vorausgewaehlt, aber das
    Diagramm zeigt trotzdem nur die eine Gesamtlinie und der Filterabschnitt bleibt
    zugeklappt (siehe test_schulungen_filterabschnitt_bleibt_ohne_filter_zugeklappt)."""
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen")

    for feldname, alle_wert in (
        ("schulung_filter", "Alle Schulungen"),
        ("format_filter", "Alle"),
        ("dauer_filter", "Alle"),
    ):
        ausschnitt_start = antwort.text.index(f'name="{feldname}"')
        ausschnitt_ende = antwort.text.index("</div>", ausschnitt_start)
        ausschnitt = antwort.text[ausschnitt_start:ausschnitt_ende]
        assert f'value="{alle_wert}"' in ausschnitt
        assert "checked" in ausschnitt


def test_schulungen_schulung_optionen_je_kategorie_alphabetisch_mit_alle_schulungen_zuerst(
    fake_caches,
):
    """ "Alle Schulungen" steht immer zuerst, unabhaengig von jeder Kategorie; innerhalb
    jeder Kategorie-Gruppe sind die Basisnamen alphabetisch sortiert (siehe
    app._schulung_gruppen). Die Reihenfolge der Gruppen selbst folgt der Konfiguration
    (hier: Scrum vor Kanban, siehe KATEGORIEN), nicht dem Alphabet."""
    _, anmeldungsverlauf_cache, _ = fake_caches
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
    positionen = {
        "Alle Schulungen": ausschnitt.index('value="Alle Schulungen"'),
        "Scrum": ausschnitt.index(">Scrum<"),
        "A-CSD": ausschnitt.index('value="A-CSD"'),
        "Kanban": ausschnitt.index(">Kanban<"),
        "KSD": ausschnitt.index('value="KSD"'),
    }
    reihenfolge = sorted(positionen, key=lambda name: positionen[name])
    assert reihenfolge == ["Alle Schulungen", "Scrum", "A-CSD", "Kanban", "KSD"]


def test_schulungen_trendlinien_standardmaessig_an(fake_caches):
    """Ohne Interaktion mit dem Filter-Formular und bei wenigen (hier: einer) Linien
    ist die Trendlinie standardmaessig an - das Kontrollkaestchen startet angehakt."""
    _, anmeldungsverlauf_cache, _ = fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "KSD", 4),
            Anmeldung(2026, 10, "KSD", 2),
        )
    )
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen")

    assert '"name":"Alle Schulungen (Trend)"' in antwort.text


def test_schulungen_trendlinien_standardmaessig_aus_bei_vielen_linien(fake_caches):
    """Ohne explizite Auswahl sind Trendlinien standardmaessig aus, sobald mehr als
    STANDARD_TRENDLINIEN_MAX_LINIEN Linien gezeichnet werden - viele Trendlinien
    uebereinander verschlechtern die Lesbarkeit eher, als dass sie helfen. Sechs
    Format-Auswahlen (die "Alle"-Reihe zusaetzlich zu fuenf echten Formaten) ergeben
    hier sechs Reihen."""
    _, anmeldungsverlauf_cache, _ = fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "KSD", 1, format="A"),
            Anmeldung(2026, 9, "KSD", 2, format="B"),
            Anmeldung(2026, 9, "KSD", 3, format="C"),
            Anmeldung(2026, 9, "KSD", 4, format="D"),
            Anmeldung(2026, 9, "KSD", 5, format="E"),
        )
    )
    client = TestClient(app_modul.app)

    antwort = client.get(
        "/schulungen?format_filter=Alle,A,B,C,D,E",
    )

    assert "(Trend)" not in antwort.text
    checkbox_start = antwort.text.index('name="trendlinien_werte"', antwort.text.index("checkbox"))
    assert "checked" not in antwort.text[checkbox_start : antwort.text.index(">", checkbox_start)]


def test_schulungen_trendlinien_explizite_auswahl_wirkt_trotz_vieler_linien(fake_caches):
    """Eine explizite Auswahl (hier: bewusst eingeschaltet) bleibt vom dynamischen
    Standard unberuehrt, auch wenn viele Linien gezeichnet werden."""
    _, anmeldungsverlauf_cache, _ = fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "KSD", 1, format="A"),
            Anmeldung(2026, 9, "KSD", 2, format="B"),
            Anmeldung(2026, 9, "KSD", 3, format="C"),
            Anmeldung(2026, 9, "KSD", 4, format="D"),
            Anmeldung(2026, 9, "KSD", 5, format="E"),
        )
    )
    client = TestClient(app_modul.app)

    antwort = client.get(
        "/schulungen?format_filter=Alle,A,B,C,D,E&trendlinien_werte=an",
    )

    assert "(Trend)" in antwort.text


def test_schulungen_trendlinien_checkbox_ausgeschaltet_zeigt_keine_trendreihe(
    fake_caches,
):
    _, anmeldungsverlauf_cache, _ = fake_caches
    anmeldungsverlauf_cache.ergebnis = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "KSD", 4),
            Anmeldung(2026, 10, "KSD", 2),
        )
    )
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen?trendlinien_werte=aus")

    assert "(Trend)" not in antwort.text


def test_schulungen_filter_zuruecksetzen_behaelt_ab_jahr():
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen?ab_jahr=2023&schulung_filter=CSM")

    href_index = antwort.text.index("Filter zurücksetzen")
    zeile = antwort.text[max(0, href_index - 200) : href_index]
    assert 'href="/schulungen?ab_jahr=2023"' in zeile


def test_schulungen_filter_zuruecksetzen_behaelt_ansicht_und_trendlinien():
    """ "Filter zurücksetzen" betrifft nur Jahre/Schulungen/Format/Dauer - Ansicht und
    Trendlinien sind Anzeige-Umschalter, keine Auswahl-Filter, und bleiben deshalb
    unangetastet."""
    client = TestClient(app_modul.app)

    antwort = client.get(
        "/schulungen?ansicht=jahresvergleich&trendlinien_werte=aus&schulung_filter=CSM"
    )

    href_index = antwort.text.index("Filter zurücksetzen")
    zeile = antwort.text[max(0, href_index - 200) : href_index]
    href_start = zeile.index('href="') + len('href="')
    href = zeile[href_start : zeile.index('"', href_start)]
    assert "ansicht=jahresvergleich" in href
    assert "trendlinien_werte=aus" in href
    assert "schulung_filter" not in href


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


def test_schulungen_wechsel_des_jahres_laedt_nicht_neu(fake_caches):
    """``ab_jahr`` filtert nur den schon geladenen Anmeldungsverlauf anders zurecht
    (siehe Anmeldungsverlauf.ab_jahr) - ein engerer Beginn ist immer eine Teilmenge
    des einen geladenen Bereichs und darf deshalb nie neu laden."""
    _, anmeldungsverlauf_cache, _ = fake_caches
    client = TestClient(app_modul.app)

    client.get(f"/schulungen?ab_jahr={app_modul.STANDARD_AB_JAHR}")
    client.get(f"/schulungen?ab_jahr={app_modul.STANDARD_AB_JAHR + 2}")

    assert anmeldungsverlauf_cache.anstossen_aufrufe == 0


def test_schulungen_ohne_gecachte_daten_zeigt_die_ladeseite(fake_caches):
    _, anmeldungsverlauf_cache, _ = fake_caches
    anmeldungsverlauf_cache.ergebnis = None
    client = TestClient(app_modul.app)

    antwort = client.get("/schulungen?ab_jahr=2023")

    assert antwort.status_code == 200
    assert "werden geladen" in antwort.text
    assert anmeldungsverlauf_cache.anstossen_aufrufe == 1


def test_schulungen_zeigt_fortschritt_der_ladeseite(fake_caches):
    _, anmeldungsverlauf_cache, _ = fake_caches
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


def test_start_stoesst_die_standardkombination_bereits_beim_start_an(fake_caches):
    dashboard_cache, anmeldungsverlauf_cache, kurzarbeit_cache = fake_caches

    with TestClient(app_modul.app):
        pass

    assert dashboard_cache.anstossen_aufrufe == [
        (int(app_modul.STANDARD_HORIZONT_MONATE), app_modul.STANDARD_AUSLASTUNG_MONATE)
    ]
    assert anmeldungsverlauf_cache.anstossen_aufrufe == 1
    assert kurzarbeit_cache.anstossen_aufrufe == 1


def test_kurzarbeit_zeigt_status_und_zaehler():
    client = TestClient(app_modul.app)

    antwort = client.get("/kurzarbeit")

    assert antwort.status_code == 200
    assert "August 2026" in antwort.text
    assert "Voraussetzung erfüllt" in antwort.text  # 3 kurzarbeitsfaehig, 1 scheitert -> 75%
    assert "plotly" in antwort.text.lower()


def test_kurzarbeit_faerbt_status_wie_die_grafik(fake_caches):
    """Dieselbe (nicht wertende) Farbfamilie wie KURZARBEIT_SCHWELLE_ERREICHT/
    KURZARBEIT_SCHWELLE_NICHT_ERREICHT in der Grafik - siehe
    .status-erfuellt/.status-nicht-erfuellt in basis.html."""
    _, _, kurzarbeit_cache = fake_caches
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


def test_kurzarbeit_zeigt_beschriftete_zeitraum_optionen():
    client = TestClient(app_modul.app)

    antwort = client.get("/kurzarbeit")

    assert "Zurückliegender Zeitraum:" in antwort.text
    assert "1 Monat</option>" in antwort.text
    assert "3 Monate</option>" in antwort.text
    assert "6 Monate</option>" in antwort.text
    assert "1 Jahr</option>" in antwort.text


def test_kurzarbeit_zeigt_schwellenwert_regler_mit_standardwerten():
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


def test_kurzarbeit_zuruecksetzen_link_verweist_auf_standardwerte_und_behaelt_zeitraum():
    client = TestClient(app_modul.app)

    antwort = client.get(
        "/kurzarbeit?anzahl_monate=12&anteil_interne_arbeit_prozent=10&ueberstunden_stunden=5"
    )

    assert 'href="/kurzarbeit?anzahl_monate=12"' in antwort.text


def test_kurzarbeit_gibt_regler_werte_als_schwellenwerte_an_den_cache_weiter(fake_caches):
    _, _, kurzarbeit_cache = fake_caches
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


def test_kurzarbeit_haelt_regler_bereich_bereits_bei_einem_einzelnen_abweichenden_wert_offen():
    client = TestClient(app_modul.app)

    antwort = client.get("/kurzarbeit?ueberstunden_stunden=20")

    assert '<details class="regler-abschnitt" open>' in antwort.text


def test_kurzarbeit_weist_regler_ausserhalb_des_wertebereichs_zurueck():
    client = TestClient(app_modul.app)

    antwort = client.get("/kurzarbeit?anteil_interne_arbeit_prozent=101")

    assert antwort.status_code == 422


def test_kurzarbeit_ohne_gecachte_daten_zeigt_die_ladeseite(fake_caches):
    _, _, kurzarbeit_cache = fake_caches
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


def test_kurzarbeit_zeigt_keine_hinweise(fake_caches):
    """Auf der Webapp lenken die Hinweise eher ab als im Notebook - dort bleiben sie
    (Kollegen-Feedback), auf der Webapp faellt die Anzeige komplett weg."""
    _, _, kurzarbeit_cache = fake_caches
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


def test_vorladen_stoesst_kurzarbeit_cache_nicht_an_wenn_ausgeschaltet(fake_caches, monkeypatch):
    _, _, kurzarbeit_cache = fake_caches
    monkeypatch.setattr(app_modul, "_KURZARBEIT_AKTIV", False)

    with TestClient(app_modul.app):
        pass

    assert kurzarbeit_cache.anstossen_aufrufe == 0


def test_navigationslinks_ohne_query_wenn_alle_parameter_auf_standard():
    """Standardwerte sollen beim Wechseln der Ansicht nicht in der URL landen - eine
    schlanke URL statt unveraendert mitgeschleppter Standardwerte."""
    client = TestClient(app_modul.app)

    antwort = client.get("/")

    assert 'href="/"' in antwort.text
    assert 'href="/dashboard"' in antwort.text
    assert 'href="/schulungen"' in antwort.text
    assert 'href="/kurzarbeit"' in antwort.text


def test_navigationslinks_lassen_standardwert_weg_auch_wenn_explizit_in_url():
    client = TestClient(app_modul.app)

    antwort = client.get(f"/?horizont_monate={app_modul.STANDARD_HORIZONT_MONATE}")

    assert 'href="/"' in antwort.text
    assert 'href="/dashboard"' in antwort.text


def test_navigationslinks_behalten_abweichenden_parameter():
    client = TestClient(app_modul.app)

    antwort = client.get("/?horizont_monate=6")

    assert 'href="/?horizont_monate=6"' in antwort.text
    assert 'href="/dashboard?horizont_monate=6"' in antwort.text


def test_verbrauchsplan_zuruecksetzen_link_ohne_abweichende_parameter_zeigt_auf_schlanke_url():
    client = TestClient(app_modul.app)

    antwort = client.get("/dashboard?verbrauchsplan=Testprojekt:2026-12")

    assert 'href="/dashboard">Verbrauchsplan zurücksetzen' in antwort.text


def test_verbrauchsplan_zuruecksetzen_link_behaelt_abweichenden_parameter():
    client = TestClient(app_modul.app)

    antwort = client.get("/dashboard?horizont_monate=6&verbrauchsplan=Testprojekt:2026-12")

    assert 'href="/dashboard?horizont_monate=6">Verbrauchsplan zurücksetzen' in antwort.text


def test_ohne_budget_filter_zuruecksetzen_link_ohne_abweichende_parameter_zeigt_auf_schlanke_url():
    client = TestClient(app_modul.app)

    antwort = client.get("/dashboard?ohne_budget_filter=Testkunde")

    assert 'href="/dashboard">Filter zurücksetzen' in antwort.text


def test_kurzarbeit_zuruecksetzen_link_laesst_standard_zeitraum_weg():
    client = TestClient(app_modul.app)

    antwort = client.get(
        f"/kurzarbeit?anzahl_monate={app_modul.STANDARD_KURZARBEIT_MONATE}"
        "&anteil_interne_arbeit_prozent=10"
    )

    assert 'href="/kurzarbeit">Schwellenwerte zurücksetzen' in antwort.text
