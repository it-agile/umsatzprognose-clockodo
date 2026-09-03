"""Abbildung der Google-Sheets-Antwort auf :class:`~umsatzprognose.domaene.kosten.Kostenplan`.

Ein Tabellenblatt je Jahr in derselben jaehrlichen Datei wie die Schulungsanmeldungen
(``KOSTEN_SHEET_IDS``, siehe :mod:`umsatzprognose.google_sheets.config`), aber ein
anderer Reiter: ``"Kosten {jahr}"``, fester Zellbereich ``L3:R15`` (Zeile 3 Kopfzeile,
Zeile 4-15 die zwoelf Monate des Jahres). Wie bei den Schulungsanmeldungen bestimmt die
Kopfzeile die Spaltenzuordnung **namentlich**, robust gegenueber der Reihenfolge der
Spalten innerhalb L:R.

``Gesamtkosten`` (die Kostenpauschale), ``Allgemeinkosten`` (deren geschaetzter Anteil
darin) und ``Kostenerfassung`` (die mit Zeitverzug aus den ``AB {Monat}``-Reitern
nachgezogenen tatsaechlichen Allgemeinkosten) stehen, wie ``Umsatz gesamt`` bei den
Schulungsanmeldungen, im deutschen Zahlenformat mit Euro-Zeichen und werden mit
derselben :func:`~umsatzprognose.domaene.zahlen.euro_parsen` geparst.
``Kostenerfassung`` ist keine Pflichtspalte und je Monat oft noch leer - erst
:attr:`~umsatzprognose.domaene.kosten.Kostenposten.kosten` entscheidet, ob und wie sie
den Allgemeinkosten-Anteil der Pauschale ersetzt (siehe dort). ``Allgemeinkosten``
selbst ist Pflichtspalte, weil sie fuer diese Ersetzung gebraucht wird, sobald eine
Erfassung vorliegt.

**Anders als bei den Schulungsanmeldungen gelten die Kosten auch fuer bereits
vergangene Monate** (siehe Moduldocstring von :mod:`umsatzprognose.domaene.kosten`) -
:meth:`KostenRepository.laden` nimmt deshalb zusaetzlich zum Prognosehorizont die
Monate der bereits geladenen Umsatzhistorie entgegen.

**Eine fehlende Quelle ist kein Fehler**, genau wie bei den Schulungsanmeldungen: ein
Jahr ohne konfigurierte Datei oder eine nicht lesbare Datei wird abgefangen und als
:class:`~umsatzprognose.domaene.hinweis.Hinweis` verzeichnet, statt die ganze Prognose
scheitern zu lassen.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import date

    from umsatzprognose.domaene.kosten import Monat

from umsatzprognose.domaene import Hinweis, Kostenplan, Kostenposten
from umsatzprognose.domaene.zahlen import euro_parsen
from umsatzprognose.google_sheets import GoogleSheetsClient, GoogleSheetsConfig

KOSTEN_BEREICH_VORLAGE = "Kosten {jahr}!L3:R15"

SPALTE_MONAT = "Monat"
SPALTE_GESAMTKOSTEN = "Gesamtkosten"
SPALTE_ALLGEMEINKOSTEN = "Allgemeinkosten"
SPALTE_KOSTENERFASSUNG = "Kostenerfassung"

MONATSNAMEN_LANG = (
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
)  # fmt: skip
_MONAT_NUMMER = {name: nummer for nummer, name in enumerate(MONATSNAMEN_LANG, start=1)}


def _monat_parsen(text: str) -> int | None:
    """``"Januar"`` -> ``1``; unbekannter Text -> ``None`` statt Exception."""
    return _MONAT_NUMMER.get(text.strip().capitalize())


def _zeilen_zu_posten(zeilen: list[list[str]], jahr: int) -> list[Kostenposten]:
    if not zeilen:
        return []
    kopf = zeilen[0]
    index = {name.strip(): i for i, name in enumerate(kopf)}
    # workaround für fehlende Monatsspalten-Bezeichnung
    index["Monat"] = 0

    fehlend = {SPALTE_MONAT, SPALTE_GESAMTKOSTEN, SPALTE_ALLGEMEINKOSTEN} - index.keys()
    if fehlend:
        raise ValueError(f"Spalten fehlen im Tabellenblatt: {sorted(fehlend)}")

    def zelle(zeile: list[str], name: str) -> str:
        position = index[name]
        return zeile[position] if position < len(zeile) else ""

    hat_erfassung = SPALTE_KOSTENERFASSUNG in index

    posten = []
    for zeile in zeilen[1:]:
        monat_text = zelle(zeile, SPALTE_MONAT).strip()
        if not monat_text:
            continue
        monat = _monat_parsen(monat_text)
        if monat is None:
            continue
        erfassung_text = zelle(zeile, SPALTE_KOSTENERFASSUNG).strip() if hat_erfassung else ""
        posten.append(
            Kostenposten(
                jahr=jahr,
                monat=monat,
                pauschale=euro_parsen(zelle(zeile, SPALTE_GESAMTKOSTEN)),
                allgemeinkosten=euro_parsen(zelle(zeile, SPALTE_ALLGEMEINKOSTEN)),
                erfasst=euro_parsen(erfassung_text) if erfassung_text else None,
            )
        )
    return posten


def _monatsfolge(stichtag: date, horizont_monate: int) -> list[Monat]:
    """``horizont_monate`` aufeinanderfolgende Monate, beginnend beim Stichtagsmonat."""
    ordnung_start = stichtag.year * 12 + (stichtag.month - 1)
    return [
        ((ordnung_start + i) // 12, (ordnung_start + i) % 12 + 1) for i in range(horizont_monate)
    ]


class KostenRepository:
    """Laedt die Kostenprognose aus den konfigurierten Google-Sheets-Dateien."""

    def __init__(self, client: GoogleSheetsClient, jahre_zu_dateien: Mapping[int, str]) -> None:
        self._client = client
        self._jahre_zu_dateien = dict(jahre_zu_dateien)

    @classmethod
    def mit_automatischen_zugangsdaten(cls) -> KostenRepository:
        """Zugangsdaten und Jahr-Zuordnung aus Colab-Secrets oder ``.env``."""
        config = GoogleSheetsConfig.automatisch()
        return cls(GoogleSheetsClient(config.oauth_client_config), config.jahre_zu_dateien)

    def laden(
        self, *, stichtag: date, horizont_monate: int = 3, historie_monate: Sequence[Monat] = ()
    ) -> Kostenplan:
        """Die Kostenprognose fuer die Historie- und Prognosehorizont-Monate.

        Anders als bei den Schulungsanmeldungen deckt der geladene Kostenplan auch die
        Vergangenheit ab: ``historie_monate`` sind die Monate der bereits geladenen
        Umsatzhistorie, ``stichtag``/``horizont_monate`` bestimmen zusaetzlich die
        vorausschauenden Monate. Reichen die benoetigten Monate ueber einen
        Jahreswechsel, werden die Dateien mehrerer Jahrgaenge gelesen und ihre Posten
        vor der Aggregation zusammengefuehrt. Ein fehlendes oder nicht lesbares Jahr
        wird nicht zum Fehler, siehe Moduldocstring.
        """
        horizont = _monatsfolge(stichtag, horizont_monate)
        monate = list(historie_monate) + [m for m in horizont if m not in historie_monate]
        jahre = sorted({jahr for jahr, _ in monate})

        posten: list[Kostenposten] = []
        hinweise: list[Hinweis] = []
        for jahr in jahre:
            spreadsheet_id = self._jahre_zu_dateien.get(jahr)
            if spreadsheet_id is None:
                hinweise.append(
                    Hinweis(f"Für {jahr} ist in KOSTEN_SHEET_IDS keine Kosten-Datei hinterlegt")
                )
                continue
            try:
                bereich = KOSTEN_BEREICH_VORLAGE.format(jahr=jahr)
                zeilen = self._client.werte(spreadsheet_id, bereich)
                posten.extend(_zeilen_zu_posten(zeilen, jahr))
            except Exception as fehler:
                hinweise.append(
                    Hinweis(
                        f"Die Kosten-Datei für {jahr} konnte nicht gelesen werden "
                        f"({type(fehler).__name__})"
                    )
                )
        return Kostenplan(posten=tuple(posten), abbildungshinweise=tuple(hinweise))
