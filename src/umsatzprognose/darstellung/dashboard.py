"""Das Dashboard - fachliche Klasse, Wissen von Fachexperten.

Eine Fassade ueber Abruf, Fachlogik und Darstellung: :meth:`Dashboard.laden` holt die
Daten, jede weitere Methode gibt eine fertige Ansicht zurueck. Im Notebook steht damit
je Zelle ein Aufruf und kein Endpunkt, kein Feldname und keine Projekt-ID.

Der Bestand wird einmal geladen und gehalten. Alle Ansichten zeigen deshalb denselben
Stand - was bei einer Groesse, die sich mit jeder Zeitbuchung bewegt, keine
Selbstverstaendlichkeit ist.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import date

    import pandas as pd
    import plotly.graph_objects as go

    from umsatzprognose.domaene import Bestand, Prognose, Schulungsplan

from umsatzprognose.clockodo import BestandRepository
from umsatzprognose.schulungen import SchulungenRepository

from . import diagramme, tabellen

STANDARD_TOP = 15


class Dashboard:
    """Alle Ansichten zu einem geladenen Bestand."""

    def __init__(self, bestand: Bestand, schulungsplan: Schulungsplan) -> None:
        self.bestand = bestand
        self.prognose: Prognose | None = None
        self.schulungsplan: Schulungsplan = schulungsplan

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
        gleichzeitig.
        """
        bestand = BestandRepository.mit_automatischen_zugangsdaten().laden(
            stichtag=stichtag,
            mit_anteilen=mit_anteilen,
            mit_verbrauchsverlauf=mit_verbrauchsverlauf,
            abgeschlossene_monate=abgeschlossene_monate,
            horizont_monate=horizont_monate,
        )
        schulungsplan = SchulungenRepository.mit_automatischen_zugangsdaten().laden(
            stichtag=stichtag, horizont_monate=horizont_monate
        )
        return cls(bestand, schulungsplan)

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
        schulungsplan = SchulungenRepository.mit_automatischen_zugangsdaten().laden(
            stichtag=stichtag, horizont_monate=horizont_monate
        )
        return cls(bestand, schulungsplan)

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

    def simuliere(self, *, monate: int = 3, laeufe: int = 10_000):
        self.prognose = self.bestand.simulieren(monate=monate, laeufe=laeufe)

    def schulungen_laden(self, *, horizont_monate: int = 3) -> None:
        """Die Schulungstermine aus den konfigurierten Google-Sheets-Dateien laden.

        Additiver Baustein neben der Bestand-Prognose (Spec Baustein
        Schulungsanmeldungen) - unabhaengig von :meth:`simuliere`, in beliebiger
        Reihenfolge aufrufbar. Die Zugangsdaten und die Jahr-zu-Datei-Zuordnung kommen,
        wie bei :meth:`laden`, aus Colab-Secrets oder einer lokalen ``.env``.
        """
        self.schulungsplan = SchulungenRepository.mit_automatischen_zugangsdaten().laden(
            self.stichtag, horizont_monate=horizont_monate
        )

    def umsatzverlauf(self) -> go.Figure:
        """Der Umsatz je Monat - Historie und, daran anschliessend, der Prognosehorizont."""
        return diagramme.umsatzverlauf(self._historie(), self.prognose, self.schulungsplan)

    def restvolumen_je_projekt(self, top: int = STANDARD_TOP) -> go.Figure:
        """Das offene Auftragsvolumen der groessten Projekte."""
        return diagramme.restvolumen_je_projekt(self.bestand.im_prognose_scope, top=top)

    def umsatztabelle(self) -> pd.DataFrame:
        """Dieselben Monate wie im Verlaufsdiagramm, zum Nachlesen - inklusive Prognose."""
        return tabellen.umsatztabelle(self._historie(), self.prognose, self.schulungsplan)

    def projekttabelle(self, top: int | None = None) -> pd.DataFrame:
        """Die Projekte der Prognose, groesstes offenes Volumen zuerst."""
        projekte = self.bestand.im_prognose_scope
        return tabellen.projekttabelle(projekte[:top] if top else projekte)

    def stundensatz_uebersteuern(self, werte: dict[str, float]) -> None:
        """Für benannte Projekte von Hand einen Stundensatz hinterlegen.

        Für Projekte, deren Stundensatz laut Hinweisen 0 ist - gebuchte Zeit ohne
        Umsatz -, lässt sich hier eine plausible Zahl nachtragen, statt dass die
        spätere Umrechnung von Euro in Stunden dort durch null teilt. ``werte``
        verwendet denselben Projektnamen wie in der Hinweistabelle, zum Beispiel
        ``{"Website-Relaunch": 95.0}``. Wirkt auf alle danach aufgerufenen Ansichten
        dieses Dashboards.
        """
        self.bestand = self.bestand.mit_stundensatz_uebersteuerungen(werte)

    def hinweise(self) -> pd.DataFrame:
        """Was zu den Zahlen zu wissen ist - Datenlage und offene fachliche Fragen."""
        hinweise = self.bestand.hinweise()
        if self.schulungsplan is not None and self.prognose is not None and self.prognose.vorhanden:
            hinweise += self.schulungsplan.hinweise(self.prognose.horizontmonate())
        return tabellen.hinweistabelle(hinweise)

    def _historie(self):
        historie = self.bestand.umsatzhistorie
        if historie is None:
            raise ValueError("Der Bestand enthält keine Umsatzhistorie.")
        return historie

    def projekte_ohne_budget(self, /, filter: Sequence[str] | None = None) -> pd.DataFrame:
        ohne_budget = self.bestand.ohne_budget(filter=filter)

        return tabellen.projekte_ohne_budget(
            (projekt.bezeichnung, projekt.budget.sonderfall or "kein Budget gesetzt")
            for projekt in sorted(ohne_budget, key=lambda projekt: projekt.bezeichnung)
        )
