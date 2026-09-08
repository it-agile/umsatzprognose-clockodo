"""Das Dashboard - fachliche Klasse, Wissen von Fachexperten.

Eine Fassade ueber Abruf, Fachlogik und Darstellung: :meth:`Dashboard.laden` holt die
Daten, jede weitere Methode gibt eine fertige Ansicht zurueck. Im Notebook steht damit
je Zelle ein Aufruf und kein Endpunkt, kein Feldname und keine Projekt-ID.

Der Bestand wird einmal geladen und gehalten. Alle Ansichten zeigen deshalb denselben
Stand - was bei einer Groesse, die sich mit jeder Zeitbuchung bewegt, keine
Selbstverstaendlichkeit ist.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING

import humanize

if TYPE_CHECKING:
    from collections.abc import Sequence

    import pandas as pd
    import plotly.graph_objects as go

    from umsatzprognose.clockodo import Fortschritt
    from umsatzprognose.domaene import (
        Auslastungsmonat,
        Bestand,
        Kostenplan,
        Mitarbeiter,
        Monatsumsatz,
        Prognose,
        Schulungsplan,
        Umsatzhistorie,
    )

from umsatzprognose.clockodo import AuslastungRepository, BestandRepository, gleichzeitig, synchron
from umsatzprognose.domaene import Auslastungssumme, NochKeinePrognose
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


# Je Abruf ein Textbaustein, sowohl fuer die sukzessive fortschritt()-Meldung waehrend
# eines laufenden Ladevorgangs (siehe Dashboard.laden_async) als auch fuer
# Dashboard.schritt_berichte() - dieselben vier Zeilen im Nachhinein aus einem schon
# geladenen Dashboard rekonstruiert, etwa wenn ein Aufrufer (siehe notebooks/setup.py)
# ein zweites Mal im selben Kernel nicht neu laedt, aber trotzdem berichten will.
def _bestand_bericht(bestand: Bestand, dauer: timedelta | None) -> str:
    return (
        f"Bestand geladen: {humanize.intcomma(len(bestand.projekte))} Projekt(e)"
        f" (in {_dauer_text(dauer)})"
    )


def _schulungsplan_bericht(schulungsplan: Schulungsplan, dauer: timedelta | None) -> str:
    return f"{len(schulungsplan.termine)} Schulung(en) geladen (in {_dauer_text(dauer)})"


def _kostenplan_bericht(kostenplan: Kostenplan, dauer: timedelta | None) -> str:
    return f"{len(kostenplan.posten)} Monat(e) mit Kostenprognose geladen (in {_dauer_text(dauer)})"


def _auslastung_bericht(auslastung: Sequence[Auslastungsmonat], dauer: timedelta | None) -> str:
    return f"{len(auslastung)} Auslastungsmonat(e) geladen (in {_dauer_text(dauer)})"


class _Stoppuhr:
    """Misst die Dauer eines ``with``-Blocks, danach als :attr:`dauer` verfuegbar."""

    def __enter__(self) -> _Stoppuhr:
        self._start = time.perf_counter()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.dauer = timedelta(seconds=time.perf_counter() - self._start)


async def _bestand_laden(
    *,
    stichtag: date,
    mit_anteilen: bool,
    mit_verbrauchsverlauf: bool,
    abgeschlossene_monate: int,
    horizont_monate: int,
    melden: Fortschritt,
    beginnt: Fortschritt,
) -> tuple[Bestand, timedelta]:
    beginnt("Bestand")
    with _Stoppuhr() as t:
        bestand = await BestandRepository.mit_automatischen_zugangsdaten().laden_async(
            stichtag=stichtag,
            mit_anteilen=mit_anteilen,
            mit_verbrauchsverlauf=mit_verbrauchsverlauf,
            abgeschlossene_monate=abgeschlossene_monate,
            horizont_monate=horizont_monate,
            cache_fortschritt=melden,
            fortschritt=melden,
        )
    melden(_bestand_bericht(bestand, t.dauer))
    return bestand, t.dauer


async def _kostenplan_laden(
    kosten_repo: KostenRepository, bestand: Bestand, *, horizont_monate: int, melden: Fortschritt
) -> tuple[Kostenplan, timedelta]:
    with _Stoppuhr() as t:
        kostenplan = await asyncio.to_thread(
            kosten_repo.laden,
            stichtag=bestand.stichtag,
            horizont_monate=horizont_monate,
            historie_monate=_historie_monate(bestand, anzahl=None),
            fortschritt=melden,
        )
    melden(_kostenplan_bericht(kostenplan, t.dauer))
    return kostenplan, t.dauer


async def _auslastung_laden(
    bestand: Bestand, *, auslastung_monate: int, melden: Fortschritt
) -> tuple[tuple[Auslastungsmonat, ...], timedelta]:
    with _Stoppuhr() as t:
        auslastung = await AuslastungRepository.mit_automatischen_zugangsdaten().laden_async(
            _aktive_mitarbeiter(bestand), stichtag=bestand.stichtag, monate=auslastung_monate
        )
    melden(_auslastung_bericht(auslastung, t.dauer))
    return auslastung, t.dauer


async def _bestand_und_abhaengige_laden(
    *,
    stichtag: date,
    mit_anteilen: bool,
    mit_verbrauchsverlauf: bool,
    abgeschlossene_monate: int,
    horizont_monate: int,
    auslastung_monate: int,
    kosten_repo: KostenRepository,
    melden: Fortschritt,
    beginnt: Fortschritt,
) -> tuple[Bestand, timedelta, Kostenplan, timedelta, tuple[Auslastungsmonat, ...], timedelta]:
    """Bestand, danach (echt davon abhaengig) Kostenplan und Auslastung gleichzeitig -
    siehe Docstring von :meth:`Dashboard.laden_async` fuer die Begruendung der
    Reihenfolge."""
    bestand, bestand_dauer = await _bestand_laden(
        stichtag=stichtag,
        mit_anteilen=mit_anteilen,
        mit_verbrauchsverlauf=mit_verbrauchsverlauf,
        abgeschlossene_monate=abgeschlossene_monate,
        horizont_monate=horizont_monate,
        melden=melden,
        beginnt=beginnt,
    )

    beginnt("Kostenplan")
    beginnt("Auslastung")
    (kostenplan, kostenplan_dauer), (auslastung, auslastung_dauer) = await gleichzeitig(
        _kostenplan_laden(kosten_repo, bestand, horizont_monate=horizont_monate, melden=melden),
        _auslastung_laden(bestand, auslastung_monate=auslastung_monate, melden=melden),
    )
    return bestand, bestand_dauer, kostenplan, kostenplan_dauer, auslastung, auslastung_dauer


async def _schulungsplan_laden(
    *, stichtag: date, horizont_monate: int, melden: Fortschritt, beginnt: Fortschritt
) -> tuple[Schulungsplan, timedelta]:
    beginnt("Schulungsplan")
    with _Stoppuhr() as t:
        schulungsplan = await asyncio.to_thread(
            SchulungenRepository.mit_automatischen_zugangsdaten().laden,
            stichtag=stichtag,
            horizont_monate=horizont_monate,
        )
    melden(_schulungsplan_bericht(schulungsplan, t.dauer))
    return schulungsplan, t.dauer


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
        self.prognose: Prognose = NochKeinePrognose(
            fehlt="Die Prognose wurde noch nicht simuliert."
        )
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
        fortschritt: Fortschritt | None = None,
        schritt_beginnt: Fortschritt | None = None,
    ) -> Dashboard:
        """Daten aus Clockodo holen und das Dashboard bereitstellen.

        Die Zugangsdaten kommen aus der Colab-Secrets-Verwaltung oder aus einer lokalen
        ``.env``, je nachdem, wo das Notebook laeuft. Die Umsatzhistorie deckt dabei
        immer alle in ``KOSTEN_SHEET_IDS`` konfigurierten Jahre ab statt eines festen
        Fensters - eine Gewinn/Verlust-Ansicht ohne Kosten waere ohnehin nur Umsatz.
        Welchen Ausschnitt davon eine einzelne Ansicht zeigt, entscheidet sie selbst
        (siehe :data:`STANDARD_HISTORIE_MONATE`). Bestand und Schulungsplan haengen an
        nichts weiter als ``stichtag``/``horizont_monate`` und starten deshalb sofort
        gleichzeitig, statt Schulungsplan unnoetig auf Bestand warten zu lassen.
        Kostenplan und Auslastung haengen dagegen echt von Bestand ab (Kostenplan ueber
        dessen Stichtag/Umsatzhistorie, Auslastung ueber dessen Mitarbeiter) und starten
        darum erst, wenn Bestand fertig ist - dann aber gleichzeitig miteinander, egal ob
        Schulungsplan zu dem Zeitpunkt schon fertig ist oder noch laeuft.
        ``SchulungenRepository.laden()`` und ``KostenRepository.laden()`` sind synchrone
        Google-Sheets-Aufrufe (siehe Moduldocstring von
        :mod:`umsatzprognose.google_sheets.client`), keine Coroutinen - ``asyncio.to_thread()``
        gibt ihnen dafuer je einen eigenen Thread, waehrend Bestand und Auslastung als
        echte Coroutinen nebenher laufen; :func:`~umsatzprognose.clockodo.gleichzeitig`
        faechert jeweils die gleichzeitig laufenden Abrufe.

        ``fortschritt``, sofern angegeben, wird nach jedem der vier Abrufe einmal mit
        einer fertigen Statuszeile (Umfang und Dauer) aufgerufen - fuer eine sukzessive
        Fortschrittsanzeige waehrend des rund halbminuetigen Ladevorgangs, etwa per
        ``tqdm`` im Notebook (siehe ``notebooks/setup.py``). Diese vier Aufrufe kommen
        dabei in der Reihenfolge, in der die jeweiligen Abrufe tatsaechlich fertig
        werden - Bestand und Schulungsplan in beliebiger Reihenfolge zueinander, danach
        Kostenplan und Auslastung ebenfalls in beliebiger Reihenfolge zueinander, aber
        immer erst nach Bestand. ``schritt_beginnt`` wird stattdessen **vor** dem
        jeweiligen Abruf einmal mit dessen Bezeichnung aufgerufen (``"Bestand"`` und
        ``"Schulungsplan"`` beide sofort, ``"Kostenplan"`` und ``"Auslastung"`` beide
        erst, sobald Bestand fertig ist) - fuer eine Anzeige, die schon waehrend des
        laufenden Abrufs zeigt, was gerade geladen wird, statt nur eines generischen
        Titels.
        ``fortschritt`` meldet zusaetzlich, sofern angegeben, je getroffenem
        Verlaufscache-Zugriff (Projektanteile, Verbrauchsverlauf) eine eigene
        Statuszeile mit dessen gemessener Dauer - ueber denselben Callback wie die vier
        Abrufe oben, nur eben zusaetzlich und mittendrin (siehe
        :func:`~umsatzprognose.clockodo.cache.gecacht_oder_neu`): so bleibt sichtbar,
        dass und wie schnell diese beiden Zugriffe kamen, auch wenn der
        "Bestand"-Schritt insgesamt dadurch ungewoehnlich schnell fertig ist. Ein
        Aufrufer, der die vier Abruf-Meldungen von den Verlaufscache-Meldungen
        unterscheiden will, erkennt Letztere daran, dass ihr Text mit keinem der vier
        Abrufberichte uebereinstimmt (siehe ``notebooks/setup.py`` fuer ein Beispiel).
        Ohne aktivierten Verlaufscache (Standardfall, siehe
        :mod:`umsatzprognose.clockodo.cache`) ohne jede Wirkung. Ohne Angabe der
        Callbacks bleibt das Verhalten wie zuvor: nur der fertige :meth:`ladebericht`
        am Ende.

        Legt ``synchron()`` um :meth:`laden_async`, wie die ``laden``-Methoden der
        Repositories um ihre eigene ``laden_async``-Coroutine (siehe
        :mod:`umsatzprognose.clockodo.nebenlaeufig`) - fuer den Aufruf ausserhalb eines
        Event-Loops.
        """
        return synchron(
            cls.laden_async(
                stichtag=stichtag,
                mit_anteilen=mit_anteilen,
                mit_verbrauchsverlauf=mit_verbrauchsverlauf,
                horizont_monate=horizont_monate,
                auslastung_monate=auslastung_monate,
                fortschritt=fortschritt,
                schritt_beginnt=schritt_beginnt,
            )
        )

    @classmethod
    async def laden_async(
        cls,
        *,
        stichtag: date | None = None,
        mit_anteilen: bool = True,
        mit_verbrauchsverlauf: bool = True,
        horizont_monate: int = 3,
        auslastung_monate: int = 12,
        fortschritt: Fortschritt | None = None,
        schritt_beginnt: Fortschritt | None = None,
    ) -> Dashboard:
        """Derselbe Ladevorgang fuer Aufrufer, die schon in einem Event-Loop stehen."""
        # humanize.i18n.activate() wirkt nur thread-lokal (siehe humanize.i18n._CURRENT).
        # Das Modul-Level-activate() oben greift deshalb nicht, wenn synchron() diese
        # Coroutine ueber einen eigenen Worker-Thread ausfuehrt (Jupyter/Colab, siehe
        # clockodo.nebenlaeufig) - ohne diese Zeile waeren die per fortschritt() sofort
        # gemeldeten Dauern englisch, nur die spaeter im Aufrufer-Thread gebauten
        # Berichte (ladebericht(), bestandsbericht()) deutsch.
        humanize.i18n.activate("de_DE")
        stichtag = stichtag or date.today()
        kosten_repo = KostenRepository.mit_automatischen_zugangsdaten()
        abgeschlossene_monate = _abgeschlossene_monate(
            stichtag, kosten_repo.fruehestes_konfiguriertes_jahr
        )

        def melden(text: str) -> None:
            if fortschritt is not None:
                fortschritt(text)

        def beginnt(name: str) -> None:
            if schritt_beginnt is not None:
                schritt_beginnt(name)

        (
            (bestand, bestand_dauer, kostenplan, kostenplan_dauer, auslastung, auslastung_dauer),
            (schulungsplan, schulungsplan_dauer),
        ) = await gleichzeitig(
            _bestand_und_abhaengige_laden(
                stichtag=stichtag,
                mit_anteilen=mit_anteilen,
                mit_verbrauchsverlauf=mit_verbrauchsverlauf,
                abgeschlossene_monate=abgeschlossene_monate,
                horizont_monate=horizont_monate,
                auslastung_monate=auslastung_monate,
                kosten_repo=kosten_repo,
                melden=melden,
                beginnt=beginnt,
            ),
            _schulungsplan_laden(
                stichtag=stichtag, horizont_monate=horizont_monate, melden=melden, beginnt=beginnt
            ),
        )

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
    def anzahl_kostenmonate(self) -> int:
        return len(self.kostenplan.posten)

    @property
    def anzahl_auslastungsmonate(self) -> int:
        return len(self.auslastung)

    def schritt_berichte(self, *, dauer: timedelta | None = None) -> tuple[str, str, str, str]:
        """Dieselben vier Statuszeilen wie ``fortschritt`` waehrend :meth:`laden_async`
        (Bestand, Schulungsplan, Kostenplan, Auslastung, in dieser Reihenfolge) - aus
        :attr:`ladedauern` und dem geladenen Bestand im Nachhinein rekonstruiert.

        Fuer einen Aufrufer, der ein schon geladenes Dashboard erneut berichten will,
        ohne neu zu laden - etwa ``notebooks/setup.py`` bei einem zweiten Aufruf im
        selben Kernel: ohne diese Methode gaebe es dabei gar keine Ausgabe mehr, weil
        kein neuer Ladevorgang (und damit kein ``fortschritt``-Aufruf) mehr stattfindet.

        ``dauer``, sofern angegeben, ersetzt in allen vier Zeilen die einzeln
        gespeicherten Dauern aus :attr:`ladedauern`. Gedacht fuer genau diesen
        Wiederholungsfall: die in :attr:`ladedauern` gespeicherten Werte stammen vom
        urspruenglichen, echten Ladevorgang (z. B. 16 Sekunden fuer Bestand) - ein
        Aufrufer, der dasselbe Dashboard nur aus seinem eigenen, viel schnelleren
        Zwischenspeicher zurueckgibt, wuerde mit den unveraenderten Werten faelschlich
        genau diese alte, teure Dauer erneut zeigen, obwohl der eigentliche Zugriff
        diesmal nur Sekundenbruchteile brauchte. Ein einzelner uebergebener Wert statt
        vier getrennter Overrides, weil ein solcher Zwischenspeicher das Dashboard immer
        als Ganzes zurueckgibt, nicht schrittweise.
        """
        dauern = self.ladedauern
        bestand_dauer = dauer if dauer is not None else dauern.bestand
        schulungsplan_dauer = dauer if dauer is not None else dauern.schulungsplan
        kostenplan_dauer = dauer if dauer is not None else dauern.kostenplan
        auslastung_dauer = dauer if dauer is not None else dauern.auslastung
        return (
            _bestand_bericht(self.bestand, bestand_dauer),
            _schulungsplan_bericht(self.schulungsplan, schulungsplan_dauer),
            _kostenplan_bericht(self.kostenplan, kostenplan_dauer),
            _auslastung_bericht(self.auslastung, auslastung_dauer),
        )

    def ladebericht(self) -> str:
        """Kurzer Ladehinweis fuer Fachexperten: Stand der Auswertung.

        Ohne die Dauer/Umfang-Zeilen je Abruf: die zeigt im Notebook bereits
        ``setup.dashboard()`` sukzessive waehrend des Ladens per ``fortschritt``
        (siehe :meth:`laden_async`) - hier noch einmal aufgefuehrt waere reine
        Wiederholung. Wer sie im Nachhinein braucht (z. B. ausserhalb eines Notebooks,
        ohne ``fortschritt``-Callback), findet sie unveraendert in
        :attr:`ladedauern`/:meth:`bestandsbericht`/:meth:`schritt_berichte`.
        """
        return f"Abrechnungsdaten geladen.\nStand der Auswertung: {self.stichtag:%d.%m.%Y}"

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

    def simuliere(
        self, *, monate: int = 3, laeufe: int = 10_000, fortschritt: Fortschritt | None = None
    ) -> None:
        """Fuehrt die Monte-Carlo-Simulation aus und haelt das Ergebnis in
        :attr:`prognose` fuer die anderen Ansichten bereit.

        ``fortschritt``, sofern angegeben, wird einmal nach Abschluss mit einer
        fertigen Statuszeile (Laeufe, Horizont, Dauer) aufgerufen - dieselbe Form wie
        beim Laden (siehe :meth:`laden_async`), aber nur ein einzelner Aufruf statt
        vier: die Simulation ist eine einzige vektorisierte numpy-Rechnung (siehe
        :func:`~umsatzprognose.domaene.simulation.simulieren`) ohne sinnvolle
        Zwischenschritte (der Horizont ist auf 1-3 Monate begrenzt, jeder davon in
        etwa gleich teuer) - ein Vorher/Nachher-Bericht wie bei einem einzelnen
        Verlaufscache-Zugriff genuegt, eine feingranulare Zwischenanzeige waere nur
        Anschein von Fortschritt ohne echten Informationsgewinn.
        """
        with _Stoppuhr() as t:
            self.prognose = self.bestand.simulieren(monate=monate, laeufe=laeufe)
        if fortschritt is not None:
            fortschritt(
                f"Simulation abgeschlossen: {humanize.intcomma(laeufe)} Laeufe ueber "
                f"{monate} Monat(e) (in {_dauer_text(t.dauer)})"
            )

    def umsatzverlauf(self, *, mit_beschriftung: bool = False) -> go.Figure:
        """Der Umsatz je Monat - Historie und, daran anschliessend, der Prognosehorizont.

        ``mit_beschriftung`` siehe :func:`~umsatzprognose.darstellung.diagramme.umsatzverlauf`
        - standardmaessig aus, weil Notebook und Webapp den Wert per Hover-Tooltip
        zeigen; nur fuer statische Bildexporte (Wochenbericht) gedacht.
        """
        return diagramme.umsatzverlauf(
            self._historie(),
            self.prognose,
            self.schulungsplan,
            self.kostenplan,
            mit_beschriftung=mit_beschriftung,
        )

    def gewinn_verlust_monatlich(
        self, *, monate: int | None = STANDARD_GEWINN_VERLUST_MONATE, mit_beschriftung: bool = False
    ) -> go.Figure:
        """Gewinn/Verlust der letzten ``monate`` abgeschlossenen Monate, je Monat ein Balken.

        ``monate=None`` zeigt alle geladenen abgeschlossenen Monate, wie bei
        :meth:`gewinn_verlust_je_jahr`. Haengt, sofern :meth:`simuliere` bereits
        gelaufen ist, zusaetzlich die Vorausschau fuer den Prognosehorizont an -
        dieselbe Prognose wie im Umsatzverlauf, kein eigener Simulationslauf.
        ``mit_beschriftung`` siehe :meth:`umsatzverlauf`.
        """
        historie = self._historie(anzahl=monate)
        letzte_monate = historie.abgeschlossene(monate)
        kosten = self.kostenplan.kosten_je_monat([m.schluessel for m in letzte_monate])
        return diagramme.gewinn_verlust_monatlich(
            letzte_monate,
            kosten,
            prognose=self.prognose,
            horizont_kosten=self._horizont_kosten(),
            schulungsplan=self.schulungsplan,
            verbrauch_laufender_monat=historie.laufender,
            mit_beschriftung=mit_beschriftung,
        )

    def gewinn_verlust_je_jahr(self, *, mit_beschriftung: bool = False) -> go.Figure:
        """Fuer jedes Kalenderjahr der geladenen Historie eine eigene Linie je Monat.

        Nutzt bewusst die gesamte geladene Historie statt eines Fensters wie
        :meth:`gewinn_verlust_monatlich` - ein Jahresvergleich braucht jedes
        verfuegbare Jahr. Gezeigt wird das Ergebnis des einzelnen Monats, nicht
        aufsummiert (siehe :meth:`umsatzrendite_kumuliert` fuer die kumulierte Sicht).
        Ein Jahr ganz ohne Kostenerfassung faellt heraus, siehe
        :func:`_mit_kostenabdeckung`. Mit Vorausschau fuer den Prognosehorizont am
        juengsten Jahr, wie :meth:`gewinn_verlust_monatlich`. ``mit_beschriftung``
        siehe :meth:`umsatzverlauf`.
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
            mit_beschriftung=mit_beschriftung,
        )

    def umsatzrendite_kumuliert(self, *, mit_beschriftung: bool = False) -> go.Figure:
        """Fuer jedes Kalenderjahr die kumulierte Umsatzrendite (Gewinn/Umsatz) je Monat.

        Nutzt wie :meth:`gewinn_verlust_je_jahr` die gesamte geladene Historie, nicht
        nur ein Fenster, und laesst ebenso ein Jahr ganz ohne Kostenerfassung weg
        (siehe :func:`_mit_kostenabdeckung`) - dort waere die Rendite sonst ueberall
        100 %, ohne dass ueberhaupt Kosten vorlaegen. Siehe
        :func:`~umsatzprognose.darstellung.diagramme.umsatzrendite_kumuliert` fuer die
        genaue Berechnung. ``mit_beschriftung`` siehe :meth:`umsatzverlauf`.
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
            mit_beschriftung=mit_beschriftung,
        )

    def _horizont_kosten(self) -> list[float]:
        """Kosten je Horizontmonat der laufenden Prognose, leer ohne Simulation."""
        if not self.prognose.vorhanden:
            return []
        return self.kostenplan.kosten_je_monat(self.prognose.horizontmonate())

    def restvolumen_je_projekt(self, top: int = STANDARD_TOP) -> go.Figure:
        """Das offene Auftragsvolumen der groessten Projekte."""
        return diagramme.restvolumen_je_projekt(self.bestand.im_prognose_scope, top=top)

    def kapazitaet_je_mitarbeiter(self, top: int = STANDARD_TOP) -> go.Figure:
        """Wer ueber die abgeschlossenen Monate des Fensters am meisten Kapazitaet hatte.

        Der laufende (Stichtags-)Monat ist unvollstaendig und wuerde einen falschen
        Eindruck erwecken - er faellt deshalb heraus, genau wie bei
        :meth:`auslastung_je_mitarbeiter`. Massgeblich sind dieselben abgeschlossenen
        Monate aus dem beim Laden angefragten Fenster (``auslastung_monate``).
        """
        stichtagsmonat = (self.bestand.stichtag.year, self.bestand.stichtag.month)
        abgeschlossen = [a for a in self.auslastung if (a.jahr, a.monat) != stichtagsmonat]
        kapazitaeten = sorted(
            (
                (summe.mitarbeiter, summe.verfuegbare_stunden)
                for summe in Auslastungssumme.je_mitarbeiter(abgeschlossen)
            ),
            key=lambda paar: paar[1],
            reverse=True,
        )
        return diagramme.kapazitaet_je_mitarbeiter(kapazitaeten, top=top)

    def kapazitaet_je_projekt(self, top: int = STANDARD_TOP) -> go.Figure:
        """Wie sich die simulierte Kapazitaet auf die Projekte im Scope verteilt."""
        projekte = {p.id: p for p in self.bestand.im_prognose_scope}
        kapazitaet = self.prognose.kapazitaet_je_projekt()
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

    def verbrauchsplan_uebersteuern(self, werte: dict[str, tuple[int, int]]) -> None:
        """Für benannte Projekte von Hand einen Verbrauchsplan hinterlegen.

        Für Projekte, deren vollständiger Verbrauch bis zu einem bestimmten Monat
        schon feststeht, obwohl dafür noch keine Buchungen in Clockodo vorliegen -
        z. B. ``{"Beispielprojekt": (2026, 12)}``. Die Simulation verteilt das
        verbleibende Restvolumen dann linear auf die Monate bis einschließlich
        diesem Zielmonat, statt dafür eine Abrufquote zu ziehen. ``werte`` verwendet
        denselben Projektnamen wie in der Hinweistabelle. Wirkt auf alle danach
        aufgerufenen Ansichten dieses Dashboards.
        """
        self.bestand = self.bestand.mit_verbrauchsplan_uebersteuerungen(werte)

    def hinweise(self, *, max_anzahl_betroffen: int = 10) -> pd.DataFrame:
        """Was zu den Zahlen zu wissen ist - Datenlage und offene fachliche Fragen."""
        hinweise = self.bestand.hinweise()
        monate = list(_historie_monate(self.bestand))
        if self.prognose.vorhanden:
            horizont = self.prognose.horizontmonate()
            if self.schulungsplan is not None:
                hinweise += self.schulungsplan.hinweise(horizont)
            monate += [m for m in horizont if m not in monate]
        if self.kostenplan is not None:
            hinweise += self.kostenplan.hinweise(monate)
        return tabellen.hinweistabelle(hinweise, max_anzahl_betroffen=max_anzahl_betroffen)

    def _historie(self, *, anzahl: int | None = STANDARD_HISTORIE_MONATE) -> Umsatzhistorie:
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
