"""Abbildung der Google-Sheets-Antwort auf :class:`~umsatzprognose.domaene.schulung.Schulungsplan`.

Die Kopfzeile des Tabellenblatts bestimmt die Spaltenzuordnung **namentlich**, nicht
ueber die Position - robust gegenueber den vielen fuer die Prognose ungenutzten Spalten
(Rabattstufen, Trainer, ...). ``Präsenz/Online`` ist dagegen keine ungenutzte Spalte
mehr: :meth:`SchulungenRepository.anmeldungsverlauf_laden` liest sie als
:attr:`~umsatzprognose.domaene.anmeldung.Anmeldung.format`, Grundlage der
Format-Unterteilung im Kategorie-Drilldown der Webapp (siehe
:meth:`~umsatzprognose.domaene.anmeldung.Anmeldungsverlauf.gliederung_je_kategorie`).

**Die Kopfzeile steht nicht zuverlaessig in Zeile 0.** Analog zum Baustein Kosten
(siehe Moduldocstring von :mod:`umsatzprognose.kosten.kosten`) geht der eigentlichen
Tabelle in manchen Jahrgaengen noch etwas anderes voraus, das selbst wie eine Kopfzeile
aussieht, aber nicht alle Pflichtspalten traegt.
:func:`~umsatzprognose.google_sheets.client.kopfzeile_finden` (geteilt mit
:mod:`umsatzprognose.kosten.kosten`) sucht deshalb **inhaltsbasiert** die erste Zeile,
die alle uebergebenen Pflichtspalten enthaelt, statt ``zeilen[0]`` anzunehmen.

**Ausgerechnet die Jahr-Spalte ist von dieser namentlichen Zuordnung ausgenommen** -
verifiziert am Jahrgang 2024, wo die Kopfzeile dort nicht ``"Jahr"``, sondern einen
Vertipper (``"x^"``) traegt. Weil sie deshalb kein verlaesslicher Pflichtspalten-Name
ist, gehoert ``Jahr`` nicht zu den bei :func:`_kopfzeile_finden` verlangten Spalten,
und :func:`_jahr_spalte_ermitteln` faellt ohne eine Spalte namens ``"Jahr"`` auf die
**erste Spalte des Blatts** zurueck - dort steht das Jahr laut Beobachtung immer, auch
wenn ihre Kopfzeilenbeschriftung fehlerhaft ist.

``Umsatz gesamt`` steht im deutschen Zahlenformat mit Euro-Zeichen, uneinheitlich
formatiert (``"12.345,67 €"``, ``"1.234,56€"``, mit/ohne Leerzeichen). Geparst wird mit
:func:`~umsatzprognose.domaene.zahlen.euro_parsen`, robust: alles außer Ziffern, Punkt
und Komma entfernen, den Tausenderpunkt entfernen, das Komma zum Dezimalpunkt machen.

**Eine fehlende Quelle ist kein Fehler**: ein Jahr ohne
konfigurierte Datei, eine nicht lesbare Datei oder eine Datei ohne auffindbare
Pflichtspalten wird abgefangen und als :class:`~umsatzprognose.domaene.hinweis.Hinweis`
verzeichnet, statt die ganze Prognose scheitern zu lassen. Das unterscheidet dieses
Repository bewusst vom Fail-fast in :mod:`umsatzprognose.clockodo` (dort meldet
``ClockodoError`` unaufgefangen).

Daneben liest :meth:`SchulungenRepository.anmeldungsverlauf_laden` aus demselben
Tabellenblatt eine zweite, unabhaengige Sicht: die Teilnehmerzahl je Schulungstyp und
Monat statt des Umsatzes, siehe Moduldocstring von
:mod:`umsatzprognose.domaene.anmeldung`. Die Kopfzeile traegt die Spalte ``TN Zahl``
zweimal - einmal als Gesamtsumme direkt vor ``Umsatz gesamt``, einmal
in der Gruppe mit ``Max Zahl``/``Restplaetze``/``Auslastung`` fuer die
Kapazitaetsauslastung. Verifiziert am Jahrgang 2024: beide tragen denselben Wert. Die
namentliche Zuordnung ueber ein dict nimmt bei einem doppelten Spaltennamen ohnehin
automatisch die zuletzt (am weitesten rechts) stehende Spalte.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from umsatzprognose.domaene.anmeldung import Kategorisierung
    from umsatzprognose.util import Fortschritt

import json
from datetime import date
from functools import partial

from dotenv import load_dotenv

from umsatzprognose.domaene import (
    Anmeldung,
    Anmeldungsverlauf,
    Hinweis,
    Schulungsplan,
    Schulungstermin,
)
from umsatzprognose.domaene.zahlen import euro_parsen
from umsatzprognose.google_sheets import (
    GoogleSheetsClient,
    GoogleSheetsConfig,
    MissingCredentialsError,
    TabellenClient,
    jahre_laden,
    kopfzeile_finden,
    zelle,
    zelle_an,
)
from umsatzprognose.util import aus_ordnung, colab_secret, in_colab, ordnung, umgebungsvariable

TABELLENBLATT = "Öffentliche Schulungen"

SPALTE_JAHR = "Jahr"
SPALTE_MONAT = "Monat"
SPALTE_UMSATZ = "Umsatz gesamt"
SPALTE_SCHULUNGSTYP = "Schulung"
SPALTE_TEILNEHMERZAHL = "TN Zahl"
SPALTE_FORMAT = "Präsenz/Online"

KATEGORIEN_VAR = "SCHULUNGEN_KATEGORIEN"

_umgebungsvariable = partial(umgebungsvariable, fehlerklasse=MissingCredentialsError)
_colab_secret = partial(colab_secret, fehlerklasse=MissingCredentialsError)


def kategorien_automatisch() -> Kategorisierung:
    """Aus der passenden Quelle: Colab-Secrets in Colab, sonst ``.env`` - dieselbe
    Auswahl wie bei :meth:`~umsatzprognose.google_sheets.GoogleSheetsConfig.automatisch`
    und :func:`~umsatzprognose.clockodo.kurzarbeit.rollenzuordnung_automatisch`.

    Die Kategorie-Zuordnung (Scrum/Kanban/Sonstige, siehe Moduldocstring von
    :mod:`umsatzprognose.domaene.anmeldung`) ist reine Konfiguration statt Fachlogik
    und wird deshalb wie :data:`~umsatzprognose.google_sheets.config.SHEET_ID_VAR` zur
    Laufzeit gelesen statt im Repository als Python-Konstante gefuehrt - Webapp und
    Notebook (``notebooks/03_schulungsanmeldungen.ipynb``) lesen dieselbe Quelle statt
    zwei unabhaengig gepflegte Kopien.
    """
    return kategorien_aus_colab_secrets() if in_colab() else kategorien_aus_umgebung()


def kategorien_aus_umgebung(*, use_dotenv: bool = True) -> Kategorisierung:
    """Aus :data:`KATEGORIEN_VAR`; lokal wird eine ``.env`` beruecksichtigt."""
    if use_dotenv:
        load_dotenv()
    return _kategorien_aus_json(_umgebungsvariable(KATEGORIEN_VAR))


def kategorien_aus_colab_secrets() -> Kategorisierung:
    """Aus der Colab-Secrets-Verwaltung. Keine ``.env`` in Colab."""
    return _kategorien_aus_json(_colab_secret(KATEGORIEN_VAR))


def _kategorien_aus_json(roh: str) -> Kategorisierung:
    try:
        wert = json.loads(roh)
    except json.JSONDecodeError as fehler:
        raise MissingCredentialsError(
            f"{KATEGORIEN_VAR} enthaelt kein gueltiges JSON: {fehler}"
        ) from fehler
    ungueltig = not isinstance(wert, dict) or not all(
        isinstance(kategorie, str)
        and isinstance(typen, list)
        and all(isinstance(typ, str) for typ in typen)
        for kategorie, typen in wert.items()
    )
    if ungueltig:
        raise MissingCredentialsError(
            f"{KATEGORIEN_VAR} muss ein JSON-Objekt Kategorie -> Liste von Schulungstypen sein."
        )
    return wert


def _jahr_spalte_ermitteln(index: dict[str, int]) -> int:
    """Ermittelt die Jahr-Spalte - ueber die Kopfzeile, sonst als erste Spalte des Blatts.

    Ausgerechnet die Jahr-Spalte ist fuer Vertipper in der Kopfzeile anfaellig (siehe
    Moduldocstring, beobachtet an ``"x^"`` statt ``"Jahr"`` im Jahrgang 2024). Ohne eine
    Spalte namens ``"Jahr"`` gilt deshalb positionsbasiert die erste Spalte (Index 0) -
    dort steht das Jahr laut Beobachtung immer, unabhaengig von ihrer Beschriftung.
    """
    return index.get(SPALTE_JAHR, 0)


def _zeilen_zu_terminen(zeilen: list[list[str]]) -> list[Schulungstermin]:
    if not zeilen:
        return []
    kopf_zeile, index = kopfzeile_finden(zeilen, {SPALTE_MONAT, SPALTE_UMSATZ})
    jahr_spalte = _jahr_spalte_ermitteln(index)

    termine = []
    for zeile in zeilen[kopf_zeile + 1 :]:
        jahr_text = zelle_an(zeile, jahr_spalte).strip()
        monat_text = zelle(zeile, index, SPALTE_MONAT).strip()
        if not jahr_text or not monat_text:
            continue
        termine.append(
            Schulungstermin(
                jahr=int(jahr_text),
                monat=int(monat_text),
                umsatz=euro_parsen(zelle(zeile, index, SPALTE_UMSATZ)),
            )
        )
    return termine


def _zeilen_zu_anmeldungen(zeilen: list[list[str]]) -> list[Anmeldung]:
    """Wie :func:`_zeilen_zu_terminen`, aber Teilnehmerzahl je Schulungstyp statt Umsatz."""
    if not zeilen:
        return []
    kopf_zeile, index = kopfzeile_finden(
        zeilen, {SPALTE_MONAT, SPALTE_SCHULUNGSTYP, SPALTE_TEILNEHMERZAHL, SPALTE_FORMAT}
    )
    jahr_spalte = _jahr_spalte_ermitteln(index)

    anmeldungen = []
    for zeile in zeilen[kopf_zeile + 1 :]:
        jahr_text = zelle_an(zeile, jahr_spalte).strip()
        monat_text = zelle(zeile, index, SPALTE_MONAT).strip()
        if not jahr_text or not monat_text:
            continue
        # Eine leere Zelle steht fuer 0 Anmeldungen, nicht fuer eine fehlende Zeile -
        # sonst wuerde ein Schulungstyp mit ausschliesslich leeren TN-Zahl-Zellen in
        # diesem Zeitraum unbemerkt ganz aus verlauf.schulungstypen verschwinden statt
        # mit 0 aufzutauchen.
        teilnehmerzahl_text = zelle(zeile, index, SPALTE_TEILNEHMERZAHL).strip()
        anmeldungen.append(
            Anmeldung(
                jahr=int(jahr_text),
                monat=int(monat_text),
                schulungstyp=zelle(zeile, index, SPALTE_SCHULUNGSTYP).strip() or "Unbekannt",
                teilnehmerzahl=int(float(teilnehmerzahl_text.replace(",", ".")))
                if teilnehmerzahl_text
                else 0,
                format=zelle(zeile, index, SPALTE_FORMAT).strip(),
            )
        )
    return anmeldungen


def _benoetigte_jahre(stichtag: date, horizont_monate: int) -> tuple[int, ...]:
    """Stichtagsjahr, und - falls der Horizont die Jahresgrenze ueberschreitet - das Folgejahr."""
    ende = ordnung(stichtag.year, stichtag.month) + (horizont_monate - 1)
    return tuple(sorted({stichtag.year, aus_ordnung(ende)[0]}))


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
        Jahrgaenge gelesen und ihre Termine vor der Aggregation zusammengefuehrt.
        Ein fehlendes oder nicht lesbares Jahr wird nicht zum Fehler, siehe
        Moduldocstring.
        """
        stichtag = stichtag or date.today()

        termine, meldungen = jahre_laden(
            self._client,
            self._jahre_zu_dateien,
            _benoetigte_jahre(stichtag, horizont_monate),
            bereich=lambda _jahr: TABELLENBLATT,
            abbilden=lambda zeilen, _jahr: _zeilen_zu_terminen(zeilen),
            fehlt_meldung="Für {jahr} ist in KOSTEN_SHEET_IDS keine Schulungs-Datei hinterlegt",
            fehler_meldung="Die Schulungs-Datei für {jahr} konnte nicht gelesen werden ({detail})",
        )
        return Schulungsplan(
            stichtag=stichtag,
            termine=tuple(termine),
            abbildungshinweise=tuple(Hinweis(m) for m in meldungen),
        )

    def anmeldungsverlauf_laden(
        self, jahre: Sequence[int], *, fortschritt: Fortschritt | None = None
    ) -> Anmeldungsverlauf:
        """Teilnehmerzahl je Schulungstyp und Monat, ueber die angegebenen Jahre hinweg.

        Anders als :meth:`laden` nicht auf den Prognosehorizont beschraenkt, siehe
        Moduldocstring von :mod:`umsatzprognose.domaene.anmeldung`.

        ``fortschritt``, sofern angegeben, meldet sich einmal je verarbeitetem Jahr mit
        der bis dahin kumulierten Anmeldungszahl - mehr Zwischenschritte gibt es nicht,
        weil Google Sheets einen Zellbereich immer als einen einzigen atomaren Abruf
        liefert (siehe :func:`~umsatzprognose.google_sheets.client.jahre_laden`).
        """
        anmeldungen, meldungen = jahre_laden(
            self._client,
            self._jahre_zu_dateien,
            jahre,
            bereich=lambda _jahr: TABELLENBLATT,
            abbilden=lambda zeilen, _jahr: _zeilen_zu_anmeldungen(zeilen),
            fehlt_meldung="Für {jahr} ist in KOSTEN_SHEET_IDS keine Schulungs-Datei hinterlegt",
            fehler_meldung="Die Schulungs-Datei für {jahr} konnte nicht gelesen werden ({detail})",
            fortschritt=fortschritt,
            fortschritt_text=lambda jahr, bisher: f"{len(bisher)} Anmeldungen bis {jahr} geladen",
        )
        return Anmeldungsverlauf(
            anmeldungen=tuple(anmeldungen),
            abbildungshinweise=tuple(Hinweis(m) for m in meldungen),
        )
