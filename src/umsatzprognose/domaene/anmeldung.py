"""Anmeldungsverlauf oeffentlicher Schulungen - Teilnehmerzahl statt Umsatz.

Zweite, unabhaengige Lesart derselben Google-Sheets-Quelle wie
:mod:`umsatzprognose.domaene.schulung` (Tabellenblatt "Oeffentliche Schulungen"): nicht
der Umsatz, sondern die Teilnehmerzahl je Schulungstyp und Monat - Grundlage fuer den
internen Verlauf "Anmeldungen bleiben auf niedrigem Niveau".

Anders als :class:`~umsatzprognose.domaene.schulung.Schulungsplan` deckt dieser Verlauf
bewusst **mehrere zurueckliegende Jahre** ab statt nur des Prognosehorizonts: eine
Teilnehmerzahl ist kein Umsatz und dupliziert daher nichts aus Clockodo - anders als beim
Baustein Schulungsanmeldungen gibt es hier kein Doppelzaehlungsrisiko, das den Blick auf
die Vergangenheit ausschliessen wuerde. Bleibt wie der Baustein Schulungsanmeldungen
additiv: kein Einfluss auf Restvolumen, Abrufquote oder Kapazitaetsdeckel.

**Keine Kategorisierung im Diagramm standardmaessig mehr** (eine fruehere Fassung
gruppierte dort immer per von Hand gepflegter Zuordnung nach Scrum/Kanban/Sonstige) -
als staendig sichtbares Liniendiagramm mit einer Linie je Kategorie veraltete das
unbemerkt, sobald neue Schulungstypen dazukamen. Primaer zaehlt dort deshalb weiterhin
nur die Gesamtzahl je Monat (siehe :meth:`Anmeldungsverlauf.je_monat`). Die Webapp
bietet dieselbe Aufschluesselung nach Kategorie, Schulungstyp, Format und Dauer aber
als **explizit gewaehlter, optionaler Filter** wieder an (siehe
:func:`~umsatzprognose.darstellung.diagramme.anmeldungsverlauf_reihen` und
``webapp/templates/schulungen.html``) - das unterscheidet sich vom damals entfernten
Verhalten: eine bewusst getroffene Auswahl veraltet nicht unbemerkt, anders als eine
immer sichtbare, aber stillschweigend unvollstaendige Gruppierung. Dieselbe
Kategorisierung steht ausserdem weiterhin als Tabellen-Drilldown hinter der Gesamtzahl
zur Verfuegung, sowohl monatsweise (:meth:`Anmeldungsverlauf.je_monat_und_kategorie`)
als auch bis auf Schulungstyp/Format/Dauer verfeinert
(:meth:`Anmeldungsverlauf.gliederung_je_kategorie`) - als Tabelle faellt eine
veraltete/unvollstaendige Zuordnung eher auf und stoert weniger als im Diagramm.

**Kategorisierung frei konfigurierbar**: eine von Hand gepflegte Zuordnung einzelner
Schulungstypen, keine Stichwortsuche - Zertifizierungen laufen ueberwiegend ueber
Kuerzel (``"CSM"``, ``"KSD"``, ...), nicht ueber ausgeschriebene Woerter wie
"Scrum"/"Kanban". Die Zuordnung selbst ist bewusst **keine Konstante dieses Moduls**,
sondern wird als Parameter uebergeben (typischerweise eine im Notebook/Skript
gepflegte ``dict[str, list[str]]``, siehe ``notebooks/03_schulungsanmeldungen.ipynb``)
- welche Kategorien es gibt und welche Schulungstypen dazuzaehlen, ist reine
Konfiguration, keine Fachlogik. Ein Schulungstyp, der in keiner Kategorie auftaucht,
faellt auf :data:`KATEGORIE_SONSTIGE` zurueck. Der Nachschlag laeuft dabei ueber den
Basisnamen (siehe :func:`_kategorie_zuordnung`), nicht ueber den rohen Schulungstyp-
Text - die Quelle schreibt den Dauer-Suffix uneinheitlich uebers Jahr (z. B. "KSI" in
2022-2024, "KSI 3-tägig" ab 2025 fuer dieselbe Schulung), ein Konfigurationseintrag muss
deshalb nicht jede Dauer-Variante einzeln auffuehren.

**Dauer-Auspraegung bevorzugt aus der ``Datum``-Spalte berechnet** (siehe
:func:`_dauer_aus_datumsspanne`), mit dem Text-Suffix des Schulungstyps als Rueckfall
(siehe :func:`_basisname_und_dauer`) dort, wo ``Datum`` fehlt oder nicht interpretierbar
ist - :func:`_dauer` buendelt beide Quellen. ``Datum`` ist reiner Freitext (uneinheitliche
Trennzeichen, gelegentliche Tippfehler, Zeitraeume statt Einzeltermine bei
berufsbegleitenden Programmen); eine Berechnung, die unplausibel lang ausfaellt (siehe
:data:`_MAX_PLAUSIBLE_DAUER_TAGE`) oder scheitert, faellt auf den Suffix zurueck statt
einen falschen Wert zu zeigen.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Collection, Iterable, Mapping, Sequence

    from umsatzprognose.util import Monat

    from .hinweis import Hinweis

    Kategorisierung = Mapping[str, Sequence[str]]

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from umsatzprognose.util import ordnung

KATEGORIE_SONSTIGE = "Sonstige"

# Erkennt einen Dauer-Suffix wie "2-tägig"/"3-tägig" am Ende eines Schulungstyps (z. B.
# "CSPO 2-tägig" -> Basisname "CSPO", Dauer "2-tägig") - rein aus dem Text abgeleitet,
# ohne Konfiguration, siehe _basisname_und_dauer().
_DAUER_MUSTER = re.compile(r"^(?P<basis>.+?)\s+(?P<dauer>\d+-tägig)$")


def _kategorie_zuordnung(kategorien: Kategorisierung) -> dict[str, str]:
    """Kehrt eine Kategorie-zu-Schulungstypen-Zuordnung zu einer Basisname-zu-Kategorie-
    Zuordnung um - fuer den Nachschlag je Anmeldung.

    Der Schluessel ist der ueber :func:`_basisname_und_dauer` ermittelte Basisname, nicht
    der rohe, in ``kategorien`` konfigurierte Schulungstyp-Text: die Quelle schreibt den
    Dauer-Suffix uneinheitlich - z. B. "KSI" in 2022-2024, "KSI 2-tägig"/"KSI 3-tägig"
    ab 2025, obwohl es sich fachlich um dieselbe Schulung handelt. Ohne diese
    Normalisierung muesste ``kategorien`` jede Dauer-Variante einzeln auffuehren und bei
    jeder neu auftauchenden Variante von Hand nachgezogen werden, sonst faellt ein
    Jahrgang stillschweigend auf :data:`KATEGORIE_SONSTIGE` zurueck. Ein Konfigurations-
    eintrag darf weiterhin wahlweise den Basisnamen oder eine konkrete Dauer-Variante
    nennen - beide normalisieren auf denselben Schluessel, mehrfach genannte Varianten
    sind also harmlos redundant, nicht falsch."""
    return {
        _basisname_und_dauer(typ)[0]: kategorie
        for kategorie, typen in kategorien.items()
        for typ in typen
    }


def _basisname_und_dauer(schulungstyp: str) -> tuple[str, str | None]:
    """Trennt einen erkannten Dauer-Suffix vom Schulungstyp-Namen ab.

    Rein aus dem Schulungstyp-Text abgeleitet (siehe :data:`_DAUER_MUSTER`), ohne
    gepflegte Zuordnung - eine neue "XYZ 2-tägig"/"XYZ 3-tägig"-Variante wird damit
    automatisch erkannt, ohne dass irgendwo eine Liste gepflegt werden muesste. Ohne
    erkannten Suffix bleibt der Schulungstyp unveraendert der Basisname, ohne Dauer.
    """
    treffer = _DAUER_MUSTER.match(schulungstyp)
    if treffer is None:
        return schulungstyp, None
    return treffer.group("basis"), treffer.group("dauer")


# Eine Schulungsdauer jenseits dieser Grenze gilt als nicht plausibel berechnet (siehe
# _dauer_aus_datumsspanne()) - die Datum-Spalte traegt neben einzelnen Trainingsterminen
# auch mehrmonatige Zeitraeume berufsbegleitender Programme (z. B. "01.01.-30.06.2025"),
# die keine Schulungsdauer im Sinne dieser Auswertung sind. 10 Tage liegt deutlich ueber
# jeder beobachteten realen Schulungsdauer (1-3 Tage) und faengt trotzdem grosszuegig
# kuenftige, laengere Formate ab, ohne Mehrmonats-Zeitraeume durchzulassen.
_MAX_PLAUSIBLE_DAUER_TAGE = 10

_MONATSNAMEN = {
    "jan": 1, "feb": 2, "mär": 3, "mrz": 3, "apr": 4, "mai": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "okt": 10, "nov": 11, "dez": 12,
}  # fmt: skip

# Trennt die beiden Termine einer Datumsspanne - beobachtete Varianten in der Quelle
# neben dem Bindestrich: "&", "+", ausgeschriebenes "und" (z. B. "13. und 14.11.2023").
# Nur das erste Vorkommen wird ersetzt (count=1 an der Aufrufstelle), falls der zweite
# Termin selbst einen Bindestrich enthaelt (kommt in der Quelle nicht vor, aber so bleibt
# ein "-" im Rest unangetastet).
_DATUMSSPANNE_TRENNER = re.compile(r"\s*(?:-|\u2013|&|\+|\bund\b)\s*", re.IGNORECASE)

# Nach der Trenner-Normalisierung: Tag(.Monat)?-Tag.Rest, wobei Rest entweder
# "Monat.Jahr" oder "Monatsname Jahr" ist (siehe _monat_und_jahr_aus_rest()).
_DATUMSSPANNE_MUSTER = re.compile(
    r"^(?P<tag1>\d{1,2})\.\s*(?:(?P<monat1>\d{1,2})\.)?-(?P<tag2>\d{1,2})\.\s*(?P<rest>.+)$",
)
# Ein einzelner Termin ohne Spanne (z. B. "01.04.2025") - eine eintaegige Schulung.
_EINZELDATUM_MUSTER = re.compile(r"^(?P<tag>\d{1,2})\.\s*(?P<rest>.+)$")

_REST_NUMERISCH = re.compile(r"^(?P<monat>\d{1,2})\.\s*0*(?P<jahr>\d{4})$")
_REST_MONATSNAME = re.compile(r"^(?P<monatname>[A-Za-zÄÖÜäöüß]+)\.?\s+0*(?P<jahr>\d{4})$")


def _monat_und_jahr_aus_rest(rest: str) -> tuple[int, int] | None:
    """Monat und Jahr aus dem Rest einer Datumsspanne/eines Einzeldatums - entweder
    numerisch (``"02.2024"``) oder mit ausgeschriebenem Monatsnamen (``"Nov 2022"``,
    auch ohne Leerzeichen davor: ``"April 2025"``). Ein Jahres-Tippfehler mit fuehrender
    Null (beobachtet: ``"02024"``) wird toleriert, ein unbekannter oder abweichend
    langer Jahreswert nicht - dann gilt die Spanne als nicht interpretierbar."""
    treffer = _REST_NUMERISCH.match(rest)
    if treffer is not None:
        return int(treffer.group("monat")), int(treffer.group("jahr"))
    treffer = _REST_MONATSNAME.match(rest)
    if treffer is None:
        return None
    monat = _MONATSNAMEN.get(treffer.group("monatname")[:3].lower())
    return (monat, int(treffer.group("jahr"))) if monat is not None else None


def _tage_aus_spanne(spanne: re.Match[str]) -> int | None:
    """Tagesanzahl einer erkannten Datumsspanne (``tag1(.monat1)?-tag2.rest``) - ``None``
    bei nicht interpretierbarem Rest oder einem ungueltigen Kalenderdatum."""
    monat_und_jahr = _monat_und_jahr_aus_rest(spanne.group("rest").strip())
    if monat_und_jahr is None:
        return None
    monat2, jahr = monat_und_jahr
    monat1 = int(spanne.group("monat1")) if spanne.group("monat1") else monat2
    try:
        start = date(jahr, monat1, int(spanne.group("tag1")))
        ende = date(jahr, monat2, int(spanne.group("tag2")))
    except ValueError:
        return None
    return (ende - start).days + 1


def _tage_aus_einzeldatum(einzeldatum: re.Match[str]) -> int | None:
    """Tagesanzahl (immer 1) eines erkannten Einzeldatums (``tag.rest``) - ``None`` bei
    nicht interpretierbarem Rest oder einem ungueltigen Kalenderdatum."""
    monat_und_jahr = _monat_und_jahr_aus_rest(einzeldatum.group("rest").strip())
    if monat_und_jahr is None:
        return None
    monat, jahr = monat_und_jahr
    try:
        date(jahr, monat, int(einzeldatum.group("tag")))
    except ValueError:
        return None
    return 1


def _dauer_aus_datumsspanne(text: str) -> str | None:
    """Berechnet die Schulungsdauer (``"N-tägig"``) aus der freitextlichen ``Datum``-
    Spalte der Quelle, statt sie wie :func:`_basisname_und_dauer` aus einem Suffix im
    Schulungstyp-Text abzuleiten.

    Die Datum-Spalte traegt die tatsaechlichen Termine und ist deshalb die
    verlaesslichere Quelle - verifiziert am Jahrgang KSI: 2022-2024 traegt der
    Schulungstyp nie einen Dauer-Suffix, obwohl die Termine durchgaengig zwei Tage
    umfassen; erst ab 2025 (als KSI tatsaechlich auf drei Tage wechselte) schreibt die
    Pflege den Suffix mit.

    ``Datum`` ist reiner, von Hand gepflegter Freitext - uneinheitliche Trennzeichen,
    Monatsnamen statt Zahl, gelegentliche Tippfehler, sowie Zeitraeume statt einzelner
    Termine (siehe :data:`_MAX_PLAUSIBLE_DAUER_TAGE`). Nicht interpretierbarer oder
    unplausibler Text liefert ``None`` statt eines geratenen Werts - der Aufrufer faellt
    dann auf :func:`_basisname_und_dauer` zurueck (siehe :func:`_dauer`)."""
    text = text.strip()
    if not text:
        return None

    spanne = _DATUMSSPANNE_MUSTER.match(_DATUMSSPANNE_TRENNER.sub("-", text, count=1))
    if spanne is not None:
        tage = _tage_aus_spanne(spanne)
    else:
        einzeldatum = _EINZELDATUM_MUSTER.match(text)
        tage = _tage_aus_einzeldatum(einzeldatum) if einzeldatum is not None else None

    if tage is None or not (1 <= tage <= _MAX_PLAUSIBLE_DAUER_TAGE):
        return None
    return f"{tage}-tägig"


def _dauer(anmeldung: Anmeldung) -> str | None:
    """Die effektive Dauer-Auspraegung einer Anmeldung: bevorzugt aus ``datum``
    berechnet (siehe :func:`_dauer_aus_datumsspanne`), sonst aus dem Text-Suffix des
    Schulungstyps abgeleitet (siehe :func:`_basisname_und_dauer`) - der Rueckfall greift,
    wo ``datum`` fehlt oder nicht interpretierbar ist."""
    return (
        _dauer_aus_datumsspanne(anmeldung.datum) or _basisname_und_dauer(anmeldung.schulungstyp)[1]
    )


def _teilnehmerzahl_je[K](
    anmeldungen: Iterable[Anmeldung],
    schluessel: Callable[[Anmeldung], K],
) -> dict[K, int]:
    """Teilnehmerzahl aufsummiert je ``schluessel(a)`` - der gemeinsame Kern hinter
    :meth:`Anmeldungsverlauf.summe_je_typ`, :meth:`~.je_monat` und
    :meth:`~.je_monat_und_typ`."""
    summen: Counter[K] = Counter()
    for a in anmeldungen:
        summen[schluessel(a)] += a.teilnehmerzahl
    return summen


@dataclass(frozen=True, slots=True)
class Anmeldung:
    """Teilnehmerzahl eines Schulungstyps in einem Monat - eine Zeile der Quelltabelle.

    ``format`` ("Präsenz"/"Online", aus der gleichnamigen Spalte) ist optional -
    leer, wenn die Quelle keinen Wert traegt. Grundlage fuer die Format-Unterteilung
    im Kategorie-Drilldown der Webapp (siehe :meth:`Anmeldungsverlauf.
    gliederung_je_kategorie`), die nur dort erscheint, wo tatsaechlich mehr als ein
    Format vorkommt.

    ``datum`` (die rohe ``Datum``-Spalte, z. B. ``"07.-08.02.2022"``) ist ebenso
    optional und dient ausschliesslich als robustere Quelle fuer die Dauer-Auspraegung
    (siehe :func:`_dauer_aus_datumsspanne`) - anders als ``format`` fliesst sie in
    keine eigene Gliederungsebene ein.
    """

    jahr: int
    monat: int
    schulungstyp: str
    teilnehmerzahl: int
    format: str = ""
    datum: str = ""

    @property
    def schluessel(self) -> Monat:
        return (self.jahr, self.monat)


@dataclass(frozen=True, slots=True)
class Anmeldungsknoten:
    """Ein Knoten im Kategorie-Drilldown der Webapp (siehe
    :meth:`Anmeldungsverlauf.gliederung_je_kategorie`) - entweder ein Blatt (``kinder``
    leer) mit eigenen Monatswerten, oder ein Gruppierungsknoten, dessen Monatswerte die
    Summe seiner Kinder sind."""

    name: str
    monate: dict[Monat, int]
    kinder: tuple[Anmeldungsknoten, ...] = ()


def _gruppieren(
    zeilen: Sequence[Anmeldung],
    schluessel: Callable[[Anmeldung], str],
) -> dict[str, list[Anmeldung]]:
    gruppen: dict[str, list[Anmeldung]] = {}
    for a in zeilen:
        gruppen.setdefault(schluessel(a), []).append(a)
    return gruppen


def _alphabetisch_mit_anmeldungen(
    gruppen: dict[str, list[Anmeldung]],
) -> list[tuple[str, list[Anmeldung]]]:
    """Sortiert alphabetisch (gross-/kleinschreibungsunabhaengig) - und laesst Gruppen
    ganz ohne Anmeldung in diesem Zeitraum weg: eine Schulung ohne Teilnehmende in
    diesem Zeitraum soll nicht als eigene (leere) Zeile auftauchen. Diese Filterung
    wirkt ausschliesslich auf Basisname-/Format-/Dauer-Ebene im Tabellen-Drilldown
    (siehe :meth:`Anmeldungsverlauf.gliederung_je_kategorie`) - eine Kategorie bleibt
    dort auch ohne Anmeldung sichtbar, weil das schon dort dokumentiert ist. Anders als
    :attr:`Anmeldungsverlauf.schulungstypen`/:attr:`~.formate`/:attr:`~.dauern` (nach
    absteigender Gesamtteilnehmerzahl, fuer die Dropdown-Optionen der Webapp-Filter) -
    in der Tabelle soll man einen bekannten Namen alphabetisch wiederfinden, nicht nach
    Anmeldezahl suchen muessen."""
    mit_anmeldungen = [
        (name, gruppe)
        for name, gruppe in gruppen.items()
        if sum(a.teilnehmerzahl for a in gruppe) > 0
    ]
    return sorted(mit_anmeldungen, key=lambda kv: kv[0].lower())


def _nach_juengstem_jahr_und_name_mit_anmeldungen(
    gruppen: dict[str, list[Anmeldung]],
) -> list[tuple[str, list[Anmeldung]]]:
    """Wie :func:`_alphabetisch_mit_anmeldungen` (dieselbe Ausblendung leerer Gruppen),
    aber primaer nach dem juengsten vorkommenden Jahr sortiert (absteigend), erst
    danach alphabetisch - fuer die direkten Basisname-Kinder einer Kategorie im
    Tabellen-Drilldown (siehe :meth:`Anmeldungsverlauf.gliederung_je_kategorie`): eine
    Schulung, die nur in einem laengst vergangenen Jahr stattfand, taucht dort
    unterhalb aller Schulungen des juengsten vorkommenden Jahres auf, statt sich rein
    alphabetisch dazwischenzumischen. Eine Schulung mit Anmeldungen in mehreren Jahren
    zaehlt dabei zu ihrem juengsten Jahr."""
    mit_anmeldungen = [
        (name, gruppe)
        for name, gruppe in gruppen.items()
        if sum(a.teilnehmerzahl for a in gruppe) > 0
    ]
    return sorted(
        mit_anmeldungen,
        key=lambda kv: (-max(a.jahr for a in kv[1]), kv[0].lower()),
    )


def _mit_dauer_kindern(name: str, zeilen: Sequence[Anmeldung]) -> Anmeldungsknoten:
    """Ein Knoten mit Dauer-Kindern, falls ``zeilen`` mehr als eine (tatsaechlich
    besetzte) Dauer-Auspraegung zeigt, sonst ein Blatt ohne Kinder - die Dauer-Ebene
    erscheint nur bei tatsaechlicher Vielfalt, nicht als immer vorhandene
    Zwischenebene. Ein Schulungstyp ohne erkannten Dauer-Suffix behaelt seinen vollen
    Namen als Label, statt mit einem erfundenen Platzhalter aufzutauchen."""
    dauer_gruppen = _gruppieren(
        zeilen,
        lambda a: _dauer(a) or a.schulungstyp,
    )
    dauern = _alphabetisch_mit_anmeldungen(dauer_gruppen)
    kinder = (
        tuple(
            Anmeldungsknoten(dauer_name, _teilnehmerzahl_je(gruppe, lambda a: a.schluessel))
            for dauer_name, gruppe in dauern
        )
        if len(dauern) > 1
        else ()
    )
    return Anmeldungsknoten(name, _teilnehmerzahl_je(zeilen, lambda a: a.schluessel), kinder)


def _basisname_knoten(basisname: str, zeilen: Sequence[Anmeldung]) -> Anmeldungsknoten:
    """Ein Basisname-Knoten (z. B. "CSPO"), mit einer Format-Zwischenebene nur dort, wo
    in ``zeilen`` tatsaechlich mehr als ein (besetztes) Format vorkommt - sonst direkt
    mit Dauer-Kindern (oder als Blatt), ohne eine Format-Ebene mit nur einer
    Auspraegung."""
    formate = _alphabetisch_mit_anmeldungen(_gruppieren(zeilen, lambda a: a.format))
    if len(formate) > 1:
        kinder = tuple(_mit_dauer_kindern(format_wert, gruppe) for format_wert, gruppe in formate)
        monate = _teilnehmerzahl_je(zeilen, lambda a: a.schluessel)
        return Anmeldungsknoten(basisname, monate, kinder)
    return _mit_dauer_kindern(basisname, zeilen)


@dataclass(frozen=True, slots=True)
class Anmeldungsverlauf:
    """Alle geladenen Anmeldungen ueber den abgedeckten Zeitraum.

    Attributes:
        abbildungshinweise: Befunde aus dem Laden der Google-Sheets-Dateien - fehlende
            Konfiguration fuer ein Jahr, eine nicht lesbare Datei. Siehe
            :meth:`~umsatzprognose.schulungen.schulungen.SchulungenRepository.anmeldungsverlauf_laden`.
    """

    anmeldungen: tuple[Anmeldung, ...] = ()
    abbildungshinweise: tuple[Hinweis, ...] = field(default_factory=tuple)

    @property
    def monate(self) -> tuple[Monat, ...]:
        """Alle vorkommenden Monate, chronologisch und ohne Duplikate."""
        return tuple(sorted({a.schluessel for a in self.anmeldungen}))

    @property
    def schulungstypen(self) -> tuple[str, ...]:
        """Alle vorkommenden Schulungstypen, nach absteigender Gesamtteilnehmerzahl."""
        summen = self.summe_je_typ()
        return tuple(sorted(summen, key=lambda typ: summen[typ], reverse=True))

    def summe_je_typ(self) -> dict[str, int]:
        """Teilnehmerzahl je Schulungstyp, ueber den gesamten abgedeckten Zeitraum -
        der Drilldown hinter der Gesamtzahl aus :meth:`je_monat`, siehe
        :func:`~umsatzprognose.darstellung.tabellen.anmeldungstabelle`."""
        return _teilnehmerzahl_je(self.anmeldungen, lambda a: a.schulungstyp)

    def je_monat_und_kategorie(self, kategorien: Kategorisierung) -> dict[str, dict[Monat, int]]:
        """Teilnehmerzahl je Monat, gruppiert nach den uebergebenen Kategorien - der
        Drilldown hinter der Gesamtzahl aus :meth:`je_monat`, siehe
        :func:`~umsatzprognose.darstellung.tabellen.anmeldungstabelle`.

        ``kategorien`` bildet Kategoriename auf die zugehoerigen Schulungstypen ab
        (siehe Moduldocstring) - ein Schulungstyp, der in keiner Kategorie auftaucht,
        landet unter :data:`KATEGORIE_SONSTIGE`. Das Ergebnis traegt genau die
        uebergebenen Kategorien in ihrer Reihenfolge, plus ``KATEGORIE_SONSTIGE`` am
        Ende - auch dann, wenn eine Kategorie in diesem Zeitraum keine Anmeldung hat.
        """
        zuordnung = _kategorie_zuordnung(kategorien)
        ergebnis: dict[str, dict[Monat, int]] = {
            name: Counter() for name in (*kategorien, KATEGORIE_SONSTIGE)
        }
        for a in self.anmeldungen:
            basisname = _basisname_und_dauer(a.schulungstyp)[0]
            summen = ergebnis[zuordnung.get(basisname, KATEGORIE_SONSTIGE)]
            summen[a.schluessel] += a.teilnehmerzahl
        return ergebnis

    def gliederung_je_kategorie(
        self,
        kategorien: Kategorisierung,
    ) -> dict[str, tuple[Anmeldungsknoten, ...]]:
        """Fuer jede Kategorie die Basisname-Knoten (z. B. "CSPO" fuer "CSPO 2-tägig"/
        "CSPO 3-tägig", siehe :func:`_basisname_und_dauer`), je nach tatsaechlich
        vorkommender Vielfalt zusaetzlich unterteilt nach Format (Praesenz/Online, aus
        :attr:`Anmeldung.format`) und/oder Dauer - der Kategorie-Drilldown fuer die
        Webapp (siehe ``webapp/templates/schulungen.html``), eine Ebene feiner als
        :meth:`je_monat_und_kategorie`.

        Eine Zwischenebene erscheint nur, wenn die geladenen Anmeldungen in diesem
        Zeitraum tatsaechlich mehr als eine (tatsaechlich besetzte) Auspraegung
        zeigen - ein Schulungstyp ohne Dauer-Suffix oder mit durchgaengig demselben
        Format bleibt ein einfacher Blatt-Knoten ohne zusaetzlichen Klick. Ein
        Basisname/Format/Dauer ganz ohne Teilnehmende in diesem Zeitraum taucht gar
        nicht erst als eigene Zeile auf (siehe :func:`_alphabetisch_mit_anmeldungen`)
        - anders als bei einer Kategorie ist das hier reine Anzeige-Deko ohne den
        Zweck, auf eine moeglicherweise veraltete Konfiguration hinzuweisen.
        Die direkten Basisname-Kinder einer Kategorie sind primaer nach ihrem
        juengsten vorkommenden Jahr sortiert (absteigend), erst dann alphabetisch
        (siehe :func:`_nach_juengstem_jahr_und_name_mit_anmeldungen`) - eine Schulung,
        die nur in einem laengst vergangenen Jahr stattfand, taucht so unterhalb aller
        Schulungen des juengsten Jahres auf, statt sich rein alphabetisch
        dazwischenzumischen. Format- und Dauer-Knoten darunter bleiben dagegen rein
        alphabetisch sortiert (:func:`_alphabetisch_mit_anmeldungen`, anders als
        :attr:`schulungstypen`/:attr:`formate`/:attr:`dauern` nach absteigender
        Gesamtteilnehmerzahl) - im Tabellen-Drilldown soll man einen bekannten Namen
        dort weiterhin alphabetisch wiederfinden, nicht nach Anmeldezahl suchen
        muessen; eine Kategorie ohne Anmeldung in diesem Zeitraum liefert dagegen
        weiterhin eine leere Tupel statt zu fehlen (derselbe Auffangmechanismus wie
        bei :meth:`je_monat_und_kategorie`).
        """
        zuordnung = _kategorie_zuordnung(kategorien)
        je_kategorie: dict[str, list[Anmeldung]] = {
            name: [] for name in (*kategorien, KATEGORIE_SONSTIGE)
        }
        for a in self.anmeldungen:
            basisname = _basisname_und_dauer(a.schulungstyp)[0]
            je_kategorie[zuordnung.get(basisname, KATEGORIE_SONSTIGE)].append(a)

        ergebnis: dict[str, tuple[Anmeldungsknoten, ...]] = {}
        for kategorie, zeilen in je_kategorie.items():
            je_basisname = _gruppieren(zeilen, lambda a: _basisname_und_dauer(a.schulungstyp)[0])
            ergebnis[kategorie] = tuple(
                _basisname_knoten(basisname, gruppe)
                for basisname, gruppe in _nach_juengstem_jahr_und_name_mit_anmeldungen(je_basisname)
            )
        return ergebnis

    def je_monat(self) -> dict[Monat, int]:
        """Summe der Teilnehmerzahl je Monat, ueber alle Schulungstypen hinweg."""
        return _teilnehmerzahl_je(self.anmeldungen, lambda a: a.schluessel)

    def je_monat_und_typ(self, schulungstyp: str) -> dict[Monat, int]:
        """Teilnehmerzahl je Monat fuer einen einzelnen Schulungstyp."""
        return _teilnehmerzahl_je(
            (a for a in self.anmeldungen if a.schulungstyp == schulungstyp),
            lambda a: a.schluessel,
        )

    def summe_je_basisname(self) -> dict[str, int]:
        """Teilnehmerzahl je Basisname (siehe :func:`_basisname_und_dauer`), ueber den
        gesamten abgedeckten Zeitraum - Dauer-Varianten wie "CSPO 2-tägig"/"CSPO
        3-tägig" zaehlen hier zusammen auf "CSPO", derselbe Zusammenfassungsschritt
        wie in der Basisname-Ebene von :meth:`gliederung_je_kategorie`."""
        return _teilnehmerzahl_je(
            self.anmeldungen,
            lambda a: _basisname_und_dauer(a.schulungstyp)[0],
        )

    @property
    def basisnamen(self) -> tuple[str, ...]:
        """Alle vorkommenden Basisnamen (Dauer-Varianten zusammengefasst, siehe
        :meth:`summe_je_basisname`), nach absteigender Gesamtteilnehmerzahl - derselbe
        Auffangmechanismus wie :attr:`schulungstypen`, fuer den Schulungen-Filter der
        Webapp, der dieselbe Zusammenfassung wie der Tabellen-Drilldown zeigt statt
        einzelner Dauer-Varianten."""
        summen = self.summe_je_basisname()
        return tuple(sorted(summen, key=lambda name: summen[name], reverse=True))

    def je_monat_und_basisname(self, basisname: str) -> dict[Monat, int]:
        """Teilnehmerzahl je Monat fuer einen Basisnamen, ueber alle seine Dauer-
        Varianten hinweg (siehe :meth:`summe_je_basisname`)."""
        return _teilnehmerzahl_je(
            (a for a in self.anmeldungen if _basisname_und_dauer(a.schulungstyp)[0] == basisname),
            lambda a: a.schluessel,
        )

    def basisnamen_je_kategorie(self, kategorien: Kategorisierung) -> dict[str, tuple[str, ...]]:
        """Die vorkommenden Basisnamen je Kategorie, jeweils nach absteigender
        Gesamtteilnehmerzahl ihres jeweils staerksten Schulungstyps (wie
        :meth:`schulungstypen_je_kategorie`, aber mit zusammengefassten Dauer-
        Varianten) - fuer die Webapp, um die Auswahlmoeglichkeiten des Schulungen-
        Filters auf die gerade gewaehlten Kategorien einzuschraenken, analog zu
        :meth:`schulungstypen_je_kategorie`.

        Dieselbe Reihenfolge und derselbe ``KATEGORIE_SONSTIGE``-Auffangmechanismus wie
        bei :meth:`schulungstypen_je_kategorie` - eine Kategorie ohne Anmeldung in
        diesem Zeitraum liefert eine leere Tupel statt zu fehlen.
        """
        zuordnung = _kategorie_zuordnung(kategorien)
        ergebnis: dict[str, list[str]] = {name: [] for name in (*kategorien, KATEGORIE_SONSTIGE)}
        gesehen: dict[str, set[str]] = {name: set() for name in ergebnis}
        for typ in self.schulungstypen:
            basisname = _basisname_und_dauer(typ)[0]
            kategorie = zuordnung.get(basisname, KATEGORIE_SONSTIGE)
            if basisname not in gesehen[kategorie]:
                gesehen[kategorie].add(basisname)
                ergebnis[kategorie].append(basisname)
        return {kategorie: tuple(namen) for kategorie, namen in ergebnis.items()}

    @property
    def formate(self) -> tuple[str, ...]:
        """Alle vorkommenden, tatsaechlich befuellten Formate (Praesenz/Online, siehe
        :attr:`Anmeldung.format`), nach absteigender Gesamtteilnehmerzahl - derselbe
        Auffangmechanismus wie :attr:`schulungstypen`, fuer den Format-Filter der
        Webapp (siehe ``webapp/templates/schulungen.html``). Eine leere ``format``-
        Angabe (Quelle ohne Wert) zaehlt nicht als eigene Auspraegung."""
        summen = _teilnehmerzahl_je((a for a in self.anmeldungen if a.format), lambda a: a.format)
        return tuple(sorted(summen, key=lambda format_wert: summen[format_wert], reverse=True))

    def je_monat_und_format(self, format_wert: str) -> dict[Monat, int]:
        """Teilnehmerzahl je Monat fuer ein einzelnes Format (Praesenz/Online), ueber
        alle Kategorien und Schulungstypen hinweg."""
        return _teilnehmerzahl_je(
            (a for a in self.anmeldungen if a.format == format_wert),
            lambda a: a.schluessel,
        )

    @property
    def dauern(self) -> tuple[str, ...]:
        """Alle vorkommenden, erkannten Dauer-Auspraegungen (siehe :func:`_dauer`, bevorzugt
        aus ``datum`` berechnet, sonst aus dem Schulungstyp-Suffix), nach absteigender
        Gesamtteilnehmerzahl - derselbe Auffangmechanismus wie :attr:`schulungstypen`,
        fuer den Dauer-Filter der Webapp. Eine Anmeldung ohne erkennbare Dauer traegt
        nicht zu dieser Liste bei."""
        summen: Counter[str] = Counter()
        for a in self.anmeldungen:
            dauer = _dauer(a)
            if dauer is not None:
                summen[dauer] += a.teilnehmerzahl
        return tuple(sorted(summen, key=lambda dauer_wert: summen[dauer_wert], reverse=True))

    def je_monat_und_dauer(self, dauer_wert: str) -> dict[Monat, int]:
        """Teilnehmerzahl je Monat fuer eine einzelne, erkannte Dauer-Auspraegung
        (z. B. ``"2-tägig"``), ueber alle Kategorien, Schulungstypen und Formate
        hinweg."""
        return _teilnehmerzahl_je(
            (a for a in self.anmeldungen if _dauer(a) == dauer_wert),
            lambda a: a.schluessel,
        )

    def je_monat_gefiltert(
        self,
        *,
        kategorien: Kategorisierung | None = None,
        kategorie: str | None = None,
        basisname: str | None = None,
        format_wert: str | None = None,
        dauer_wert: str | None = None,
    ) -> dict[Monat, int]:
        """Teilnehmerzahl je Monat, gleichzeitig (UND-verknuepft) eingeschraenkt auf
        eine beliebige Kombination der uebrigen ``je_monat_und_*``-Kriterien - Grundlage
        fuer die kombinierbaren Filter-Dropdowns der Webapp (siehe
        ``webapp.app._anmeldungsreihen``), die z. B. Basisname UND Dauer gleichzeitig
        einschraenken sollen ("CSPO 2-tägig" statt getrennter "CSPO"- und
        "2-tägig"-Linien). Jedes Kriterium ist optional (``None`` = keine Einschraenkung
        auf dieser Achse); ``kategorie`` setzt ``kategorien`` voraus, dieselbe Zuordnung
        wie bei :meth:`je_monat_und_kategorie`."""
        if kategorie is not None and kategorien is None:
            msg = "kategorie setzt kategorien voraus"
            raise ValueError(msg)
        zuordnung = _kategorie_zuordnung(kategorien) if kategorien is not None else {}

        def passt(a: Anmeldung) -> bool:
            basis = _basisname_und_dauer(a.schulungstyp)[0]
            if kategorie is not None and zuordnung.get(basis, KATEGORIE_SONSTIGE) != kategorie:
                return False
            if basisname is not None and basis != basisname:
                return False
            if dauer_wert is not None and _dauer(a) != dauer_wert:
                return False
            return format_wert is None or a.format == format_wert

        return _teilnehmerzahl_je((a for a in self.anmeldungen if passt(a)), lambda a: a.schluessel)

    def schulungstypen_je_kategorie(
        self,
        kategorien: Kategorisierung,
    ) -> dict[str, tuple[str, ...]]:
        """Die vorkommenden Schulungstypen je Kategorie, jeweils nach absteigender
        Gesamtteilnehmerzahl (wie :attr:`schulungstypen`) - fuer die Webapp, um die
        Auswahlmoeglichkeiten des Schulungen-Filters auf die gerade gewaehlten
        Kategorien einzuschraenken (siehe ``webapp/app.py``), ohne dass diese
        Einschraenkung selbst Fachlogik waere.

        Dieselbe Reihenfolge und derselbe ``KATEGORIE_SONSTIGE``-Auffangmechanismus wie
        bei :meth:`je_monat_und_kategorie` - eine Kategorie ohne Anmeldung in diesem
        Zeitraum liefert eine leere Tupel statt zu fehlen.
        """
        zuordnung = _kategorie_zuordnung(kategorien)
        ergebnis: dict[str, list[str]] = {name: [] for name in (*kategorien, KATEGORIE_SONSTIGE)}
        for typ in self.schulungstypen:
            basisname = _basisname_und_dauer(typ)[0]
            ergebnis[zuordnung.get(basisname, KATEGORIE_SONSTIGE)].append(typ)
        return {kategorie: tuple(typen) for kategorie, typen in ergebnis.items()}

    def letzte(self, *, monate: int, stichtag: date) -> Anmeldungsverlauf:
        """Nur die ``monate`` Kalendermonate bis einschliesslich des Stichtagsmonats.

        ``monate`` ist keyword-only, damit an der Aufrufstelle sofort lesbar ist, was
        die Zahl bedeutet (``letzte(monate=13, ...)`` statt einer nackten ``13``).
        Grundlage fuer einen konfigurierbaren Betrachtungszeitraum im Diagramm (etwa die
        letzten 13 Monate ab heute, inklusive des laufenden Monats) -
        :func:`~umsatzprognose.darstellung.diagramme.anmeldungsverlauf` wendet selbst
        kein Zeitfenster an, sondern zeigt den Verlauf unveraendert.
        """
        ende = ordnung(stichtag.year, stichtag.month)
        start = ende - (monate - 1)
        gefiltert = tuple(a for a in self.anmeldungen if start <= ordnung(a.jahr, a.monat) <= ende)
        return type(self)(anmeldungen=gefiltert, abbildungshinweise=self.abbildungshinweise)

    def ab_jahr(self, jahr: int) -> Anmeldungsverlauf:
        """Nur die Anmeldungen ab (einschliesslich) dem angegebenen Jahr.

        Anders als :meth:`letzte` kein rollierendes Fenster relativ zu einem Stichtag,
        sondern ein fester Beginn - Grundlage fuer einen waehlbaren Betrachtungsbeginn
        (etwa "seit 2022"), der schmaler sein kann als der insgesamt geladene Zeitraum,
        ohne dass dafuer neu geladen werden muesste (siehe
        :class:`~umsatzprognose.webapp.cache.AnmeldungsverlaufCache`).
        """
        gefiltert = tuple(a for a in self.anmeldungen if a.jahr >= jahr)
        return type(self)(anmeldungen=gefiltert, abbildungshinweise=self.abbildungshinweise)

    def nur_jahre(self, jahre: Collection[int]) -> Anmeldungsverlauf:
        """Nur die Anmeldungen genau eines der angegebenen Jahre.

        Anders als :meth:`ab_jahr` kein zusammenhaengender Beginn, sondern eine
        beliebige Teilmenge einzelner Kalenderjahre - Grundlage fuer die Jahres-Auswahl
        des Anmeldungsverlauf-Diagramms der Webapp (siehe ``webapp/app.py``), die im
        Gegensatz zu ``ab_jahr`` nur das Diagramm, nicht die Schulungsdetails-Tabelle
        einschraenkt.
        """
        gefiltert = tuple(a for a in self.anmeldungen if a.jahr in jahre)
        return type(self)(anmeldungen=gefiltert, abbildungshinweise=self.abbildungshinweise)
