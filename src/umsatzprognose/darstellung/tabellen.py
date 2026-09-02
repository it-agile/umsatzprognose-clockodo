"""Die Tabellen des Dashboards.

Die Zahlen sind hier bereits in deutscher Schreibweise
formatiert: die Tabellen sind zum Lesen gedacht, nicht zum Weiterrechnen - wer rechnen
will, nimmt die Fachobjekte, die hinter jeder Zeile stehen.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from umsatzprognose.domaene import (
        Hinweis,
        Kostenplan,
        Prognose,
        Projekt,
        Schulungsplan,
        Umsatzhistorie,
    )

import pandas as pd

from umsatzprognose.domaene.umsatzhistorie import MONATSNAMEN
from umsatzprognose.domaene.zahlen import euro

# Diese Tabellen sind zum Lesen gedacht - kein abgeschnittener Hinweistext.
pd.set_option("display.max_colwidth", None)

PROJEKTSPALTEN = ["Kunde", "Projekt", "Beauftragt", "Verbraucht", "Offen", "Budget überschritten"]
UMSATZSPALTEN = [
    "Monat",
    "Abgerechnet",
    "Nicht abgerechnet",
    "Prognostiziert",
    "Schulungsanmeldungen",
    "Summe",
    "Kosten",
    "Gewinn",
]
HINWEISSPALTEN = ["Hinweis", "Betroffen", "Projekte"]
PROJEKT_OHNE_BUDGET_SPALTEN = ["Projekt", "Grund"]


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
    kostenplan: Kostenplan | None = None,
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

    Mit ``kostenplan`` kommen **Kosten** und **Gewinn** (Summe minus Kosten) dazu -
    anders als die Schulungsanmeldungen fuer **jeden** Monat, auch die Historie: die
    Kostenprognose gilt laut Quelle auch fuer bereits vergangene Monate, siehe
    Moduldocstring von :mod:`umsatzprognose.domaene.kosten`.

    Der erste Horizontmonat ist derselbe Kalendermonat wie der laufende und
    ergaenzt dessen Zeile deshalb nur um die Prognose, statt eine zweite Zeile fuer
    denselben Monat anzuhaengen.
    """
    laufender = historie.laufender
    kosten_historie = (
        kostenplan.kosten_je_monat([m.schluessel for m in historie.monate])
        if kostenplan is not None
        else [None] * len(historie.monate)
    )
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
            "Kosten": euro(kosten) if kosten is not None else "",
            "Gewinn": euro(monat.umsatz - kosten) if kosten is not None else "",
        }
        for monat, kosten in zip(historie.monate, kosten_historie, strict=True)
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
        kosten_horizont = (
            kostenplan.kosten_je_monat(horizont)
            if kostenplan is not None
            else [None] * len(horizont)
        )

        for (jahr, monat), wert, gebuchter_betrag, schulungsbetrag, kosten in zip(
            horizont, median, gebucht, schulung, kosten_horizont, strict=True
        ):
            beschriftung = f"{MONATSNAMEN[monat - 1]} {jahr}"
            if zeilen and zeilen[-1]["Monat"] == beschriftung:
                summe_wert = basis + wert + schulungsbetrag
                zeilen[-1]["Prognostiziert"] = euro(wert)
                zeilen[-1]["Schulungsanmeldungen"] = (
                    euro(schulungsbetrag) if schulungsbetrag else ""
                )
                zeilen[-1]["Summe"] = euro(summe_wert)
                zeilen[-1]["Kosten"] = euro(kosten) if kosten is not None else ""
                zeilen[-1]["Gewinn"] = euro(summe_wert - kosten) if kosten is not None else ""
            else:
                summe_wert = wert + schulungsbetrag
                zeilen.append(
                    {
                        "Monat": beschriftung,
                        "Abgerechnet": "",
                        "Nicht abgerechnet": euro(gebuchter_betrag) if gebuchter_betrag else "",
                        "Prognostiziert": euro(wert - gebuchter_betrag),
                        "Schulungsanmeldungen": euro(schulungsbetrag) if schulungsbetrag else "",
                        "Summe": euro(summe_wert),
                        "Kosten": euro(kosten) if kosten is not None else "",
                        "Gewinn": euro(summe_wert - kosten) if kosten is not None else "",
                    }
                )

    tabelle = pd.DataFrame(zeilen, columns=UMSATZSPALTEN)
    tabelle.index = [""] * len(tabelle)
    return tabelle


def hinweistabelle(hinweise: Sequence[Hinweis]) -> pd.DataFrame:
    """Die Befunde zur Datenlage, mit den betroffenen Projekten in der letzten Spalte."""
    tabelle = pd.DataFrame(
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
    tabelle.index = [""] * len(tabelle)
    return tabelle


def projekte_ohne_budget(projekte: Iterable[tuple[str, str]]) -> pd.DataFrame:
    tabelle = pd.DataFrame(
        [
            {
                "Projekt": projekt[0],
                "Grund": projekt[1],
            }
            for projekt in projekte
        ],
        columns=PROJEKT_OHNE_BUDGET_SPALTEN,
    )
    tabelle.index = [""] * len(tabelle)
    return tabelle
