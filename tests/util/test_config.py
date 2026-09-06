"""Tests fuer umsatzprognose.util.config - die gemeinsamen Bausteine, auf denen
clockodo.config und google_sheets.config aufbauen (siehe deren eigene Tests fuer die
konkrete Verdrahtung mit ihrer jeweiligen ``MissingCredentialsError``).
"""

from __future__ import annotations

import sys
import types

import pytest

from umsatzprognose.util.config import colab_secret, in_colab, umgebungsvariable


class _TestError(Exception):
    """Platzhalter-Exception, wie sie ``clockodo``/``google_sheets`` je eigene tragen."""


def test_in_colab_ist_false_ausserhalb_von_colab():
    # In der Testumgebung ist google.colab nicht installiert - der echte, unveraenderte
    # Pfad und keine Annahme, die man extra herstellen muesste.
    assert in_colab() is False


def test_umgebungsvariable_liest_und_entfernt_leerzeichen(monkeypatch):
    monkeypatch.setenv("BEISPIEL_VAR", "  wert  ")
    assert umgebungsvariable("BEISPIEL_VAR", fehlerklasse=_TestError) == "wert"


def test_umgebungsvariable_wirft_bei_fehlender_variable(monkeypatch):
    monkeypatch.delenv("FEHLENDE_VAR", raising=False)
    with pytest.raises(_TestError, match="FEHLENDE_VAR"):
        umgebungsvariable("FEHLENDE_VAR", fehlerklasse=_TestError)


def test_umgebungsvariable_wirft_bei_nur_leerzeichen(monkeypatch):
    monkeypatch.setenv("LEERE_VAR", "   ")
    with pytest.raises(_TestError, match="LEERE_VAR"):
        umgebungsvariable("LEERE_VAR", fehlerklasse=_TestError)


def _fake_colab_userdata(monkeypatch, get):
    """Registriert ein Fake fuer ``from google.colab import userdata``.

    ``google.colab`` ist ausserhalb von Colab nicht installiert; das Modul wird deshalb
    nur fuer die Dauer des Tests in ``sys.modules`` eingehaengt.
    """
    fake_userdata = types.SimpleNamespace(get=get)
    fake_colab = types.ModuleType("google.colab")
    fake_colab.userdata = fake_userdata  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google.colab", fake_colab)
    monkeypatch.setitem(
        sys.modules, "google", sys.modules.get("google", types.ModuleType("google"))
    )


def test_colab_secret_liest_und_entfernt_leerzeichen(monkeypatch):
    _fake_colab_userdata(monkeypatch, get=lambda name: f"  wert-fuer-{name}  ")
    assert colab_secret("BEISPIEL_SECRET", fehlerklasse=_TestError) == "wert-fuer-BEISPIEL_SECRET"


def test_colab_secret_wirft_wenn_secret_leer(monkeypatch):
    _fake_colab_userdata(monkeypatch, get=lambda name: "   ")
    with pytest.raises(_TestError, match="leer"):
        colab_secret("BEISPIEL_SECRET", fehlerklasse=_TestError)


def test_colab_secret_wirft_wenn_userdata_fehlschlaegt(monkeypatch):
    def get(name):
        raise RuntimeError("Secret nicht abrufbar")

    _fake_colab_userdata(monkeypatch, get=get)
    with pytest.raises(_TestError, match="BEISPIEL_SECRET") as fehler:
        colab_secret("BEISPIEL_SECRET", fehlerklasse=_TestError)
    assert fehler.value.__cause__ is not None
