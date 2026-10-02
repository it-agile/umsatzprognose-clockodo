"""Projekte ohne Budget - ein historisch gespeister Bedarf statt eines Restvolumens.

Ein Projekt ohne bezifferbares Budget (:func:`~umsatzprognose.domaene.projekt.verwertbar`)
hat kein Restvolumen, aus dem sich eine Abrufquote ziehen liesse - es faellt aus der
Budget-Simulation (:attr:`~umsatzprognose.domaene.projekt.Projekt.im_prognose_scope`).
Tatsaechlich erzeugen manche dieser Projekte aber dauerhaft Umsatz (etwa ein laufendes
Coaching nach Stunden). :class:`OhneBudgetModell` beschreibt, welche davon in die
Prognose gehoeren und woher ihr Bedarf kommt:

- **Bedarf aus der eigenen Historie.** Je Lauf und Horizontmonat wird zufaellig einer
  der letzten :attr:`~OhneBudgetModell.historie_monate` abgeschlossenen Monate des
  Projekts gezogen und sein Umsatz fortgeschrieben - Monate ohne Buchung eingeschlossen.
  Haeufigkeit und Hoehe ergeben sich so aus derselben Ziehung: ein Projekt, das in einem
  von sechs Monaten gebucht wurde, traegt im Mittel nur ein Sechstel dieses Betrags bei.
- **Ausschluss.** Projekte, deren Name einen der :attr:`~OhneBudgetModell.ausschluss`-
  Bausteine enthaelt, werden nicht modelliert - etwa interne Projekte (ohne Umsatz) oder
  Projekte, deren Umsatz anderweitig feststeht.
- **Schulungen belegen Kapazitaet.** Projekte, die einen der
  :attr:`~OhneBudgetModell.schulung`-Bausteine enthalten, erzeugen hier keinen Umsatz
  (er steht ueber den Schulungsplan fest), ihre Stunden sind aber fakturierbar und
  stehen deshalb nicht als verfuegbare Kapazitaet zur Verfuegung
  (:meth:`~OhneBudgetModell.reservierte_stunden`).

Die Namensbausteine sind reine Konfiguration (Projektnamen gehoeren nicht ins
Repository) und werden per Teilstring gegen :attr:`Projekt.bezeichnung` geprueft, wie
der Projektfilter der Webapp.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .bestand import Bestand
    from .projekt import Projekt

from dataclasses import dataclass

import numpy as np

from umsatzprognose.util import aus_ordnung, ordnung

from .projekt import verwertbar

STANDARD_HISTORIE_MONATE = 6


@dataclass(frozen=True, slots=True)
class OhneBudgetModell:
    """Welche Projekte ohne Budget in die Prognose eingehen und aus welchem Fenster
    ihr Bedarf stammt.

    Attributes:
        ausschluss: Namensbausteine von Projekten, die gar nicht modelliert werden.
        schulung: Namensbausteine von Projekten, die keinen Umsatz erzeugen, aber
            Kapazitaet belegen. Gelten zugleich als ausgeschlossen.
        historie_monate: Laenge des Fensters abgeschlossener Monate, aus dem der Bedarf
            gezogen wird.
    """

    ausschluss: tuple[str, ...] = ()
    schulung: tuple[str, ...] = ()
    historie_monate: int = STANDARD_HISTORIE_MONATE

    def __post_init__(self) -> None:
        if self.historie_monate < 1:
            raise ValueError(
                f"historie_monate muss mindestens 1 sein, nicht {self.historie_monate}",
            )

    def ist_schulung(self, projekt: Projekt) -> bool:
        return _enthaelt(projekt, self.schulung)

    def ist_ausgeschlossen(self, projekt: Projekt) -> bool:
        return self.ist_schulung(projekt) or _enthaelt(projekt, self.ausschluss)

    def projekte(self, bestand: Bestand) -> tuple[Projekt, ...]:
        """Aktive, nicht abgeschlossene Projekte ohne bezifferbares Budget, die nicht
        ausgeschlossen sind - die Projekte, deren Bedarf die Simulation fortschreibt."""
        return tuple(
            p
            for p in bestand.aktive_projekte
            if not p.abgeschlossen and not verwertbar(p.budget) and not self.ist_ausgeschlossen(p)
        )

    def fenster(self, bestand: Bestand) -> tuple[tuple[int, int], ...]:
        """Die letzten ``historie_monate`` abgeschlossenen Monate vor dem Stichtag."""
        letzter = ordnung(bestand.stichtag.year, bestand.stichtag.month) - 1
        return tuple(
            aus_ordnung(letzter - abstand) for abstand in range(self.historie_monate - 1, -1, -1)
        )

    def umsatz_historie(self, bestand: Bestand, projekte: tuple[Projekt, ...]) -> np.ndarray:
        """Euro je Projekt (Zeilen) und Fenstermonat (Spalten), 0 ohne Buchung."""
        fenster = self.fenster(bestand)
        verlaeufe = {v.projekt.id: v for v in bestand.verbrauchsverlaeufe}
        return np.array(
            [
                [
                    float(verlauf.gebucht(*monat)) if (verlauf := verlaeufe.get(p.id)) else 0.0
                    for monat in fenster
                ]
                for p in projekte
            ],
        ).reshape(len(projekte), len(fenster))

    def reservierte_stunden(self, bestand: Bestand) -> dict[int, float]:
        """Mittlere Monatsstunden der Schulungsprojekte je Person (Schluessel: Personen-ID).

        Die Stunden eines Monats im Fenster werden ueber den historischen Anteil
        (:meth:`~umsatzprognose.domaene.projekt.Projekt.anteil_je_mitarbeiter`) auf die
        Personen verteilt, dann ueber das Fenster gemittelt. Eine Naeherung: der Anteil
        stammt aus der gesamten Historie des Projekts, nicht aus den Fenstermonaten.
        """
        fenster = self.fenster(bestand)
        verlaeufe = {v.projekt.id: v for v in bestand.verbrauchsverlaeufe}
        je_person: dict[int, float] = {}
        for projekt in bestand.aktive_projekte:
            if not self.ist_schulung(projekt) or (verlauf := verlaeufe.get(projekt.id)) is None:
                continue
            stunden = sum(m.stunden for m in verlauf.monate if m.schluessel in fenster)
            for person, anteil in projekt.anteil_je_mitarbeiter().items():
                je_person[person.id] = je_person.get(person.id, 0.0) + stunden * anteil
        return {pid: s / len(fenster) for pid, s in je_person.items()}


def _enthaelt(projekt: Projekt, bausteine: tuple[str, ...]) -> bool:
    return any(baustein in projekt.bezeichnung for baustein in bausteine)
