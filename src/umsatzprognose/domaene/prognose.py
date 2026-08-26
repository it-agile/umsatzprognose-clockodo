"""Prognose - die Ausgabe der Simulation, und die Naht, an der sie andockt.

Zwei Implementierungen: :class:`NochKeinePrognose` sagt aus, dass es keine Bandbreite
gibt, und warum - etwa weil die Abrufquote-Verteilung (5.2) mangels Beobachtungen nicht
geschaetzt werden konnte oder kein Projekt im Prognose-Scope liegt. Die Monte-Carlo-
Simulation aus Spec 5.4 selbst,
:class:`~umsatzprognose.domaene.simulation.MonteCarloPrognose`, liefert die tatsaechliche
Bandbreite; beide werden ueber
:meth:`umsatzprognose.domaene.bestand.Bestand.simulieren` erreicht, das je nach Datenlage
zwischen ihnen entscheidet.
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
        "Für den Bestand gibt es keine Bandbreite: entweder liegt kein Projekt im "
        "Prognose-Scope, oder die Abrufquote-Verteilung (Spec 5.2) konnte mangels "
        "Beobachtungen mit Restvolumen > 0 zu Monatsbeginn nicht geschätzt werden."
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
