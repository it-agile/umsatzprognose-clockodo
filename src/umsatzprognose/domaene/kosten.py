"""Kostenprognose - Gesamtkosten je Monat aus einer externen Planungstabelle.

**Additiv und unabhaengig von der Bestand-Simulation**, wie
:mod:`umsatzprognose.domaene.schulung`: kein Monte-Carlo-Lauf, keine Bandbreite - der
Betrag je Monat steht in der externen Kostenplanung schon fest.

**Anders als der Schulungsplan gilt die Kostenprognose auch fuer bereits vergangene und
den laufenden Monat**, nicht nur fuer den Prognosehorizont: Clockodo liefert keine
Ist-Kosten, nur Umsaetze aus Einsaetzen, also gibt es keine andere Quelle fuer
Vergangenheitsmonate. :class:`Kostenplan` filtert deshalb, anders als
:class:`~umsatzprognose.domaene.schulung.Schulungsplan`, nicht nach einem Stichtag -
welche Monate gebraucht werden, entscheidet allein der Aufrufer ueber die an
:meth:`Kostenplan.kosten_je_monat` uebergebenen Monate.

**Gesichert oder Pauschale:** Die Quelle traegt die Kostenpauschale, bis die Kosten eines
Monats gesichert sind, und stellt den Betrag dann um. Ob ein einzelner Monat noch der
Pauschale entspricht, sagt :attr:`Kostenposten.entspricht_pauschale`; welche Monate als
gesichert gelten, entscheidet :meth:`Kostenplan.kostenstatus_je_monat` rueckwaertsblickend
(siehe dort).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Sequence

    from umsatzprognose.util import Monat

    from .hinweis import Hinweis

from dataclasses import dataclass, field
from decimal import Decimal

from .umsatzhistorie import betrag_je_monat, hinweise_mit_fehlenden_monaten

Kostenstatus = Literal["gesichert", "pauschale", "unbekannt"]


@dataclass(frozen=True, slots=True)
class Kostenposten:
    """Die Kosten eines Kalendermonats laut Kostenplanungstabelle.

    ``kosten`` ist der Betrag, wie ihn die Quelle ausweist. ``entspricht_pauschale``
    sagt, ob dieser Betrag noch der ursprünglich geplanten Kostenpauschale gleicht - dann
    steht der Monat in der Quelle noch nicht auf gesicherten Kosten.
    """

    jahr: int
    monat: int
    kosten: Decimal
    entspricht_pauschale: bool = False

    @property
    def schluessel(self) -> Monat:
        return (self.jahr, self.monat)


@dataclass(frozen=True, slots=True)
class Kostenplan:
    """Alle geladenen Kostenposten.

    Attributes:
        abbildungshinweise: Befunde aus dem Laden der Google-Sheets-Dateien - fehlende
            Konfiguration fuer ein Jahr, eine nicht lesbare Datei. Siehe
            :meth:`~umsatzprognose.kosten.kosten.KostenRepository.laden`.
    """

    posten: tuple[Kostenposten, ...] = ()
    abbildungshinweise: tuple[Hinweis, ...] = field(default_factory=tuple)

    def kosten_je_monat(self, monate: Sequence[Monat]) -> list[Decimal]:
        """Gesamtkosten je uebergebenem Monat, 0 ohne passenden Posten."""
        return betrag_je_monat(self.posten, monate, betrag=lambda p: p.kosten)

    def summe(self, monate: Sequence[Monat]) -> Decimal:
        return sum(self.kosten_je_monat(monate), Decimal("0"))

    def kostenstatus_je_monat(self, monate: Sequence[Monat]) -> list[Kostenstatus]:
        """Je Monat, ob seine Kosten gesichert sind, noch auf der Pauschale beruhen oder
        unbekannt sind (kein Posten) - Grundlage fuer die Darstellung.

        Rueckwaertsblickend: die Pauschale-Monate bilden nur den Block am Ende. Der
        letzte Monat, dessen Betrag nicht mehr der Pauschale entspricht, und alle Monate
        davor gelten als gesichert - auch aeltere Monate, deren Betrag in der Quelle nie
        umgestellt wurde. Gibt es keinen solchen Monat, beruht jeder Monat mit Posten
        auf der Pauschale.
        """
        grenze = max(
            (p.schluessel for p in self.posten if not p.entspricht_pauschale), default=None
        )
        vorhanden = {p.schluessel for p in self.posten}
        return [
            "unbekannt"
            if monat not in vorhanden
            else "gesichert"
            if grenze is not None and monat <= grenze
            else "pauschale"
            for monat in monate
        ]

    def hinweise(self, monate: Sequence[Monat]) -> tuple[Hinweis, ...]:
        """Befunde aus der Abbildung, plus fehlende Monate.

        Ob ein Monat fehlt, weil die Datei nicht geladen wurde, oder weil sie geladen
        ist, aber keinen Posten fuer diesen Monat enthaelt, sieht fuer den Leser gleich
        aus - beides ist kein Fehler, sondern eine Datenluecke, die sich in 0
        niederschlaegt.
        """
        vorhanden = {p.schluessel for p in self.posten}
        return hinweise_mit_fehlenden_monaten(
            self.abbildungshinweise,
            text="Für diese Monate liegt keine Kostenprognose vor - die Kosten werden mit "
            "0 angenommen",
            monate=monate,
            vorhandene_monate=vorhanden,
        )
