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

**Keine Kategorisierung im Diagramm mehr** (eine fruehere Fassung gruppierte dort per
von Hand gepflegter Zuordnung nach Scrum/Kanban/Sonstige, siehe Spec Abschnitt 9) - als
Liniendiagramm mit einer Linie je Kategorie veraltete das unbemerkt, sobald neue
Schulungstypen dazukamen. Primaer zaehlt dort nur noch die Gesamtzahl je Monat (siehe
:meth:`Anmeldungsverlauf.je_monat`). Dieselbe Kategorisierung bleibt aber als Drilldown
hinter der Gesamtzahl erhalten, weiterhin je Monat aufgeschluesselt
(:meth:`Anmeldungsverlauf.je_monat_und_kategorie`) - als Tabelle faellt eine
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

from collections import Counter
from dataclasses import dataclass, field

from umsatzprognose.util import ordnung

KATEGORIE_SONSTIGE = "Sonstige"


def _kategorie_zuordnung(kategorien: Kategorisierung) -> dict[str, str]:
    """Kehrt eine Kategorie-zu-Schulungstypen-Zuordnung zu einer Schulungstyp-zu-Kategorie-
    Zuordnung um - fuer den Nachschlag je Anmeldung."""
    return {typ: kategorie for kategorie, typen in kategorien.items() for typ in typen}


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


@dataclass(frozen=True)
class Anmeldung:
    """Teilnehmerzahl eines Schulungstyps in einem Monat - eine Zeile der Quelltabelle."""

    jahr: int
    monat: int
    schulungstyp: str
    teilnehmerzahl: int

    @property
    def schluessel(self) -> Monat:
        return (self.jahr, self.monat)


@dataclass(frozen=True)
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

    def je_monat(self) -> dict[Monat, int]:
        """Summe der Teilnehmerzahl je Monat, ueber alle Schulungstypen hinweg."""
        return _teilnehmerzahl_je(self.anmeldungen, lambda a: a.schluessel)

    def je_monat_und_typ(self, schulungstyp: str) -> dict[Monat, int]:
        """Teilnehmerzahl je Monat fuer einen einzelnen Schulungstyp."""
        return _teilnehmerzahl_je(
            (a for a in self.anmeldungen if a.schulungstyp == schulungstyp), lambda a: a.schluessel
        )

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
