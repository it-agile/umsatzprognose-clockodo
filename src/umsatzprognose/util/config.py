"""Umgebungserkennung und das Lesen von Zugangsdaten - gemeinsam fuer ``clockodo`` und
``google_sheets``, die beide Umgebungsvariablen und Colab-Secrets nach demselben Muster
lesen, aber mit eigener ``MissingCredentialsError``-Klasse quittieren.
"""

from __future__ import annotations

import importlib.util
import os


def in_colab() -> bool:
    """Ob der Code in Google Colab laeuft."""
    return (
        importlib.util.find_spec("google") is not None
        and importlib.util.find_spec("google.colab") is not None
    )


def umgebungsvariable(name: str, *, fehlerklasse: type[Exception]) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise fehlerklasse(
            f"Umgebungsvariable {name} ist nicht gesetzt. "
            "Siehe .env.sample; lokal in eine .env eintragen, in Colab ueber "
            "die Secrets-Verwaltung bereitstellen."
        )
    return value


def colab_secret(name: str, *, fehlerklasse: type[Exception]) -> str:
    """Ein Colab-Secret lesen und im Fehlerfall sagen, was zu tun ist."""
    from google.colab import userdata

    try:
        value = userdata.get(name)
    except Exception as fehler:
        raise fehlerklasse(
            f"Colab-Secret '{name}' nicht nutzbar ({type(fehler).__name__}).\n"
            "Anlegen: linke Seitenleiste, Schluessel-Symbol -> 'Neues Secret'.\n"
            "Danach den Schalter 'Notebook-Zugriff' fuer dieses Notebook aktivieren - "
            "ohne ihn existiert das Secret, ist aber gesperrt."
        ) from fehler
    if not (value or "").strip():
        raise fehlerklasse(f"Colab-Secret '{name}' ist leer.")
    return value.strip()
