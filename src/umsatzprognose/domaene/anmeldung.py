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

**Kategorisierung frei konfigurierbar** (:meth:`Anmeldungsverlauf.je_monat_und_kategorie`),
wie in der internen ZDF-Praesentation (dort Scrum/Kanban/Sonstige): eine von Hand
gepflegte Zuordnung einzelner Schulungstypen, keine Stichwortsuche - Zertifizierungen
laufen ueberwiegend ueber Kuerzel (``"CSM"``, ``"KSD"``, ...), nicht ueber
ausgeschriebene Woerter wie "Scrum"/"Kanban". Die Zuordnung selbst ist bewusst **keine
Konstante dieses Moduls**, sondern wird als Parameter uebergeben (typischerweise eine im
Notebook gepflegte ``dict[str, list[str]]``, siehe
``notebooks/03_schulungsanmeldungen.ipynb``) - welche Kategorien es gibt und welche
Schulungstypen dazuzaehlen, ist reine Konfiguration, keine Fachlogik. Ein Schulungstyp,
der in keiner Kategorie auftaucht, faellt auf :data:`KATEGORIE_SONSTIGE` zurueck.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import date

    from umsatzprognose.util import Monat

    from .hinweis import Hinweis

    Kategorisierung = Mapping[str, Sequence[str]]

from dataclasses import dataclass, field

from umsatzprognose.util import ordnung

KATEGORIE_SONSTIGE = "Sonstige"


def _kategorie_zuordnung(kategorien: Kategorisierung) -> dict[str, str]:
    """Kehrt eine Kategorie-zu-Schulungstypen-Zuordnung zu einer Schulungstyp-zu-Kategorie-
    Zuordnung um - fuer den Nachschlag je Anmeldung."""
    return {typ: kategorie for kategorie, typen in kategorien.items() for typ in typen}


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
        summen: dict[str, int] = {}
        for a in self.anmeldungen:
            summen[a.schulungstyp] = summen.get(a.schulungstyp, 0) + a.teilnehmerzahl
        return tuple(sorted(summen, key=lambda typ: summen[typ], reverse=True))

    def je_monat(self) -> dict[Monat, int]:
        """Summe der Teilnehmerzahl je Monat, ueber alle Schulungstypen hinweg."""
        summen: dict[Monat, int] = {}
        for a in self.anmeldungen:
            summen[a.schluessel] = summen.get(a.schluessel, 0) + a.teilnehmerzahl
        return summen

    def je_monat_und_typ(self, schulungstyp: str) -> dict[Monat, int]:
        """Teilnehmerzahl je Monat fuer einen einzelnen Schulungstyp."""
        summen: dict[Monat, int] = {}
        for a in self.anmeldungen:
            if a.schulungstyp == schulungstyp:
                summen[a.schluessel] = summen.get(a.schluessel, 0) + a.teilnehmerzahl
        return summen

    def je_monat_und_kategorie(self, kategorien: Kategorisierung) -> dict[str, dict[Monat, int]]:
        """Teilnehmerzahl je Monat, gruppiert nach den uebergebenen Kategorien.

        ``kategorien`` bildet Kategoriename auf die zugehoerigen Schulungstypen ab
        (siehe Moduldocstring) - ein Schulungstyp, der in keiner Kategorie auftaucht,
        landet unter :data:`KATEGORIE_SONSTIGE`. Das Ergebnis traegt genau die
        uebergebenen Kategorien in ihrer Reihenfolge, plus ``KATEGORIE_SONSTIGE`` am
        Ende - auch dann, wenn eine Kategorie in diesem Zeitraum keine Anmeldung hat.
        """
        zuordnung = _kategorie_zuordnung(kategorien)
        ergebnis: dict[str, dict[Monat, int]] = {
            name: {} for name in (*kategorien, KATEGORIE_SONSTIGE)
        }
        for a in self.anmeldungen:
            summen = ergebnis[zuordnung.get(a.schulungstyp, KATEGORIE_SONSTIGE)]
            summen[a.schluessel] = summen.get(a.schluessel, 0) + a.teilnehmerzahl
        return ergebnis

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
