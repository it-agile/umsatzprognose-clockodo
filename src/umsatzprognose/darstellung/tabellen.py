"""Die Tabellen des Dashboards.

Der einzige Ort mit pandas. Die Zahlen sind hier bereits in deutscher Schreibweise
formatiert: die Tabellen sind zum Lesen gedacht, nicht zum Weiterrechnen - wer rechnen
will, nimmt die Fachobjekte, die hinter jeder Zeile stehen.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from umsatzprognose.domaene.hinweis import Hinweis
from umsatzprognose.domaene.prognose import Prognose
from umsatzprognose.domaene.projekt import Projekt
from umsatzprognose.domaene.umsatzhistorie import MONATSNAMEN, Umsatzhistorie
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


def umsatztabelle(historie: Umsatzhistorie, prognose: Prognose | None = None) -> pd.DataFrame:
    """Ein Monat je Zeile, juengster zuletzt, und daran anschliessend der Prognosehorizont.

    Dieselben Monate und derselbe Median wie im Diagramm (:func:`~umsatzprognose.
    darstellung.diagramme.umsatzverlauf`): fuer den laufenden Monat die Summe aus dem
    schon gebuchten Betrag (``historie.laufender``) und dem Median dieses Monats, fuer
    die folgenden Monate der Median allein - der enthaelt die Untergrenze aus bereits
    Gebuchtem schon (Spec 5.4, ``Monatsumsatz = max(simuliert, gebucht)``), ein zweites
    Draufaddieren waere falsch. Prognostizierte Zeilen tragen ein ``*`` am Betrag statt
    einer zweiten Schriftart - die Tabelle bleibt eine gewoehnliche DataFrame.
    """
    laufender = historie.laufender
    zeilen = [
        {
            "Monat": monat.beschriftung,
            "Umsatz": euro(monat.umsatz),
            "Stunden": stunden(monat.stunden),
            "Status": "läuft noch"
            if laufender and monat.schluessel == laufender.schluessel
            else "abgeschlossen",
        }
        for monat in historie.monate
    ]

    if prognose is not None and prognose.vorhanden:
        horizont = prognose.horizontmonate()
        median = prognose.monatswerte()[0.50]
        basis0 = laufender.umsatz if laufender else 0.0
        gesamt = [basis0 + median[0], *median[1:]]
        zeilen.extend(
            {
                "Monat": f"{MONATSNAMEN[monat - 1]} {jahr}",
                "Umsatz": f"{euro(betrag)} *",
                "Stunden": "",
                "Status": "prognostiziert",
            }
            for (jahr, monat), betrag in zip(horizont, gesamt, strict=True)
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
