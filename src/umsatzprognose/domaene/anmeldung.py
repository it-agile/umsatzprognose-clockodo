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
faellt auf :data:`KATEGORIE_SONSTIGE` zurueck.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence
    from datetime import date

    from umsatzprognose.util import Monat

    from .hinweis import Hinweis

    Kategorisierung = Mapping[str, Sequence[str]]

import re
from collections import Counter
from dataclasses import dataclass, field

from umsatzprognose.util import ordnung

KATEGORIE_SONSTIGE = "Sonstige"

# Erkennt einen Dauer-Suffix wie "2-tägig"/"3-tägig" am Ende eines Schulungstyps (z. B.
# "CSPO 2-tägig" -> Basisname "CSPO", Dauer "2-tägig") - rein aus dem Text abgeleitet,
# ohne Konfiguration, siehe _basisname_und_dauer().
_DAUER_MUSTER = re.compile(r"^(?P<basis>.+?)\s+(?P<dauer>\d+-tägig)$")


def _kategorie_zuordnung(kategorien: Kategorisierung) -> dict[str, str]:
    """Kehrt eine Kategorie-zu-Schulungstypen-Zuordnung zu einer Schulungstyp-zu-Kategorie-
    Zuordnung um - fuer den Nachschlag je Anmeldung."""
    return {typ: kategorie for kategorie, typen in kategorien.items() for typ in typen}


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


def _teilnehmerzahl_je[K](
    anmeldungen: Iterable[Anmeldung], schluessel: Callable[[Anmeldung], K]
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
    """

    jahr: int
    monat: int
    schulungstyp: str
    teilnehmerzahl: int
    format: str = ""

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
    zeilen: Sequence[Anmeldung], schluessel: Callable[[Anmeldung], str]
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


def _mit_dauer_kindern(name: str, zeilen: Sequence[Anmeldung]) -> Anmeldungsknoten:
    """Ein Knoten mit Dauer-Kindern, falls ``zeilen`` mehr als eine (tatsaechlich
    besetzte) Dauer-Auspraegung zeigt, sonst ein Blatt ohne Kinder - die Dauer-Ebene
    erscheint nur bei tatsaechlicher Vielfalt, nicht als immer vorhandene
    Zwischenebene. Ein Schulungstyp ohne erkannten Dauer-Suffix behaelt seinen vollen
    Namen als Label, statt mit einem erfundenen Platzhalter aufzutauchen."""
    dauer_gruppen = _gruppieren(
        zeilen, lambda a: _basisname_und_dauer(a.schulungstyp)[1] or a.schulungstyp
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
            summen = ergebnis[zuordnung.get(a.schulungstyp, KATEGORIE_SONSTIGE)]
            summen[a.schluessel] += a.teilnehmerzahl
        return ergebnis

    def gliederung_je_kategorie(
        self, kategorien: Kategorisierung
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
        Basisname-, Format- und Dauer-Knoten sind alphabetisch sortiert (anders als
        :attr:`schulungstypen`/:attr:`formate`/:attr:`dauern` nach absteigender
        Gesamtteilnehmerzahl) - im Tabellen-Drilldown soll man einen bekannten Namen
        alphabetisch wiederfinden, nicht nach Anmeldezahl suchen muessen; eine
        Kategorie ohne Anmeldung in diesem Zeitraum liefert dagegen weiterhin eine
        leere Tupel statt zu fehlen (derselbe Auffangmechanismus wie bei
        :meth:`je_monat_und_kategorie`).
        """
        zuordnung = _kategorie_zuordnung(kategorien)
        je_kategorie: dict[str, list[Anmeldung]] = {
            name: [] for name in (*kategorien, KATEGORIE_SONSTIGE)
        }
        for a in self.anmeldungen:
            je_kategorie[zuordnung.get(a.schulungstyp, KATEGORIE_SONSTIGE)].append(a)

        ergebnis: dict[str, tuple[Anmeldungsknoten, ...]] = {}
        for kategorie, zeilen in je_kategorie.items():
            je_basisname = _gruppieren(zeilen, lambda a: _basisname_und_dauer(a.schulungstyp)[0])
            ergebnis[kategorie] = tuple(
                _basisname_knoten(basisname, gruppe)
                for basisname, gruppe in _alphabetisch_mit_anmeldungen(je_basisname)
            )
        return ergebnis

    def je_monat(self) -> dict[Monat, int]:
        """Summe der Teilnehmerzahl je Monat, ueber alle Schulungstypen hinweg."""
        return _teilnehmerzahl_je(self.anmeldungen, lambda a: a.schluessel)

    def je_monat_und_typ(self, schulungstyp: str) -> dict[Monat, int]:
        """Teilnehmerzahl je Monat fuer einen einzelnen Schulungstyp."""
        return _teilnehmerzahl_je(
            (a for a in self.anmeldungen if a.schulungstyp == schulungstyp), lambda a: a.schluessel
        )

    def summe_je_basisname(self) -> dict[str, int]:
        """Teilnehmerzahl je Basisname (siehe :func:`_basisname_und_dauer`), ueber den
        gesamten abgedeckten Zeitraum - Dauer-Varianten wie "CSPO 2-tägig"/"CSPO
        3-tägig" zaehlen hier zusammen auf "CSPO", derselbe Zusammenfassungsschritt
        wie in der Basisname-Ebene von :meth:`gliederung_je_kategorie`."""
        return _teilnehmerzahl_je(
            self.anmeldungen, lambda a: _basisname_und_dauer(a.schulungstyp)[0]
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
            kategorie = zuordnung.get(typ, KATEGORIE_SONSTIGE)
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
            (a for a in self.anmeldungen if a.format == format_wert), lambda a: a.schluessel
        )

    @property
    def dauern(self) -> tuple[str, ...]:
        """Alle vorkommenden, erkannten Dauer-Auspraegungen (siehe
        :func:`_basisname_und_dauer`), nach absteigender Gesamtteilnehmerzahl -
        derselbe Auffangmechanismus wie :attr:`schulungstypen`, fuer den Dauer-Filter
        der Webapp. Ein Schulungstyp ohne erkannten Dauer-Suffix traegt nicht zu dieser
        Liste bei."""
        summen: Counter[str] = Counter()
        for a in self.anmeldungen:
            dauer = _basisname_und_dauer(a.schulungstyp)[1]
            if dauer is not None:
                summen[dauer] += a.teilnehmerzahl
        return tuple(sorted(summen, key=lambda dauer_wert: summen[dauer_wert], reverse=True))

    def je_monat_und_dauer(self, dauer_wert: str) -> dict[Monat, int]:
        """Teilnehmerzahl je Monat fuer eine einzelne, erkannte Dauer-Auspraegung
        (z. B. ``"2-tägig"``), ueber alle Kategorien, Schulungstypen und Formate
        hinweg."""
        return _teilnehmerzahl_je(
            (a for a in self.anmeldungen if _basisname_und_dauer(a.schulungstyp)[1] == dauer_wert),
            lambda a: a.schluessel,
        )

    def schulungstypen_je_kategorie(
        self, kategorien: Kategorisierung
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
            ergebnis[zuordnung.get(typ, KATEGORIE_SONSTIGE)].append(typ)
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
