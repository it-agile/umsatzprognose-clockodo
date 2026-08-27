"""HTTP-Zugriff auf die Google Sheets API fuer die Schulungs-Tabellenblaetter.

Ein Google-Sheet je Jahr, Tabellenblatt ``Öffentliche Schulungen`` (Spec Abschnitt 5.3).
**Kein Service-Account** - fuer diese Anlage gibt Google nur eine OAuth-Client-ID aus,
kein Service-Account-Key. Die Anmeldung laeuft deshalb je Umgebung unterschiedlich:

- **In Colab** authentifiziert sich die aufrufende Person ueber ihr eigenes Google-Konto
  (``google.colab.auth.authenticate_user``) - kein Client-JSON noetig, keine
  Token-Datei. Sie braucht selbst Lesezugriff auf die Trainings-Sheets.
- **Lokal** startet ein einmaliger interaktiver Login im Browser
  (``google_auth_oauthlib.flow.InstalledAppFlow``), auf Basis des Client-JSON aus
  :class:`~umsatzprognose.schulungen.config.SchulungenConfig`. Das Ergebnis (Refresh-Token)
  wird in :data:`TOKEN_PFAD` zwischengespeichert und danach automatisch erneuert -
  die Datei ist in ``.gitignore`` aufgenommen.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from google.auth.credentials import Credentials as CredentialsBase

from googleapiclient.discovery import build

from .config import OAUTH_CLIENT_VAR, MissingCredentialsError, in_colab

SCOPES = ("https://www.googleapis.com/auth/spreadsheets.readonly",)
TABELLENBLATT = "Öffentliche Schulungen"
TOKEN_PFAD = Path(".google_oauth_token.json")


class SchulungenSheetsClient:
    """Lesender Zugriff auf ein Tabellenblatt je Aufruf."""

    def __init__(self, oauth_client_config: dict | None = None) -> None:
        credentials = (
            _colab_credentials() if in_colab() else _lokale_credentials(oauth_client_config)
        )
        self._service = build("sheets", "v4", credentials=credentials, cache_discovery=False)

    def werte(self, spreadsheet_id: str, bereich: str = TABELLENBLATT) -> list[list[str]]:
        """Alle Zellwerte des Tabellenblatts, zeilenweise, roh als Strings.

        Die erste Zeile ist die Kopfzeile - die Zuordnung auf Spaltennamen macht
        :mod:`umsatzprognose.schulungen.schulungen`, nicht dieser Client.
        """
        antwort = (
            self._service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=bereich)
            .execute()
        )
        return antwort.get("values", [])


def _colab_credentials() -> CredentialsBase:
    """Anmeldung als die aufrufende Person selbst - kein Client-JSON, keine Token-Datei."""
    import google.auth
    from google.colab import auth  # type: ignore[import-not-found]

    auth.authenticate_user()
    credentials, _ = google.auth.default(scopes=SCOPES)
    return credentials


def _lokale_credentials(oauth_client_config: dict | None) -> CredentialsBase:
    """Ein zwischengespeicherter Token, sonst ein einmaliger Login im Browser."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    if oauth_client_config is None:
        raise MissingCredentialsError(
            f"Fuer den lokalen Login fehlt das OAuth-Client-JSON aus {OAUTH_CLIENT_VAR}."
        )

    credentials = None
    if TOKEN_PFAD.exists():
        credentials = Credentials.from_authorized_user_file(str(TOKEN_PFAD), SCOPES)

    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_config(oauth_client_config, SCOPES)
            credentials = flow.run_local_server(port=0)
        TOKEN_PFAD.write_text(credentials.to_json())

    return credentials
