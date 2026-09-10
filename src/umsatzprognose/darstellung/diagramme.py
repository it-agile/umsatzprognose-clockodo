"""Die Diagramme des Dashboards.

Jede Funktion nimmt Fachobjekte und gibt eine plotly-Figur zurueck. Was dargestellt wird,
entscheidet die Domaene; hier steht nur, wie.

Gestaltung:
 * verschiedene Sättigungen einer Farbe für [abgerechnet, nicht abgerechnet, prognostiziert].
 * verschiedene Farben für unetrschiedliche Quellen
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NotRequired, TypedDict, Unpack

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    import pandas as pd

    from umsatzprognose.domaene import (
        Anmeldungsverlauf,
        Auslastungsmonat,
        Auslastungssumme,
        Kostenplan,
        Kurzarbeitsbewertung,
        Mitarbeiter,
        Monatsumsatz,
        Prognose,
        Projekt,
        Schulungsplan,
        Umsatzhistorie,
    )
    from umsatzprognose.util import Monat

import textwrap
from dataclasses import dataclass
from decimal import Decimal

import plotly.graph_objects as go

from umsatzprognose.darstellung.gestaltung import (
    ACHSE,
    ERGEBNIS_NEGATIV,
    ERGEBNIS_POSITIV,
    FLAECHE,
    JAHRESFARBEN,
    KOSTEN,
    KOSTEN_HELL,
    KURZARBEIT_SCHWELLE_ERREICHT,
    KURZARBEIT_SCHWELLE_NICHT_ERREICHT,
    PROGNOSE_DECKKRAFT,
    SCHRIFT,
    SCHULUNG,
    SERIE,
    SERIE_HELL,
    TICKWINKEL,
    TINTE,
    TINTE_GEDAEMPFT,
    TINTE_ZWEITRANGIG,
    TREND,
    VORLAEUFIG_DECKKRAFT,
    achsen,
    figur,
)
from umsatzprognose.domaene import NochKeinePrognose
from umsatzprognose.domaene.umsatzhistorie import MONATSNAMEN
from umsatzprognose.domaene.zahlen import STUNDEN_JE_TAG, euro, prozent, tage, tausend_euro

# Getrennte Laengen fuer Kunde und Projekt: der Kundenname ist oft der laengere Teil,
# unterscheidet aber die Zeilen eines Kunden nicht. Wird alles gemeinsam am Ende
# gekuerzt, sehen zwei Projekte desselben Kunden identisch aus.
MAXIMALE_KUNDENLAENGE = 22
MAXIMALE_PROJEKTLAENGE = 38

_KEINE_PROGNOSE = NochKeinePrognose()


def umsatzverlauf(
    historie: Umsatzhistorie,
    prognose: Prognose = _KEINE_PROGNOSE,
    schulungsplan: Schulungsplan | None = None,
    kostenplan: Kostenplan | None = None,
    *,
    hoehe: int = 420,
    mit_beschriftung: bool = False,
) -> go.Figure:
    """Monatsumsatz als Balken: Historie, und daran anschliessend der Prognosehorizont.

    Drei Sättigungen einer Farbe, nach Rechnungsstellung unterschieden statt nach Kalendermonat:
    **abgerechnet** (satt, nur abgeschlossene Vergangenheitsmonate), **nicht
    abgerechnet** (hell, deckend - der laufende Monat und, im Prognosehorizont, bereits
    in Clockodo gebuchte Betraege kuenftiger Monate, die per Definition noch nicht
    abgerechnet sein koennen) und **prognostiziert** (hell, gedaempft - der Rest bis zum
    Median der Simulation, siehe
    :data:`~umsatzprognose.darstellung.gestaltung.PROGNOSE_DECKKRAFT`). Sicherheit einer
    Zahl zeigt sich also ueber die Deckkraft, nicht ueber eine dritte Farbfamilie. Ein
    duenner Fehlerbalken je Monat zeigt, wie weit die 85-%- und 95-%-Niveaus darunter
    liegen. Ohne ``prognose`` oder ohne Bandbreite bleibt das Bild bei der
    Historie; die Begruendung steht dann als Hinweis rechts daneben.

    Mit ``schulungsplan`` kommt, additiv unterhalb von "Bereits gebucht" und
    "Prognostiziert", ein eigenfarbiger Balkenabschnitt "Schulungsanmeldungen" fuer den
    Umsatz aus bereits geplanten oeffentlichen Schulungsterminen hinzu - unabhaengig
    von der Bestand-Bandbreite und ohne eigene Unsicherheit.

    Mit ``kostenplan`` kommen je Monat zwei weitere, eigenstaendige Balken neben dem
    Umsatzbalken hinzu (Historie und Prognosehorizont): "Kosten" und "Ergebnis" (Umsatz
    minus Kosten, dieselbe Zahl wie die Spalte "Gewinn" in
    :func:`~umsatzprognose.darstellung.tabellen.umsatztabelle`) - gruen bei einem
    positiven, rot (ein anderer Farbton als "Kosten") bei einem negativen Ergebnis. Der
    Kostenbalken selbst zeigt zwei Saettigungen derselben Farbe, analog zu
    "Abgerechnet"/"Nicht abgerechnet" beim Umsatz: satt fuer Monate mit einer
    tatsaechlich erfassten Kostenerfassung, hell fuer Monate, die noch auf der
    geschaetzten Kostenpauschale beruhen (siehe
    :meth:`~umsatzprognose.domaene.kosten.Kostenposten.kosten`). Anders als der Umsatz
    ohne eigene Bandbreite, der Wert steht in der externen Kostenplanung schon fest.

    Der erste Horizontmonat ist derselbe Kalendermonat wie der laufende - beide teilen
    dieselbe Balkenbeschriftung und stapeln sich deshalb an derselben Stelle
    uebereinander, ohne dass ``historie`` und ``prognose`` dafuer denselben Stichtag
    tragen muessten explizit geprueft zu werden; in der Praxis stammen beide ohnehin aus
    demselben :class:`~umsatzprognose.domaene.bestand.Bestand`.

    ``mit_beschriftung`` zeigt zusaetzlich den Wert je Balken als Text (Historie,
    Kosten, Ergebnis) bzw. den Gesamtwert je Prognosehorizontmonat - fuer statische
    Bildexporte ohne Hover-Interaktivitaet (Wochenbericht). In Notebooks und der Webapp
    liefert plotly den Wert ohnehin per Tooltip, deshalb dort standardmaessig aus.
    """
    monate = historie.monate
    laufender = historie.laufender
    durchschnitt = historie.durchschnitt()

    untertitel = (
        f"Durchschnitt der {len(historie.abgeschlossene())} abgeschlossenen "
        f"Monate: {euro(durchschnitt, nachkommastellen=0)}"
    )
    if prognose.vorhanden:
        anteil = prognose.kapazitaet_limitierend_anteil()
        if anteil > 0:
            untertitel += f". Kapazität war in {anteil:.0%} der Läufe der limitierende Faktor"

    fig = figur("Umsatz je Monat", untertitel=untertitel, hoehe=hoehe)
    fig.add_bar(
        x=[m.beschriftung for m in monate],
        y=[float(m.umsatz) for m in monate],
        offsetgroup="umsatz",
        marker={
            "color": [
                SERIE_HELL if laufender and m.schluessel == laufender.schluessel else SERIE
                for m in monate
            ]
        },
        customdata=[[euro(m.umsatz), f"{m.stunden:,.0f}".replace(",", ".")] for m in monate],
        hovertemplate="<b>%{x}</b><br>%{customdata[0]}<br>%{customdata[1]} Stunden<extra></extra>",
        showlegend=False,
        name="Historie",
    )

    horizont_gesamtumsatz: dict[tuple[int, int], Decimal] = {}
    if prognose.vorhanden:
        horizont_gesamtumsatz = _prognosehorizont(
            fig,
            prognose,
            verbrauch_laufender_monat=laufender,
            schulungsplan=schulungsplan,
        )
    else:
        _keine_prognose_hinweis(fig, prognose)

    horizont_gebucht: list[Decimal] = prognose.gebucht() if prognose.vorhanden else []
    horizont_schulung: list[Decimal] = (
        schulungsplan.umsatz_je_monat(prognose.horizontmonate())
        if prognose.vorhanden and schulungsplan is not None
        else []
    )
    kosten_balken = KostenBalkenErgebnis()
    if kostenplan is not None:
        kosten_balken = _kosten_und_ergebnis(
            fig, monate, prognose, kostenplan, horizont_gesamtumsatz
        )
    if mit_beschriftung:
        # Erst hier, an der oeffentlichen Funktion, statt in den Bauhelfern oben - die
        # bleiben dadurch unveraendert nutzbar, ob mit oder ohne Beschriftung. Liest die
        # Werte aus den schon gezeichneten Spuren zurueck, statt sie erneut zu berechnen.
        # Der laufende Monat traegt am Prognosehorizont nur die Basis eines groesseren
        # Stapels (siehe _balken_beschriften) - dort faellt die Historie-Beschriftung
        # zugunsten der Gesamtwert-Annotation weiter unten weg.
        horizont_monate = {
            _monatsbeschriftung(jahr, monat) for jahr, monat in horizont_gesamtumsatz
        }
        _balken_beschriften(
            fig, "Historie", "Kosten", "Ergebnis", uebersprungen={"Historie": horizont_monate}
        )
        # Eine Beschriftung fuer die Summe aus Schulungsanmeldungen, bereits gebuchtem
        # und simuliertem Umsatz reicht, statt jedes der drei Segmente einzeln zu
        # beschriften (die waeren dafuer meist zu schmal) - oberhalb des ganzen
        # Balkenstapels, den _horizont_gesamtumsatz bereits aufsummiert.
        for (jahr, monat), betrag in horizont_gesamtumsatz.items():
            beschriftung = _monatsbeschriftung(jahr, monat)
            fig.add_annotation(
                x=beschriftung,
                y=float(betrag),
                text=tausend_euro(betrag),
                showarrow=False,
                yshift=10,
                font={"color": TINTE_ZWEITRANGIG, "size": 11},
            )
    _umsatzverlauf_legende(
        fig,
        laufender=laufender,
        horizont_gebucht=horizont_gebucht,
        prognose=prognose,
        horizont_schulung=horizont_schulung,
        kosten_balken=kosten_balken,
    )

    achsen(fig)
    fig.update_layout(bargap=0.3, bargroupgap=0.08, barcornerradius=4, barmode="group")
    fig.update_yaxes(tickformat=",.0f", ticksuffix=" €", rangemode="tozero")
    _tickangle_setzen(fig)
    return fig


def _umsatzverlauf_legende(
    fig: go.Figure,
    *,
    laufender: Monatsumsatz | None,
    horizont_gebucht: Sequence[Decimal],
    prognose: Prognose,
    horizont_schulung: Sequence[Decimal],
    kosten_balken: KostenBalkenErgebnis,
) -> None:
    """Legendeneintraege fuer :func:`umsatzverlauf`, ausgelagert um dessen Komplexitaet
    innerhalb der konfigurierten mccabe-Grenze zu halten - reine Fortsetzung des
    Balkenaufbaus, kein eigenstaendig wiederverwendeter Baustein."""
    _legendeintrag(fig, "Abgerechnet", SERIE)
    if laufender or any(horizont_gebucht):
        _legendeintrag(fig, "Nicht abgerechnet", SERIE_HELL)
    if prognose.vorhanden:
        _legendeintrag(fig, "Prognostiziert", SERIE_HELL, deckkraft=PROGNOSE_DECKKRAFT)
    if any(horizont_schulung):
        _legendeintrag(fig, "Schulungsanmeldungen", SCHULUNG)
    if kosten_balken.gezeichnet:
        if kosten_balken.hat_erfassung:
            _legendeintrag(fig, "Kosten (erfasst)", KOSTEN)
        if kosten_balken.hat_pauschale:
            _legendeintrag(fig, "Kosten (Pauschale)", KOSTEN_HELL)
        _legendeintrag(fig, "Ergebnis (positiv)", ERGEBNIS_POSITIV)
        _legendeintrag(fig, "Ergebnis (negativ)", ERGEBNIS_NEGATIV)
    _horizontale_legende(fig)


def _legendeintrag(fig: go.Figure, name: str, farbe: str, *, deckkraft: float = 1.0) -> None:
    """Eine unsichtbare Spur einzig fuer den Legendeneintrag."""
    fig.add_scatter(
        x=[None],
        y=[None],
        mode="markers",
        marker={"symbol": "square", "size": 11, "color": farbe, "opacity": deckkraft},
        name=name,
        showlegend=True,
        hoverinfo="skip",
    )


class _TickangleKwargs(TypedDict):
    categoryorder: NotRequired[str]
    categoryarray: NotRequired[list[str]]


def _tickangle_setzen(fig: go.Figure, **kwargs: Unpack[_TickangleKwargs]) -> None:
    """Schliesst die x-Achse ab: :data:`TICKWINKEL` plus optionale weitere
    ``update_xaxes``-Kwargs (z. B. ``categoryorder``/``categoryarray`` fuer eine feste
    Monatsreihenfolge) - gemeinsamer letzter Schritt aller Diagramme mit Monatsachse."""
    fig.update_xaxes(tickangle=TICKWINKEL, **kwargs)


def _horizontale_legende(fig: go.Figure) -> None:
    """Legende unterhalb der Figur, wie in :func:`umsatzverlauf` - fuer Diagramme mit
    mehreren Legendenkategorien nebeneinander statt der plotly-Standardlegende rechts."""
    fig.update_layout(
        showlegend=True,
        legend={
            "orientation": "h",
            "yanchor": "top",
            "y": -0.22,
            "xanchor": "center",
            "x": 0.5,
            "font": {"size": 12, "color": TINTE_ZWEITRANGIG},
            "bgcolor": "rgba(0,0,0,0)",
        },
        margin={"b": 60},
    )


def _datensicherheit_legende(fig: go.Figure, *, vorlaeufig: bool, prognose: bool) -> None:
    """Legendeneintraege fuer die Deckkraft-Konvention: Daten, vorlaeufige Daten, Prognose.

    Dieselbe Konvention wie in :func:`umsatzverlauf` (dort ueber "Abgerechnet"/"Nicht
    abgerechnet"/"Prognostiziert" mit je eigener Farbe erklaert) - hier zeigt eine
    einzelne neutrale Farbe in drei Deckkraeften dieselbe Sicherheit, weil Farbe in
    diesen Diagrammen bereits etwas anderes bedeutet (Vorzeichen des Ergebnisses bzw.
    Kalenderjahr).
    """
    _legendeintrag(fig, "Daten", TINTE_ZWEITRANGIG)
    if vorlaeufig:
        _legendeintrag(fig, "Vorläufig", TINTE_ZWEITRANGIG, deckkraft=VORLAEUFIG_DECKKRAFT)
    if prognose:
        _legendeintrag(fig, "Prognose", TINTE_ZWEITRANGIG, deckkraft=PROGNOSE_DECKKRAFT)


def _monatsbeschriftung(jahr: int, monat: int) -> str:
    """Dieselbe Form wie :attr:`Monatsumsatz.beschriftung` - Voraussetzung fuers Stapeln."""
    return f"{MONATSNAMEN[monat - 1]} {jahr}"


def _alle_monatsschluessel(
    monate: Sequence[Monatsumsatz], prognose: Prognose
) -> list[tuple[int, int]]:
    """Die Monate der Historie, ergaenzt um den Prognosehorizont (ohne Dopplung)."""
    schluessel = [m.schluessel for m in monate]
    if prognose.vorhanden:
        schluessel += [m for m in prognose.horizontmonate() if m not in schluessel]
    return schluessel


# Unterhalb dieser Schwelle waere der gedrehte Text im (dann sehr kurzen) Balken
# selbst kaum lesbar - siehe _balken_beschriften.
BALKENTEXT_SCHWELLE = 100_000.0


def _balken_beschriften(
    fig: go.Figure, *namen: str, uebersprungen: Mapping[str, set[str]] | None = None
) -> None:
    """Haengt an die genannten, bereits gezeichneten Balkenspuren ihren Wert als Text.

    Arbeitet auf der fertigen Figur statt den Wert beim Bau jeder Spur ueber ein
    ``mit_beschriftung``-Kwarg mitzugeben - die Bauhelfer (:func:`_kosten_und_ergebnis`
    etc.) bleiben dadurch unveraendert, ob mit oder ohne Beschriftung gezeichnet wird;
    nur die oeffentlichen Diagrammfunktionen kennen den Unterschied. Liest den Wert aus
    der schon gesetzten ``y`` der jeweiligen Spur zurueck, ohne ihn ein zweites Mal zu
    berechnen. Spuren, die gar nicht gezeichnet wurden (z. B. "Kosten" ohne
    Kostenplan), werden stillschweigend uebersprungen. Fuer statische Bildexporte ohne
    Hover-Interaktivitaet (Wochenbericht).

    Ab :data:`BALKENTEXT_SCHWELLE` liegend im Balken (``textangle=-90``, helle Schrift
    fuer Kontrast auf der Balkenfarbe) - bei vielen Monaten und mehreren Balkengruppen
    nebeneinander wuerde waagerechter Text ueber dem Balken mit dem der Nachbarmonate
    ueberlappen. ``constraintext="none"``: plotly schrumpft den Text sonst automatisch,
    sobald der Balken schmal ist. Darunter waere der gedrehte Text selbst kaum lesbar -
    dort deshalb waagerecht und schwarz, als eigene Annotation unterhalb der Nulllinie
    statt auf Balkenhoehe (``textangle`` gilt fuer eine Balkenspur nur einheitlich,
    nicht je Punkt einzeln) - waagerechter Text auf Balkenhoehe wuerde sonst durch den
    gedrehten Text eines hohen Nachbarbalkens reichen. Nur vereinzelte kleine Balken
    brauchen ueberhaupt diese Beschriftung, der Bereich unter der Nulllinie ist deshalb
    fast immer frei.

    ``uebersprungen`` (Spurname -> Monatsbeschriftungen) lässt einzelne Punkte ganz aus
    - fuer :func:`umsatzverlauf`s "Historie"-Balken des laufenden Monats, der am
    Prognosehorizont nur die Basis eines groesseren Stapels ist (Schulungsanmeldungen/
    Bereits gebucht/Prognostiziert obendrauf): eine eigene Beschriftung mit dem
    (kleineren) Basiswert allein waere dort irrefuehrend neben der Gesamtwert-Annotation
    fuer den ganzen Stapel.
    """

    def _spur_beschriften(spur: go.Bar) -> None:
        # ``spur.y`` traegt die schon an plotly uebergebenen ``float``-Werte zurueck
        # (siehe Moduldocstring zur Decimal/float-Grenze) - fuer die Beschriftung hier
        # zurueck in ``Decimal`` gewandelt, ueber ``str()`` statt direkt, um keinen
        # zweiten Binaerrundungsfehler oben drauf zu setzen.
        ausgenommen = (uebersprungen or {}).get(spur.name, set())
        spur.update(
            text=[
                tausend_euro(Decimal(str(wert)))
                if x not in ausgenommen and abs(wert) >= BALKENTEXT_SCHWELLE
                else ""
                for x, wert in zip(spur.x, spur.y, strict=True)
            ],
            textposition="inside",
            textangle=-90,
            insidetextanchor="middle",
            textfont={"color": "#ffffff", "size": 13},
            cliponaxis=False,
            constraintext="none",
        )
        for x, wert in zip(spur.x, spur.y, strict=True):
            if x not in ausgenommen and abs(wert) < BALKENTEXT_SCHWELLE:
                fig.add_annotation(
                    x=x,
                    y=0,
                    text=tausend_euro(Decimal(str(wert))),
                    showarrow=False,
                    yshift=-30,
                    font={"color": TINTE, "size": 13},
                )

    fig.for_each_trace(_spur_beschriften, selector=lambda spur: spur.name in namen)


@dataclass(frozen=True)
class KostenBalkenErgebnis:
    """Was der Aufrufer von :func:`_kosten_und_ergebnis` fuer die Legende braucht.

    Ersetzt ein zuvor positionsabhaengiges ``tuple[bool, bool, bool]`` - dieselben drei
    Fragen, jetzt benannt statt per Tupel-Entpacken der Reihe nach geraten.
    """

    gezeichnet: bool = False
    hat_pauschale: bool = False
    hat_erfassung: bool = False


def _kosten_und_ergebnis(
    fig: go.Figure,
    monate: Sequence[Monatsumsatz],
    prognose: Prognose,
    kostenplan: Kostenplan,
    horizont_gesamtumsatz: dict[tuple[int, int], Decimal],
) -> KostenBalkenErgebnis:
    """Kosten- und Ergebnis-Balken ueber die volle Breite - Historie und Prognosehorizont.

    Je Monat zwei eigene Balken neben dem Umsatzbalken (eigenes ``offsetgroup``, siehe
    ``barmode="group"`` in :func:`umsatzverlauf`): "Kosten" und "Ergebnis" (Umsatz minus
    Kosten - der Umsatz kommt fuer die Historie aus ``monate``, fuer den
    Prognosehorizont aus ``horizont_gesamtumsatz``, siehe :func:`_prognosehorizont`),
    gruen bei positivem, rot bei negativem Vorzeichen. Der Kostenbalken zeigt je Monat
    eine von zwei Saettigungen derselben Farbe, je nachdem ob fuer den Monat eine
    Kostenerfassung vorliegt (siehe :meth:`Kostenplan.hat_erfassung_je_monat`).

    Returns:
        Ob Balken gezeichnet wurden (mindestens ein Monat mit Kosten > 0), ob darunter
        mindestens ein Monat mit der geschaetzten Pauschale und ob mindestens ein Monat
        mit einer tatsaechlichen Kostenerfassung ist - dient dem Aufrufer als Grundlage
        fuer die Legendeneintraege.
    """
    schluessel = _alle_monatsschluessel(monate, prognose)
    kosten = kostenplan.kosten_je_monat(schluessel)
    if not any(kosten):
        return KostenBalkenErgebnis()
    hat_erfassung = kostenplan.hat_erfassung_je_monat(schluessel)
    gesamtumsatz = {m.schluessel: m.umsatz for m in monate} | horizont_gesamtumsatz
    ergebnis = [
        gesamtumsatz.get(s, Decimal("0")) - k for s, k in zip(schluessel, kosten, strict=True)
    ]
    beschriftungen = [_monatsbeschriftung(jahr, monat) for jahr, monat in schluessel]
    fig.add_bar(
        x=beschriftungen,
        y=[float(k) for k in kosten],
        offsetgroup="kosten",
        marker={"color": [KOSTEN if e else KOSTEN_HELL for e in hat_erfassung]},
        customdata=[[euro(betrag)] for betrag in kosten],
        hovertemplate="<b>%{x}</b><br>Kosten: %{customdata[0]}<extra></extra>",
        name="Kosten",
        showlegend=False,
    )
    fig.add_bar(
        x=beschriftungen,
        y=[float(e) for e in ergebnis],
        offsetgroup="ergebnis",
        marker={"color": [ERGEBNIS_POSITIV if b >= 0 else ERGEBNIS_NEGATIV for b in ergebnis]},
        customdata=[[euro(betrag)] for betrag in ergebnis],
        hovertemplate="<b>%{x}</b><br>Ergebnis: %{customdata[0]}<extra></extra>",
        name="Ergebnis",
        showlegend=False,
    )
    return KostenBalkenErgebnis(
        gezeichnet=True, hat_pauschale=not all(hat_erfassung), hat_erfassung=any(hat_erfassung)
    )


def _schulung_je_monat(
    schulungsplan: Schulungsplan | None, horizont: Sequence[tuple[int, int]]
) -> list[Decimal]:
    """Schulungsumsatz je Horizontmonat, 0 je Monat ohne ``schulungsplan``."""
    if schulungsplan is None:
        return [Decimal("0")] * len(horizont)
    return list(schulungsplan.umsatz_je_monat(horizont))


def _horizont_gesamtumsatz(
    prognose: Prognose,
    *,
    verbrauch_laufender_monat: Monatsumsatz | None = None,
    schulungsplan: Schulungsplan | None = None,
) -> dict[tuple[int, int], Decimal]:
    """Gesamtumsatz je Horizontmonat - bereits Realisiertes/Gebuchtes plus Median-Prognose.

    Reine Berechnung ohne Zeichnen, im Unterschied zu :func:`_prognosehorizont`, die
    dieselbe Zahl als Nebenprodukt des Balkenaufbaus zurueckgibt - fuer Aufrufer wie
    :func:`gewinn_verlust_monatlich`, die den Prognosehorizont brauchen, ohne selbst
    einen Umsatzverlauf zu zeichnen.

    Der erste Horizontmonat ist der laufende: er addiert das vor dem Stichtag bereits
    realisierte ``verbrauch_laufender_monat`` zum simulierten Rest-des-Monats-Umsatz.
    Fuer die folgenden Monate deckt der Median bereits den vollen Monat ab - das Modell
    rechnet einen bereits gebuchten Betrag als Untergrenze ein
    (``Monatsumsatz = max(simulierter Umsatz, bereits gebuchter Umsatz)``, siehe
    :mod:`umsatzprognose.domaene.simulation`); nur ``schulungsplan`` kommt additiv fuer
    jeden Monat hinzu, weil er ausserhalb der Simulation steht.
    """
    horizont = prognose.horizontmonate()
    if not horizont:
        return {}
    median = prognose.monatswerte()[0.50]
    schulung = _schulung_je_monat(schulungsplan, horizont)
    basis0 = verbrauch_laufender_monat.umsatz if verbrauch_laufender_monat else Decimal("0")
    gesamt = [basis0 + median[0] + schulung[0]] + [
        m + s for m, s in zip(median[1:], schulung[1:], strict=True)
    ]
    return dict(zip(horizont, gesamt, strict=True))


def _prognosehorizont(
    fig: go.Figure,
    prognose: Prognose,
    *,
    verbrauch_laufender_monat: Monatsumsatz | None,
    schulungsplan: Schulungsplan | None = None,
) -> dict[tuple[int, int], Decimal]:
    """Haengt die Horizontmonate als zweigeteilte Balken an eine bestehende Figur an.

    Der erste Horizontmonat ist der laufende Monat: dessen "bereits gebucht"-Anteil
    steht schon als Balken in der Historie (``verbrauch_laufender_monat``), hier kommt
    nur noch das Prognostizierte obendrauf. Fuer die folgenden Monate liefert
    :meth:`Prognose.gebucht` den gesicherten Anteil. Alle Segmente teilen sich
    ``offsetgroup="umsatz"`` (siehe ``barmode="group"`` in :func:`umsatzverlauf`) und
    ``base``/``y`` werden bewusst manuell gesetzt statt ueber ``barmode="stack"`` (der
    laeuft bei mehreren Kategorien mit gleichem Namen nicht zuverlaessig zusammen) -
    stattdessen zeichnet jede Spur ihr Segment selbst von ``base`` bis ``base + y``.

    Mit ``schulungsplan`` kommt, additiv und unabhaengig von der Simulation, ein
    weiteres Segment "Schulungsanmeldungen" **unten im Stapel** hinzu - direkt ueber dem
    fuer den laufenden Monat schon gezeichneten Historie-Balken bzw. bei 0 fuer die
    folgenden Monate; "Bereits gebucht" und "Prognostiziert" ruecken entsprechend nach
    oben.

    Returns:
        Je Horizontmonat der Gesamtumsatz (Summe aller Segmente) - Grundlage fuer den
        Ergebnis-Balken in :func:`_kosten_und_ergebnis`.
    """
    horizont = prognose.horizontmonate()
    if not horizont:
        return {}
    beschriftungen = [_monatsbeschriftung(jahr, monat) for jahr, monat in horizont]
    monatswerte = prognose.monatswerte()
    gebucht = prognose.gebucht()
    median, p85, p95 = monatswerte[0.50], monatswerte[0.85], monatswerte[0.95]

    basis0 = verbrauch_laufender_monat.umsatz if verbrauch_laufender_monat else Decimal("0")
    schulung = _schulung_je_monat(schulungsplan, horizont)
    schulung_basis = [basis0, *([Decimal("0")] * (len(horizont) - 1))]
    sockel = [basis0 + schulung[0]] + [
        g + s for g, s in zip(gebucht[1:], schulung[1:], strict=True)
    ]
    prognostiziert = [median[0]] + [m - g for m, g in zip(median[1:], gebucht[1:], strict=True)]

    if any(schulung):
        fig.add_bar(
            x=beschriftungen,
            y=[float(s) for s in schulung],
            base=[float(b) for b in schulung_basis],
            offsetgroup="umsatz",
            marker={"color": SCHULUNG},
            customdata=[[euro(betrag)] for betrag in schulung],
            hovertemplate="<b>%{x}</b><br>Schulungsanmeldungen: %{customdata[0]}<extra></extra>",
            showlegend=False,
            name="Schulungsanmeldungen",
        )

    if any(gebucht[1:]):
        fig.add_bar(
            x=beschriftungen[1:],
            y=[float(g) for g in gebucht[1:]],
            base=[float(s) for s in schulung[1:]],
            offsetgroup="umsatz",
            marker={"color": SERIE_HELL},
            customdata=[[euro(betrag)] for betrag in gebucht[1:]],
            hovertemplate="<b>%{x}</b><br>Bereits gebucht: %{customdata[0]}<extra></extra>",
            showlegend=False,
            name="Bereits gebucht",
        )

    fig.add_bar(
        x=beschriftungen,
        y=[float(p) for p in prognostiziert],
        base=[float(s) for s in sockel],
        offsetgroup="umsatz",
        marker={"color": SERIE_HELL, "opacity": PROGNOSE_DECKKRAFT},
        customdata=list(zip([euro(m) for m in median], [euro(p) for p in p85], strict=True)),
        hovertemplate=(
            "<b>%{x}</b><br>Erwartet (Median): %{customdata[0]}<br>"
            "85%-Niveau: %{customdata[1]}<extra></extra>"
        ),
        # Direkt an diesem Balken statt an einer eigenen Spur, damit die Fehlerbalken
        # dessen ``offsetgroup="umsatz"`` erben und ueber dem Umsatzbalken sitzen, statt
        # unter ``barmode="group"`` in der Mitte aller Balkengruppen zu landen.
        error_y={
            "type": "data",
            "symmetric": False,
            "array": [0.0] * len(beschriftungen),
            "arrayminus": [float(m - p) for m, p in zip(median, p95, strict=True)],
            "color": TINTE_GEDAEMPFT,
            "thickness": 1.5,
            "width": 5,
        },
        showlegend=False,
        name="Prognostiziert",
    )

    return _horizont_gesamtumsatz(
        prognose, verbrauch_laufender_monat=verbrauch_laufender_monat, schulungsplan=schulungsplan
    )


def _keine_prognose_hinweis(fig: go.Figure, prognose: Prognose) -> None:
    fig.add_annotation(
        text=_umgebrochen(prognose.begruendung, breite=46),
        showarrow=False,
        x=0.99,
        y=0.9,
        xref="paper",
        yref="paper",
        xanchor="right",
        yanchor="top",
        align="right",
        font={"color": TINTE_ZWEITRANGIG, "size": 11},
    )


def _historie_und_horizont_werte(
    monate: Sequence[Monatsumsatz],
    kosten: Sequence[Decimal],
    prognose: Prognose,
    horizont_kosten: Sequence[Decimal],
    schulungsplan: Schulungsplan | None,
    verbrauch_laufender_monat: Monatsumsatz | None,
) -> tuple[list[str], list[Decimal], list[Decimal], list[float]]:
    """Umsatz und Ergebnis (Umsatz minus Kosten) je Monat, Historie gefolgt vom Horizont.

    Gemeinsame Grundlage fuer :func:`gewinn_verlust_monatlich`, :func:`gewinn_verlust_je_jahr`
    und :func:`umsatzrendite_kumuliert`.

    Returns:
        Beschriftungen, Umsatz je Monat, Ergebnis je Monat und eine parallele
        Deckkraft-Liste: 1.0 fuer die Historie,
        :data:`~umsatzprognose.darstellung.gestaltung.VORLAEUFIG_DECKKRAFT` fuer den
        ersten Horizontmonat (derselbe Kalendermonat wie der laufende - eine Mischung
        aus bereits gebuchtem Umsatz und simuliertem Rest, siehe
        :func:`_horizont_gesamtumsatz`) und
        :data:`~umsatzprognose.darstellung.gestaltung.PROGNOSE_DECKKRAFT` fuer die
        uebrigen, rein simulierten Horizontmonate - dieselbe Konvention wie bei
        :func:`_prognosehorizont`: Sicherheit einer Zahl zeigt sich ueber die
        Deckkraft, nicht ueber eine eigene Farbe.
    """
    beschriftungen = [m.beschriftung for m in monate]
    umsatz = [m.umsatz for m in monate]
    ergebnis = [u - k for u, k in zip(umsatz, kosten, strict=True)]
    deckkraft = [1.0] * len(monate)

    if prognose.vorhanden:
        horizont = prognose.horizontmonate()
        gesamtumsatz = _horizont_gesamtumsatz(
            prognose,
            verbrauch_laufender_monat=verbrauch_laufender_monat,
            schulungsplan=schulungsplan,
        )
        beschriftungen += [_monatsbeschriftung(jahr, monat) for jahr, monat in horizont]
        horizont_umsatz = [gesamtumsatz[schluessel] for schluessel in horizont]
        umsatz += horizont_umsatz
        ergebnis += [u - k for u, k in zip(horizont_umsatz, horizont_kosten, strict=True)]
        # Der erste Horizontmonat ist derselbe Kalendermonat wie der laufende und
        # deshalb kein reines Simulationsergebnis, sondern teils schon gebucht.
        if horizont:
            deckkraft += [VORLAEUFIG_DECKKRAFT] + [PROGNOSE_DECKKRAFT] * (len(horizont) - 1)

    return beschriftungen, umsatz, ergebnis, deckkraft


def _je_jahr(
    monate: Sequence[Monatsumsatz],
    prognose: Prognose,
    umsatz: Sequence[Decimal],
    ergebnis: Sequence[Decimal],
    deckkraft: Sequence[float],
) -> dict[int, list[tuple[int, Decimal, Decimal, float]]]:
    """Ordnet die parallelen Werte-Listen nach Kalenderjahr, je Jahr chronologisch.

    Gemeinsame Grundlage fuer :func:`gewinn_verlust_je_jahr` und
    :func:`umsatzrendite_kumuliert` - jeder Eintrag ist ``(monat, umsatz, ergebnis,
    deckkraft)``.
    """
    schluessel = [m.schluessel for m in monate]
    if prognose.vorhanden:
        schluessel += list(prognose.horizontmonate())

    jahre: dict[int, list[tuple[int, Decimal, Decimal, float]]] = {}
    for (jahr, monat), u, e, deck in zip(schluessel, umsatz, ergebnis, deckkraft, strict=True):
        jahre.setdefault(jahr, []).append((monat, u, e, deck))
    return jahre


# Je Abschnitt: Deckkraft, Strichart (None = durchgezogen) und Hover-Zusatz - dieselbe
# Reihenfolge wie die Deckkraft-Werte aus :func:`_historie_und_horizont_werte` (Daten,
# dann hoechstens ein Punkt mit VORLAEUFIG_DECKKRAFT, dann PROGNOSE_DECKKRAFT).
_LINIENABSCHNITTE = (
    (1.0, None, ""),
    (VORLAEUFIG_DECKKRAFT, None, " (vorläufig)"),
    (PROGNOSE_DECKKRAFT, "dot", " (Vorausschau)"),
)


def _jahreslinien[T: (Decimal, float)](
    fig: go.Figure,
    jahre: dict[int, list[tuple[int, Decimal, Decimal, float]]],
    *,
    werte: Callable[[list[tuple[int, Decimal, Decimal, float]]], list[T]],
    formatieren: Callable[[T], str],
) -> dict[int, list[tuple[str, T, str]]]:
    """Zeichnet fuer jedes Jahr eine Linie in bis zu drei Abschnitten (siehe
    :data:`_LINIENABSCHNITTE`): Daten (durchgezogen, volle Deckkraft), vorlaeufige
    Daten des laufenden Monats (durchgezogen, mittlere Deckkraft) und simulierte
    Prognose (gestrichelt, gedaempft).

    ``werte`` errechnet aus den Punkten eines Jahres (``monat, umsatz, ergebnis,
    deckkraft``) die y-Werte, ``formatieren`` die Hover-Beschriftung je Wert. Jeder
    Abschnitt beginnt am letzten Punkt des vorigen, damit die Linie ohne Bruch
    weiterlaeuft; fehlt ein Abschnitt fuer ein Jahr (z. B. kein Vorlaeufig-Punkt, weil
    kein Prognosehorizont in dieses Jahr faellt), entfaellt er einfach.

    Returns:
        Je Jahr eine Liste von Punkten (Beschriftung, Wert, Farbe) - fuer eine optionale
        Beschriftung beim Aufrufer (siehe :func:`_endpunkte_beschriften`), ohne sie hier
        selbst zu zeichnen. Dieselben Monate fuer jedes Jahr: die Vereinigung aus dem
        letzten Punkt jeder Linie und - traegt ein Jahr sowohl echte (volle Deckkraft)
        als auch simulierte Punkte - der Grenze zwischen beiden (z. B. der laufende
        Monat des aktuellen Jahres). Andere Jahre zeigen an dieser Grenze ihren eigenen
        Wert desselben Kalendermonats, statt dort leer zu bleiben - erst das macht die
        Zahlen zwischen den Jahren vergleichbar.
    """
    beschriftungen_je_jahr: dict[int, list[str]] = {}
    werte_je_jahr: dict[int, list[T]] = {}
    monate_je_jahr: dict[int, list[int]] = {}
    farbe_je_jahr: dict[int, str] = {}
    eigene_monate_je_jahr: dict[int, set[int]] = {}

    for index, jahr in enumerate(sorted(jahre)):
        punkte = jahre[jahr]
        farbe = JAHRESFARBEN[index % len(JAHRESFARBEN)]
        beschriftungen = [MONATSNAMEN[monat - 1] for monat, *_rest in punkte]
        y = werte(punkte)
        monate = [monat for monat, *_rest in punkte]
        deckkraft_folge = [deck for *_rest, deck in punkte]

        ende = 0
        jahr_hat_legende = False
        for deckkraft, dash, hinweis in _LINIENABSCHNITTE:
            start = max(ende - 1, 0)
            neues_ende = ende
            while neues_ende < len(punkte) and deckkraft_folge[neues_ende] == deckkraft:
                neues_ende += 1
            if neues_ende == ende:
                continue
            fig.add_scatter(
                x=beschriftungen[start:neues_ende],
                y=[float(v) for v in y[start:neues_ende]],
                mode="lines+markers",
                line={"color": farbe, "width": 2, "dash": dash},
                marker={"size": 6, "opacity": deckkraft},
                opacity=deckkraft,
                customdata=[[formatieren(wert)] for wert in y[start:neues_ende]],
                hovertemplate=f"<b>{jahr} %{{x}}</b><br>%{{customdata[0]}}{hinweis}<extra></extra>",
                name=str(jahr),
                legendgroup=str(jahr),
                showlegend=not jahr_hat_legende,
            )
            jahr_hat_legende = True
            ende = neues_ende

        # Letzter Index mit voller Deckkraft (1.0) - die Grenze zwischen echten und
        # simulierten Punkten. -1, wenn das Jahr (nur moeglich am aktuellen
        # Prognosehorizont) gar keinen echten Punkt traegt.
        grenze = -1
        for i, deck in enumerate(deckkraft_folge):
            if deck != 1.0:
                break
            grenze = i

        eigene_monate = {monate[-1]}
        if grenze not in (-1, len(punkte) - 1):
            eigene_monate.add(monate[grenze])

        beschriftungen_je_jahr[jahr] = beschriftungen
        werte_je_jahr[jahr] = y
        monate_je_jahr[jahr] = monate
        farbe_je_jahr[jahr] = farbe
        eigene_monate_je_jahr[jahr] = eigene_monate

    alle_monate: set[int] = set()
    for eigene_monate in eigene_monate_je_jahr.values():
        alle_monate |= eigene_monate

    return {
        jahr: [
            (beschriftungen_je_jahr[jahr][i], werte_je_jahr[jahr][i], farbe_je_jahr[jahr])
            for i, monat in enumerate(monate_je_jahr[jahr])
            if monat in alle_monate
        ]
        for jahr in jahre
    }


def _endpunkte_beschriften[T: (Decimal, float)](
    fig: go.Figure,
    letzte_punkte: dict[int, list[tuple[str, T, str]]],
    formatieren: Callable[[T], str],
) -> None:
    """Beschriftet die Punkte aus :func:`_jahreslinien` (Ist/Simulation-Grenze und/oder
    Linienende).

    Gemeinsam fuer :func:`gewinn_verlust_je_jahr` und :func:`umsatzrendite_kumuliert` -
    hoechstens zwei Punkte je Jahr, nicht jeder einzelne Monat, sonst waere bei bis zu
    acht Jahren auf derselben Monatsachse eine Beschriftung je Punkt unlesbar. Fuer
    statische Bildexporte ohne Hover-Interaktivitaet (Wochenbericht).
    """
    for jahr, punkte in letzte_punkte.items():
        for beschriftung, wert, farbe in punkte:
            fig.add_annotation(
                x=beschriftung,
                y=float(wert),
                text=f"{jahr}: {formatieren(wert)}",
                showarrow=False,
                xanchor="left",
                yshift=8,
                font={"color": farbe, "size": 11},
            )


def gewinn_verlust_monatlich(
    monate: Sequence[Monatsumsatz],
    kosten: Sequence[Decimal],
    *,
    prognose: Prognose = _KEINE_PROGNOSE,
    horizont_kosten: Sequence[Decimal] = (),
    schulungsplan: Schulungsplan | None = None,
    verbrauch_laufender_monat: Monatsumsatz | None = None,
    hoehe: int = 380,
    mit_beschriftung: bool = False,
) -> go.Figure:
    """Gewinn/Verlust je Monat als Balken - gruen bei Gewinn, rot bei Verlust.

    ``kosten`` steht parallel zu ``monate`` (siehe
    :meth:`~umsatzprognose.domaene.kosten.Kostenplan.kosten_je_monat`). Anders als
    :func:`_kosten_und_ergebnis` zeigt diese Funktion nur das Ergebnis selbst, ohne
    Umsatz- und Kostenbalken daneben - fuer einen reinen Gewinn/Verlust-Rueckblick ueber
    mehrere Monate statt eines Ausschnitts aus dem Umsatzverlauf.

    Mit ``prognose`` haengt sich, additiv an die Historie, eine Vorausschau fuer den
    Prognosehorizont an (``horizont_kosten`` parallel zu ``prognose.horizontmonate()``)
    - gedaempfte Balken statt einer eigenen Farbe, dieselbe Konvention wie beim
    Umsatzverlauf; der erste Horizontmonat (derselbe Kalendermonat wie der laufende)
    bekommt dabei eine eigene Zwischenstufe, siehe
    :data:`~umsatzprognose.darstellung.gestaltung.VORLAEUFIG_DECKKRAFT`. Eine Legende
    erklaert die drei Stufen, siehe :func:`_datensicherheit_legende`.
    ``verbrauch_laufender_monat`` liefert das vor dem Stichtag bereits Realisierte des
    laufenden Monats, ``schulungsplan`` zusaetzlich additiven Umsatz aus bereits
    geplanten Schulungsterminen - siehe :func:`_horizont_gesamtumsatz`.
    ``mit_beschriftung`` siehe :func:`umsatzverlauf`.
    """
    beschriftungen, _umsatz, ergebnis, deckkraft = _historie_und_horizont_werte(
        monate, kosten, prognose, horizont_kosten, schulungsplan, verbrauch_laufender_monat
    )
    gesamt = sum(ergebnis, Decimal("0"))
    horizont = prognose.horizontmonate() if prognose.vorhanden else ()

    untertitel = f"Summe über {len(monate)} Monate: {euro(gesamt, nachkommastellen=0)}"
    fig = figur("Gewinn/Verlust je Monat", untertitel=untertitel, hoehe=hoehe)
    fig.add_bar(
        x=beschriftungen,
        y=[float(e) for e in ergebnis],
        marker={
            "color": [ERGEBNIS_POSITIV if e >= 0 else ERGEBNIS_NEGATIV for e in ergebnis],
            "opacity": deckkraft,
        },
        customdata=[[euro(betrag)] for betrag in ergebnis],
        hovertemplate="<b>%{x}</b><br>%{customdata[0]}<extra></extra>",
        name="Ergebnis",
        showlegend=False,
    )
    if mit_beschriftung:
        _balken_beschriften(fig, "Ergebnis")
    if not prognose.vorhanden:
        _keine_prognose_hinweis(fig, prognose)
    if horizont:
        _datensicherheit_legende(fig, vorlaeufig=True, prognose=len(horizont) > 1)
        _horizontale_legende(fig)
    achsen(fig)
    fig.update_layout(bargap=0.3, barcornerradius=4)
    fig.update_yaxes(tickformat=",.0f", ticksuffix=" €")
    _tickangle_setzen(fig)
    return fig


def gewinn_verlust_je_jahr(
    monate: Sequence[Monatsumsatz],
    kosten: Sequence[Decimal],
    *,
    prognose: Prognose = _KEINE_PROGNOSE,
    horizont_kosten: Sequence[Decimal] = (),
    schulungsplan: Schulungsplan | None = None,
    verbrauch_laufender_monat: Monatsumsatz | None = None,
    hoehe: int = 380,
    mit_beschriftung: bool = False,
) -> go.Figure:
    """Fuer jedes Kalenderjahr in ``monate`` eine eigene Linie der monatlichen Werte.

    Anders als :func:`gewinn_verlust_monatlich` ist das hier bewusst kein
    zusammenhaengender Zeitraum, sondern ein Jahresvergleich auf einer gemeinsamen
    Monatsachse (Jan bis Dez) - wie in der urspruenglichen Praesentation. Gezeigt wird
    das Ergebnis je einzelnem Monat, nicht aufsummiert (fuer die kumulierte Sicht
    siehe :func:`umsatzrendite_kumuliert`). ``monate`` traegt deshalb typischerweise
    die gesamte geladene Historie, nicht nur ein Fenster wie die uebrigen Ansichten
    (siehe :meth:`~umsatzprognose.darstellung.dashboard.Dashboard.gewinn_verlust_je_jahr`).

    Mit ``prognose`` (siehe :func:`gewinn_verlust_monatlich` fuer die uebrigen
    Parameter) haengt sich an das juengste Jahr die Vorausschau fuer den
    Prognosehorizont an - gestrichelt und gedaempft ab dem letzten Ist-Monat, ohne
    Bruch. Faellt der Horizont in ein neues Kalenderjahr, beginnt dessen Linie direkt
    gestrichelt, ohne eigenen Ist-Abschnitt. ``mit_beschriftung`` siehe
    :func:`umsatzverlauf`.
    """
    _beschriftungen, umsatz, ergebnis, deckkraft = _historie_und_horizont_werte(
        monate, kosten, prognose, horizont_kosten, schulungsplan, verbrauch_laufender_monat
    )
    jahre = _je_jahr(monate, prognose, umsatz, ergebnis, deckkraft)

    fig = figur("Gewinn/Verlust je Monat und Jahr", hoehe=hoehe)
    letzte_punkte = _jahreslinien(
        fig,
        jahre,
        werte=lambda punkte: [ergebnis for _monat, _umsatz, ergebnis, _deck in punkte],
        formatieren=euro,
    )
    if mit_beschriftung:
        _endpunkte_beschriften(fig, letzte_punkte, euro)
    fig.add_hline(y=0, line={"color": ACHSE, "width": 1})
    if VORLAEUFIG_DECKKRAFT in deckkraft or PROGNOSE_DECKKRAFT in deckkraft:
        _datensicherheit_legende(
            fig,
            vorlaeufig=VORLAEUFIG_DECKKRAFT in deckkraft,
            prognose=PROGNOSE_DECKKRAFT in deckkraft,
        )
    _horizontale_legende(fig)
    achsen(fig)
    fig.update_yaxes(tickformat=",.0f", ticksuffix=" €")
    _tickangle_setzen(fig, categoryorder="array", categoryarray=list(MONATSNAMEN))
    return fig


def umsatzrendite_kumuliert(
    monate: Sequence[Monatsumsatz],
    kosten: Sequence[Decimal],
    *,
    prognose: Prognose = _KEINE_PROGNOSE,
    horizont_kosten: Sequence[Decimal] = (),
    schulungsplan: Schulungsplan | None = None,
    verbrauch_laufender_monat: Monatsumsatz | None = None,
    hoehe: int = 380,
    mit_beschriftung: bool = False,
) -> go.Figure:
    """Fuer jedes Kalenderjahr die kumulierte Umsatzrendite (Gewinn/Umsatz) je Monat.

    "Kumuliert" heisst hier: kumulierter Gewinn geteilt durch kumulierten Umsatz bis
    zu diesem Monat (eine Year-to-Date-Marge) - nicht die Summe monatlicher
    Prozentwerte, die von unterschiedlich grossen Monatsumsaetzen verzerrt waere.
    Januar zeigt deshalb die Rendite des Monats selbst, Februar die der ersten beiden
    Monate zusammen, und so weiter. Aufbau und Vorausschau-Konvention wie
    :func:`gewinn_verlust_je_jahr`, dort auch die uebrigen Parameter erklaert. Ein
    Monat ganz ohne Umsatz (weder Ist noch Vorausschau) zeigt 0 % statt eines Fehlers.
    ``mit_beschriftung`` siehe :func:`umsatzverlauf`.
    """
    _beschriftungen, umsatz, ergebnis, deckkraft = _historie_und_horizont_werte(
        monate, kosten, prognose, horizont_kosten, schulungsplan, verbrauch_laufender_monat
    )
    jahre = _je_jahr(monate, prognose, umsatz, ergebnis, deckkraft)

    def rendite_je_monat(punkte: list[tuple[int, Decimal, Decimal, float]]) -> list[float]:
        # Eine reine Verhaeltniszahl (Gewinn/Umsatz) und keine Geldgroesse - deshalb ab
        # hier bewusst in ``float`` gerechnet, wie die uebrigen Quoten der Domaene.
        kumulierter_umsatz = kumuliertes_ergebnis = 0.0
        werte = []
        for _monat, monatsumsatz, monatsergebnis, _deck in punkte:
            kumulierter_umsatz += float(monatsumsatz)
            kumuliertes_ergebnis += float(monatsergebnis)
            anteil = kumuliertes_ergebnis / kumulierter_umsatz if kumulierter_umsatz else 0.0
            werte.append(anteil * 100)
        return werte

    def prozentformat(prozentpunkte: float) -> str:
        return prozent(prozentpunkte / 100, nachkommastellen=1)

    fig = figur("Kumulierte Umsatzrendite je Jahr", hoehe=hoehe)
    letzte_punkte = _jahreslinien(fig, jahre, werte=rendite_je_monat, formatieren=prozentformat)
    if mit_beschriftung:
        _endpunkte_beschriften(fig, letzte_punkte, prozentformat)
    fig.add_hline(y=0, line={"color": ACHSE, "width": 1})
    if VORLAEUFIG_DECKKRAFT in deckkraft or PROGNOSE_DECKKRAFT in deckkraft:
        _datensicherheit_legende(
            fig,
            vorlaeufig=VORLAEUFIG_DECKKRAFT in deckkraft,
            prognose=PROGNOSE_DECKKRAFT in deckkraft,
        )
    _horizontale_legende(fig)
    achsen(fig)
    fig.update_yaxes(tickformat=",.1f", ticksuffix=" %")
    _tickangle_setzen(fig, categoryorder="array", categoryarray=list(MONATSNAMEN))
    return fig


def _rangliste_hoehe(anzahl: int) -> int:
    return max(260, 70 + 30 * anzahl)


def _rangliste_untertitel(gesamt: int, gezeigt: int, mitte: str) -> str:
    """``"{gesamt} {mitte}"``, ergaenzt um den Rest-Hinweis, wenn nicht alle gezeigt werden."""
    rest = gesamt - gezeigt
    untertitel = f"{gesamt} {mitte}"
    if rest > 0:
        untertitel += f", gezeigt sind die {gezeigt} größten und {rest} weitere folgen"
    return untertitel


def _liegende_rangliste(
    fig: go.Figure,
    *,
    werte: Sequence[float],
    text: Sequence[str],
    ticktext: Sequence[str],
    hovertemplate: str,
    customdata: Sequence[object] | None = None,
) -> None:
    """Die liegenden Balken einer bereits auf ``top`` gekuerzten und umgekehrten Rangliste.

    Gemeinsamer Kern von :func:`restvolumen_je_projekt`, :func:`kapazitaet_je_mitarbeiter`,
    :func:`auslastung_je_mitarbeiter` und :func:`kapazitaet_je_projekt` - die Werte
    selbst, ihre Beschriftung und der Hovertext unterscheiden sich, Balkenaufbau und
    Achsen nicht.
    """
    fig.add_bar(
        x=list(werte),
        y=list(range(len(werte))),
        orientation="h",
        marker={"color": SERIE},
        text=list(text),
        textposition="outside",
        textfont={"color": TINTE_ZWEITRANGIG, "size": 12},
        cliponaxis=False,
        customdata=customdata,
        hovertemplate=hovertemplate,
        showlegend=False,
    )
    achsen(fig, gitter_x=True, gitter_y=False)
    fig.update_layout(bargap=0.4, barcornerradius=4)
    groesster = max(werte, default=0.0)
    # Luft rechts, sonst schneidet der Rand die Beschriftung des laengsten Balkens ab.
    fig.update_xaxes(visible=False, range=[0, groesster * 1.18])
    fig.update_yaxes(
        tickmode="array",
        tickvals=list(range(len(werte))),
        ticktext=list(ticktext),
        tickfont={"color": TINTE, "size": 12},
        automargin=True,
    )


def restvolumen_je_projekt(
    projekte: Sequence[Projekt], *, top: int = 15, hoehe: int | None = None
) -> go.Figure:
    """Die groessten offenen Volumina als liegende Balken, beschriftet mit dem Betrag.

    Liegend, weil die Beschriftung aus Kunde und Projekt besteht und senkrecht
    unlesbar waere. Die Zahl steht am Balkenende - bei hoechstens 15 Zeilen ist das
    ruhiger als eine zusaetzliche Achse.
    """
    gezeigt = list(projekte[:top])
    gesamt = sum((p.restvolumen_prognosewirksam or Decimal("0") for p in projekte), Decimal("0"))
    untertitel = _rangliste_untertitel(
        len(projekte), len(gezeigt), f"Projekte mit zusammen {euro(gesamt, nachkommastellen=0)}"
    )
    fig = figur(
        "Offenes Auftragsvolumen je Projekt",
        untertitel=untertitel,
        hoehe=hoehe or _rangliste_hoehe(len(gezeigt)),
    )
    # Die Kategorie ist die Position, nicht die Beschriftung: zwei Projekte koennen
    # denselben Namen tragen oder auf denselben gekuerzten Namen fallen, und plotly
    # wuerde sie dann zu einem Balken addieren - eine still falsche Zahl.
    umgekehrt = list(reversed(gezeigt))
    _liegende_rangliste(
        fig,
        werte=[float(p.restvolumen_prognosewirksam or Decimal("0")) for p in umgekehrt],
        text=[tausend_euro(p.restvolumen_prognosewirksam or Decimal("0")) for p in umgekehrt],
        ticktext=[_achsenbeschriftung(p) for p in umgekehrt],
        customdata=[
            [p.bezeichnung, euro(p.auftragsvolumen or Decimal("0")), euro(p.verbrauchtes_volumen)]
            for p in umgekehrt
        ],
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>Offen: %{x:,.0f} €<br>"
            "Beauftragt: %{customdata[1]}<br>Verbraucht: %{customdata[2]}<extra></extra>"
        ),
    )
    return fig


def kapazitaet_je_mitarbeiter(
    kapazitaeten: Sequence[tuple[Mitarbeiter, float]], *, top: int = 15, hoehe: int | None = None
) -> go.Figure:
    """Verfuegbare Kapazitaet je Person, aufsummiert ueber mehrere Monate, in Tagen.

    ``kapazitaeten`` kommt bereits absteigend sortiert (siehe
    :meth:`~umsatzprognose.darstellung.dashboard.Dashboard.kapazitaet_je_mitarbeiter`),
    analog zu :func:`restvolumen_je_projekt`. Angezeigt wird in Personentagen à
    :data:`~umsatzprognose.domaene.zahlen.STUNDEN_JE_TAG` Stunden statt in Stunden -
    die griffigere Einheit fuer "wer hat noch Luft".
    """
    gezeigt = list(kapazitaeten[:top])
    gesamt = sum(stunden for _, stunden in kapazitaeten)
    untertitel = _rangliste_untertitel(
        len(kapazitaeten), len(gezeigt), f"Personen mit zusammen {tage(gesamt)}"
    )
    fig = figur(
        "Verfügbare Kapazität je Person",
        untertitel=untertitel,
        hoehe=hoehe or _rangliste_hoehe(len(gezeigt)),
    )
    umgekehrt = list(reversed(gezeigt))
    _liegende_rangliste(
        fig,
        werte=[stunden / STUNDEN_JE_TAG for _, stunden in umgekehrt],
        text=[tage(stunden) for _, stunden in umgekehrt],
        ticktext=[_gekuerzt(str(m), MAXIMALE_PROJEKTLAENGE) for m, _ in umgekehrt],
        hovertemplate="<b>%{y}</b><br>%{text}<extra></extra>",
    )
    return fig


def auslastung_je_mitarbeiter(
    auslastungen: Sequence[Auslastungsmonat] | Sequence[Auslastungssumme],
    *,
    top: int = 15,
    hoehe: int | None = None,
) -> go.Figure:
    """Anteil abrechenbarer Stunden an der verfuegbaren Kapazitaet, liegende Balken in Prozent.

    Personen ohne verfuegbare Kapazitaet im dargestellten Zeitraum (``quote is None``,
    siehe :attr:`~umsatzprognose.domaene.auslastung.Auslastungsmonat.quote` bzw.
    :attr:`~umsatzprognose.domaene.auslastung.Auslastungssumme.quote`) werden
    weggelassen, statt sie mit einer irrefuehrenden 0%-Auslastung zu zeigen.
    """
    mit_quote = [(a, a.quote) for a in auslastungen if a.quote is not None]
    mit_quote.sort(key=lambda paar: paar[1], reverse=True)
    gezeigt = mit_quote[:top]
    untertitel = _rangliste_untertitel(
        len(mit_quote), len(gezeigt), "Personen mit hinterlegter Kapazität"
    )
    fig = figur(
        "Auslastung je Person", untertitel=untertitel, hoehe=hoehe or _rangliste_hoehe(len(gezeigt))
    )
    umgekehrt = list(reversed(gezeigt))
    _liegende_rangliste(
        fig,
        werte=[quote for _, quote in umgekehrt],
        text=[prozent(quote) for _, quote in umgekehrt],
        ticktext=[_gekuerzt(str(a.mitarbeiter), MAXIMALE_PROJEKTLAENGE) for a, _ in umgekehrt],
        hovertemplate="<b>%{y}</b><br>%{text}<extra></extra>",
    )
    return fig


def kapazitaet_je_projekt(
    kapazitaeten: Sequence[tuple[Projekt, float]], *, top: int = 15, hoehe: int | None = None
) -> go.Figure:
    """Simulierte Kapazitaet je Projekt, als liegende Balken in Tagen.

    Zeigt, wie sich die in der Monte-Carlo-Simulation ueber den Prognosehorizont
    tatsaechlich verbrauchte Kapazitaet auf die Projekte im Scope verteilt (Median der
    gelieferten Stunden ueber alle Laeufe, siehe
    :meth:`~umsatzprognose.domaene.prognose.Prognose.kapazitaet_je_projekt`).
    Pauschalprojekte ohne ableitbaren Stundensatz zeigen dabei bewusst 0 Tage - sie
    verbrauchen keine Personenkapazitaet, obwohl sie Umsatz liefern.
    """
    gezeigt = list(kapazitaeten[:top])
    gesamt = sum(stunden for _, stunden in kapazitaeten)
    untertitel = _rangliste_untertitel(
        len(kapazitaeten), len(gezeigt), f"Projekte mit zusammen {tage(gesamt)}"
    )
    fig = figur(
        "Simulierte Kapazität je Projekt",
        untertitel=untertitel,
        hoehe=hoehe or _rangliste_hoehe(len(gezeigt)),
    )
    umgekehrt = list(reversed(gezeigt))
    _liegende_rangliste(
        fig,
        werte=[stunden / STUNDEN_JE_TAG for _, stunden in umgekehrt],
        text=[tage(stunden) for _, stunden in umgekehrt],
        ticktext=[_achsenbeschriftung(p) for p, _ in umgekehrt],
        customdata=[[p.bezeichnung] for p, _ in umgekehrt],
        hovertemplate="<b>%{customdata[0]}</b><br>%{text}<extra></extra>",
    )
    return fig


def _achsenbeschriftung(projekt: Projekt) -> str:
    """Kunde und Projekt, jeweils fuer sich gekuerzt."""
    kunde = _gekuerzt(str(projekt.kunde), MAXIMALE_KUNDENLAENGE) if projekt.kunde else ""
    name = _gekuerzt(projekt.name or f"Projekt {projekt.id}", MAXIMALE_PROJEKTLAENGE)
    return f"{kunde} / {name}" if kunde else name


def _gekuerzt(text: str, laenge: int) -> str:
    return text if len(text) <= laenge else text[: laenge - 1] + "…"


def _umgebrochen(text: str, breite: int = 80) -> str:
    """Zeilenumbruch fuer die Plotly-Annotation - ``break_long_words=False`` und
    ``break_on_hyphens=False``, weil hier nur an Leerraum umgebrochen werden soll, nie
    innerhalb eines (auch zusammengesetzten) Wortes."""
    zeilen = textwrap.wrap(
        " ".join(text.split()), width=breite, break_long_words=False, break_on_hyphens=False
    )
    return "<br>".join(zeilen)


def _linearer_trend(werte: Sequence[float]) -> list[float]:
    """Ausgleichsgerade (kleinste Quadrate) ueber den Monatsindex 0..n-1.

    Eine Gerade statt einer geglaetteten Kurve, weil sie die Richtung des Verlaufs ueber
    den ganzen Betrachtungszeitraum in einer Steigung zusammenfasst. Bei weniger als
    zwei Werten ist eine Gerade nicht definiert - ``werte`` unveraendert zurueckgegeben.
    """
    n = len(werte)
    if n < 2:
        return list(werte)
    summe_x = n * (n - 1) / 2
    summe_x2 = sum(x * x for x in range(n))
    summe_y = sum(werte)
    summe_xy = sum(x * y for x, y in enumerate(werte))
    nenner = n * summe_x2 - summe_x * summe_x
    steigung = (n * summe_xy - summe_x * summe_y) / nenner
    achsenabschnitt = (summe_y - steigung * summe_x) / n
    return [achsenabschnitt + steigung * x for x in range(n)]


def anmeldungsverlauf(verlauf: Anmeldungsverlauf, *, hoehe: int = 420) -> go.Figure:
    """Teilnehmerzahl oeffentlicher Schulungen je Monat, insgesamt - eine Linie mit
    Datenpunkten, dazu eine lineare Trendlinie (Ausgleichsgerade), siehe
    :func:`_linearer_trend`.

    Bewusst nur die Gesamtzahl, keine Aufschluesselung nach Kategorie oder
    Schulungstyp mehr im Diagramm (eine fruehere Fassung gruppierte per von Hand
    gepflegter Zuordnung nach Scrum/Kanban/Sonstige - das veraltete unbemerkt, sobald
    neue Schulungstypen dazukamen). Der Blick auf einzelne Schulungstypen ist ein
    eigener Drilldown als Tabelle, siehe
    :func:`~umsatzprognose.darstellung.tabellen.anmeldungstabelle`.

    Anders als :func:`umsatzverlauf` keine Umsatzgroesse, sondern die Teilnehmerzahl aus
    der Spalte ``TN Zahl`` (siehe Moduldocstring von
    :mod:`umsatzprognose.domaene.anmeldung`). ``verlauf`` liefert bereits den
    gewuenschten Betrachtungszeitraum (etwa ueber
    :meth:`~umsatzprognose.domaene.anmeldung.Anmeldungsverlauf.letzte` fuer ein
    konfigurierbares Fenster wie die letzten 13 Monate) - diese Funktion zeigt ihn
    unveraendert, ohne selbst ein Zeitfenster anzuwenden.

    Anders als die uebrigen Diagrammfunktionen bewusst ohne ``mit_beschriftung``: eine
    einzelne Zahl am Ende der Linie hilft bei so wenigen Monaten kaum weiter, der
    Hover-Tooltip reicht - siehe :func:`umsatzverlauf` fuer den Parameter bei den
    uebrigen Diagrammen.
    """
    monate = verlauf.monate
    fig = figur(
        "Anmeldungen je Monat",
        untertitel="Teilnehmerzahl öffentlicher Schulungen, mit Trend",
        hoehe=hoehe,
    )
    if not monate:
        fig.add_annotation(
            text="Keine Anmeldedaten für den gewählten Zeitraum geladen.",
            showarrow=False,
            font={"color": TINTE_ZWEITRANGIG, "size": 13},
        )
        return fig

    beschriftungen = [f"{MONATSNAMEN[monat - 1]} {jahr}" for jahr, monat in monate]
    je_monat = verlauf.je_monat()
    gesamt = [je_monat.get(m, 0) for m in monate]

    fig.add_scatter(
        x=beschriftungen,
        y=gesamt,
        mode="lines+markers",
        name="Anmeldungen",
        line={"color": TINTE, "width": 2},
        marker={"size": 6, "color": TINTE},
    )
    fig.add_scatter(
        x=beschriftungen,
        y=_linearer_trend(gesamt),
        mode="lines",
        name="Trend",
        line={"color": TREND, "width": 2, "dash": "dash"},
    )

    _horizontale_legende(fig)
    achsen(fig)
    fig.update_yaxes(rangemode="tozero")
    _tickangle_setzen(fig)
    return fig


def anmeldungsverlauf_reihen(
    reihen: Mapping[str, Mapping[Monat, int]],
    monate: Sequence[Monat],
    *,
    mit_trend: bool = False,
    hoehe: int = 420,
) -> go.Figure:
    """Wie :func:`anmeldungsverlauf`, aber mit einer waehlbaren Anzahl benannter,
    einzeln eingefaerbter Reihen statt nur der Gesamtzahl - der interaktive Filter in
    der Webapp (siehe ``webapp/templates/schulungen.html`` und Moduldocstring von
    :mod:`umsatzprognose.domaene.anmeldung`).

    ``reihen`` bildet einen Anzeigenamen (Kategorie, Schulungstyp, Format oder Dauer)
    auf seine Monatswerte ab - die Aufrufstelle entscheidet, was eine Reihe bedeutet,
    diese Funktion zeichnet nur. Die Reihe ``"Alle Schulungen"`` behaelt die Farbe
    :data:`~umsatzprognose.darstellung.gestaltung.TINTE` aus :func:`anmeldungsverlauf`,
    fuer denselben Anblick wie ohne jede Auswahl. Alle anderen Reihen bekommen der
    Reihe nach (nicht nach Alphabet, sondern nach Einfuegereihenfolge in ``reihen``)
    eine Farbe aus :data:`~umsatzprognose.darstellung.gestaltung.JAHRESFARBEN` - dieselbe
    CVD-sichere Palette wie beim Kalenderjahresvergleich
    (:func:`gewinn_verlust_je_jahr`), hier je gewaehltem Filterkriterium statt je Jahr.

    ``mit_trend`` ergaenzt je Reihe eine gestrichelte lineare Trendlinie
    (:func:`_linearer_trend`) in derselben Farbe, ohne eigenen Legendeneintrag -
    zusammen mit der Datenlinie durch dieselbe ``legendgroup`` verbunden.
    """
    fig = figur(
        "Anmeldungen je Monat",
        untertitel="Teilnehmerzahl öffentlicher Schulungen" + (", mit Trend" if mit_trend else ""),
        hoehe=hoehe,
    )
    if not monate or not reihen:
        fig.add_annotation(
            text="Keine Anmeldedaten für den gewählten Zeitraum/die gewählte Auswahl.",
            showarrow=False,
            font={"color": TINTE_ZWEITRANGIG, "size": 13},
        )
        return fig

    beschriftungen = [f"{MONATSNAMEN[monat - 1]} {jahr}" for jahr, monat in monate]
    farbenindex = 0
    for name, je_monat in reihen.items():
        if name == "Alle Schulungen":
            farbe = TINTE
        else:
            farbe = JAHRESFARBEN[farbenindex % len(JAHRESFARBEN)]
            farbenindex += 1
        werte = [je_monat.get(monat, 0) for monat in monate]
        fig.add_scatter(
            x=beschriftungen,
            y=werte,
            mode="lines+markers",
            name=name,
            legendgroup=name,
            line={"color": farbe, "width": 2},
            marker={"size": 6, "color": farbe},
        )
        if mit_trend:
            fig.add_scatter(
                x=beschriftungen,
                y=_linearer_trend([float(w) for w in werte]),
                mode="lines",
                name=f"{name} (Trend)",
                legendgroup=name,
                showlegend=False,
                line={"color": farbe, "width": 2, "dash": "dash"},
            )

    _horizontale_legende(fig)
    achsen(fig)
    fig.update_yaxes(rangemode="tozero")
    _tickangle_setzen(fig)
    return fig


def kurzarbeit_grafik(
    ergebnisse: Mapping[Monat, Kurzarbeitsbewertung],
    *,
    mit_beschriftung: bool = False,
    hoehe: int = 420,
) -> go.Figure:
    """Kurzarbeitsbereitschaft je Monat: ein groesserer Balken fuer die Gesamtzahl
    einbezogener Personen, ein schmalerer davor fuer die tatsaechlich
    kurzarbeitsfaehigen, dazu die Quote als Linie auf einer zweiten y-Achse - die
    Marker der Linie sind je nachdem eingefaerbt, ob die Schwelle in diesem Monat
    erreicht wurde.

    Anders als die uebrigen Diagrammfunktionen mit einer sichtbaren Legende (drei statt
    einer einzelnen Kategorie: Gesamtanzahl, Kurzarbeitsfaehig, Quote). ``mit_beschriftung``
    zeigt Werte als Text an Balken/Punkten - fuer den statischen Bildexport im
    Wochenbericht (``scripts/wochenbericht.py``) ohne Hover-Tooltip; Notebook und Webapp
    lassen es aus und zeigen die Werte interaktiv per Hover, wie bei den uebrigen
    Diagrammen (siehe :func:`umsatzverlauf`).
    """
    monate = sorted(ergebnisse)
    beschriftungen = [f"{MONATSNAMEN[monat[1] - 1]} {monat[0]}" for monat in monate]
    schwelle = ergebnisse[monate[-1]].schwellenwerte.quote_organisation

    gesamtzahlen = [ergebnisse[m].anzahl_einbezogen for m in monate]
    kurzarbeitsfaehig = [ergebnisse[m].anzahl_kurzarbeitsfaehig for m in monate]
    quoten = [ergebnisse[m].quote for m in monate]
    quoten_prozent = [(q or 0.0) * 100 for q in quoten]
    markerfarben = [
        KURZARBEIT_SCHWELLE_ERREICHT
        if (q is not None and q >= schwelle)
        else KURZARBEIT_SCHWELLE_NICHT_ERREICHT
        for q in quoten
    ]

    fig = figur(
        "Kurzarbeitsbereitschaft je Monat",
        untertitel=f"Kurzarbeitsfähige Personen je Monat, Schwelle {schwelle:.0%}",
        hoehe=hoehe,
    )
    achsen(fig)
    fig.add_bar(
        x=beschriftungen,
        y=gesamtzahlen,
        name="Gesamtanzahl",
        width=0.6,
        marker_color=SERIE_HELL,
        text=[str(g) for g in gesamtzahlen] if mit_beschriftung else None,
        textposition="outside",
    )
    fig.add_bar(
        x=beschriftungen,
        y=kurzarbeitsfaehig,
        name="Kurzarbeitsfähig",
        width=0.3,
        marker_color=SERIE,
        text=[str(k) for k in kurzarbeitsfaehig] if mit_beschriftung else None,
        textposition="outside",
    )
    fig.add_scatter(
        x=beschriftungen,
        y=quoten_prozent,
        name="Quote",
        mode="lines+markers",
        yaxis="y2",
        line={"color": TREND, "width": 2},
        marker={"color": markerfarben, "size": 9},
        text=[f"{q:.0%}" if q is not None else "n/a" for q in quoten] if mit_beschriftung else None,
        textposition="top center",
    )
    fig.add_shape(
        type="line",
        xref="paper",
        x0=0,
        x1=1,
        yref="y2",
        y0=schwelle * 100,
        y1=schwelle * 100,
        line={"color": TINTE_GEDAEMPFT, "width": 1, "dash": "dash"},
    )
    fig.update_layout(
        barmode="overlay",
        showlegend=True,
        yaxis2={
            "overlaying": "y",
            "side": "right",
            "ticksuffix": "%",
            "range": [0, 100],
            "showgrid": False,
        },
    )
    fig.update_yaxes(rangemode="tozero")
    _tickangle_setzen(fig)
    return fig


def kennzahlen(eintraege: Sequence[tuple[str, float, str]], *, hoehe: int = 150) -> go.Figure:
    """Die Kopfzeile des Dashboards: wenige grosse Zahlen nebeneinander.

    Args:
        eintraege: je Kachel Beschriftung, Wert und Einheit (etwa ``"EUR"``).
    """
    fig = figur("", hoehe=hoehe, grid={"rows": 1, "columns": len(eintraege), "pattern": "coupled"})
    fig.update_layout(margin={"l": 12, "r": 12, "t": 24, "b": 12})
    for spalte, (beschriftung, wert, einheit) in enumerate(eintraege):
        fig.add_trace(
            go.Indicator(
                mode="number",
                value=wert,
                title={"text": beschriftung, "font": {"size": 13, "color": TINTE_GEDAEMPFT}},
                number={
                    "valueformat": ",.0f",
                    "suffix": f" {einheit}" if einheit else "",
                    "font": {"size": 30, "color": TINTE},
                },
                domain={"row": 0, "column": spalte},
            )
        )
    return fig


def tabelle_als_grafik(titel: str, tabelle: pd.DataFrame, *, hoehe: int | None = None) -> go.Figure:
    """Eine der Tabellen aus :mod:`umsatzprognose.darstellung.tabellen` als
    plotly-Figur statt als Text.

    Fuer Ausgabewege ohne echte Tabellendarstellung: den Bildexport in
    ``scripts/wochenbericht.py`` (Slack kann eine eingebettete Tabelle nicht
    darstellen) und ``scripts/diagramme_exportieren.py``. Nicht fuer Notebook/Webapp
    gedacht - dort reicht pandas' eigenes Rendering (Zellenausgabe bzw. ``to_html()``).
    ``hoehe`` ohne Angabe richtet sich nach der Zeilenzahl, damit weder Leerraum
    uebrigbleibt noch Zeilen abgeschnitten werden.
    """
    zeilenhoehe = 26
    fig = figur(titel, hoehe=hoehe or 70 + zeilenhoehe * (len(tabelle) + 1))
    ausrichtung = ["left"] + ["right"] * (len(tabelle.columns) - 1)
    fig.add_trace(
        go.Table(
            header={
                "values": [f"<b>{spalte}</b>" for spalte in tabelle.columns],
                "fill_color": SERIE,
                "font": {"color": "#ffffff", "family": SCHRIFT, "size": 13},
                "align": ausrichtung,
                "height": 30,
            },
            cells={
                "values": [tabelle[spalte] for spalte in tabelle.columns],
                "fill_color": FLAECHE,
                "font": {"color": TINTE, "family": SCHRIFT, "size": 12},
                "align": ausrichtung,
                "height": zeilenhoehe,
            },
        )
    )
    fig.update_layout(margin={"l": 12, "r": 12, "t": 40, "b": 12})
    return fig
