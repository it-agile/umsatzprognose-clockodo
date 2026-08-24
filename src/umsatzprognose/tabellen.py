"""Darstellung der Ergebnisse als DataFrame.

Getrennt von der Rechenlogik: :mod:`umsatzprognose.restvolumen` bleibt frei von
pandas, hier steht nur die Abbildung der Ergebnisobjekte auf Tabellenspalten - damit
das Notebook keine eigene Umformung mitschleppt.
"""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from umsatzprognose.restvolumen import ProjektRestvolumen

SPALTEN = [
    "projects_id",
    "budget",
    "revenue_kumuliert",
    "restvolumen_roh",
    "prognosewirksam",
    "ueberschritten",
]


def restvolumen_tabelle(restvolumina: Iterable[ProjektRestvolumen]) -> pd.DataFrame:
    """Restvolumina als Tabelle, absteigend nach prognosewirksamem Volumen."""
    tabelle = pd.DataFrame(
        [
            {
                "projects_id": r.projects_id,
                "budget": r.budget,
                "revenue_kumuliert": r.revenue_kumuliert,
                "restvolumen_roh": r.roh,
                "prognosewirksam": r.prognosewirksam,
                "ueberschritten": r.ueberschritten,
            }
            for r in restvolumina
        ],
        columns=SPALTEN,
    )
    return tabelle.sort_values("prognosewirksam", ascending=False)
