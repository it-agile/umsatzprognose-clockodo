"""Befunde, die neben den Zahlen mitlaufen.

Ein :class:`Hinweis` ist kein Fehler und kein Log-Eintrag, sondern ein fachlicher
Befund, der die Zahlen einordnet: dass 78 aktive Projekte ohne Budget aus der Prognose
fallen, dass ein Budget in Stunden statt in Euro gefuehrt wird, dass Umsatz auf einen
Kunden ohne Projekt gebucht wurde. Frueher standen diese Angaben als ``print`` im
Notebook und waren damit weder pruefbar noch weiterverwendbar.

Zwei Quellen erzeugen Hinweise: die Abbildungsschicht (:mod:`umsatzprognose.clockodo`)
meldet, was ihr beim Lesen der Antworten auffiel, der :class:`~umsatzprognose.domaene.
bestand.Bestand` leitet die fachlichen Befunde aus den Objekten ab. Das Dashboard fuehrt
beides zusammen.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Hinweis:
    """Ein Befund in Fachsprache, samt der betroffenen Objekte.

    Attributes:
        text: eine Zeile, an einen Fachexperten gerichtet - ohne Feldnamen und
            Endpunkte.
        betroffene: IDs der betroffenen Projekte oder Personen. Leer, wenn der Hinweis
            sich auf das Ganze bezieht.
    """

    text: str
    betroffene: tuple[str, ...] = ()

    @property
    def anzahl(self) -> int:
        return len(self.betroffene)

    def __str__(self) -> str:
        return f"{self.text} ({self.anzahl})" if self.betroffene else self.text
