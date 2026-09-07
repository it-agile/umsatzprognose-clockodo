"""Test fuer webapp.app - nur mit installiertem ``web``-Extra (siehe pyproject.toml).

Ohne das Extra wird der Test uebersprungen statt die gesamte Testsuite brechen zu
lassen - ``fastapi`` ist bewusst keine Basisabhaengigkeit (siehe Moduldocstring von
:mod:`umsatzprognose.webapp`).
"""

from __future__ import annotations

from datetime import date

import pytest

from umsatzprognose.darstellung import Dashboard
from umsatzprognose.domaene import (
    Anmeldungsverlauf,
    Bestand,
    Gesamtbudget,
    Hinweis,
    Kostenplan,
    Kunde,
    Kurzarbeitsbewertung,
    Monatsumsatz,
    Projekt,
    Schulungsplan,
    Schulungstermin,
    Schwellenwerte,
    Umsatzhistorie,
)

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from umsatzprognose.webapp import app as app_modul  # noqa: E402

STICHTAG = date(2026, 8, 24)
KUNDE = Kunde(id=1, name="Testkunde")
HISTORIE = Umsatzhistorie.zum_stichtag([Monatsumsatz(2026, 8, 1000.0, 10.0)], STICHTAG)
PROJEKTE = (
    Projekt(
        id=1,
        name="Testprojekt",
        kunde=KUNDE,
        aktiv=True,
        budget=Gesamtbudget(betrag=5000.0),
        verbrauchtes_volumen=1000.0,
        verbrauchte_stunden=10.0,
    ),
)
BESTAND = Bestand(stichtag=STICHTAG, projekte=PROJEKTE, umsatzhistorie=HISTORIE)
SCHULUNGSPLAN = Schulungsplan(stichtag=STICHTAG, termine=(Schulungstermin(2026, 8, 2500.0),))
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
    return dashboard_cache, anmeldungsverlauf_cache, kurzarbeit_cache


def test_uebersicht_zeigt_stichtag_und_die_drei_datencheck_grafiken():
    client = TestClient(app_modul.app)

    antwort = client.get("/")

    assert antwort.status_code == 200
    assert "24.08.2026" in antwort.text
    assert "plotly" in antwort.text.lower()


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
    """Dieselbe Farbfamilie wie ERGEBNIS_POSITIV/ERGEBNIS_NEGATIV in der Grafik -
    siehe .status-positiv/.status-negativ in basis.html."""
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

    assert '<td class="status-positiv">Voraussetzung erfüllt</td>' in antwort.text
    assert '<td class="status-negativ">Voraussetzung nicht erfüllt</td>' in antwort.text
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
    """Aggregatzahlen ja, aber keine Personennamen oder IDs (Spec Abschnitt 2/6)."""
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
