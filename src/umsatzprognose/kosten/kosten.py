"""Abbildung der Google-Sheets-Antwort auf :class:`~umsatzprognose.domaene.kosten.Kostenplan`.

Ein Tabellenblatt je Jahr in derselben jaehrlichen Datei wie die Schulungsanmeldungen
(``KOSTEN_SHEET_IDS``, siehe :mod:`umsatzprognose.google_sheets.config`), aber ein
anderer Reiter: ``"Kosten {jahr}"``. Gelesen wird pauschal Zeile 1-20 (**ohne festen
Zeilen- oder Spaltenbereich**): weder Kopfzeilen-Zeile noch Spaltenlage stimmen
zwischen den Jahrgaengen verlaesslich ueberein (verifiziert am Jahrgang 2022, wo der
eigentlichen Monatsuebersicht im selben Zeilenbereich noch eine andere Tabelle
vorausgeht, z. B. eine Mitarbeiteraufstellung mit eigener, aehnlicher aber nicht
identischer Kopfzeile). Kopfzeile und Spaltenzuordnung werden deshalb **inhaltsbasiert**
ermittelt: :func:`_kopfzeile_finden` sucht die erste Zeile, die sowohl ``Gesamtkosten``
als auch ``Allgemeinkosten`` traegt, und bestimmt darueber gleichzeitig die
Spaltenposition jeder Kopfzeilen-Bezeichnung.

``Monat`` traegt nicht in jedem Jahrgang eine eigene Kopfzeilen-Bezeichnung. Ohne eine
Spalte namens ``Monat`` faellt :func:`_monat_spalte_ermitteln` deshalb auf die Spalte
zurueck, deren Zellen sich ueberwiegend als deutscher Monatsname parsen lassen (siehe
:func:`_monat_parsen`) - inhaltsbasiert statt positionsbasiert, aus demselben Grund wie
bei der Kopfzeile selbst.

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

    from umsatzprognose.util import Monat

from umsatzprognose.domaene import Erfasst, Geschaetzt, Hinweis, Kostenplan, Kostenposten
from umsatzprognose.domaene.zahlen import euro_parsen
from umsatzprognose.google_sheets import (
    GoogleSheetsClient,
    GoogleSheetsConfig,
    TabellenClient,
    jahre_laden,
)
from umsatzprognose.util import monatsfolge

KOSTEN_BEREICH_VORLAGE = "Kosten {jahr}!1:20"

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


def _monat_spalte_ermitteln(zeilen: list[list[str]], index: dict[str, int]) -> int:
    """Ermittelt die Spalte mit den Monatsnamen - per Kopfzeile oder sonst per Inhalt.

    Traegt die Kopfzeile eine Spalte namens ``Monat``, gilt deren Position. Manche
    Jahrgaenge haben dort aber gar keine Bezeichnung; als Rueckfall zaehlt dann je
    Spalte, wie viele ihrer Zellen sich als deutscher Monatsname parsen lassen (siehe
    :func:`_monat_parsen`), und es gewinnt die Spalte mit den meisten Treffern -
    inhaltsbasiert, weil auch die Position zwischen Jahrgaengen nicht verlaesslich
    gleich ist (siehe Moduldocstring).

    Raises:
        ValueError: keine Spalte enthaelt auch nur einen erkennbaren Monatsnamen.
    """
    if SPALTE_MONAT in index:
        return index[SPALTE_MONAT]

    datenzeilen = zeilen[1:]
    anzahl_spalten = max((len(zeile) for zeile in datenzeilen), default=0)
    treffer_je_spalte = [
        sum(1 for zeile in datenzeilen if spalte < len(zeile) and _monat_parsen(zeile[spalte]))
        for spalte in range(anzahl_spalten)
    ]
    beste_spalte = max(range(anzahl_spalten), default=None, key=treffer_je_spalte.__getitem__)
    if beste_spalte is None or treffer_je_spalte[beste_spalte] == 0:
        raise ValueError("Keine Spalte mit erkennbaren Monatsnamen gefunden")
    return beste_spalte


def _kopfzeile_finden(zeilen: list[list[str]]) -> tuple[int, dict[str, int]]:
    """Findet die Zeile mit den Pflichtspalten ``Gesamtkosten`` und ``Allgemeinkosten``.

    Manchen Jahrgaengen (etwa 2022) geht der Monatsuebersicht im selben Zeilenbereich
    eine andere Tabelle voraus (z. B. eine Mitarbeiteraufstellung) - deren Kopfzeile
    traegt teils aehnliche, aber nicht beide Pflichtspalten. Deshalb wird nicht die
    erste Zeile als Kopfzeile angenommen, sondern inhaltsbasiert die erste Zeile
    gesucht, die beide Pflichtspalten enthaelt - robust gegenueber zusaetzlichen Zeilen
    davor, analog zu :func:`_monat_spalte_ermitteln` fuer die Monatsspalte.

    Raises:
        ValueError: keine Zeile enthaelt beide Pflichtspalten.
    """
    pflicht = {SPALTE_GESAMTKOSTEN, SPALTE_ALLGEMEINKOSTEN}
    for i, zeile in enumerate(zeilen):
        index = {name.strip(): j for j, name in enumerate(zeile) if name.strip()}
        if pflicht <= index.keys():
            return i, index
    raise ValueError(f"Spalten fehlen im Tabellenblatt: {sorted(pflicht)}")


def _zeilen_zu_posten(zeilen: list[list[str]], jahr: int) -> list[Kostenposten]:
    if not zeilen:
        return []
    kopf_zeile, index = _kopfzeile_finden(zeilen)
    monat_spalte = _monat_spalte_ermitteln(zeilen[kopf_zeile:], index)

    def zelle_an(zeile: list[str], spalte: int) -> str:
        return zeile[spalte] if spalte < len(zeile) else ""

    def zelle(zeile: list[str], name: str) -> str:
        return zelle_an(zeile, index[name])

    hat_erfassung = SPALTE_KOSTENERFASSUNG in index

    posten = []
    for zeile in zeilen[kopf_zeile + 1 :]:
        monat_text = zelle_an(zeile, monat_spalte).strip()
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
                erfassung=Erfasst(euro_parsen(erfassung_text)) if erfassung_text else Geschaetzt(),
            )
        )
    return posten


def _monatsfolge(stichtag: date, horizont_monate: int) -> list[Monat]:
    """``horizont_monate`` aufeinanderfolgende Monate, beginnend beim Stichtagsmonat."""
    return monatsfolge((stichtag.year, stichtag.month), horizont_monate)


class KostenRepository:
    """Laedt die Kostenprognose aus den konfigurierten Google-Sheets-Dateien."""

    def __init__(self, client: TabellenClient, jahre_zu_dateien: Mapping[int, str]) -> None:
        self._client = client
        self._jahre_zu_dateien = dict(jahre_zu_dateien)

    @classmethod
    def mit_automatischen_zugangsdaten(cls) -> KostenRepository:
        """Zugangsdaten und Jahr-Zuordnung aus Colab-Secrets oder ``.env``."""
        config = GoogleSheetsConfig.automatisch()
        return cls(GoogleSheetsClient(config.oauth_client_config), config.jahre_zu_dateien)

    @property
    def fruehestes_konfiguriertes_jahr(self) -> int | None:
        """Das aelteste Jahr mit hinterlegter Kosten-Datei, ``None`` ohne jede Konfiguration.

        Grundlage fuer :func:`~umsatzprognose.darstellung.dashboard.Dashboard.laden`, um
        die Umsatzhistorie so weit zurueck zu laden, wie auch eine Kostenprognose dafuer
        vorliegt - eine Gewinn/Verlust-Ansicht ohne Kosten waere ohnehin nur Umsatz.
        """
        return min(self._jahre_zu_dateien) if self._jahre_zu_dateien else None

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

        posten, meldungen = jahre_laden(
            self._client,
            self._jahre_zu_dateien,
            jahre,
            bereich=lambda jahr: KOSTEN_BEREICH_VORLAGE.format(jahr=jahr),
            abbilden=_zeilen_zu_posten,
            fehlt_meldung="Für {jahr} ist in KOSTEN_SHEET_IDS keine Kosten-Datei hinterlegt",
            fehler_meldung="Die Kosten-Datei für {jahr} konnte nicht gelesen werden ({detail})",
        )
        return Kostenplan(
            posten=tuple(posten), abbildungshinweise=tuple(Hinweis(m) for m in meldungen)
        )
