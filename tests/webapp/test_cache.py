"""Tests fuer webapp.cache - ohne fastapi, damit sie ohne das ``web``-Extra laufen.

Ersetzt ``Dashboard.laden_async``/``SchulungenRepository.anmeldungsverlauf_laden``
durch einen Zaehler statt echt zu laden - geprueft wird nur, ob/wann/mit welchen
Parametern geladen wird, nicht was ein echtes Dashboard bzw. ein echter
Anmeldungsverlauf enthaelt. ``anstossen()`` startet einen Hintergrund-Task; die Tests
warten darauf ueber ein ``asyncio.Event``, statt eine feste Zeit zu schlafen.
"""

from __future__ import annotations

import asyncio
import time
from datetime import date

import pytest

from umsatzprognose.clockodo import KurzarbeitRepository
from umsatzprognose.darstellung import Dashboard
from umsatzprognose.domaene import Anmeldungsverlauf, Personenmonat, Rollenzuordnung, Schwellenwerte
from umsatzprognose.schulungen import SchulungenRepository
from umsatzprognose.webapp import cache as webapp_cache
from umsatzprognose.webapp.cache import (
    AnmeldungsverlaufCache,
    DashboardCache,
    KurzarbeitCache,
    standard_ttl_sekunden,
)

STICHTAG = date(2026, 8, 24)


class _FakeDashboard:
    def __init__(self, *, horizont_monate: int, auslastung_monate: int) -> None:
        self.stichtag = STICHTAG
        self.horizont_monate = horizont_monate
        self.auslastung_monate = auslastung_monate
        self.simulierte_monate: int | None = None

    def simuliere(self, *, monate: int, fortschritt=None) -> None:
        self.simulierte_monate = monate
        if fortschritt is not None:
            fortschritt(f"Simulation abgeschlossen: {monate} Monat(e)")


@pytest.fixture
def ladezaehler(monkeypatch):
    aufrufe: list[tuple[int, int]] = []
    fertig = asyncio.Event()

    async def _fake_laden_async(
        *, stichtag=None, horizont_monate=3, auslastung_monate=12, fortschritt=None
    ):
        aufrufe.append((horizont_monate, auslastung_monate))
        if fortschritt is not None:
            fortschritt(f"Bestand geladen: {horizont_monate}/{auslastung_monate}")
        fertig.set()
        return _FakeDashboard(horizont_monate=horizont_monate, auslastung_monate=auslastung_monate)

    monkeypatch.setattr(Dashboard, "laden_async", _fake_laden_async)
    return aufrufe, fertig


async def _bis_geladen(fertig: asyncio.Event) -> None:
    await asyncio.wait_for(fertig.wait(), timeout=1)
    await asyncio.sleep(0)  # dem Hintergrund-Task die Gelegenheit geben, den Cache zu fuellen


def test_anstossen_laedt_im_hintergrund_und_bereit_liefert_danach_das_ergebnis(ladezaehler):
    aufrufe, fertig = ladezaehler
    cache = DashboardCache(ttl_sekunden=60)

    async def ablauf():
        assert cache.bereit(horizont_monate=3, auslastung_monate=12) is None
        cache.anstossen(horizont_monate=3, auslastung_monate=12)
        await _bis_geladen(fertig)
        return cache.bereit(horizont_monate=3, auslastung_monate=12)

    dashboard = asyncio.run(ablauf())
    assert aufrufe == [(3, 12)]
    assert dashboard.simulierte_monate == 3


def test_fortschritt_zeigt_gemeldete_zeilen_waehrend_des_ladens_und_ist_danach_leer(
    monkeypatch,
):
    """Waehrend des Hintergrund-Ladevorgangs landen ``fortschritt``-Meldungen (aus
    ``Dashboard.laden_async``) sofort in ``DashboardCache.fortschritt`` - fuer die
    Ladeseite (siehe ``webapp.app``). Nach Abschluss ist die Liste wieder leer, weil
    ``bereit()`` dann ohnehin das fertige Dashboard liefert."""
    gemeldet = asyncio.Event()
    weiter = asyncio.Event()

    async def _fake_laden_async(
        *, stichtag=None, horizont_monate=3, auslastung_monate=12, fortschritt
    ):
        fortschritt(f"Bestand geladen: {horizont_monate}/{auslastung_monate}")
        gemeldet.set()
        await weiter.wait()
        return _FakeDashboard(horizont_monate=horizont_monate, auslastung_monate=auslastung_monate)

    monkeypatch.setattr(Dashboard, "laden_async", _fake_laden_async)
    cache = DashboardCache(ttl_sekunden=60)

    async def ablauf():
        assert cache.fortschritt(horizont_monate=3, auslastung_monate=12) == []
        cache.anstossen(horizont_monate=3, auslastung_monate=12)
        await asyncio.wait_for(gemeldet.wait(), timeout=1)
        waehrend_des_ladens = cache.fortschritt(horizont_monate=3, auslastung_monate=12)

        weiter.set()
        await asyncio.sleep(0)  # dem Hintergrund-Task die Gelegenheit geben, fertig zu werden
        nach_abschluss = cache.fortschritt(horizont_monate=3, auslastung_monate=12)
        return waehrend_des_ladens, nach_abschluss

    waehrend_des_ladens, nach_abschluss = asyncio.run(ablauf())
    assert waehrend_des_ladens == ["Bestand geladen: 3/12"]
    assert nach_abschluss == []
    assert cache.bereit(horizont_monate=3, auslastung_monate=12) is not None


def test_anstossen_ruft_kein_zweites_mal_auf_waehrend_es_schon_laeuft(ladezaehler):
    aufrufe, fertig = ladezaehler
    cache = DashboardCache(ttl_sekunden=60)

    async def ablauf():
        cache.anstossen(horizont_monate=3, auslastung_monate=12)
        cache.anstossen(horizont_monate=3, auslastung_monate=12)
        await _bis_geladen(fertig)

    asyncio.run(ablauf())
    assert aufrufe == [(3, 12)]


def test_anstossen_fuer_andere_parameter_laedt_einen_eigenen_eintrag(ladezaehler):
    aufrufe, fertig = ladezaehler
    cache = DashboardCache(ttl_sekunden=60)

    async def ablauf():
        cache.anstossen(horizont_monate=3, auslastung_monate=12)
        await _bis_geladen(fertig)
        fertig.clear()
        cache.anstossen(horizont_monate=6, auslastung_monate=12)
        await _bis_geladen(fertig)

    asyncio.run(ablauf())
    assert aufrufe == [(3, 12), (6, 12)]


def test_bereit_ist_nach_ablauf_der_ttl_wieder_none(ladezaehler, monkeypatch):
    _aufrufe, fertig = ladezaehler
    cache = DashboardCache(ttl_sekunden=1)

    async def ablauf():
        cache.anstossen(horizont_monate=3, auslastung_monate=12)
        await _bis_geladen(fertig)

    asyncio.run(ablauf())
    assert cache.bereit(horizont_monate=3, auslastung_monate=12) is not None

    # Erst NACH dem Warten faelschen - asyncio.wait_for verlaesst sich selbst auf
    # time.monotonic() fuer seine Ablaufzeit.
    echte_uhr = time.monotonic
    monkeypatch.setattr("time.monotonic", lambda: echte_uhr() + 2)
    assert cache.bereit(horizont_monate=3, auslastung_monate=12) is None


def test_anstossen_meldet_einen_fehlgeschlagenen_ladevorgang_statt_ihn_zu_verlieren(
    monkeypatch, capsys
):
    async def _schlaegt_fehl(
        *, stichtag=None, horizont_monate=3, auslastung_monate=12, fortschritt=None
    ):
        raise ValueError("kaputt")

    monkeypatch.setattr(Dashboard, "laden_async", _schlaegt_fehl)
    cache = DashboardCache(ttl_sekunden=60)

    async def ablauf():
        cache.anstossen(horizont_monate=3, auslastung_monate=12)
        for _ in range(100):
            await asyncio.sleep(0)

    asyncio.run(ablauf())
    assert cache.bereit(horizont_monate=3, auslastung_monate=12) is None
    assert "kaputt" in capsys.readouterr().out
    assert cache.fehler(horizont_monate=3, auslastung_monate=12) == "kaputt"


def test_fehler_ist_leer_ohne_gescheiterten_ladevorgang():
    cache = DashboardCache(ttl_sekunden=60)
    assert cache.fehler(horizont_monate=3, auslastung_monate=12) is None


def test_ein_erfolgreicher_ladevorgang_loescht_einen_vorherigen_fehler(monkeypatch):
    fertig = asyncio.Event()

    async def _schlaegt_fehl(
        *, stichtag=None, horizont_monate=3, auslastung_monate=12, fortschritt=None
    ):
        raise ValueError("kaputt")

    async def _gelingt(*, stichtag=None, horizont_monate=3, auslastung_monate=12, fortschritt=None):
        fertig.set()
        return _FakeDashboard(horizont_monate=horizont_monate, auslastung_monate=auslastung_monate)

    cache = DashboardCache(ttl_sekunden=60)

    async def ablauf():
        monkeypatch.setattr(Dashboard, "laden_async", _schlaegt_fehl)
        cache.anstossen(horizont_monate=3, auslastung_monate=12)
        for _ in range(100):
            await asyncio.sleep(0)
        assert cache.fehler(horizont_monate=3, auslastung_monate=12) == "kaputt"

        monkeypatch.setattr(Dashboard, "laden_async", _gelingt)
        cache.anstossen(horizont_monate=3, auslastung_monate=12)
        await _bis_geladen(fertig)

    asyncio.run(ablauf())
    assert cache.bereit(horizont_monate=3, auslastung_monate=12) is not None
    assert cache.fehler(horizont_monate=3, auslastung_monate=12) is None


@pytest.fixture
def anmeldungsverlauf_ladezaehler(monkeypatch):
    aufrufe: list[range] = []
    fertig = asyncio.Event()

    def _fake_anmeldungsverlauf_laden(self, jahre):
        aufrufe.append(jahre)
        fertig.set()
        return Anmeldungsverlauf()

    monkeypatch.setattr(
        SchulungenRepository, "anmeldungsverlauf_laden", _fake_anmeldungsverlauf_laden
    )
    monkeypatch.setattr(
        SchulungenRepository,
        "mit_automatischen_zugangsdaten",
        classmethod(lambda cls: cls.__new__(cls)),  # type: ignore[call-overload]
    )
    return aufrufe, fertig


def test_anmeldungsverlauf_cache_fortschritt_ist_leer_ohne_laufenden_ladevorgang():
    """``anmeldungsverlauf_laden()`` ist ein einzelner synchroner Aufruf ohne
    Zwischenschritt (siehe ``AnmeldungsverlaufCache.anstossen``) - beobachtbar bleibt
    deshalb nur der Zustand vor bzw. nach einem Ladevorgang, nie waehrenddessen."""
    cache = AnmeldungsverlaufCache(ab_jahr=2022, ttl_sekunden=60)
    assert cache.fortschritt() == []


def test_anmeldungsverlauf_cache_laedt_ab_dem_konstruktor_jahr(anmeldungsverlauf_ladezaehler):
    aufrufe, fertig = anmeldungsverlauf_ladezaehler
    cache = AnmeldungsverlaufCache(ab_jahr=2022, ttl_sekunden=60)

    async def ablauf():
        assert cache.bereit() is None
        cache.anstossen()
        await _bis_geladen(fertig)
        return cache.bereit()

    verlauf = asyncio.run(ablauf())
    assert list(aufrufe[0]) == list(range(2022, date.today().year + 1))
    assert verlauf is not None


def test_anmeldungsverlauf_cache_laedt_bei_wiederholtem_anstossen_nur_einmal(
    anmeldungsverlauf_ladezaehler,
):
    """Ein enger gewaehlter Betrachtungsbeginn (z. B. 'seit 2024' statt 'seit 2022')
    ist beim Filtern in :meth:`Anmeldungsverlauf.ab_jahr` immer eine Teilmenge dieses
    einen geladenen Bereichs - der Cache kennt deshalb gar kein zweites ``ab_jahr``
    mehr, das einen eigenen Ladevorgang auslösen könnte."""
    aufrufe, fertig = anmeldungsverlauf_ladezaehler
    cache = AnmeldungsverlaufCache(ab_jahr=2022, ttl_sekunden=60)

    async def ablauf():
        cache.anstossen()
        await _bis_geladen(fertig)
        cache.anstossen()  # weiterhin frisch - loest keinen zweiten Ladevorgang aus
        cache.anstossen()

    asyncio.run(ablauf())
    assert len(aufrufe) == 1


def test_standard_ttl_sekunden_ohne_env_ist_der_standard(monkeypatch):
    monkeypatch.delenv("WEBAPP_CACHE_TTL_SEKUNDEN", raising=False)
    assert standard_ttl_sekunden() == 60 * 60


def test_standard_ttl_sekunden_liest_env(monkeypatch):
    monkeypatch.setenv("WEBAPP_CACHE_TTL_SEKUNDEN", "42")
    assert standard_ttl_sekunden() == 42


def test_standard_ttl_sekunden_bei_ungueltigem_wert_ist_der_standard(monkeypatch):
    monkeypatch.setenv("WEBAPP_CACHE_TTL_SEKUNDEN", "nicht-numerisch")
    assert standard_ttl_sekunden() == 60 * 60


@pytest.fixture
def kurzarbeit_ladezaehler(monkeypatch):
    aufrufe: list[int] = []
    fertig = asyncio.Event()

    async def _fake_laden_async(self, *, stichtag=None, anzahl_monate=1, fortschritt=None):
        aufrufe.append(anzahl_monate)
        fertig.set()
        return {
            (2026, 8): (
                Personenmonat(
                    mitarbeiter_id=1,
                    name="Anna Beispiel",
                    jahr=2026,
                    monat=8,
                    interne_stunden=40.0,
                    externe_stunden=120.0,
                    gesamt_stunden=160.0,
                    ueberstundenstand=0.0,
                ),
            )
        }

    monkeypatch.setattr(KurzarbeitRepository, "laden_async", _fake_laden_async)
    monkeypatch.setattr(
        KurzarbeitRepository,
        "mit_automatischen_zugangsdaten",
        classmethod(lambda cls: cls.__new__(cls)),  # type: ignore[call-overload]
    )
    monkeypatch.setattr(webapp_cache, "rollenzuordnung_automatisch", Rollenzuordnung)
    return aufrufe, fertig


def test_kurzarbeit_cache_bewertet_die_geladenen_rohdaten(kurzarbeit_ladezaehler):
    aufrufe, fertig = kurzarbeit_ladezaehler
    cache = KurzarbeitCache(maximale_monate=12, ttl_sekunden=60)

    async def ablauf():
        assert cache.bereit(anzahl_monate=6, schwellenwerte=Schwellenwerte()) is None
        cache.anstossen()
        await _bis_geladen(fertig)
        return cache.bereit(anzahl_monate=6, schwellenwerte=Schwellenwerte())

    ergebnisse = asyncio.run(ablauf())
    # Geladen wird immer mit der konfigurierten maximale_monate, nicht mit der
    # angefragten anzahl_monate (siehe Klassendocstring von KurzarbeitCache).
    assert aufrufe == [12]
    assert ergebnisse is not None
    assert ergebnisse[(2026, 8)].anzahl_kurzarbeitsfaehig == 1


def test_kurzarbeit_cache_zeigt_zwischenschritte_waehrend_des_ladens(monkeypatch):
    """``KurzarbeitRepository.laden_async()`` meldet sich je Zweig (siehe dessen
    Docstring) - diese Zwischenmeldungen landen sofort in
    ``KurzarbeitCache.fortschritt``, genau wie beim ``DashboardCache``."""
    gemeldet = asyncio.Event()
    weiter = asyncio.Event()

    async def _fake_laden_async(self, *, stichtag=None, anzahl_monate=1, fortschritt):
        fortschritt("Personen geladen")
        gemeldet.set()
        await weiter.wait()
        return {}

    monkeypatch.setattr(KurzarbeitRepository, "laden_async", _fake_laden_async)
    monkeypatch.setattr(
        KurzarbeitRepository,
        "mit_automatischen_zugangsdaten",
        classmethod(lambda cls: cls.__new__(cls)),  # type: ignore[call-overload]
    )
    monkeypatch.setattr(webapp_cache, "rollenzuordnung_automatisch", Rollenzuordnung)
    cache = KurzarbeitCache(maximale_monate=12, ttl_sekunden=60)

    async def ablauf():
        assert cache.fortschritt() == []
        cache.anstossen()
        await asyncio.wait_for(gemeldet.wait(), timeout=1)
        waehrend_des_ladens = cache.fortschritt()

        weiter.set()
        await asyncio.sleep(0)  # dem Hintergrund-Task die Gelegenheit geben, fertig zu werden
        nach_abschluss = cache.fortschritt()
        return waehrend_des_ladens, nach_abschluss

    waehrend_des_ladens, nach_abschluss = asyncio.run(ablauf())
    assert waehrend_des_ladens == ["Personen geladen"]
    assert nach_abschluss == []
    assert cache.bereit(anzahl_monate=6, schwellenwerte=Schwellenwerte()) is not None


def test_kurzarbeit_cache_wechsel_der_anzahl_monate_loest_keinen_neuen_ladevorgang_aus(
    monkeypatch,
):
    """Ein Dropdown-Wechsel (6 -> 3 Monate) schneidet nur in-memory heraus, statt
    erneut bei Clockodo zu laden - Muster wie AnmeldungsverlaufCache, nicht wie
    DashboardCache (siehe Klassendocstring von KurzarbeitCache)."""
    aufrufe: list[int] = []
    fertig = asyncio.Event()

    async def _fake_laden_async(self, *, stichtag=None, anzahl_monate=1, fortschritt=None):
        aufrufe.append(anzahl_monate)
        fertig.set()
        return {
            (2026, 6): (
                Personenmonat(
                    mitarbeiter_id=1,
                    name="Anna Beispiel",
                    jahr=2026,
                    monat=6,
                    interne_stunden=0.0,
                    externe_stunden=160.0,
                    gesamt_stunden=160.0,
                    ueberstundenstand=0.0,
                ),
            ),
            (2026, 7): (
                Personenmonat(
                    mitarbeiter_id=1,
                    name="Anna Beispiel",
                    jahr=2026,
                    monat=7,
                    interne_stunden=0.0,
                    externe_stunden=160.0,
                    gesamt_stunden=160.0,
                    ueberstundenstand=0.0,
                ),
            ),
            (2026, 8): (
                Personenmonat(
                    mitarbeiter_id=1,
                    name="Anna Beispiel",
                    jahr=2026,
                    monat=8,
                    interne_stunden=40.0,
                    externe_stunden=120.0,
                    gesamt_stunden=160.0,
                    ueberstundenstand=0.0,
                ),
            ),
        }

    monkeypatch.setattr(KurzarbeitRepository, "laden_async", _fake_laden_async)
    monkeypatch.setattr(
        KurzarbeitRepository,
        "mit_automatischen_zugangsdaten",
        classmethod(lambda cls: cls.__new__(cls)),  # type: ignore[call-overload]
    )
    monkeypatch.setattr(webapp_cache, "rollenzuordnung_automatisch", Rollenzuordnung)
    cache = KurzarbeitCache(maximale_monate=12, ttl_sekunden=60)

    async def ablauf():
        cache.anstossen()
        await _bis_geladen(fertig)
        drei_monate = cache.bereit(anzahl_monate=3, schwellenwerte=Schwellenwerte())
        ein_monat = cache.bereit(anzahl_monate=1, schwellenwerte=Schwellenwerte())
        return drei_monate, ein_monat

    drei_monate, ein_monat = asyncio.run(ablauf())
    # Nur ein einziger Ladevorgang, mit der konfigurierten maximale_monate - nicht
    # je einer fuer 3 und fuer 1 Monat.
    assert aufrufe == [12]
    assert sorted(drei_monate) == [(2026, 6), (2026, 7), (2026, 8)]
    assert sorted(ein_monat) == [(2026, 8)]


def test_kurzarbeit_cache_wechsel_der_schwellenwerte_loest_keinen_neuen_ladevorgang_aus(
    kurzarbeit_ladezaehler,
):
    """Ein Regler-Wechsel (z. B. auf der Weboberflaeche) bewertet dieselben
    geladenen Rohdaten nur neu, statt erneut bei Clockodo zu laden - siehe
    Klassendocstring von KurzarbeitCache."""
    aufrufe, fertig = kurzarbeit_ladezaehler
    cache = KurzarbeitCache(maximale_monate=12, ttl_sekunden=60)

    async def ablauf():
        cache.anstossen()
        await _bis_geladen(fertig)
        milde = cache.bereit(
            anzahl_monate=6, schwellenwerte=Schwellenwerte(anteil_interne_arbeit=0.1)
        )
        streng = cache.bereit(
            anzahl_monate=6, schwellenwerte=Schwellenwerte(anteil_interne_arbeit=0.9)
        )
        return milde, streng

    milde, streng = asyncio.run(ablauf())
    assert aufrufe == [12]
    # Die geladene Person hat 40 von 160 Stunden intern (25 %) - unterhalb einer
    # 90-%-Schwelle, oberhalb einer 10-%-Schwelle.
    assert milde[(2026, 8)].anzahl_kurzarbeitsfaehig == 1
    assert streng[(2026, 8)].anzahl_kurzarbeitsfaehig == 0
