"""Abbildung der Google-Sheets-Antwort auf :class:`~umsatzprognose.domaene.schulung.Schulungsplan`.

Die Kopfzeile des Tabellenblatts bestimmt die Spaltenzuordnung **namentlich**, nicht
ueber die Position - robust gegenueber den vielen fuer die Prognose ungenutzten Spalten
(Rabattstufen, Trainer, Praesenz/Online, ...; siehe Spec Abschnitt 4).

``Umsatz gesamt`` steht im deutschen Zahlenformat mit Euro-Zeichen, uneinheitlich
formatiert (``"12.345,67 €"``, ``"1.234,56€"``, mit/ohne Leerzeichen). Geparst wird mit
:func:`~umsatzprognose.domaene.zahlen.euro_parsen`, robust: alles außer Ziffern, Punkt
und Komma entfernen, den Tausenderpunkt entfernen, das Komma zum Dezimalpunkt machen.

**Eine fehlende Quelle ist laut Spec Abschnitt 6 kein Fehler**: ein Jahr ohne
konfigurierte Datei oder eine nicht lesbare Datei wird abgefangen und als
:class:`~umsatzprognose.domaene.hinweis.Hinweis` verzeichnet, statt die ganze Prognose
scheitern zu lassen. Das unterscheidet dieses Repository bewusst vom Fail-fast in
:mod:`umsatzprognose.clockodo` (dort meldet ``ClockodoError`` unaufgefangen).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

from datetime import date

from umsatzprognose.domaene import Hinweis, Schulungsplan, Schulungstermin
from umsatzprognose.domaene.zahlen import euro_parsen
from umsatzprognose.google_sheets import GoogleSheetsClient, GoogleSheetsConfig, TabellenClient

TABELLENBLATT = "Öffentliche Schulungen"

SPALTE_JAHR = "Jahr"
SPALTE_MONAT = "Monat"
SPALTE_UMSATZ = "Umsatz gesamt"


def _zeilen_zu_terminen(zeilen: list[list[str]]) -> list[Schulungstermin]:
    if not zeilen:
        return []
    kopf = zeilen[0]
    index = {name.strip(): i for i, name in enumerate(kopf)}
    fehlend = {SPALTE_JAHR, SPALTE_MONAT, SPALTE_UMSATZ} - index.keys()
    if fehlend:
        raise ValueError(f"Spalten fehlen im Tabellenblatt: {sorted(fehlend)}")

    def zelle(zeile: list[str], name: str) -> str:
        position = index[name]
        return zeile[position] if position < len(zeile) else ""

    termine = []
    for zeile in zeilen[1:]:
        jahr_text = zelle(zeile, SPALTE_JAHR).strip()
        monat_text = zelle(zeile, SPALTE_MONAT).strip()
        if not jahr_text or not monat_text:
            continue
        termine.append(
            Schulungstermin(
                jahr=int(jahr_text),
                monat=int(monat_text),
                umsatz=euro_parsen(zelle(zeile, SPALTE_UMSATZ)),
            )
        )
    return termine


def _benoetigte_jahre(stichtag: date, horizont_monate: int) -> tuple[int, ...]:
    """Stichtagsjahr, und - falls der Horizont die Jahresgrenze ueberschreitet - das Folgejahr."""
    ordnung_ende = stichtag.year * 12 + (stichtag.month - 1) + (horizont_monate - 1)
    return tuple(sorted({stichtag.year, ordnung_ende // 12}))


class SchulungenRepository:
    """Laedt die Schulungstermine aus den konfigurierten Google-Sheets-Dateien."""

    def __init__(self, client: TabellenClient, jahre_zu_dateien: Mapping[int, str]) -> None:
        self._client = client
        self._jahre_zu_dateien = dict(jahre_zu_dateien)

    @classmethod
    def mit_automatischen_zugangsdaten(cls) -> SchulungenRepository:
        """Zugangsdaten und Jahr-Zuordnung aus Colab-Secrets oder ``.env``."""
        config = GoogleSheetsConfig.automatisch()
        return cls(GoogleSheetsClient(config.oauth_client_config), config.jahre_zu_dateien)

    def laden(self, *, stichtag: date | None, horizont_monate: int = 3) -> Schulungsplan:
        """Der Schulungsplan zum Stichtag, ueber alle vom Horizont beruehrten Jahre.

        Reicht der Horizont ueber einen Jahreswechsel, werden die Dateien mehrerer
        Jahrgaenge gelesen und ihre Termine vor der Aggregation zusammengefuehrt
        (Spec 5.3). Ein fehlendes oder nicht lesbares Jahr wird nicht zum Fehler, siehe
        Moduldocstring.
        """
        stichtag = stichtag or date.today()

        termine: list[Schulungstermin] = []
        hinweise: list[Hinweis] = []
        for jahr in _benoetigte_jahre(stichtag, horizont_monate):
            spreadsheet_id = self._jahre_zu_dateien.get(jahr)
            if spreadsheet_id is None:
                hinweise.append(
                    Hinweis(f"Für {jahr} ist in KOSTEN_SHEET_IDS keine Schulungs-Datei hinterlegt")
                )
                continue
            try:
                zeilen = self._client.werte(spreadsheet_id, TABELLENBLATT)
                termine.extend(_zeilen_zu_terminen(zeilen))
            except Exception as fehler:
                hinweise.append(
                    Hinweis(
                        f"Die Schulungs-Datei für {jahr} konnte nicht gelesen werden "
                        f"({type(fehler).__name__})"
                    )
                )
        return Schulungsplan(
            stichtag=stichtag, termine=tuple(termine), abbildungshinweise=tuple(hinweise)
        )
