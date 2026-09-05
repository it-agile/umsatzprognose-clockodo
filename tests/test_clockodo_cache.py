"""Tests zum optionalen Verlaufscache aus :mod:`umsatzprognose.clockodo.cache`."""

from __future__ import annotations

import asyncio

import pytest

from umsatzprognose.clockodo import cache


def test_ohne_umgebungsvariable_ist_der_cache_aus(monkeypatch):
    monkeypatch.delenv(cache.TTL_ENV, raising=False)
    assert cache.ttl_sekunden() is None


def test_gesetzte_zahl_wird_uebernommen(monkeypatch):
    monkeypatch.setenv(cache.TTL_ENV, "300")
    assert cache.ttl_sekunden() == 300


def test_gesetzt_aber_keine_zahl_ergibt_den_standardwert(monkeypatch):
    monkeypatch.setenv(cache.TTL_ENV, "an")
    assert cache.ttl_sekunden() == cache.STANDARD_TTL_SEKUNDEN


def test_cutoff_monate_parameter_geht_vor_umgebungsvariable(monkeypatch):
    monkeypatch.setenv(cache.CUTOFF_ENV, "3")
    assert cache.cutoff_monate(9) == 9


def test_cutoff_monate_liest_umgebungsvariable_ohne_parameter(monkeypatch):
    monkeypatch.setenv(cache.CUTOFF_ENV, "3")
    assert cache.cutoff_monate() == 3


def test_cutoff_monate_ohne_beides_ist_der_standardwert(monkeypatch):
    monkeypatch.delenv(cache.CUTOFF_ENV, raising=False)
    assert cache.cutoff_monate() == cache.STANDARD_CUTOFF_MONATE


def test_cutoff_monate_gesetzt_aber_keine_zahl_ergibt_den_standardwert(monkeypatch):
    monkeypatch.setenv(cache.CUTOFF_ENV, "bald")
    assert cache.cutoff_monate() == cache.STANDARD_CUTOFF_MONATE


@pytest.mark.parametrize(
    ("time_until", "monate", "erwartet"),
    [
        ("2026-09-05T23:59:59Z", 6, "2026-03-01T00:00:00Z"),
        ("2026-01-31T23:59:59Z", 1, "2025-12-01T00:00:00Z"),
        ("2026-03-15T23:59:59Z", 0, "2026-03-01T00:00:00Z"),
    ],
)
def test_cutoff_datum_zaehlt_ueber_die_jahresgrenze(time_until, monate, erwartet):
    assert cache.cutoff_datum(time_until, monate=monate) == erwartet


def test_gecacht_oder_neu_ruft_den_lader_nur_beim_ersten_mal(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "VERZEICHNIS", tmp_path)
    aufrufe = 0

    async def lader():
        nonlocal aufrufe
        aufrufe += 1
        return [{"group": 1, "revenue": 10.0}]

    async def zweimal():
        erstes = await cache.gecacht_oder_neu("schluessel", ttl=60, lader=lader)
        zweites = await cache.gecacht_oder_neu("schluessel", ttl=60, lader=lader)
        return erstes, zweites

    erstes, zweites = asyncio.run(zweimal())

    assert aufrufe == 1
    assert erstes == zweites == [{"group": 1, "revenue": 10.0}]


def test_gecacht_oder_neu_laedt_nach_ablauf_der_ttl_neu(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "VERZEICHNIS", tmp_path)
    aufrufe = 0

    async def lader():
        nonlocal aufrufe
        aufrufe += 1
        return aufrufe

    async def zweimal_ohne_gueltigkeit():
        await cache.gecacht_oder_neu("schluessel", ttl=0, lader=lader)
        return await cache.gecacht_oder_neu("schluessel", ttl=0, lader=lader)

    ergebnis = asyncio.run(zweimal_ohne_gueltigkeit())

    assert aufrufe == 2
    assert ergebnis == 2


def test_schluessel_ist_deterministisch_und_unterscheidet_zeitfenster():
    a = cache.schluessel(["projects_id"], time_since="2021-01-01", time_until="2026-01-01")
    b = cache.schluessel(["projects_id"], time_since="2021-01-01", time_until="2026-02-01")

    assert a == cache.schluessel(["projects_id"], time_since="2021-01-01", time_until="2026-01-01")
    assert a != b
