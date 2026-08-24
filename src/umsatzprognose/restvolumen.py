"""Restvolumen je Projekt in Euro - Spec Abschnitt 5.1.

Formel laut Spec: ``budget.amount - revenue_kumuliert``, wobei ``revenue_kumuliert``
aus ``/v2/entrygroups`` stammt.

Budgetueberschreitungen sind seit Spec v0.5 geregelt: ``budget.hard`` ist bei allen
aktiven Projekten ``false`` (Stand 24.08.2026; drei inaktive Projekte haben ``true``),
der Verbrauch kann das Budget also uebersteigen - aber nur in der Historie. Die
Prognose ueberschreitet das Budget nicht. Daher die zwei Groessen
:attr:`ProjektRestvolumen.roh` (vorzeichenbehaftet, macht Ueberschreitungen fuer die
Kalibrierung sichtbar) und :attr:`ProjektRestvolumen.prognosewirksam` (bei 0 gekappt,
Ausgangswert der Simulation). Fuer ein Projekt mit historisch ueberschrittenem Budget
wird kein zukuenftiger Umsatz prognostiziert.

Nicht von der Spec abgedeckt: Projekte ohne gesetztes Budget haben kein bezifferbares
Auftragsvolumen und damit kein Restvolumen. Sie werden nicht auf 0 gerechnet, sondern
von :func:`restvolumen_je_projekt` uebersprungen und separat zurueckgemeldet.

Die in 5.1 erwaehnte Normalisierung von Pauschalleistungen ueber den effektiven
Stundensatz ist hier noch nicht umgesetzt: die Definition des effektiven
Stundensatzes steht in Spec v0.3, die dem Repository nicht vorliegt. Das Feld
``hourly_rate`` aus ``/v2/entrygroups`` taugt dafuer ohnehin nicht - es ist bei 778 von
870 Gruppen ``null``; der Satz muss aus ``revenue`` und ``duration`` kommen.
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
