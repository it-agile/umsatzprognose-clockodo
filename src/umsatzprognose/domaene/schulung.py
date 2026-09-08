"""Schulungsanmeldungen - Umsatz aus bereits geplanten oeffentlichen Schulungsterminen.

**Additiv und unabhaengig von der Bestand-Simulation**: kein Monte-Carlo-Lauf,
keine Bandbreite - der Betrag je Termin steht in der externen Planungstabelle schon fest.
Die einzige Unsicherheit ist die Pflegequalitaet der Quelle selbst, nicht ein
stochastisches Modell. Deshalb nimmt :meth:`Schulungsplan.umsatz_je_monat` die
Horizontmonate als Parameter entgegen, statt selbst eine Horizontlaenge zu kennen - der
Baustein bleibt so unabhaengig von :class:`~umsatzprognose.domaene.prognose.Prognose`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import date

    from umsatzprognose.util import Monat

    from .hinweis import Hinweis

from dataclasses import dataclass, field
from decimal import Decimal

from .umsatzhistorie import betrag_je_monat, hinweise_mit_fehlenden_monaten


@dataclass(frozen=True)
class Schulungstermin:
    """Ein Termin einer oeffentlichen Schulung - nur die fuer die Prognose relevanten Felder.

    Teilnehmerzahlen, Rabattstufen, Trainer- und Praesenz/Online-Angaben sowie der
    Bemerkungsfreitext (u. a. ein moeglicher Stornogrund) sind nicht Teil des Modells.
    """

    jahr: int
    monat: int
    umsatz: Decimal

    @property
    def schluessel(self) -> Monat:
        return (self.jahr, self.monat)


@dataclass(frozen=True)
class Schulungsplan:
    """Alle geladenen Schulungstermine zu einem Stichtag.

    Attributes:
        abbildungshinweise: Befunde aus dem Laden der Google-Sheets-Dateien - fehlende
            Konfiguration fuer ein Jahr, eine nicht lesbare Datei. Siehe
            :meth:`~umsatzprognose.schulungen.schulungen.SchulungenRepository.laden`.
    """

    stichtag: date
    termine: tuple[Schulungstermin, ...] = ()
    abbildungshinweise: tuple[Hinweis, ...] = field(default_factory=tuple)

    def _relevante_termine(self) -> tuple[Schulungstermin, ...]:
        """Nur Monate ab dem Stichtagsmonat - Vergangenes ist bereits Ist-Umsatz."""
        grenze = (self.stichtag.year, self.stichtag.month)
        return tuple(t for t in self.termine if t.schluessel >= grenze)

    def umsatz_je_monat(self, horizontmonate: Sequence[Monat]) -> list[Decimal]:
        """Summe von ``Umsatz gesamt`` je uebergebenem Monat, 0 ohne passenden Termin."""
        return betrag_je_monat(self._relevante_termine(), horizontmonate, betrag=lambda t: t.umsatz)

    def summe(self, horizontmonate: Sequence[Monat]) -> Decimal:
        return sum(self.umsatz_je_monat(horizontmonate), Decimal("0"))

    def hinweise(self, horizontmonate: Sequence[Monat]) -> tuple[Hinweis, ...]:
        """Befunde aus der Abbildung, plus fehlende Horizontmonate.

        Ob ein Monat fehlt, weil die Datei nicht geladen wurde, oder weil sie geladen
        ist, aber keinen Termin fuer diesen Monat enthaelt, sieht fuer den Leser gleich
        aus - beides ist kein Fehler, sondern eine Datenluecke, die sich in 0
        niederschlaegt.
        """
        vorhanden = {t.schluessel for t in self._relevante_termine()}
        return hinweise_mit_fehlenden_monaten(
            self.abbildungshinweise,
            text="Für diese Monate liegt keine Schulungsanmeldung vor - der Umsatz aus "
            "Schulungsanmeldungen wird mit 0 angenommen",
            monate=horizontmonate,
            vorhandene_monate=vorhanden,
        )
