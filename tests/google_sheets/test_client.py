"""Tests fuer google_sheets.client - nur der Teil ohne echten Netz-/Browser-Zugriff.

``GoogleSheetsClient`` selbst (OAuth-Login, HTTP-Zugriff) bleibt ungetestet: eine
sinnvolle Pruefung braeuchte entweder einen echten interaktiven Login oder so viel
Mocking der google-auth-Bibliotheken, dass am Ende nur noch deren Aufrufreihenfolge
geprueft wuerde, nicht eigenes Verhalten. ``jahre_laden()`` und ``kopfzeile_finden()``
(der zwischen ``schulungen``/``kosten`` geteilte Teil) sind zusaetzlich ueber die Tests
von ``schulungen``/``kosten`` abgedeckt, die sie aufrufen.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from umsatzprognose.google_sheets.client import (
    TOKEN_PFAD_STANDARD,
    _lokale_credentials,
    kopfzeile_finden,
    token_pfad,
    zelle,
    zelle_an,
)
from umsatzprognose.google_sheets.config import MissingCredentialsError


def test_lokale_credentials_ohne_oauth_client_json_wirft():
    with pytest.raises(MissingCredentialsError, match="GOOGLE_OAUTH_CLIENT_JSON"):
        _lokale_credentials(None)


def test_token_pfad_ohne_env_ist_der_standardpfad(monkeypatch):
    monkeypatch.delenv("GOOGLE_OAUTH_TOKEN_PFAD", raising=False)
    assert token_pfad() == TOKEN_PFAD_STANDARD


def test_token_pfad_liest_env(monkeypatch, tmp_path):
    eigener_pfad = tmp_path / "token.json"
    monkeypatch.setenv("GOOGLE_OAUTH_TOKEN_PFAD", str(eigener_pfad))
    assert token_pfad() == Path(eigener_pfad)


def test_kopfzeile_finden_findet_erste_zeile_mit_allen_pflichtspalten():
    zeilen = [["Bemerkung"], ["A", "B", "C"]]
    zeile_index, index = kopfzeile_finden(zeilen, {"A", "C"})
    assert zeile_index == 1
    assert index == {"A": 0, "B": 1, "C": 2}


def test_kopfzeile_finden_bei_doppeltem_spaltennamen_gewinnt_die_rechte():
    _, index = kopfzeile_finden([["A", "A"]], {"A"})
    assert index["A"] == 1


def test_kopfzeile_finden_ohne_treffer_wirft():
    with pytest.raises(ValueError, match="A"):
        kopfzeile_finden([["B"]], {"A"})


def test_zelle_an_ueber_zeilenende_hinaus_ist_leer():
    assert zelle_an(["x"], 1) == ""


def test_zelle_liest_ueber_den_index_nach_spaltenname():
    index = {"Name": 1}
    assert zelle(["x", "Anna"], index, "Name") == "Anna"
