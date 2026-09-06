"""Tests fuer clockodo.config: die drei benannten Konstruktoren von ClockodoCredentials.

Die zugrunde liegenden Bausteine (Lesen einer Umgebungsvariable/eines Colab-Secrets)
sind in test_config.py getestet; hier geht es um die Verdrahtung mit den vier
Clockodo-Feldern und um MissingCredentialsError als die Clockodo-eigene Fehlerklasse.
"""

from __future__ import annotations

import sys
import types

import pytest

from umsatzprognose.clockodo import config as clockodo_config
from umsatzprognose.clockodo.config import ClockodoCredentials, MissingCredentialsError

UMGEBUNG = {
    "CLOCKODO_API_USER": "user@example.com",
    "CLOCKODO_API_KEY": "geheim",
    "CLOCKODO_APP_NAME": "test",
    "CLOCKODO_APP_EMAIL": "a@b.de",
}


def _setze_umgebung(monkeypatch, **overrides):
    werte = {**UMGEBUNG, **overrides}
    for name, wert in werte.items():
        if wert is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, wert)


def test_aus_umgebung_liest_alle_vier_felder(monkeypatch):
    _setze_umgebung(monkeypatch)
    creds = ClockodoCredentials.aus_umgebung(use_dotenv=False)
    assert creds == ClockodoCredentials(
        api_user=UMGEBUNG["CLOCKODO_API_USER"],
        api_key=UMGEBUNG["CLOCKODO_API_KEY"],
        app_name=UMGEBUNG["CLOCKODO_APP_NAME"],
        app_email=UMGEBUNG["CLOCKODO_APP_EMAIL"],
    )


def test_aus_umgebung_wirft_bei_fehlender_variable(monkeypatch):
    _setze_umgebung(monkeypatch, CLOCKODO_API_KEY=None)
    with pytest.raises(MissingCredentialsError, match="CLOCKODO_API_KEY"):
        ClockodoCredentials.aus_umgebung(use_dotenv=False)


def test_aus_colab_secrets_liest_alle_vier_felder(monkeypatch):
    fake_userdata = types.SimpleNamespace(get=lambda name: UMGEBUNG[name])
    fake_colab = types.ModuleType("google.colab")
    fake_colab.userdata = fake_userdata  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google.colab", fake_colab)
    monkeypatch.setitem(
        sys.modules, "google", sys.modules.get("google", types.ModuleType("google"))
    )

    creds = ClockodoCredentials.aus_colab_secrets()

    assert creds.api_user == UMGEBUNG["CLOCKODO_API_USER"]
    assert creds.api_key == UMGEBUNG["CLOCKODO_API_KEY"]
    assert creds.app_name == UMGEBUNG["CLOCKODO_APP_NAME"]
    assert creds.app_email == UMGEBUNG["CLOCKODO_APP_EMAIL"]


def test_automatisch_waehlt_umgebung_ausserhalb_von_colab(monkeypatch):
    _setze_umgebung(monkeypatch)
    monkeypatch.setattr(clockodo_config, "in_colab", lambda: False)
    creds = ClockodoCredentials.automatisch()
    assert creds.api_user == UMGEBUNG["CLOCKODO_API_USER"]


def test_automatisch_waehlt_colab_secrets_in_colab(monkeypatch):
    aufgerufen = []
    monkeypatch.setattr(clockodo_config, "in_colab", lambda: True)
    monkeypatch.setattr(
        ClockodoCredentials, "aus_colab_secrets", classmethod(lambda cls: aufgerufen.append(True))
    )
    ClockodoCredentials.automatisch()
    assert aufgerufen == [True]
