"""Konfiguration fuer den Zugriff auf Google-Sheets-Dateien: Zugangsdaten je Umgebung
und die Zuordnung Jahr -> Spreadsheet-ID.

Gemeinsame Infrastruktur fuer alle Bausteine, die aus denselben jaehrlichen
Google-Sheets-Dateien lesen (aktuell :mod:`umsatzprognose.schulungen` und
:mod:`umsatzprognose.kosten` - unterschiedliche Tabellenblaetter derselben Datei je
Jahr). Analog zu :mod:`umsatzprognose.clockodo.config`: benannte Konstruktoren
``automatisch``/``aus_umgebung``/``aus_colab_secrets`` waehlen bzw. lesen die Quelle.
Bewusst keine Abhaengigkeit zu ``clockodo`` - siehe Moduldocstring von
:mod:`umsatzprognose.schulungen`.

**Kein Service-Account, sondern ein OAuth-Consent-Flow** - Google gibt fuer diese
Anlage keine Service-Account-Keys aus, sondern eine OAuth-Client-ID
(``installed``/``web``-JSON aus der Google-Cloud-Konsole, Anwendungstyp
"Desktopanwendung"). Die eigentliche Anmeldung passiert deshalb erst in
:mod:`umsatzprognose.google_sheets.client` - unterschiedlich je Umgebung:

- **In Colab** meldet sich die aufrufende Person ueber ihr eigenes Google-Konto an
  (``google.colab.auth.authenticate_user``), kein Client-JSON noetig. Sie braucht dafuer
  selbst Lesezugriff auf die betreffenden Sheets.
- **Lokal** braucht es das OAuth-Client-JSON aus ``GOOGLE_OAUTH_CLIENT_JSON``, um einen
  einmaligen interaktiven Login im Browser zu starten; das Ergebnis wird lokal
  zwischengespeichert (siehe ``client.py``).

Eine zweite Umgebungsvariable/ein Colab-Secret in beiden Umgebungen:

``TRAINING_SHEET_ID``
    Ein JSON-Objekt Jahr -> Spreadsheet-ID, z. B. ``{"2026": "…", "2027": "…"}`` - eine
    Datei je Jahr. Der Name ist historisch (die erste Nutzung war die
    Schulungsanmeldungen-Tabelle) und bleibt bewusst unveraendert, weil dieselbe Datei
    inzwischen auch fuer die Kostenprognose verwendet wird - ein anderer Name waere nur
    Migrationsaufwand ohne fachlichen Nutzen.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from dotenv import load_dotenv

from umsatzprognose.util import in_colab

OAUTH_CLIENT_VAR = "GOOGLE_OAUTH_CLIENT_JSON"
SHEET_ID_VAR = "TRAINING_SHEET_ID"


class MissingCredentialsError(RuntimeError):
    """Eine benoetigte Umgebungsvariable oder ein Colab-Secret fehlt oder ist ungueltig."""


@dataclass(frozen=True)
class GoogleSheetsConfig:
    """Alles, was fuer den Zugriff auf die Google-Sheets-Dateien noetig ist.

    Attributes:
        jahre_zu_dateien: Jahr -> Spreadsheet-ID, in beiden Umgebungen gebraucht.
        oauth_client_config: das OAuth-Client-JSON, nur lokal gebraucht - in Colab
            bleibt es ``None``, weil dort ``google.colab.auth`` die Anmeldung uebernimmt.
    """

    jahre_zu_dateien: dict[int, str]
    oauth_client_config: dict | None = None

    @classmethod
    def automatisch(cls) -> GoogleSheetsConfig:
        """Aus der passenden Quelle: Colab-Secrets in Colab, sonst ``.env``."""
        return cls.aus_colab_secrets() if in_colab() else cls.aus_umgebung()

    @classmethod
    def aus_umgebung(cls, *, use_dotenv: bool = True) -> GoogleSheetsConfig:
        """Aus Umgebungsvariablen; lokal wird eine ``.env`` beruecksichtigt."""
        if use_dotenv:
            load_dotenv()
        return cls(
            jahre_zu_dateien=_jahre_zu_dateien(_umgebungsvariable(SHEET_ID_VAR)),
            oauth_client_config=_oauth_client_json(_umgebungsvariable(OAUTH_CLIENT_VAR)),
        )

    @classmethod
    def aus_colab_secrets(cls) -> GoogleSheetsConfig:
        """Aus der Colab-Secrets-Verwaltung. Kein Client-JSON - siehe Klassendocstring."""
        return cls(jahre_zu_dateien=_jahre_zu_dateien(_colab_secret(SHEET_ID_VAR)))


def _oauth_client_json(roh: str) -> dict:
    try:
        wert = json.loads(roh)
    except json.JSONDecodeError as fehler:
        raise MissingCredentialsError(
            f"{OAUTH_CLIENT_VAR} enthaelt kein gueltiges JSON: {fehler}"
        ) from fehler
    if not isinstance(wert, dict) or not ({"installed", "web"} & wert.keys()):
        raise MissingCredentialsError(
            f"{OAUTH_CLIENT_VAR} sieht nicht nach einer OAuth-Client-ID aus - erwartet wird "
            "das JSON aus der Google-Cloud-Konsole mit einem aeusseren Schluessel "
            "'installed' oder 'web' (Anwendungstyp \"Desktopanwendung\"), kein "
            "Service-Account-Key."
        )
    return wert


def _jahre_zu_dateien(roh: str) -> dict[int, str]:
    try:
        wert = json.loads(roh)
    except json.JSONDecodeError as fehler:
        raise MissingCredentialsError(
            f"{SHEET_ID_VAR} enthaelt kein gueltiges JSON: {fehler}"
        ) from fehler
    if not isinstance(wert, dict):
        raise MissingCredentialsError(f"{SHEET_ID_VAR} muss ein JSON-Objekt Jahr -> ID sein.")
    try:
        return {int(jahr): str(spreadsheet_id) for jahr, spreadsheet_id in wert.items()}
    except (TypeError, ValueError) as fehler:
        raise MissingCredentialsError(
            f"{SHEET_ID_VAR} hat keine Jahreszahlen als Schluessel."
        ) from fehler


def _umgebungsvariable(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise MissingCredentialsError(
            f"Umgebungsvariable {name} ist nicht gesetzt. "
            "Siehe .env.sample; lokal in eine .env eintragen, in Colab ueber "
            "die Secrets-Verwaltung bereitstellen."
        )
    return value


def _colab_secret(name: str) -> str:
    """Ein Colab-Secret lesen und im Fehlerfall sagen, was zu tun ist."""
    from google.colab import userdata  # type: ignore[import-not-found]

    try:
        value = userdata.get(name)
    except Exception as fehler:
        raise MissingCredentialsError(
            f"Colab-Secret '{name}' nicht nutzbar ({type(fehler).__name__}).\n"
            "Anlegen: linke Seitenleiste, Schluessel-Symbol -> 'Neues Secret'.\n"
            "Danach den Schalter 'Notebook-Zugriff' fuer dieses Notebook aktivieren - "
            "ohne ihn existiert das Secret, ist aber gesperrt."
        ) from fehler
    if not (value or "").strip():
        raise MissingCredentialsError(f"Colab-Secret '{name}' ist leer.")
    return value.strip()
