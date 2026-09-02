"""Tests fuer google_sheets.config: Parsing der Umgebungsvariablen, ohne Netzzugriff.

Insbesondere die Unterscheidung OAuth-Client-ID vs. Service-Account-Key - ein
Service-Account-Key ist fuer diese Anlage kein gueltiger Wert fuer
GOOGLE_OAUTH_CLIENT_JSON (siehe Moduldocstring von google_sheets.config). Gemeinsame
Konfiguration fuer :mod:`umsatzprognose.schulungen` und :mod:`umsatzprognose.kosten`.
"""

from __future__ import annotations

import pytest

from umsatzprognose.google_sheets.config import (
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
    with pytest.raises(MissingCredentialsError, match="TRAINING_SHEET_ID"):
        _jahre_zu_dateien("kein-json")
