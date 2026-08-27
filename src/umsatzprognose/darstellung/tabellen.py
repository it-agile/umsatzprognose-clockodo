"""Die Tabellen des Dashboards.

Die Zahlen sind hier bereits in deutscher Schreibweise
formatiert: die Tabellen sind zum Lesen gedacht, nicht zum Weiterrechnen - wer rechnen
will, nimmt die Fachobjekte, die hinter jeder Zeile stehen.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from umsatzprognose.domaene import (
        Hinweis,
        Prognose,
        Projekt,
        Schulungsplan,
        Umsatzhistorie,
    )

import pandas as pd

from umsatzprognose.domaene.umsatzhistorie import MONATSNAMEN
from umsatzprognose.domaene.zahlen import euro

PROJEKTSPALTEN = ["Kunde", "Projekt", "Beauftragt", "Verbraucht", "Offen", "Budget überschritten"]
UMSATZSPALTEN = [
    "Monat",
    "Abgerechnet",
    "Nicht abgerechnet",
    "Prognostiziert",
    "Schulungsanmeldungen",
    "Summe",
]
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


def umsatztabelle(
    historie: Umsatzhistorie,
    prognose: Prognose | None = None,
    schulungsplan: Schulungsplan | None = None,
) -> pd.DataFrame:
    """Ein Monat je Zeile, juengster zuletzt, und daran anschliessend der Prognosehorizont.

    Der Umsatz steht nicht mehr in einer Spalte, sondern nach Rechnungsstellung
    aufgeteilt - dieselbe Unterscheidung wie im Diagramm (:func:`~umsatzprognose.
    darstellung.diagramme.umsatzverlauf`): **Abgerechnet** fuer abgeschlossene
    Vergangenheitsmonate, **Nicht abgerechnet** fuer schon in Clockodo gebuchte, aber
    per Definition noch nicht abgerechnete Betraege (der laufende Monat, und im
    Prognosehorizont bereits gebuchte kuenftige Monate, :meth:`Prognose.gebucht`), und
    **Prognostiziert** fuer den Rest bis zum Median der Simulation. Mit
    ``schulungsplan`` kommt zusaetzlich **Schulungsanmeldungen** dazu - additiv und
    unabhaengig von der Bestand-Bandbreite (Spec Baustein Schulungsanmeldungen,
    Abschnitt 6). Die Summenspalte fasst alle vier je Monat zusammen.

    Der erste Horizontmonat ist derselbe Kalendermonat wie der laufende und
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
            "Schulungsanmeldungen": "",
            "Summe": euro(monat.umsatz),
        }
        for monat in historie.monate
    ]

    if prognose is not None and prognose.vorhanden:
        horizont = prognose.horizontmonate()
        median = prognose.monatswerte()[0.50]
        gebucht = prognose.gebucht()
        basis = laufender.umsatz if laufender else 0.0
        schulung = (
            schulungsplan.umsatz_je_monat(horizont)
            if schulungsplan is not None
            else [0.0] * len(horizont)
        )

        for (jahr, monat), wert, gebuchter_betrag, schulungsbetrag in zip(
            horizont, median, gebucht, schulung, strict=True
        ):
            beschriftung = f"{MONATSNAMEN[monat - 1]} {jahr}"
            if zeilen and zeilen[-1]["Monat"] == beschriftung:
                zeilen[-1]["Prognostiziert"] = euro(wert)
                zeilen[-1]["Schulungsanmeldungen"] = (
                    euro(schulungsbetrag) if schulungsbetrag else ""
                )
                zeilen[-1]["Summe"] = euro(basis + wert + schulungsbetrag)
            else:
                zeilen.append(
                    {
                        "Monat": beschriftung,
                        "Abgerechnet": "",
                        "Nicht abgerechnet": euro(gebuchter_betrag) if gebuchter_betrag else "",
                        "Prognostiziert": euro(wert - gebuchter_betrag),
                        "Schulungsanmeldungen": euro(schulungsbetrag) if schulungsbetrag else "",
                        "Summe": euro(wert + schulungsbetrag),
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
