"""Gemeinsamer Google-Sheets-Zugriff fuer alle Bausteine, die aus den jaehrlichen
Google-Sheets-Dateien lesen (aktuell :mod:`umsatzprognose.schulungen` und
:mod:`umsatzprognose.kosten`).

Kennt weder einen bestimmten Baustein noch ein bestimmtes Tabellenblatt - nur
Zugangsdaten (:class:`GoogleSheetsConfig`) und den rohen Lesezugriff
(:class:`GoogleSheetsClient`). Welcher Reiter/Zellbereich gelesen wird und wie die
gelesenen Zeilen auf Fachobjekte abgebildet werden, entscheidet jeder Aufrufer selbst.
"""

from umsatzprognose.google_sheets.client import GoogleSheetsClient, TabellenClient
from umsatzprognose.google_sheets.config import GoogleSheetsConfig, MissingCredentialsError

__all__ = [
    "GoogleSheetsClient",
    "GoogleSheetsConfig",
    "MissingCredentialsError",
    "TabellenClient",
]
