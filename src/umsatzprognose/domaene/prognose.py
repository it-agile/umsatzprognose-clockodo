"""Prognose - die Ausgabe der Simulation, und die Naht, an der sie andockt.

Die Monte-Carlo-Simulation aus Spec 5.4 ist **nicht gebaut**. Was ihr fehlt, sind keine
Programmierarbeit, sondern zwei Modellgroessen: die Verteilung der Abrufquote (5.2) und
die Definition der Referenzklassen (6). Beide stehen laut Spec v0.5 "unveraendert zu
v0.3", und v0.3 liegt dem Repository nicht vor. Plausible Werte zu erfinden hiesse, eine
Bandbreite auszuweisen, die niemand kalibriert hat.

Statt die Luecke zu verschweigen, hat sie hier eine Form: :class:`NochKeinePrognose`
sagt aus, dass es keine gibt, und warum. Das Dashboard zeigt das an der Stelle an, an
der spaeter die Bandbreite steht. Kommt die Simulation, tritt sie als zweite
Implementierung von :class:`Prognose` daneben - aufgerufen ueber
:meth:`umsatzprognose.domaene.bestand.Bestand.simulieren`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

# Spec 5.5: die Bandbreite wird auf diesen Niveaus ausgewiesen.
KONFIDENZNIVEAUS = (0.95, 0.85, 0.50)


class Prognose(ABC):
    """Das Ergebnis eines Prognoselaufs ueber den Bestand."""

    @property
    @abstractmethod
    def vorhanden(self) -> bool:
        """Ob belastbare Zahlen vorliegen."""

    @property
    @abstractmethod
    def begruendung(self) -> str:
        """Eine Zeile fuer die Darstellung - was die Prognose sagt oder warum nicht."""

    @abstractmethod
    def monatswerte(self) -> dict[float, list[float]]:
        """Je Konfidenzniveau ein Umsatzwert pro Monat des Horizonts (Spec 5.5)."""

    @abstractmethod
    def summe(self) -> dict[float, float]:
        """Je Konfidenzniveau der Umsatz ueber den gesamten Horizont (Spec 5.5)."""

    @abstractmethod
    def kapazitaet_limitierend_anteil(self) -> float:
        """Anteil der Laeufe, in denen die Kapazitaet der Engpass war (Spec 5.5).

        Die Groesse unterscheidet einen Nachfrage- von einem Kapazitaetsengpass und ist
        laut Spec ein geforderter Output, nicht ein Nebenprodukt.
        """


@dataclass(frozen=True)
class NochKeinePrognose(Prognose):
    """Es gibt keine Prognose, und zwar aus einem benennbaren Grund."""

    fehlt: str = (
        "Die Simulation nach Spec 5.4 ist noch nicht gebaut. Dafür fehlen die "
        "Verteilung der Abrufquote und die Definition der Referenzklassen; beide "
        "stehen in Spec v0.3, die nicht vorliegt."
    )

    @property
    def vorhanden(self) -> bool:
        return False

    @property
    def begruendung(self) -> str:
        return self.fehlt

    def monatswerte(self) -> dict[float, list[float]]:
        return {}

    def summe(self) -> dict[float, float]:
        return {}

    def kapazitaet_limitierend_anteil(self) -> float:
        return 0.0
