"""Darstellung der Ergebnisse als DataFrame.

Getrennt von der Rechenlogik: :mod:`umsatzprognose.restvolumen` bleibt frei von
pandas, hier steht nur die Abbildung der Ergebnisobjekte auf Tabellenspalten - damit
das Notebook keine eigene Umformung mitschleppt.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import pandas as pd

from umsatzprognose.restvolumen import ProjektRestvolumen
from umsatzprognose.stammdaten import ProjektBezeichnung

SPALTEN = [
    "projects_id",
    "kunde",
    "projekt",
    "budget",
    "revenue_kumuliert",
    "restvolumen_roh",
    "prognosewirksam",
    "ueberschritten",
]


LEERE_BEZEICHNUNG = ProjektBezeichnung(kunde=None, projekt=None)


def restvolumen_tabelle(
    restvolumina: Iterable[ProjektRestvolumen],
    bezeichnungen: Mapping[int, ProjektBezeichnung] | None = None,
) -> pd.DataFrame:
    """Restvolumina als Tabelle, absteigend nach prognosewirksamem Volumen.

    Args:
        restvolumina: die berechneten Restvolumina.
        bezeichnungen: ``projects_id`` -> Kunden- und Projektname aus
            :func:`umsatzprognose.stammdaten.bezeichnungen_je_projekt`. Nur
            Beschriftung, keine Rechengroesse - fehlt die Zuordnung, bleiben die
            Spalten ``kunde`` und ``projekt`` leer, die Zahlen bleiben dieselben.
    """
    bezeichnungen = bezeichnungen or {}
    tabelle = pd.DataFrame(
        [
            {
                "projects_id": r.projects_id,
                "kunde": bezeichnungen.get(r.projects_id, LEERE_BEZEICHNUNG).kunde,
                "projekt": bezeichnungen.get(r.projects_id, LEERE_BEZEICHNUNG).projekt,
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
