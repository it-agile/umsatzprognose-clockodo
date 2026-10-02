"""Konfiguration des Modells fuer Projekte ohne Budget aus der Umgebung.

Welche Projekte ausgeschlossen sind oder Kapazitaet belegen, haengt von den
Projektnamen der jeweiligen Clockodo-Installation ab und gehoert deshalb nicht ins
Repository, sondern wie ``SCHULUNGEN_KATEGORIEN`` in eine Umgebungsvariable
(:data:`OHNE_BUDGET_MODELL_VAR`, siehe ``.env.sample``; in GitHub Actions als Secret,
siehe ``.github/workflows/wochenbericht.yml``, in Colab als Colab-Secret). Ungesetzt
bleibt das Modell aus: Projekte ohne Budget fallen dann wie bisher aus der Prognose.
"""

from __future__ import annotations

import json
from functools import partial

from dotenv import load_dotenv

from umsatzprognose.domaene import OhneBudgetModell
from umsatzprognose.domaene.ohne_budget import STANDARD_HISTORIE_MONATE
from umsatzprognose.util import colab_secret, in_colab, umgebungsvariable

from .config import MissingCredentialsError

OHNE_BUDGET_MODELL_VAR = "OHNE_BUDGET_MODELL"


class MissingOhneBudgetModellError(MissingCredentialsError):
    """Die Konfiguration des Modells fuer Projekte ohne Budget ist ungueltig."""


_umgebungsvariable = partial(umgebungsvariable, fehlerklasse=MissingOhneBudgetModellError)
_colab_secret = partial(colab_secret, fehlerklasse=MissingOhneBudgetModellError)


def ohne_budget_modell_automatisch() -> OhneBudgetModell | None:
    """Aus der passenden Quelle: Colab-Secrets in Colab, sonst Umgebungsvariable (lokal
    mit ``.env``, in GitHub Actions als Secret ueber ``env:`` durchgereicht) - dieselbe
    Auswahl wie bei ``rollenzuordnung_automatisch()``. ``None``, wenn die Konfiguration
    fehlt."""
    return (
        ohne_budget_modell_aus_colab_secrets() if in_colab() else ohne_budget_modell_aus_umgebung()
    )


def ohne_budget_modell_aus_colab_secrets() -> OhneBudgetModell | None:
    """Aus der Colab-Secrets-Verwaltung; ``None``, wenn das Secret nicht angelegt ist.
    Keine ``.env`` in Colab."""
    try:
        roh = _colab_secret(OHNE_BUDGET_MODELL_VAR)
    except MissingOhneBudgetModellError:
        return None
    return _modell_aus_json(roh)


def ohne_budget_modell_aus_umgebung(*, use_dotenv: bool = True) -> OhneBudgetModell | None:
    """Aus :data:`OHNE_BUDGET_MODELL_VAR`; ``None``, wenn die Variable nicht gesetzt ist.

    Erwartet ein JSON-Objekt mit den optionalen Schluesseln ``ausschluss`` und
    ``schulung`` (je eine Liste von Namensbausteinen) sowie ``historie_monate``.
    Lokal wird eine ``.env`` beruecksichtigt.
    """
    if use_dotenv:
        load_dotenv()
    try:
        roh = _umgebungsvariable(OHNE_BUDGET_MODELL_VAR)
    except MissingOhneBudgetModellError:
        return None
    return _modell_aus_json(roh)


def _modell_aus_json(roh: str) -> OhneBudgetModell:
    try:
        wert = json.loads(roh)
    except json.JSONDecodeError as fehler:
        raise MissingOhneBudgetModellError(
            f"{OHNE_BUDGET_MODELL_VAR} enthaelt kein gueltiges JSON: {fehler}",
        ) from fehler
    if not isinstance(wert, dict):
        raise MissingOhneBudgetModellError(f"{OHNE_BUDGET_MODELL_VAR} muss ein JSON-Objekt sein.")
    historie_monate = wert.get("historie_monate", STANDARD_HISTORIE_MONATE)
    if not isinstance(historie_monate, int) or isinstance(historie_monate, bool):
        raise MissingOhneBudgetModellError("historie_monate muss eine ganze Zahl sein.")
    try:
        return OhneBudgetModell(
            ausschluss=_bausteine(wert, "ausschluss"),
            schulung=_bausteine(wert, "schulung"),
            historie_monate=historie_monate,
        )
    except ValueError as fehler:
        raise MissingOhneBudgetModellError(str(fehler)) from fehler


def _bausteine(wert: dict[str, object], schluessel: str) -> tuple[str, ...]:
    bausteine = wert.get(schluessel, [])
    if not isinstance(bausteine, list) or not all(isinstance(b, str) for b in bausteine):
        raise MissingOhneBudgetModellError(
            f"{schluessel} in {OHNE_BUDGET_MODELL_VAR} muss eine Liste von Texten sein.",
        )
    return tuple(bausteine)
