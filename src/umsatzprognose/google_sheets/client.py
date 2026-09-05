"""HTTP-Zugriff auf die Google Sheets API - gemeinsame Infrastruktur fuer alle
Bausteine, die aus denselben jaehrlichen Google-Sheets-Dateien lesen (siehe
Moduldocstring von :mod:`umsatzprognose.google_sheets.config`).

**Kein Service-Account** - fuer diese Anlage gibt Google nur eine OAuth-Client-ID aus,
kein Service-Account-Key. Die Anmeldung laeuft deshalb je Umgebung unterschiedlich:

- **In Colab** authentifiziert sich die aufrufende Person ueber ihr eigenes Google-Konto
  (``google.colab.auth.authenticate_user``) - kein Client-JSON noetig, keine
  Token-Datei. Sie braucht selbst Lesezugriff auf die betreffenden Sheets.
- **Lokal** startet ein einmaliger interaktiver Login im Browser
  (``google_auth_oauthlib.flow.InstalledAppFlow``), auf Basis des Client-JSON aus
  :class:`~umsatzprognose.google_sheets.config.GoogleSheetsConfig`. Das Ergebnis
  (Refresh-Token) wird in :data:`TOKEN_PFAD` zwischengespeichert und danach automatisch
  erneuert - die Datei ist in ``.gitignore`` aufgenommen.

Dieses Modul kennt keinen bestimmten Baustein und damit auch kein bestimmtes
Tabellenblatt - welcher Reiter bzw. Zellbereich gelesen wird, entscheidet jeder
Aufrufer (:mod:`umsatzprognose.schulungen`, :mod:`umsatzprognose.kosten`, ...) selbst.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

    from google.auth.credentials import Credentials as CredentialsBase

from googleapiclient.discovery import build

from umsatzprognose.util import in_colab

from .config import OAUTH_CLIENT_VAR, MissingCredentialsError

SCOPES = ("https://www.googleapis.com/auth/spreadsheets.readonly",)
TOKEN_PFAD = Path(".google_oauth_token.json")


class TabellenClient(Protocol):
    """Das Interface, das ``schulungen/`` und ``kosten/`` vom Sheets-Zugriff brauchen.

    Macht ``SchulungenRepository`` und ``KostenRepository`` unabhaengig von der
    konkreten Implementierung :class:`GoogleSheetsClient` - Tests koennen einen
    einfachen Fake ohne echte Google-Anbindung einsetzen.
    """

    def werte(self, spreadsheet_id: str, bereich: str) -> list[list[str]]: ...


def kopfzeile_finden(
    zeilen: list[list[str]], pflichtspalten: set[str]
) -> tuple[int, dict[str, int]]:
    """Findet die erste Zeile, die alle ``pflichtspalten`` traegt, samt Spaltenposition.

    Gemeinsame Logik von ``schulungen/`` und ``kosten/``: in beiden Tabellenblaettern
    steht die Kopfzeile nicht zuverlaessig in Zeile 0 - manchen Jahrgaengen geht die
    eigentliche Tabelle im selben Zeilenbereich noch etwas anderes voraus, das nicht
    alle Pflichtspalten traegt (z. B. eine Mitarbeiteraufstellung mit aehnlicher, aber
    nicht identischer Kopfzeile). Deshalb wird nicht ``zeilen[0]`` angenommen, sondern
    inhaltsbasiert gesucht. Bei einem doppelten Spaltennamen gewinnt die zuletzt (am
    weitesten rechts) stehende Spalte.

    Raises:
        ValueError: keine Zeile enthaelt alle ``pflichtspalten``.
    """
    for i, zeile in enumerate(zeilen):
        index = {name.strip(): j for j, name in enumerate(zeile) if name.strip()}
        if pflichtspalten <= index.keys():
            return i, index
    raise ValueError(f"Spalten fehlen im Tabellenblatt: {sorted(pflichtspalten)}")


def zelle_an(zeile: list[str], spalte: int) -> str:
    """Der Zellwert an ``spalte``, oder ``""`` wenn die Zeile dort schon endet."""
    return zeile[spalte] if spalte < len(zeile) else ""


def zelle(zeile: list[str], index: Mapping[str, int], name: str) -> str:
    """Der Zellwert der Spalte ``name``, ueber ``index`` aus :func:`kopfzeile_finden`."""
    return zelle_an(zeile, index[name])


def jahre_laden[T](
    client: TabellenClient,
    jahre_zu_dateien: Mapping[int, str],
    jahre: Iterable[int],
    *,
    bereich: Callable[[int], str],
    abbilden: Callable[[list[list[str]], int], list[T]],
    fehlt_meldung: str,
    fehler_meldung: str,
) -> tuple[list[T], list[str]]:
    """Je Jahr eine Datei lesen und abbilden - gemeinsamer Ablauf von ``schulungen/`` und
    ``kosten/``, die beide dieselbe jaehrliche Google-Sheets-Datei ueber
    ``KOSTEN_SHEET_IDS`` referenzieren.

    Ein fehlendes oder nicht lesbares Jahr ist bei beiden kein Fehler, sondern eine
    Meldung (Text statt :class:`~umsatzprognose.domaene.hinweis.Hinweis`, damit dieses
    Modul unabhaengig von ``domaene`` bleibt - der Aufrufer macht daraus einen
    ``Hinweis``). ``fehlt_meldung``/``fehler_meldung`` sind Format-Vorlagen mit den
    Platzhaltern ``{jahr}`` bzw. zusaetzlich ``{detail}``.
    """
    objekte: list[T] = []
    meldungen: list[str] = []
    for jahr in jahre:
        spreadsheet_id = jahre_zu_dateien.get(jahr)
        if spreadsheet_id is None:
            meldungen.append(fehlt_meldung.format(jahr=jahr))
            continue
        try:
            zeilen = client.werte(spreadsheet_id, bereich(jahr))
            objekte.extend(abbilden(zeilen, jahr))
        except Exception as fehler:
            meldungen.append(fehler_meldung.format(jahr=jahr, detail=_fehlerdetail(fehler)))
    return objekte, meldungen


def _fehlerdetail(fehler: Exception) -> str:
    """Exceptiontyp, plus Meldung sofern vorhanden - fuer Meldungen bei Ladefehlern.

    Nur der Typname allein (etwa ``ValueError``) sagt beim Diagnostizieren nichts
    darueber, *warum* eine Datei nicht gelesen werden konnte. Die Meldung beschreibt nur
    Struktur (Spaltennamen, Fehlerart), keine gelesenen Werte.
    """
    text = str(fehler)
    return f"{type(fehler).__name__}: {text}" if text else type(fehler).__name__


class GoogleSheetsClient:
    """Lesender Zugriff auf einen Zellbereich je Aufruf."""

    def __init__(self, oauth_client_config: dict | None = None) -> None:
        credentials = (
            _colab_credentials() if in_colab() else _lokale_credentials(oauth_client_config)
        )
        self._service = build("sheets", "v4", credentials=credentials, cache_discovery=False)

    def werte(self, spreadsheet_id: str, bereich: str) -> list[list[str]]:
        """Alle Zellwerte des angegebenen Bereichs, zeilenweise, roh als Strings.

        ``bereich`` ist ein A1-Bereich, meist ein Tabellenblattname (z. B.
        ``"Öffentliche Schulungen"``) oder ein Tabellenblattname mit Zellbereich (z. B.
        ``"Kosten 2026!3:15"`` fuer einen Zeilenbereich ohne Spaltenbegrenzung, oder
        ``"Kosten 2026!L3:R15"`` mit fester Spaltenbegrenzung). Ob die erste Zeile eine
        Kopfzeile ist und wie die
        Zuordnung auf Spaltennamen erfolgt, entscheidet der Aufrufer, nicht dieser
        Client.
        """
        antwort = (
            self._service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=bereich)
            .execute()
        )
        return antwort.get("values", [])


def _colab_credentials() -> CredentialsBase:
    """Anmeldung als die aufrufende Person selbst - kein Client-JSON, keine Token-Datei.

    ``USE_AUTH_EPHEM=0`` erzwingt Colabs aelteren, auf ``gcloud auth login`` basierenden
    Login-Fluss statt des neueren ephemeren Consent-Dialogs, der bei manchen Konten
    (insbesondere Google-Workspace) mit ``MessageError: credential propagation was
    unsuccessful`` fehlschlaegt (https://github.com/googlecolab/colabtools/issues/4343,
    Stand 2026 weiterhin offen).
    """
    import os

    import google.auth
    from google.colab import auth

    os.environ["USE_AUTH_EPHEM"] = "0"
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
