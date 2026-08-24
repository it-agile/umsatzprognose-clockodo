"""Restvolumen je Projekt in Euro - Spec Abschnitt 5.1.

Formel laut Spec: ``budget.amount - revenue_kumuliert``, wobei ``revenue_kumuliert``
aus ``/v2/entrygroups`` stammt.

Zwei Punkte deckt die Spec v0.4 nicht ab; sie sind hier bewusst explizit gemacht
statt stillschweigend entschieden:

1. ``budget.hard`` ist in dieser Installation ``false``. Der Verbrauch kann das
   Budget also uebersteigen, das rohe Restvolumen wird dann negativ. Fuer die
   Prognose ist daraus nichts mehr abrufbar, deshalb liefert
   :attr:`ProjektRestvolumen.prognosewirksam` den bei 0 gekappten Wert. Das rohe
   Ergebnis bleibt als :attr:`ProjektRestvolumen.roh` erhalten, damit
   Budgetueberschreitungen bei der Kalibrierung sichtbar bleiben.
2. Projekte ohne gesetztes Budget haben kein bezifferbares Auftragsvolumen und
   damit kein Restvolumen. Sie werden nicht auf 0 gerechnet, sondern von
   :func:`restvolumen_je_projekt` uebersprungen und separat zurueckgemeldet.

Die in 5.1 erwaehnte Normalisierung von Pauschalleistungen ueber den effektiven
Stundensatz ist hier noch nicht umgesetzt: die Definition des effektiven
Stundensatzes steht in Spec v0.3, die dem Repository nicht vorliegt.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class ProjektRestvolumen:
    """Restvolumen eines Projekts in Euro."""

    projects_id: int
    budget: float
    revenue_kumuliert: float

    @property
    def roh(self) -> float:
        """``budget - revenue_kumuliert``, auch negativ bei Budgetueberschreitung."""
        return self.budget - self.revenue_kumuliert

    @property
    def prognosewirksam(self) -> float:
        """Bei 0 gekapptes Restvolumen - der Teil, der noch abgerufen werden kann."""
        return max(0.0, self.roh)

    @property
    def ueberschritten(self) -> bool:
        return self.roh < 0


def restvolumen_je_projekt(
    budgets: Mapping[int, float | None],
    revenue_kumuliert: Mapping[int, float],
) -> tuple[list[ProjektRestvolumen], list[int]]:
    """Berechnet das Restvolumen fuer alle Projekte mit gesetztem Budget.

    Args:
        budgets: ``projects_id`` -> ``budget.amount`` aus ``/v4/projects``.
            ``None`` bedeutet "kein Budget gesetzt".
        revenue_kumuliert: ``projects_id`` -> aufsummiertes ``revenue`` aus
            ``/v2/entrygroups``. Fehlende Projekte gelten als noch nicht bebucht.

    Returns:
        Die berechneten Restvolumina sowie die IDs der Projekte ohne Budget.
    """
    ergebnisse: list[ProjektRestvolumen] = []
    ohne_budget: list[int] = []

    for projects_id, budget in budgets.items():
        if budget is None:
            ohne_budget.append(projects_id)
            continue
        ergebnisse.append(
            ProjektRestvolumen(
                projects_id=projects_id,
                budget=float(budget),
                revenue_kumuliert=float(revenue_kumuliert.get(projects_id, 0.0)),
            )
        )

    return ergebnisse, ohne_budget


def summe_prognosewirksam(restvolumina: Iterable[ProjektRestvolumen]) -> float:
    """Summe der noch abrufbaren Restvolumina - Ausgangsgroesse der Simulation."""
    return sum(r.prognosewirksam for r in restvolumina)
