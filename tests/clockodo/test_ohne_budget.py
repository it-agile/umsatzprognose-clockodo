"""Tests zur Konfiguration des Modells fuer Projekte ohne Budget."""

from __future__ import annotations

import pytest

from umsatzprognose.clockodo import ohne_budget as modul
from umsatzprognose.clockodo.ohne_budget import (
    OHNE_BUDGET_MODELL_VAR,
    MissingOhneBudgetModellError,
    ohne_budget_modell_aus_colab_secrets,
    ohne_budget_modell_aus_umgebung,
    ohne_budget_modell_automatisch,
)
from umsatzprognose.domaene import OhneBudgetModell


def test_ohne_gesetzte_variable_gibt_es_kein_modell(monkeypatch):
    monkeypatch.delenv(OHNE_BUDGET_MODELL_VAR, raising=False)

    # use_dotenv=False: isoliert vom lokalen .env dieses Klons.
    assert ohne_budget_modell_aus_umgebung(use_dotenv=False) is None


def test_liest_ausschluss_schulung_und_fenster(monkeypatch):
    monkeypatch.setenv(
        OHNE_BUDGET_MODELL_VAR,
        '{"ausschluss": ["Intern"], "schulung": ["Kurs"], "historie_monate": 4}',
    )

    assert ohne_budget_modell_aus_umgebung(use_dotenv=False) == OhneBudgetModell(
        ausschluss=("Intern",), schulung=("Kurs",), historie_monate=4
    )


def test_fehlende_schluessel_haben_standardwerte(monkeypatch):
    monkeypatch.setenv(OHNE_BUDGET_MODELL_VAR, "{}")

    assert ohne_budget_modell_aus_umgebung(use_dotenv=False) == OhneBudgetModell()


@pytest.mark.parametrize(
    ("inhalt", "fehlertext"),
    [
        ("kein json", "kein gueltiges JSON"),
        ("[]", "JSON-Objekt"),
        ('{"ausschluss": "Intern"}', "Liste von Texten"),
        ('{"schulung": [1]}', "Liste von Texten"),
        ('{"historie_monate": "6"}', "ganze Zahl"),
        ('{"historie_monate": 0}', "historie_monate"),
    ],
)
def test_ungueltige_konfiguration_nennt_den_grund(monkeypatch, inhalt, fehlertext):
    monkeypatch.setenv(OHNE_BUDGET_MODELL_VAR, inhalt)

    with pytest.raises(MissingOhneBudgetModellError, match=fehlertext):
        ohne_budget_modell_aus_umgebung(use_dotenv=False)


def test_automatisch_liest_ausserhalb_von_colab_die_umgebungsvariable(monkeypatch):
    """In GitHub Actions kommt das Secret ueber ``env:`` als Umgebungsvariable an; eine
    ``.env`` mit anderem Inhalt darf eine bereits gesetzte Variable nicht ueberschreiben."""
    monkeypatch.setattr(modul, "in_colab", lambda: False)
    monkeypatch.setenv(OHNE_BUDGET_MODELL_VAR, '{"schulung": ["Kurs"]}')

    assert ohne_budget_modell_automatisch() == OhneBudgetModell(schulung=("Kurs",))


def test_leere_umgebungsvariable_gilt_als_nicht_gesetzt(monkeypatch):
    """Ein in der Action durchgereichtes, aber nicht angelegtes Secret ist leer."""
    monkeypatch.setattr(modul, "in_colab", lambda: False)
    monkeypatch.setenv(OHNE_BUDGET_MODELL_VAR, "")

    assert ohne_budget_modell_automatisch() is None


def test_automatisch_liest_in_colab_das_secret(monkeypatch):
    monkeypatch.setattr(modul, "in_colab", lambda: True)
    monkeypatch.setattr(modul, "_colab_secret", lambda name: '{"ausschluss": ["Intern"]}')

    assert ohne_budget_modell_automatisch() == OhneBudgetModell(ausschluss=("Intern",))


def test_fehlendes_colab_secret_gibt_kein_modell(monkeypatch):
    def fehlt(name):
        raise MissingOhneBudgetModellError("nicht angelegt")

    monkeypatch.setattr(modul, "_colab_secret", fehlt)

    assert ohne_budget_modell_aus_colab_secrets() is None
