"""Prognose - die Ausgabe der Simulation, und die Naht, an der sie andockt.

Zwei Implementierungen: :class:`NochKeinePrognose` sagt aus, dass es keine Bandbreite
gibt, und warum - etwa weil die Abrufquote-Verteilung mangels Beobachtungen nicht
geschaetzt werden konnte oder kein Projekt im Prognose-Scope liegt. Die Monte-Carlo-
Simulation selbst,
:class:`~umsatzprognose.domaene.simulation.MonteCarloPrognose`, liefert die tatsaechliche
Bandbreite; beide werden ueber
:meth:`umsatzprognose.domaene.bestand.Bestand.simulieren` erreicht, das je nach Datenlage
zwischen ihnen entscheidet.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

# die Bandbreite wird auf diesen Niveaus ausgewiesen.
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
    def horizontmonate(self) -> tuple[tuple[int, int], ...]:
        """Die Monate des Horizonts (Jahr, Monat), in der Reihenfolge von :meth:`monatswerte`
        und :meth:`gebucht`."""

    @abstractmethod
    def monatswerte(self) -> dict[float, list[float]]:
        """Je Konfidenzniveau ein Umsatzwert pro Monat des Horizonts."""

    @abstractmethod
    def gebucht(self) -> list[float]:
        """Bereits gebuchter Betrag je Horizontmonat.

        Fuer den Stichtagsmonat immer 0: dort laesst sich der Anteil vor dem Stichtag
        nicht von dem danach trennen (Monatsgruppierung ohne Tagesgrenze), und was vor
        dem Stichtag schon feststand, zeigt die Historie getrennt.
        """

    @abstractmethod
    def summe(self) -> dict[float, float]:
        """Je Konfidenzniveau der Umsatz ueber den gesamten Horizont."""

    @abstractmethod
    def kapazitaet_limitierend_anteil(self) -> float:
        """Anteil der Laeufe, in denen die Kapazitaet der Engpass war.

        Die Groesse unterscheidet einen Nachfrage- von einem Kapazitaetsengpass und ist
        ein geforderter Output, nicht ein Nebenprodukt.
        """

    @abstractmethod
    def kapazitaet_je_projekt(self) -> dict[int, float]:
        """Median der ueber den Horizont gelieferten Stunden je Projekt-ID.

        Zeigt, wie sich die in der Simulation tatsaechlich verbrauchte Kapazitaet auf
        die Projekte im Prognose-Scope verteilt - Projekte ohne ableitbaren
        Stundensatz (Pauschalleistungen) tragen 0 bei, weil fuer sie kein
        Stundenbedarf ableitbar ist.
        """


@dataclass(frozen=True)
class NochKeinePrognose(Prognose):
    """Es gibt keine Prognose, und zwar aus einem benennbaren Grund."""

    fehlt: str = (
        "Für den Bestand gibt es keine Bandbreite: entweder liegt kein Projekt im "
        "Prognose-Scope, oder die Abrufquote-Verteilung konnte mangels "
        "Beobachtungen mit Restvolumen > 0 zu Monatsbeginn nicht geschätzt werden."
    )

    @property
    def vorhanden(self) -> bool:
        return False

    @property
    def begruendung(self) -> str:
        return self.fehlt

    def horizontmonate(self) -> tuple[tuple[int, int], ...]:
        return ()

    def monatswerte(self) -> dict[float, list[float]]:
        return {}

    def gebucht(self) -> list[float]:
        return []

    def summe(self) -> dict[float, float]:
        return {}

    def kapazitaet_limitierend_anteil(self) -> float:
        return 0.0

    def kapazitaet_je_projekt(self) -> dict[int, float]:
        return {}
