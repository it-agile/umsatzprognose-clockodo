"""Tests fuer google_sheets.config: Parsing der Umgebungsvariablen, ohne Netzzugriff.

Insbesondere die Unterscheidung OAuth-Client-ID vs. Service-Account-Key - ein
Service-Account-Key ist fuer diese Anlage kein gueltiger Wert fuer
GOOGLE_OAUTH_CLIENT_JSON (siehe Moduldocstring von google_sheets.config). Gemeinsame
Konfiguration fuer :mod:`umsatzprognose.schulungen` und :mod:`umsatzprognose.kosten`.
"""

from __future__ import annotations

import sys
import types

import pytest

from umsatzprognose.google_sheets import config as google_sheets_config
from umsatzprognose.google_sheets.config import (
    GoogleSheetsConfig,
    MissingCredentialsError,
    _jahre_zu_dateien,
    _oauth_client_json,
)

OAUTH_CLIENT_JSON = (
    '{"installed": {"client_id": "beispiel.apps.googleusercontent.com", '
    '"client_secret": "geheim", "auth_uri": "https://accounts.google.com/o/oauth2/auth", '
    '"token_uri": "https://oauth2.googleapis.com/token"}}'
)
SERVICE_ACCOUNT_JSON = (
    '{"type": "service_account", "project_id": "beispiel", '
    '"private_key": "-----BEGIN PRIVATE KEY-----\\n...\\n-----END PRIVATE KEY-----\\n", '
    '"client_email": "beispiel@beispiel.iam.gserviceaccount.com"}'
)


def test_oauth_client_json_akzeptiert_installed_json():
    wert = _oauth_client_json(OAUTH_CLIENT_JSON)
    assert wert["installed"]["client_id"] == "beispiel.apps.googleusercontent.com"


def test_oauth_client_json_lehnt_service_account_key_ab():
    # Genau der Fall, der zur Umstellung gefuehrt hat: Google gibt fuer diese Anlage
    # nur eine OAuth-Client-ID aus, kein Service-Account-Key - eine solche Datei soll
    # eine verstaendliche Fehlermeldung ausloesen statt einen kryptischen Fehler tief in
    # googleapiclient.
    with pytest.raises(MissingCredentialsError, match="Service-Account"):
        _oauth_client_json(SERVICE_ACCOUNT_JSON)


def test_oauth_client_json_lehnt_ungueltiges_json_ab():
    with pytest.raises(MissingCredentialsError, match="GOOGLE_OAUTH_CLIENT_JSON"):
        _oauth_client_json("kein-json")


def test_jahre_zu_dateien_wandelt_schluessel_in_int():
    assert _jahre_zu_dateien('{"2026": "sheet-a", "2027": "sheet-b"}') == {
        2026: "sheet-a",
        2027: "sheet-b",
    }


def test_jahre_zu_dateien_lehnt_ungueltiges_json_ab():
    with pytest.raises(MissingCredentialsError, match="KOSTEN_SHEET_IDS"):
        _jahre_zu_dateien("kein-json")


def test_jahre_zu_dateien_lehnt_json_ab_das_kein_objekt_ist():
    with pytest.raises(MissingCredentialsError, match="JSON-Objekt"):
        _jahre_zu_dateien("[1, 2, 3]")


def test_jahre_zu_dateien_lehnt_nicht_numerische_schluessel_ab():
    with pytest.raises(MissingCredentialsError, match="Jahreszahlen"):
        _jahre_zu_dateien('{"nicht-numerisch": "sheet-a"}')


def _setze_umgebung(monkeypatch):
    monkeypatch.setenv("KOSTEN_SHEET_IDS", '{"2026": "sheet-2026"}')
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_JSON", OAUTH_CLIENT_JSON)


def test_aus_umgebung_liest_jahre_und_oauth_client(monkeypatch):
    _setze_umgebung(monkeypatch)
    config = GoogleSheetsConfig.aus_umgebung(use_dotenv=False)
    assert config.jahre_zu_dateien == {2026: "sheet-2026"}
    assert config.oauth_client_config is not None
    assert config.oauth_client_config["installed"]["client_id"] == (
        "beispiel.apps.googleusercontent.com"
    )


def test_aus_umgebung_wirft_bei_fehlender_variable(monkeypatch):
    monkeypatch.delenv("KOSTEN_SHEET_IDS", raising=False)
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_JSON", OAUTH_CLIENT_JSON)
    with pytest.raises(MissingCredentialsError, match="KOSTEN_SHEET_IDS"):
        GoogleSheetsConfig.aus_umgebung(use_dotenv=False)


def test_aus_colab_secrets_liest_nur_jahre_ohne_oauth_client(monkeypatch):
    fake_userdata = types.SimpleNamespace(get=lambda name: '{"2027": "sheet-2027"}')
    fake_colab = types.ModuleType("google.colab")
    fake_colab.userdata = fake_userdata  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google.colab", fake_colab)
    monkeypatch.setitem(
        sys.modules, "google", sys.modules.get("google", types.ModuleType("google"))
    )

    config = GoogleSheetsConfig.aus_colab_secrets()

    assert config.jahre_zu_dateien == {2027: "sheet-2027"}
    assert config.oauth_client_config is None


def test_automatisch_waehlt_umgebung_ausserhalb_von_colab(monkeypatch):
    _setze_umgebung(monkeypatch)
    monkeypatch.setattr(google_sheets_config, "in_colab", lambda: False)
    config = GoogleSheetsConfig.automatisch()
    assert config.jahre_zu_dateien == {2026: "sheet-2026"}


def test_automatisch_waehlt_colab_secrets_in_colab(monkeypatch):
    aufgerufen = []
    monkeypatch.setattr(google_sheets_config, "in_colab", lambda: True)
    monkeypatch.setattr(
        GoogleSheetsConfig, "aus_colab_secrets", classmethod(lambda cls: aufgerufen.append(True))
    )
    GoogleSheetsConfig.automatisch()
    assert aufgerufen == [True]
