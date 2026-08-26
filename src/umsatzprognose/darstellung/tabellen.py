"""Die Tabellen des Dashboards.

Der einzige Ort mit pandas. Die Zahlen sind hier bereits in deutscher Schreibweise
formatiert: die Tabellen sind zum Lesen gedacht, nicht zum Weiterrechnen - wer rechnen
will, nimmt die Fachobjekte, die hinter jeder Zeile stehen.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from umsatzprognose.domaene import Hinweis, Prognose, Projekt, Umsatzhistorie

import pandas as pd

from umsatzprognose.domaene.umsatzhistorie import MONATSNAMEN
from umsatzprognose.domaene.zahlen import euro

PROJEKTSPALTEN = ["Kunde", "Projekt", "Beauftragt", "Verbraucht", "Offen", "Budget überschritten"]
UMSATZSPALTEN = ["Monat", "Abgerechnet", "Nicht abgerechnet", "Prognostiziert", "Summe"]
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


def umsatztabelle(historie: Umsatzhistorie, prognose: Prognose | None = None) -> pd.DataFrame:
    """Ein Monat je Zeile, juengster zuletzt, und daran anschliessend der Prognosehorizont.

    Der Umsatz steht nicht mehr in einer Spalte, sondern nach Rechnungsstellung
    aufgeteilt - dieselbe Unterscheidung wie im Diagramm (:func:`~umsatzprognose.
    darstellung.diagramme.umsatzverlauf`): **Abgerechnet** fuer abgeschlossene
    Vergangenheitsmonate, **Nicht abgerechnet** fuer schon in Clockodo gebuchte, aber
    per Definition noch nicht abgerechnete Betraege (der laufende Monat, und im
    Prognosehorizont bereits gebuchte kuenftige Monate, :meth:`Prognose.gebucht`), und
    **Prognostiziert** fuer den Rest bis zum Median der Simulation. Die Summenspalte
    fasst die drei je Monat zusammen.

    Der erste Horizontmonat ist derselbe Kalendermonat wie der laufende (Spec 5.4) und
    ergaenzt dessen Zeile deshalb nur um die Prognose, statt eine zweite Zeile fuer
    denselben Monat anzuhaengen.
    """
    laufender = historie.laufender
    zeilen = [
        {
            "Monat": monat.beschriftung,
            "Abgerechnet": ""
            if laufender and monat.schluessel == laufender.schluessel
            else euro(monat.umsatz),
            "Nicht abgerechnet": euro(monat.umsatz)
            if laufender and monat.schluessel == laufender.schluessel
            else "",
            "Prognostiziert": "",
            "Summe": euro(monat.umsatz),
        }
        for monat in historie.monate
    ]

    if prognose is not None and prognose.vorhanden:
        horizont = prognose.horizontmonate()
        median = prognose.monatswerte()[0.50]
        gebucht = prognose.gebucht()
        basis = laufender.umsatz if laufender else 0.0

        for (jahr, monat), wert, gebuchter_betrag in zip(horizont, median, gebucht, strict=True):
            beschriftung = f"{MONATSNAMEN[monat - 1]} {jahr}"
            if zeilen and zeilen[-1]["Monat"] == beschriftung:
                zeilen[-1]["Prognostiziert"] = euro(wert)
                zeilen[-1]["Summe"] = euro(basis + wert)
            else:
                zeilen.append(
                    {
                        "Monat": beschriftung,
                        "Abgerechnet": "",
                        "Nicht abgerechnet": euro(gebuchter_betrag) if gebuchter_betrag else "",
                        "Prognostiziert": euro(wert - gebuchter_betrag),
                        "Summe": euro(wert),
                    }
                )

    return pd.DataFrame(zeilen, columns=UMSATZSPALTEN)


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
