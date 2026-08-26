"""Das Dashboard - die einzige Klasse, die ein Fachexperte im Notebook anfasst.

Eine Fassade ueber Abruf, Fachlogik und Darstellung: :meth:`Dashboard.laden` holt die
Daten, jede weitere Methode gibt eine fertige Ansicht zurueck. Im Notebook steht damit
je Zelle ein Aufruf und kein Endpunkt, kein Feldname und keine Projekt-ID.

Der Bestand wird einmal geladen und gehalten. Alle Ansichten zeigen deshalb denselben
Stand - was bei einer Groesse, die sich mit jeder Zeitbuchung bewegt, keine
Selbstverstaendlichkeit ist.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.graph_objects as go

from umsatzprognose.clockodo.bestand import BestandRepository
from umsatzprognose.darstellung import diagramme, tabellen
from umsatzprognose.domaene.bestand import Bestand

STANDARD_TOP = 15


class Dashboard:
    """Alle Ansichten zu einem geladenen Bestand."""

    def __init__(self, bestand: Bestand) -> None:
        self.bestand = bestand

    @classmethod
    def laden(
        cls,
        *,
        stichtag: date | None = None,
        mit_anteilen: bool = True,
        mit_verbrauchsverlauf: bool = True,
        abgeschlossene_monate: int = 12,
        horizont_monate: int = 3,
    ) -> Dashboard:
        """Daten aus Clockodo holen und das Dashboard bereitstellen.

        Die Zugangsdaten kommen aus der Colab-Secrets-Verwaltung oder aus einer lokalen
        ``.env``, je nachdem, wo das Notebook laeuft. Die sieben Abrufe laufen
        gleichzeitig; gegen die echte Installation bestimmt der langsamste die Dauer.
        """
        bestand = BestandRepository.mit_automatischen_zugangsdaten().laden(
            stichtag=stichtag,
            mit_anteilen=mit_anteilen,
            mit_verbrauchsverlauf=mit_verbrauchsverlauf,
            abgeschlossene_monate=abgeschlossene_monate,
            horizont_monate=horizont_monate,
        )
        return cls(bestand)

    @classmethod
    async def laden_async(
        cls,
        *,
        stichtag: date | None = None,
        mit_anteilen: bool = True,
        mit_verbrauchsverlauf: bool = True,
        abgeschlossene_monate: int = 12,
        horizont_monate: int = 3,
    ) -> Dashboard:
        """Derselbe Ladevorgang fuer Aufrufer, die schon in einem Event-Loop stehen."""
        bestand = await BestandRepository.mit_automatischen_zugangsdaten().laden_async(
            stichtag=stichtag,
            mit_anteilen=mit_anteilen,
            mit_verbrauchsverlauf=mit_verbrauchsverlauf,
            abgeschlossene_monate=abgeschlossene_monate,
            horizont_monate=horizont_monate,
        )
        return cls(bestand)

    @property
    def stichtag(self) -> date:
        return self.bestand.stichtag

    def kennzahlen(self) -> go.Figure:
        """Die vier Zahlen, mit denen ein Blick auf das Dashboard beginnt."""
        historie = self._historie()
        monate = len(historie.abgeschlossene())
        return diagramme.kennzahlen(
            [
                (f"Umsatz letzte {monate} Monate", historie.summe(), "EUR"),
                ("Durchschnitt je Monat", historie.durchschnitt(), "EUR"),
                ("Offenes Auftragsvolumen", self.bestand.restvolumen_prognosewirksam, "EUR"),
                ("Projekte in der Prognose", len(self.bestand.im_prognose_scope), ""),
            ]
        )

    def umsatzverlauf(self) -> go.Figure:
        """Der Umsatz je Monat - alle Buchungen, auch die ohne Projektbezug."""
        return diagramme.umsatzverlauf(self._historie())

    def restvolumen_je_projekt(self, top: int = STANDARD_TOP) -> go.Figure:
        """Das offene Auftragsvolumen der groessten Projekte."""
        return diagramme.restvolumen_je_projekt(self.bestand.im_prognose_scope, top=top)

    def prognose(self, monate: int = 3) -> go.Figure:
        """Die Prognose der naechsten Monate - noch ohne Zahlen, siehe Spec 5.4."""
        return diagramme.prognose(self.bestand.simulieren(monate))

    def umsatztabelle(self) -> pd.DataFrame:
        """Dieselben Monate wie im Verlaufsdiagramm, zum Nachlesen."""
        return tabellen.umsatztabelle(self._historie())

    def projekttabelle(self, top: int | None = None) -> pd.DataFrame:
        """Die Projekte der Prognose, groesstes offenes Volumen zuerst."""
        projekte = self.bestand.im_prognose_scope
        return tabellen.projekttabelle(projekte[:top] if top else projekte)

    def hinweise(self) -> pd.DataFrame:
        """Was zu den Zahlen zu wissen ist - Datenlage und offene fachliche Fragen."""
        return tabellen.hinweistabelle(self.bestand.hinweise())

    def _historie(self):
        historie = self.bestand.umsatzhistorie
        if historie is None:
            raise ValueError("Der Bestand enthält keine Umsatzhistorie.")
        return historie
