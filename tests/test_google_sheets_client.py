"""Tests fuer google_sheets.client - nur der Teil ohne echten Netz-/Browser-Zugriff.

``GoogleSheetsClient`` selbst (OAuth-Login, HTTP-Zugriff) bleibt ungetestet: eine
sinnvolle Pruefung braeuchte entweder einen echten interaktiven Login oder so viel
Mocking der google-auth-Bibliotheken, dass am Ende nur noch deren Aufrufreihenfolge
geprueft wuerde, nicht eigenes Verhalten. ``jahre_laden()`` (der wiederverwendbare Teil)
ist ueber die Tests von ``schulungen``/``kosten`` abgedeckt, die es aufrufen.
"""

from __future__ import annotations

import pytest

from umsatzprognose.google_sheets.client import _lokale_credentials
from umsatzprognose.google_sheets.config import MissingCredentialsError


def test_lokale_credentials_ohne_oauth_client_json_wirft():
    with pytest.raises(MissingCredentialsError, match="GOOGLE_OAUTH_CLIENT_JSON"):
        _lokale_credentials(None)
