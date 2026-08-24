"""Zugangsdaten und Basiskonfiguration fuer die Clockodo-API.

Die drei Header und die Basis-URL sind der offiziellen Clockodo-Doku entnommen
(https://www.clockodo.com/en/api/): Authentifizierung ueber ``X-ClockodoApiUser``
(E-Mail) und ``X-ClockodoApiKey``, dazu zwingend ``X-Clockodo-External-Application``
im Format ``name;email`` mit maximal 50 Zeichen Gesamtlaenge.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

BASE_URL = "https://my.clockodo.com/api"

# Clockodo-Vorgabe: name + ";" + email zusammen maximal 50 Zeichen.
EXTERNAL_APPLICATION_MAX_LENGTH = 50


class MissingCredentialsError(RuntimeError):
    """Eine benoetigte Umgebungsvariable ist nicht gesetzt."""


@dataclass(frozen=True)
class ClockodoCredentials:
    """Alles, was fuer einen authentifizierten Clockodo-Request noetig ist."""

    api_user: str
    api_key: str
    app_name: str
    app_email: str

    def __post_init__(self) -> None:
        length = len(self.external_application)
        if length > EXTERNAL_APPLICATION_MAX_LENGTH:
            raise ValueError(
                f"X-Clockodo-External-Application ist {length} Zeichen lang, "
                f"erlaubt sind {EXTERNAL_APPLICATION_MAX_LENGTH}: "
                f"{self.external_application!r}"
            )

    @property
    def external_application(self) -> str:
        return f"{self.app_name};{self.app_email}"

    def headers(self) -> dict[str, str]:
        return {
            "X-ClockodoApiUser": self.api_user,
            "X-ClockodoApiKey": self.api_key,
            "X-Clockodo-External-Application": self.external_application,
        }


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise MissingCredentialsError(
            f"Umgebungsvariable {name} ist nicht gesetzt. "
            "Siehe .env.sample; lokal in eine .env eintragen, in Colab ueber "
            "die Secrets-Verwaltung bereitstellen."
        )
    return value


def load_credentials(*, use_dotenv: bool = True) -> ClockodoCredentials:
    """Liest die Zugangsdaten aus der Umgebung.

    Lokal wird eine ``.env`` im Projektwurzelverzeichnis beruecksichtigt. In Colab
    ``use_dotenv=False`` setzen und die Werte vorher via ``os.environ`` aus den
    Colab-Secrets uebernehmen.
    """
    if use_dotenv:
        load_dotenv()
    return ClockodoCredentials(
        api_user=_require("CLOCKODO_API_USER"),
        api_key=_require("CLOCKODO_API_KEY"),
        app_name=_require("CLOCKODO_APP_NAME"),
        app_email=_require("CLOCKODO_APP_EMAIL"),
    )


def in_colab() -> bool:
    """Ob der Code in Google Colab laeuft."""
    try:
        import google.colab  # noqa: F401
    except ImportError:
        return False
    return True


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
            "ohne ihn existiert das Secret, ist aber gesperrt.\n"
            "Details im README, Abschnitt 'Deployment (Google Colab)'."
        ) from fehler
    if not (value or "").strip():
        raise MissingCredentialsError(f"Colab-Secret '{name}' ist leer.")
    return value.strip()


def load_credentials_colab() -> ClockodoCredentials:
    """Zugangsdaten aus der Colab-Secrets-Verwaltung. Keine ``.env`` in Colab."""
    return ClockodoCredentials(
        api_user=_colab_secret("CLOCKODO_API_USER"),
        api_key=_colab_secret("CLOCKODO_API_KEY"),
        app_name=_colab_secret("CLOCKODO_APP_NAME"),
        app_email=_colab_secret("CLOCKODO_APP_EMAIL"),
    )


def load_credentials_auto() -> ClockodoCredentials:
    """Zugangsdaten aus der passenden Quelle: Colab-Secrets in Colab, sonst ``.env``."""
    return load_credentials_colab() if in_colab() else load_credentials(use_dotenv=True)
