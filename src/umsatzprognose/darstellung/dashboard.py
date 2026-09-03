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

    from umsatzprognose.domaene import (
        Auslastungsmonat,
        Bestand,
        Kostenplan,
        Mitarbeiter,
        Prognose,
        Schulungsplan,
    )

from umsatzprognose.clockodo import (
    AuslastungRepository,
    BestandRepository,
    ClockodoClient,
    ClockodoCredentials,
)
from umsatzprognose.domaene.projekt import sonderfall
from umsatzprognose.kosten import KostenRepository
from umsatzprognose.schulungen import SchulungenRepository

from . import diagramme, tabellen

STANDARD_TOP = 15
STANDARD_GEWINN_VERLUST_MONATE = 11


def _historie_monate(bestand: Bestand) -> tuple[tuple[int, int], ...]:
    """Die Monate der Umsatzhistorie, als Schluessel - leer ohne geladene Historie."""
    historie = bestand.umsatzhistorie
    return tuple(m.schluessel for m in historie.monate) if historie is not None else ()


def _aktive_mitarbeiter(bestand: Bestand) -> dict[int, Mitarbeiter]:
    """Aktive Personen nach ID - Grundlage fuer den Auslastungs-Abruf."""
    return {m.id: m for m in bestand.mitarbeiter if m.aktiv}


class Dashboard:
    """Alle Ansichten zu einem geladenen Bestand."""

    def __init__(
        self,
        bestand: Bestand,
        schulungsplan: Schulungsplan,
        kostenplan: Kostenplan,
        auslastung: tuple[Auslastungsmonat, ...] = (),
    ) -> None:
        self.bestand = bestand
        self.prognose: Prognose | None = None
        self.schulungsplan: Schulungsplan = schulungsplan
        self.kostenplan: Kostenplan = kostenplan
        self.auslastung: tuple[Auslastungsmonat, ...] = auslastung

    @classmethod
    def laden(
        cls,
        *,
        stichtag: date | None = None,
        mit_anteilen: bool = True,
        mit_verbrauchsverlauf: bool = True,
        abgeschlossene_monate: int = 12,
        horizont_monate: int = 3,
        auslastung_monate: int = 12,
    ) -> Dashboard:
        """Daten aus Clockodo holen und das Dashboard bereitstellen.

        Die Zugangsdaten kommen aus der Colab-Secrets-Verwaltung oder aus einer lokalen
        ``.env``, je nachdem, wo das Notebook laeuft. Bestand, Schulungsplan und
        Kostenplan werden gleichzeitig geladen; die Auslastung erst danach, weil sie die
        Personen des geladenen Bestands braucht.
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
        kostenplan = KostenRepository.mit_automatischen_zugangsdaten().laden(
            stichtag=bestand.stichtag,
            horizont_monate=horizont_monate,
            historie_monate=_historie_monate(bestand),
        )
        auslastung = AuslastungRepository(ClockodoClient(ClockodoCredentials.automatisch())).laden(
            _aktive_mitarbeiter(bestand), stichtag=bestand.stichtag, monate=auslastung_monate
        )
        return cls(bestand, schulungsplan, kostenplan, auslastung)

    @classmethod
    async def laden_async(
        cls,
        *,
        stichtag: date | None = None,
        mit_anteilen: bool = True,
        mit_verbrauchsverlauf: bool = True,
        abgeschlossene_monate: int = 12,
        horizont_monate: int = 3,
        auslastung_monate: int = 12,
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
        kostenplan = KostenRepository.mit_automatischen_zugangsdaten().laden(
            stichtag=bestand.stichtag,
            horizont_monate=horizont_monate,
            historie_monate=_historie_monate(bestand),
        )
        auslastung = await AuslastungRepository(
            ClockodoClient(ClockodoCredentials.automatisch())
        ).laden_async(
            _aktive_mitarbeiter(bestand), stichtag=bestand.stichtag, monate=auslastung_monate
        )
        return cls(bestand, schulungsplan, kostenplan, auslastung)

    @property
    def stichtag(self) -> date:
        return self.bestand.stichtag

    @property
    def anzahl_schulungen(self) -> int:
        return len(self.schulungsplan.termine)

    @property
    def anzahl_kostenmonate(self) -> int:
        return len(self.kostenplan.posten)

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

    def umsatzverlauf(self) -> go.Figure:
        """Der Umsatz je Monat - Historie und, daran anschliessend, der Prognosehorizont."""
        return diagramme.umsatzverlauf(
            self._historie(), self.prognose, self.schulungsplan, self.kostenplan
        )

    def gewinn_verlust_monatlich(
        self, *, monate: int = STANDARD_GEWINN_VERLUST_MONATE
    ) -> go.Figure:
        """Gewinn/Verlust der letzten ``monate`` abgeschlossenen Monate, je Monat ein Balken.

        Haengt, sofern :meth:`simuliere` bereits gelaufen ist, zusaetzlich die
        Vorausschau fuer den Prognosehorizont an - dieselbe Prognose wie im
        Umsatzverlauf, kein eigener Simulationslauf.
        """
        historie = self._historie()
        letzte_monate = historie.abgeschlossene(monate)
        kosten = self.kostenplan.kosten_je_monat([m.schluessel for m in letzte_monate])
        return diagramme.gewinn_verlust_monatlich(
            letzte_monate,
            kosten,
            prognose=self.prognose,
            horizont_kosten=self._horizont_kosten(),
            schulungsplan=self.schulungsplan,
            verbrauch_laufender_monat=historie.laufender,
        )

    def gewinn_verlust_kumuliert(
        self, *, monate: int = STANDARD_GEWINN_VERLUST_MONATE
    ) -> go.Figure:
        """Der ueber dieselben Monate aufsummierte Gewinn/Verlust, als Linie.

        Mit Vorausschau fuer den Prognosehorizont, wie :meth:`gewinn_verlust_monatlich`.
        """
        historie = self._historie()
        letzte_monate = historie.abgeschlossene(monate)
        kosten = self.kostenplan.kosten_je_monat([m.schluessel for m in letzte_monate])
        return diagramme.gewinn_verlust_kumuliert(
            letzte_monate,
            kosten,
            prognose=self.prognose,
            horizont_kosten=self._horizont_kosten(),
            schulungsplan=self.schulungsplan,
            verbrauch_laufender_monat=historie.laufender,
        )

    def _horizont_kosten(self) -> list[float]:
        """Kosten je Horizontmonat der laufenden Prognose, leer ohne Simulation."""
        if self.prognose is None or not self.prognose.vorhanden:
            return []
        return self.kostenplan.kosten_je_monat(self.prognose.horizontmonate())

    def restvolumen_je_projekt(self, top: int = STANDARD_TOP) -> go.Figure:
        """Das offene Auftragsvolumen der groessten Projekte."""
        return diagramme.restvolumen_je_projekt(self.bestand.im_prognose_scope, top=top)

    def kapazitaet_je_mitarbeiter(self, top: int = STANDARD_TOP) -> go.Figure:
        """Wer im anstehenden Monat noch Kapazitaet hat."""
        jahr, monat = self.bestand.stichtag.year, self.bestand.stichtag.month
        return diagramme.kapazitaet_je_mitarbeiter(
            self.bestand.mitarbeiter_kapazitaet(jahr, monat), top=top
        )

    def kapazitaet_je_projekt(self, top: int = STANDARD_TOP) -> go.Figure:
        """Wie sich die simulierte Kapazitaet auf die Projekte im Scope verteilt."""
        projekte = {p.id: p for p in self.bestand.im_prognose_scope}
        kapazitaet = self.prognose.kapazitaet_je_projekt() if self.prognose is not None else {}
        kapazitaeten = sorted(
            ((projekte[pid], stunden) for pid, stunden in kapazitaet.items() if pid in projekte),
            key=lambda paar: paar[1],
            reverse=True,
        )
        return diagramme.kapazitaet_je_projekt(kapazitaeten, top=top)

    def auslastung_je_mitarbeiter(
        self, monat: tuple[int, int] | None = None, *, top: int = STANDARD_TOP
    ) -> go.Figure:
        """Wer wie stark ausgelastet ist, fuer einen Monat (Default: der Stichtagsmonat).

        ``self.auslastung`` ist bereits mit :meth:`laden`/:meth:`laden_async` geladen -
        wer das Dashboard direkt konstruiert (etwa in Tests), traegt es selbst nach.
        """
        jahr, mon = monat or (self.bestand.stichtag.year, self.bestand.stichtag.month)
        gefiltert = [a for a in self.auslastung if (a.jahr, a.monat) == (jahr, mon)]
        return diagramme.auslastung_je_mitarbeiter(gefiltert, top=top)

    def umsatztabelle(self) -> pd.DataFrame:
        """Dieselben Monate wie im Verlaufsdiagramm, zum Nachlesen - inklusive Prognose."""
        return tabellen.umsatztabelle(
            self._historie(), self.prognose, self.schulungsplan, self.kostenplan
        )

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

    def hinweise(self, *, max_anzahl_betroffen: int = 10) -> pd.DataFrame:
        """Was zu den Zahlen zu wissen ist - Datenlage und offene fachliche Fragen."""
        hinweise = self.bestand.hinweise()
        monate = list(_historie_monate(self.bestand))
        if self.prognose is not None and self.prognose.vorhanden:
            horizont = self.prognose.horizontmonate()
            if self.schulungsplan is not None:
                hinweise += self.schulungsplan.hinweise(horizont)
            monate += [m for m in horizont if m not in monate]
        if self.kostenplan is not None:
            hinweise += self.kostenplan.hinweise(monate)
        return tabellen.hinweistabelle(hinweise, max_anzahl_betroffen=max_anzahl_betroffen)

    def _historie(self):
        historie = self.bestand.umsatzhistorie
        if historie is None:
            raise ValueError("Der Bestand enthält keine Umsatzhistorie.")
        return historie

    def projekte_ohne_budget(self, /, filter: Sequence[str] | None = None) -> pd.DataFrame:
        ohne_budget = self.bestand.ohne_budget(filter=filter)

        return tabellen.projekte_ohne_budget(
            (projekt.bezeichnung, grund)
            for projekt in sorted(ohne_budget, key=lambda projekt: projekt.bezeichnung)
            if (grund := sonderfall(projekt.budget)) is not None
        )
