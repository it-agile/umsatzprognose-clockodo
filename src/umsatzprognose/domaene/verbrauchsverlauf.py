"""Verbrauchsverlauf - was ein Projekt Monat fuer Monat abgerufen hat.

Die Grundlage der Abrufquote-Schaetzung und der Ort, an dem zwei
wichtige Punkte sitzen: die **Rueckrechnung** des Restvolumens auf einen vergangenen
Monatsbeginn und die Frage, welche Monate ueberhaupt als Beobachtung zaehlen.

**Das Restvolumen zu einem vergangenen Monatsbeginn wird zurueckgerechnet**, weil es
nicht gespeichert ist:

    Restvolumen(Monatsbeginn) = Budget_heute - Verbrauch aller Monate davor

**Derselbe Verlauf traegt einen zweiten Zweck.** Die Simulationslogik braucht je Projekt und
Horizontmonat den *bereits gebuchten* Betrag als Untergrenze der Bandbreite; das ist
:meth:`Verbrauchsverlauf.gebucht` auf einen Monat nach dem Stichtag.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import date

    from .projekt import Projekt

from dataclasses import dataclass

from umsatzprognose.util import aus_ordnung, ordnung

from .abrufquote import Abrufquote
from .umsatzhistorie import Monatsumsatz


@dataclass(frozen=True)
class Verbrauchsverlauf:
    """Die Monate eines Projekts mit Buchung, chronologisch und ohne Doppelte.

    Attributes:
        monate: nur Monate, in denen etwas gebucht wurde. Die Luecken dazwischen
            entstehen in :meth:`beobachtungsmonate` - sie gehoeren zur Deutung und nicht
            zu den Daten.
    """

    projekt: Projekt
    monate: tuple[Monatsumsatz, ...] = ()

    @classmethod
    def fuer(cls, projekt: Projekt, monate: Iterable[Monatsumsatz]) -> Verbrauchsverlauf:
        """Sortiert die Monate und fasst doppelte Schluessel zusammen."""
        gesammelt: dict[tuple[int, int], Monatsumsatz] = {}
        for monat in monate:
            vorhanden = gesammelt.get(monat.schluessel)
            gesammelt[monat.schluessel] = (
                monat
                if vorhanden is None
                else Monatsumsatz(
                    jahr=monat.jahr,
                    monat=monat.monat,
                    umsatz=vorhanden.umsatz + monat.umsatz,
                    stunden=vorhanden.stunden + monat.stunden,
                )
            )
        return cls(
            projekt=projekt,
            monate=tuple(gesammelt[schluessel] for schluessel in sorted(gesammelt)),
        )

    def __str__(self) -> str:
        return f"{self.projekt.bezeichnung}: {len(self.monate)} Monate mit Buchung"

    @property
    def erster_monat(self) -> tuple[int, int] | None:
        return self.monate[0].schluessel if self.monate else None

    @property
    def letzter_monat(self) -> tuple[int, int] | None:
        return self.monate[-1].schluessel if self.monate else None

    @property
    def verbrauch(self) -> float:
        """Der gesamte Verbrauch des Verlaufs - Pruefsumme gegen das Projekt."""
        return sum(monat.umsatz for monat in self.monate)

    def gebucht(self, jahr: int, monat: int) -> float:
        """Der in diesem Monat gebuchte Umsatz; 0, wenn nichts gebucht wurde.

        Hier ist 0 die richtige Antwort und nicht ``None``: ein Monat ohne Buchung ist
        ein Monat ohne Abruf. Fuer einen Monat **nach** dem Stichtag ist derselbe Wert
        die Untergrenze der Bandbreite.
        """
        for eintrag in self.monate:
            if eintrag.schluessel == (jahr, monat):
                return eintrag.umsatz
        return 0.0

    def verbrauch_vor(self, jahr: int, monat: int) -> float:
        """Summierter Verbrauch aller Monate **vor** diesem - der Blick auf Monatsbeginn."""
        grenze = ordnung(jahr, monat)
        return sum(
            eintrag.umsatz for eintrag in self.monate if ordnung(*eintrag.schluessel) < grenze
        )

    def restvolumen_zu_monatsbeginn(self, jahr: int, monat: int) -> float | None:
        """Das aus dem heutigen Budget zurueckgerechnete Restvolumen.

        ``None``, wenn das Projekt kein bezifferbares Auftragsvolumen hat - dann
        gibt es kein Restvolumen, und eine 0 waere eine andere Aussage. Der Wert ist
        vorzeichenbehaftet: ein historisch ueberschrittenes Budget ergibt hier negativ,
        und solche Monate sind keine Beobachtung.
        """
        auftragsvolumen = self.projekt.auftragsvolumen
        if auftragsvolumen is None:
            return None
        return auftragsvolumen - self.verbrauch_vor(jahr, monat)

    def beobachtungsmonate(self, stichtag: date) -> tuple[tuple[int, int], ...]:
        """Die Monate, die als Beobachtung in Frage kommen - lueckenlos.

        Die Regel steht im Modulkopf. Ob ein Monat es dann wirklich wird, entscheidet
        das Restvolumen zu seinem Beginn (:meth:`abrufquoten`).
        """
        beginn = self.erster_monat
        if beginn is None:
            return ()

        # Der Stichtagsmonat ist angebrochen und zaehlt nie mit; ein beendetes Projekt
        # endet zusaetzlich mit seiner letzten Buchung. Buchungen nach dem Stichtag
        # gehoeren zum Horizont und nicht zur Historie - deshalb das Minimum.
        letzter_vollstaendiger = ordnung(stichtag.year, stichtag.month) - 1
        ende = letzter_vollstaendiger
        if not self.projekt.im_prognose_scope and self.letzter_monat is not None:
            ende = min(ende, ordnung(*self.letzter_monat))

        return tuple(aus_ordnung(o) for o in range(ordnung(*beginn), ende + 1))

    def abrufquoten(self, stichtag: date) -> tuple[Abrufquote, ...]:
        """Die Beobachtungen dieses Projekts fuer die Verteilung.

        Ausgelassen werden Monate mit einem Restvolumen von 0 oder darunter: die Quote
        waere undefiniert, nicht 0. Quoten ueber 1 bleiben dagegen stehen - Budgets sind
        weiche Grenzen, und gekappt wird erst in der Simulation.
        """
        auftragsvolumen = self.projekt.auftragsvolumen
        fenster = self.beobachtungsmonate(stichtag)
        if auftragsvolumen is None or not fenster:
            return ()

        # Einmal durch das Fenster mit laufender Summe, statt je Monat neu zu summieren:
        # ueber einige tausend Projekt-Monate hinweg ist der Unterschied zwischen
        # linear und quadratisch spuerbar, und die Verteilung wird bei jeder Ansicht
        # neu gebildet.
        gebucht = {monat.schluessel: monat.umsatz for monat in self.monate}
        verbraucht = self.verbrauch_vor(*fenster[0])
        quoten: list[Abrufquote] = []
        for jahr, monat in fenster:
            restvolumen = auftragsvolumen - verbraucht
            verbrauch = gebucht.get((jahr, monat), 0.0)
            verbraucht += verbrauch
            if restvolumen <= 0:
                continue
            quoten.append(
                Abrufquote(
                    projekt=self.projekt,
                    jahr=jahr,
                    monat=monat,
                    verbrauch=verbrauch,
                    restvolumen_zu_monatsbeginn=restvolumen,
                )
            )
        return tuple(quoten)
