"""Das Dashboard - fachliche Klasse, Wissen von Fachexperten.

Eine Fassade ueber Abruf, Fachlogik und Darstellung: :meth:`Dashboard.laden` holt die
Daten, jede weitere Methode gibt eine fertige Ansicht zurueck. Im Notebook steht damit
je Zelle ein Aufruf und kein Endpunkt, kein Feldname und keine Projekt-ID.

Der Bestand wird einmal geladen und gehalten. Alle Ansichten zeigen deshalb denselben
Stand - was bei einer Groesse, die sich mit jeder Zeitbuchung bewegt, keine
Selbstverstaendlichkeit ist.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING

import humanize

if TYPE_CHECKING:
    from collections.abc import Sequence

    import pandas as pd
    import plotly.graph_objects as go

    from umsatzprognose.domaene import (
        Auslastungsmonat,
        Bestand,
        Kostenplan,
        Mitarbeiter,
        Monatsumsatz,
        Prognose,
        Schulungsplan,
    )

from umsatzprognose.clockodo import AuslastungRepository, BestandRepository
from umsatzprognose.domaene.auslastung import Auslastungssumme
from umsatzprognose.domaene.projekt import sonderfall
from umsatzprognose.kosten import KostenRepository
from umsatzprognose.schulungen import SchulungenRepository

from . import diagramme, tabellen

STANDARD_TOP = 15
STANDARD_GEWINN_VERLUST_MONATE = 11
# Fenster fuer Ansichten, die bewusst nicht die gesamte geladene Historie zeigen (siehe
# Dashboard._historie) - deckt sich mit dem frueheren Standard fuer abgeschlossene_monate,
# bevor der Ladevorgang auf "immer alle konfigurierten Jahre" umgestellt wurde.
STANDARD_HISTORIE_MONATE = 12

humanize.i18n.activate("de_DE")


def _abgeschlossene_monate(stichtag: date, fruehestes_jahr: int | None) -> int:
    """Monate zurueck bis Januar des fruehesten konfigurierten Kosten-Jahres.

    Ohne konfiguriertes Kosten-Jahr (``fruehestes_jahr`` ``None``) bleibt es beim
    bisherigen Standardfenster - ohne Kostenquelle gibt es ohnehin keinen mehrjaehrigen
    Gewinn/Verlust-Vergleich. Ebenso als Untergrenze, falls ``fruehestes_jahr`` einmal
    in der Zukunft liegen sollte, statt eine negative Monatszahl zu liefern.
    """
    if fruehestes_jahr is None:
        return STANDARD_HISTORIE_MONATE
    return max(
        STANDARD_HISTORIE_MONATE, (stichtag.year - fruehestes_jahr) * 12 + stichtag.month - 1
    )


def _historie_monate(
    bestand: Bestand, *, anzahl: int | None = STANDARD_HISTORIE_MONATE
) -> tuple[tuple[int, int], ...]:
    """Die Monate des Historie-Fensters, als Schluessel - leer ohne geladene Historie.

    ``anzahl`` wie bei :meth:`~umsatzprognose.domaene.umsatzhistorie.Umsatzhistorie.letzte`
    - ``None`` liefert die gesamte geladene Historie statt nur des Standardfensters.
    """
    historie = bestand.umsatzhistorie
    if historie is None:
        return ()
    return tuple(m.schluessel for m in historie.letzte(anzahl).monate)


def _mit_kostenabdeckung(
    monate: Sequence[Monatsumsatz], kostenplan: Kostenplan
) -> tuple[Monatsumsatz, ...]:
    """Filtert Kalenderjahre heraus, fuer die ueberhaupt kein Kostenposten vorliegt.

    Gedacht fuer Jahresvergleiche (:meth:`~Dashboard.gewinn_verlust_je_jahr`,
    :meth:`~Dashboard.umsatzrendite_kumuliert`): ohne jede Kostenerfassung eines
    Jahres waere ``kosten_je_monat`` dort ueberall 0 - das Jahr saehe dann so aus, als
    gaebe es keine Kosten, statt als fehlende Datengrundlage (fuer eine Umsatzrendite
    besonders irrefuehrend: 100 % in jedem Monat). Ist gar keine Kostenquelle
    konfiguriert (``kostenplan.posten`` insgesamt leer), bleibt es dagegen bei der
    ueblichen Annahme 0 fuer alle Monate - wie ueberall sonst im Dashboard. Eine
    einzelne Luecke innerhalb eines sonst abgedeckten Jahres bleibt ebenfalls bei
    dieser Annahme (siehe Moduldocstring von :mod:`umsatzprognose.domaene.kosten`).
    """
    if not kostenplan.posten:
        return tuple(monate)
    abgedeckte_jahre = {jahr for jahr, _monat in (p.schluessel for p in kostenplan.posten)}
    return tuple(m for m in monate if m.jahr in abgedeckte_jahre)


def _aktive_mitarbeiter(bestand: Bestand) -> dict[int, Mitarbeiter]:
    """Aktive Personen nach ID - Grundlage fuer den Auslastungs-Abruf."""
    return {m.id: m for m in bestand.mitarbeiter if m.aktiv}


def _dauer_text(dauer: timedelta | None) -> str:
    """Ladezeit lesbar auf Deutsch - unbestimmt, solange sie nicht gemessen wurde."""
    return humanize.naturaldelta(dauer) if dauer is not None else "unbekannter Dauer"


@dataclass(frozen=True)
class Ladedauern:
    """Wie lange der Abruf jedes einzelnen Repositories gedauert hat.

    Vier unabhaengige Abrufe stecken hinter einem Dashboard - Bestand, Schulungsplan,
    Kostenplan und Auslastung -, jeder mit eigener Antwortzeit. Ein einzelner
    Gesamtwert wuerde verschleiern, welcher davon eine Ladung tatsaechlich verlangsamt.
    Ein Feld bleibt ``None``, solange sein Abruf nicht gemessen wurde (etwa bei einem
    direkt konstruierten Dashboard, z. B. in Tests).
    """

    bestand: timedelta | None = None
    schulungsplan: timedelta | None = None
    kostenplan: timedelta | None = None
    auslastung: timedelta | None = None


class Dashboard:
    """Alle Ansichten zu einem geladenen Bestand."""

    def __init__(
        self,
        bestand: Bestand,
        schulungsplan: Schulungsplan,
        kostenplan: Kostenplan,
        auslastung: tuple[Auslastungsmonat, ...] = (),
        ladedauern: Ladedauern | None = None,
    ) -> None:
        self.bestand = bestand
        self.prognose: Prognose | None = None
        self.schulungsplan: Schulungsplan = schulungsplan
        self.kostenplan: Kostenplan = kostenplan
        self.auslastung: tuple[Auslastungsmonat, ...] = auslastung
        self.ladedauern: Ladedauern = ladedauern or Ladedauern()

    @classmethod
    def laden(
        cls,
        *,
        stichtag: date | None = None,
        mit_anteilen: bool = True,
        mit_verbrauchsverlauf: bool = True,
        horizont_monate: int = 3,
        auslastung_monate: int = 12,
    ) -> Dashboard:
        """Daten aus Clockodo holen und das Dashboard bereitstellen.

        Die Zugangsdaten kommen aus der Colab-Secrets-Verwaltung oder aus einer lokalen
        ``.env``, je nachdem, wo das Notebook laeuft. Die Umsatzhistorie deckt dabei
        immer alle in ``KOSTEN_SHEET_IDS`` konfigurierten Jahre ab statt eines festen
        Fensters - eine Gewinn/Verlust-Ansicht ohne Kosten waere ohnehin nur Umsatz.
        Welchen Ausschnitt davon eine einzelne Ansicht zeigt, entscheidet sie selbst
        (siehe :data:`STANDARD_HISTORIE_MONATE`). Bestand, Schulungsplan und
        Kostenplan werden gleichzeitig geladen; die Auslastung erst danach, weil sie die
        Personen des geladenen Bestands braucht.
        """
        stichtag = stichtag or date.today()
        kosten_repo = KostenRepository.mit_automatischen_zugangsdaten()
        abgeschlossene_monate = _abgeschlossene_monate(
            stichtag, kosten_repo.fruehestes_konfiguriertes_jahr
        )

        start = time.perf_counter()
        bestand = BestandRepository.mit_automatischen_zugangsdaten().laden(
            stichtag=stichtag,
            mit_anteilen=mit_anteilen,
            mit_verbrauchsverlauf=mit_verbrauchsverlauf,
            abgeschlossene_monate=abgeschlossene_monate,
            horizont_monate=horizont_monate,
        )
        bestand_dauer = timedelta(seconds=time.perf_counter() - start)

        start = time.perf_counter()
        schulungsplan = SchulungenRepository.mit_automatischen_zugangsdaten().laden(
            stichtag=stichtag, horizont_monate=horizont_monate
        )
        schulungsplan_dauer = timedelta(seconds=time.perf_counter() - start)

        start = time.perf_counter()
        kostenplan = kosten_repo.laden(
            stichtag=bestand.stichtag,
            horizont_monate=horizont_monate,
            historie_monate=_historie_monate(bestand, anzahl=None),
        )
        kostenplan_dauer = timedelta(seconds=time.perf_counter() - start)

        start = time.perf_counter()
        auslastung = AuslastungRepository.mit_automatischen_zugangsdaten().laden(
            _aktive_mitarbeiter(bestand), stichtag=bestand.stichtag, monate=auslastung_monate
        )
        auslastung_dauer = timedelta(seconds=time.perf_counter() - start)

        ladedauern = Ladedauern(
            bestand=bestand_dauer,
            schulungsplan=schulungsplan_dauer,
            kostenplan=kostenplan_dauer,
            auslastung=auslastung_dauer,
        )
        return cls(bestand, schulungsplan, kostenplan, auslastung, ladedauern)

    @classmethod
    async def laden_async(
        cls,
        *,
        stichtag: date | None = None,
        mit_anteilen: bool = True,
        mit_verbrauchsverlauf: bool = True,
        horizont_monate: int = 3,
        auslastung_monate: int = 12,
    ) -> Dashboard:
        """Derselbe Ladevorgang fuer Aufrufer, die schon in einem Event-Loop stehen."""
        stichtag = stichtag or date.today()
        kosten_repo = KostenRepository.mit_automatischen_zugangsdaten()
        abgeschlossene_monate = _abgeschlossene_monate(
            stichtag, kosten_repo.fruehestes_konfiguriertes_jahr
        )

        start = time.perf_counter()
        bestand = await BestandRepository.mit_automatischen_zugangsdaten().laden_async(
            stichtag=stichtag,
            mit_anteilen=mit_anteilen,
            mit_verbrauchsverlauf=mit_verbrauchsverlauf,
            abgeschlossene_monate=abgeschlossene_monate,
            horizont_monate=horizont_monate,
        )
        bestand_dauer = timedelta(seconds=time.perf_counter() - start)

        start = time.perf_counter()
        schulungsplan = SchulungenRepository.mit_automatischen_zugangsdaten().laden(
            stichtag=stichtag, horizont_monate=horizont_monate
        )
        schulungsplan_dauer = timedelta(seconds=time.perf_counter() - start)

        start = time.perf_counter()
        kostenplan = kosten_repo.laden(
            stichtag=bestand.stichtag,
            horizont_monate=horizont_monate,
            historie_monate=_historie_monate(bestand, anzahl=None),
        )
        kostenplan_dauer = timedelta(seconds=time.perf_counter() - start)

        start = time.perf_counter()
        auslastung = await AuslastungRepository.mit_automatischen_zugangsdaten().laden_async(
            _aktive_mitarbeiter(bestand), stichtag=bestand.stichtag, monate=auslastung_monate
        )
        auslastung_dauer = timedelta(seconds=time.perf_counter() - start)

        ladedauern = Ladedauern(
            bestand=bestand_dauer,
            schulungsplan=schulungsplan_dauer,
            kostenplan=kostenplan_dauer,
            auslastung=auslastung_dauer,
        )
        return cls(bestand, schulungsplan, kostenplan, auslastung, ladedauern)

    @property
    def stichtag(self) -> date:
        return self.bestand.stichtag

    @property
    def anzahl_schulungen(self) -> int:
        return len(self.schulungsplan.termine)

    @property
    def anzahl_kostenmonate(self) -> int:
        return len(self.kostenplan.posten)

    @property
    def anzahl_auslastungsmonate(self) -> int:
        return len(self.auslastung)

    def ladebericht(self) -> str:
        """Kurzer Ladehinweis fuer Fachexperten: Stand, Umfang und Dauer je Abruf."""
        dauern = self.ladedauern
        return (
            f"Abrechnungsdaten geladen.\n"
            f"Stand der Auswertung: {self.stichtag:%d.%m.%Y}\n"
            f"Bestand geladen (in {_dauer_text(dauern.bestand)})\n"
            f"{self.anzahl_schulungen} Schulung(en) geladen"
            f" (in {_dauer_text(dauern.schulungsplan)})\n"
            f"{self.anzahl_kostenmonate} Monat(e) mit Kostenprognose geladen"
            f" (in {_dauer_text(dauern.kostenplan)})\n"
            f"{self.anzahl_auslastungsmonate} Auslastungsmonat(e) geladen"
            f" (in {_dauer_text(dauern.auslastung)})"
        )

    def bestandsbericht(self) -> str:
        """Zahlen zum geladenen Bestand fuer die technische Pruefung, samt Ladezeit je Abruf."""
        bestand = self.bestand
        dauern = self.ladedauern
        return (
            f"Stichtag: {bestand.stichtag}\n"
            f"Projekte gesamt:    {humanize.intcomma(len(bestand.projekte))}"
            f"  (Bestand geladen in {_dauer_text(dauern.bestand)})\n"
            f"davon aktiv:        {humanize.intcomma(len(bestand.aktive_projekte))}\n"
            f"davon im Scope:     {humanize.intcomma(len(bestand.im_prognose_scope))}"
            "  (aktiv und mit Euro-Budget)\n"
            f"Personen:           {humanize.intcomma(len(bestand.mitarbeiter))}\n"
            f"Kunden mit Projekt: {humanize.intcomma(len(bestand.kunden))}\n"
            f"Kostenmonate:       {humanize.intcomma(self.anzahl_kostenmonate)}"
            f"  (Kostenplan geladen in {_dauer_text(dauern.kostenplan)})\n"
            f"Auslastungsmonate:  {humanize.intcomma(self.anzahl_auslastungsmonate)}"
            f"  (Auslastung geladen in {_dauer_text(dauern.auslastung)})"
        )

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

    def gewinn_verlust_je_jahr(self) -> go.Figure:
        """Fuer jedes Kalenderjahr der geladenen Historie eine eigene Linie je Monat.

        Nutzt bewusst die gesamte geladene Historie statt eines Fensters wie
        :meth:`gewinn_verlust_monatlich` - ein Jahresvergleich braucht jedes
        verfuegbare Jahr. Gezeigt wird das Ergebnis des einzelnen Monats, nicht
        aufsummiert (siehe :meth:`umsatzrendite_kumuliert` fuer die kumulierte Sicht).
        Ein Jahr ganz ohne Kostenerfassung faellt heraus, siehe
        :func:`_mit_kostenabdeckung`. Mit Vorausschau fuer den Prognosehorizont am
        juengsten Jahr, wie :meth:`gewinn_verlust_monatlich`.
        """
        historie = self._historie(anzahl=None)
        letzte_monate = _mit_kostenabdeckung(historie.abgeschlossene(), self.kostenplan)
        kosten = self.kostenplan.kosten_je_monat([m.schluessel for m in letzte_monate])
        return diagramme.gewinn_verlust_je_jahr(
            letzte_monate,
            kosten,
            prognose=self.prognose,
            horizont_kosten=self._horizont_kosten(),
            schulungsplan=self.schulungsplan,
            verbrauch_laufender_monat=historie.laufender,
        )

    def umsatzrendite_kumuliert(self) -> go.Figure:
        """Fuer jedes Kalenderjahr die kumulierte Umsatzrendite (Gewinn/Umsatz) je Monat.

        Nutzt wie :meth:`gewinn_verlust_je_jahr` die gesamte geladene Historie, nicht
        nur ein Fenster, und laesst ebenso ein Jahr ganz ohne Kostenerfassung weg
        (siehe :func:`_mit_kostenabdeckung`) - dort waere die Rendite sonst ueberall
        100 %, ohne dass ueberhaupt Kosten vorlaegen. Siehe
        :func:`~umsatzprognose.darstellung.diagramme.umsatzrendite_kumuliert` fuer die
        genaue Berechnung.
        """
        historie = self._historie(anzahl=None)
        letzte_monate = _mit_kostenabdeckung(historie.abgeschlossene(), self.kostenplan)
        kosten = self.kostenplan.kosten_je_monat([m.schluessel for m in letzte_monate])
        return diagramme.umsatzrendite_kumuliert(
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

    def auslastung_je_mitarbeiter(self, *, top: int = STANDARD_TOP) -> go.Figure:
        """Wer wie stark ausgelastet ist, aufsummiert ueber alle geladenen abgeschlossenen Monate.

        Der laufende (Stichtags-)Monat ist unvollstaendig gebucht und wuerde die Quote
        verfaelschen - er faellt deshalb heraus. Massgeblich sind die davor liegenden
        Monate aus dem beim Laden angefragten Fenster (``auslastung_monate``).
        ``self.auslastung`` ist bereits mit :meth:`laden`/:meth:`laden_async` geladen -
        wer das Dashboard direkt konstruiert (etwa in Tests), traegt es selbst nach.
        """
        stichtagsmonat = (self.bestand.stichtag.year, self.bestand.stichtag.month)
        abgeschlossen = [a for a in self.auslastung if (a.jahr, a.monat) != stichtagsmonat]
        return diagramme.auslastung_je_mitarbeiter(
            Auslastungssumme.je_mitarbeiter(abgeschlossen), top=top
        )

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

    def _historie(self, *, anzahl: int | None = STANDARD_HISTORIE_MONATE):
        """Die Umsatzhistorie, standardmaessig auf :data:`STANDARD_HISTORIE_MONATE`
        begrenzt - ``anzahl=None`` liefert die gesamte geladene Historie."""
        historie = self.bestand.umsatzhistorie
        if historie is None:
            raise ValueError("Der Bestand enthält keine Umsatzhistorie.")
        return historie.letzte(anzahl)

    def projekte_ohne_budget(self, /, filter: Sequence[str] | None = None) -> pd.DataFrame:
        ohne_budget = self.bestand.ohne_budget(filter=filter)

        return tabellen.projekte_ohne_budget(
            (projekt.bezeichnung, grund)
            for projekt in sorted(ohne_budget, key=lambda projekt: projekt.bezeichnung)
            if (grund := sonderfall(projekt.budget)) is not None
        )
