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
    """Eine benoetigte Umgebungsvariable oder ein Colab-Secret fehlt."""


def in_colab() -> bool:
    """Ob der Code in Google Colab laeuft."""
    try:
        import google.colab  # noqa: F401
    except ImportError:
        return False
    return True


@dataclass(frozen=True)
class ClockodoCredentials:
    """Alles, was fuer einen authentifizierten Clockodo-Request noetig ist.

    Gebaut wird ueber die benannten Konstruktoren: :meth:`automatisch` waehlt die
    Quelle selbst, :meth:`aus_umgebung` liest ``.env`` und Umgebungsvariablen,
    :meth:`aus_colab_secrets` die Colab-Secrets-Verwaltung.
    """

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

    @classmethod
    def automatisch(cls) -> ClockodoCredentials:
        """Aus der passenden Quelle: Colab-Secrets in Colab, sonst ``.env``."""
        return cls.aus_colab_secrets() if in_colab() else cls.aus_umgebung()

    @classmethod
    def aus_umgebung(cls, *, use_dotenv: bool = True) -> ClockodoCredentials:
        """Aus Umgebungsvariablen; lokal wird eine ``.env`` beruecksichtigt."""
        if use_dotenv:
            load_dotenv()
        return cls(
            api_user=_umgebungsvariable("CLOCKODO_API_USER"),
            api_key=_umgebungsvariable("CLOCKODO_API_KEY"),
            app_name=_umgebungsvariable("CLOCKODO_APP_NAME"),
            app_email=_umgebungsvariable("CLOCKODO_APP_EMAIL"),
        )

    @classmethod
    def aus_colab_secrets(cls) -> ClockodoCredentials:
        """Aus der Colab-Secrets-Verwaltung. Keine ``.env`` in Colab."""
        return cls(
            api_user=_colab_secret("CLOCKODO_API_USER"),
            api_key=_colab_secret("CLOCKODO_API_KEY"),
            app_name=_colab_secret("CLOCKODO_APP_NAME"),
            app_email=_colab_secret("CLOCKODO_APP_EMAIL"),
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
            "ohne ihn existiert das Secret, ist aber gesperrt.\n"
            "Details im README, Abschnitt 'Deployment (Google Colab)'."
        ) from fehler
    if not (value or "").strip():
        raise MissingCredentialsError(f"Colab-Secret '{name}' ist leer.")
    return value.strip()
