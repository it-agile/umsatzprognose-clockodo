"""Schulungsanmeldungen - Umsatz aus bereits geplanten oeffentlichen Schulungsterminen.

**Additiv und unabhaengig von der Bestand-Simulation** (Spec 5.4): kein Monte-Carlo-Lauf,
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

from .umsatzhistorie import fehlende_monate_hinweis


@dataclass(frozen=True)
class Schulungstermin:
    """Ein Termin einer oeffentlichen Schulung - nur die fuer die Prognose relevanten Felder.

    Teilnehmerzahlen, Rabattstufen, Trainer- und Praesenz/Online-Angaben sowie der
    Bemerkungsfreitext (u. a. ein moeglicher Stornogrund) sind nicht Teil des Modells,
    siehe Spec Abschnitt 2.
    """

    jahr: int
    monat: int
    umsatz: float

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
        """Nur Monate ab dem Stichtagsmonat - Vergangenes ist bereits Ist-Umsatz (Spec 5.2)."""
        grenze = (self.stichtag.year, self.stichtag.month)
        return tuple(t for t in self.termine if t.schluessel >= grenze)

    def umsatz_je_monat(self, horizontmonate: Sequence[Monat]) -> list[float]:
        """Summe von ``Umsatz gesamt`` je uebergebenem Monat, 0 ohne passenden Termin (Spec 5.1)."""
        summen: dict[Monat, float] = {}
        for termin in self._relevante_termine():
            summen[termin.schluessel] = summen.get(termin.schluessel, 0.0) + termin.umsatz
        return [summen.get(monat, 0.0) for monat in horizontmonate]

    def summe(self, horizontmonate: Sequence[Monat]) -> float:
        return sum(self.umsatz_je_monat(horizontmonate))

    def hinweise(self, horizontmonate: Sequence[Monat]) -> tuple[Hinweis, ...]:
        """Befunde aus der Abbildung, plus fehlende Horizontmonate (Spec 6).

        Ob ein Monat fehlt, weil die Datei nicht geladen wurde, oder weil sie geladen
        ist, aber keinen Termin fuer diesen Monat enthaelt, sieht fuer den Leser gleich
        aus - beides ist kein Fehler, sondern eine Datenluecke, die sich in 0
        niederschlaegt.
        """
        vorhanden = {t.schluessel for t in self._relevante_termine()}
        fachlich = fehlende_monate_hinweis(
            "Für diese Monate liegt keine Schulungsanmeldung vor - der Umsatz aus "
            "Schulungsanmeldungen wird mit 0 angenommen",
            horizontmonate,
            vorhanden,
        )
        return self.abbildungshinweise + fachlich
