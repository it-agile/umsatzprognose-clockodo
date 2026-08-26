"""Die Tabellen des Dashboards.

Der einzige Ort mit pandas. Die Zahlen sind hier bereits in deutscher Schreibweise
formatiert: die Tabellen sind zum Lesen gedacht, nicht zum Weiterrechnen - wer rechnen
will, nimmt die Fachobjekte, die hinter jeder Zeile stehen.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from umsatzprognose.domaene.hinweis import Hinweis
from umsatzprognose.domaene.projekt import Projekt
from umsatzprognose.domaene.umsatzhistorie import Umsatzhistorie
from umsatzprognose.domaene.zahlen import euro, stunden

PROJEKTSPALTEN = ["Kunde", "Projekt", "Beauftragt", "Verbraucht", "Offen", "Budget überschritten"]
UMSATZSPALTEN = ["Monat", "Umsatz", "Stunden", "Status"]
HINWEISSPALTEN = ["Hinweis", "Betroffen", "Projekte"]


def projekttabelle(projekte: Sequence[Projekt]) -> pd.DataFrame:
    """Ein Projekt je Zeile, in der Reihenfolge, in der es uebergeben wurde."""
    return pd.DataFrame(
        [
            {
                "Kunde": str(p.kunde) if p.kunde else "",
                "Projekt": p.name or f"Projekt {p.id}",
                "Beauftragt": euro(p.auftragsvolumen) if p.auftragsvolumen is not None else "",
                "Verbraucht": euro(p.verbrauchtes_volumen),
                "Offen": euro(p.restvolumen_prognosewirksam)
                if p.restvolumen_prognosewirksam is not None
                else "",
                "Budget überschritten": "ja" if p.budget_ueberschritten else "",
            }
            for p in projekte
        ],
        columns=PROJEKTSPALTEN,
    )


def umsatztabelle(historie: Umsatzhistorie) -> pd.DataFrame:
    """Ein Monat je Zeile, juengster zuletzt - dieselbe Reihenfolge wie im Diagramm."""
    laufender = historie.laufender
    return pd.DataFrame(
        [
            {
                "Monat": monat.beschriftung,
                "Umsatz": euro(monat.umsatz),
                "Stunden": stunden(monat.stunden),
                "Status": "läuft noch"
                if laufender and monat.schluessel == laufender.schluessel
                else "abgeschlossen",
            }
            for monat in historie.monate
        ],
        columns=UMSATZSPALTEN,
    )


def hinweistabelle(hinweise: Sequence[Hinweis]) -> pd.DataFrame:
    """Die Befunde zur Datenlage, mit den betroffenen Projekten in der letzten Spalte."""
    return pd.DataFrame(
        [
            {
                "Hinweis": hinweis.text,
                "Betroffen": hinweis.anzahl or "",
                "Projekte": ", ".join(str(i) for i in hinweis.betroffene[:8])
                + (" …" if hinweis.anzahl > 8 else ""),
            }
            for hinweis in hinweise
        ],
        columns=HINWEISSPALTEN,
    )
