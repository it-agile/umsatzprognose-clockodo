"""Die Diagramme des Dashboards.

Jede Funktion nimmt Fachobjekte und gibt eine plotly-Figur zurueck. Was dargestellt wird,
entscheidet die Domaene; hier steht nur, wie.

Gestaltung:
 * verschiedene Sättigungen einer Farbe für [abgerechnet, nicht abgerechnet, prognostiziert].
 * verschiedene Farben für unetrschiedliche Quellen
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from umsatzprognose.domaene import (
        Auslastungsmonat,
        Auslastungssumme,
        Kostenplan,
        Mitarbeiter,
        Monatsumsatz,
        Prognose,
        Projekt,
        Schulungsplan,
        Umsatzhistorie,
    )

from dataclasses import dataclass

import plotly.graph_objects as go

from umsatzprognose.darstellung.gestaltung import (
    ACHSE,
    ERGEBNIS_NEGATIV,
    ERGEBNIS_POSITIV,
    JAHRESFARBEN,
    KOSTEN,
    KOSTEN_HELL,
    PROGNOSE_DECKKRAFT,
    SCHULUNG,
    SERIE,
    SERIE_HELL,
    TINTE,
    TINTE_GEDAEMPFT,
    TINTE_ZWEITRANGIG,
    VORLAEUFIG_DECKKRAFT,
    achsen,
    figur,
)
from umsatzprognose.domaene.umsatzhistorie import MONATSNAMEN
from umsatzprognose.domaene.zahlen import STUNDEN_JE_TAG, euro, prozent, tage, tausend_euro

# Getrennte Laengen fuer Kunde und Projekt: der Kundenname ist oft der laengere Teil,
# unterscheidet aber die Zeilen eines Kunden nicht. Wird alles gemeinsam am Ende
# gekuerzt, sehen zwei Projekte desselben Kunden identisch aus.
MAXIMALE_KUNDENLAENGE = 22
MAXIMALE_PROJEKTLAENGE = 38


def umsatzverlauf(
    historie: Umsatzhistorie,
    prognose: Prognose | None = None,
    schulungsplan: Schulungsplan | None = None,
    kostenplan: Kostenplan | None = None,
    *,
    hoehe: int = 420,
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
    Umsatz aus bereits geplanten oeffentlichen Schulungsterminen hinzu (Spec Baustein
    Schulungsanmeldungen, Abschnitt 6) - unabhaengig von der Bestand-Bandbreite und ohne
    eigene Unsicherheit.

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
    """
    monate = historie.monate
    laufender = historie.laufender
    durchschnitt = historie.durchschnitt()

    untertitel = (
        f"Durchschnitt der {len(historie.abgeschlossene())} abgeschlossenen "
        f"Monate: {euro(durchschnitt, nachkommastellen=0)}"
    )
    if prognose is not None and prognose.vorhanden:
        anteil = prognose.kapazitaet_limitierend_anteil()
        if anteil > 0:
            untertitel += f". Kapazität war in {anteil:.0%} der Läufe der limitierende Faktor"

    fig = figur("Umsatz je Monat", untertitel=untertitel, hoehe=hoehe)
    fig.add_bar(
        x=[m.beschriftung for m in monate],
        y=[m.umsatz for m in monate],
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

    horizont_gesamtumsatz: dict[tuple[int, int], float] = {}
    if prognose is not None:
        if prognose.vorhanden:
            horizont_gesamtumsatz = _prognosehorizont(
                fig,
                prognose,
                verbrauch_laufender_monat=laufender,
                schulungsplan=schulungsplan,
            )
        else:
            _keine_prognose_hinweis(fig, prognose)

    horizont_gebucht = prognose.gebucht() if prognose is not None and prognose.vorhanden else []
    horizont_schulung = (
        schulungsplan.umsatz_je_monat(prognose.horizontmonate())
        if prognose is not None and prognose.vorhanden and schulungsplan is not None
        else []
    )
    kosten_balken = KostenBalkenErgebnis()
    if kostenplan is not None:
        kosten_balken = _kosten_und_ergebnis(
            fig, monate, prognose, kostenplan, horizont_gesamtumsatz
        )
    _legendeintrag(fig, "Abgerechnet", SERIE)
    if laufender or any(horizont_gebucht):
        _legendeintrag(fig, "Nicht abgerechnet", SERIE_HELL)
    if prognose is not None and prognose.vorhanden:
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

    achsen(fig)
    fig.update_layout(bargap=0.3, bargroupgap=0.08, barcornerradius=4, barmode="group")
    fig.update_yaxes(tickformat=",.0f", ticksuffix=" €", rangemode="tozero")
    fig.update_xaxes(tickangle=0)
    return fig


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
    monate: Sequence[Monatsumsatz], prognose: Prognose | None
) -> list[tuple[int, int]]:
    """Die Monate der Historie, ergaenzt um den Prognosehorizont (ohne Dopplung)."""
    schluessel = [m.schluessel for m in monate]
    if prognose is not None and prognose.vorhanden:
        schluessel += [m for m in prognose.horizontmonate() if m not in schluessel]
    return schluessel


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
    prognose: Prognose | None,
    kostenplan: Kostenplan,
    horizont_gesamtumsatz: dict[tuple[int, int], float],
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
    ergebnis = [gesamtumsatz.get(s, 0.0) - k for s, k in zip(schluessel, kosten, strict=True)]
    beschriftungen = [_monatsbeschriftung(jahr, monat) for jahr, monat in schluessel]
    fig.add_bar(
        x=beschriftungen,
        y=kosten,
        offsetgroup="kosten",
        marker={"color": [KOSTEN if e else KOSTEN_HELL for e in hat_erfassung]},
        customdata=[[euro(betrag)] for betrag in kosten],
        hovertemplate="<b>%{x}</b><br>Kosten: %{customdata[0]}<extra></extra>",
        name="Kosten",
        showlegend=False,
    )
    fig.add_bar(
        x=beschriftungen,
        y=ergebnis,
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


def _horizont_gesamtumsatz(
    prognose: Prognose,
    *,
    verbrauch_laufender_monat: Monatsumsatz | None = None,
    schulungsplan: Schulungsplan | None = None,
) -> dict[tuple[int, int], float]:
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
    schulung = (
        list(schulungsplan.umsatz_je_monat(horizont))
        if schulungsplan is not None
        else [0.0] * len(horizont)
    )
    basis0 = verbrauch_laufender_monat.umsatz if verbrauch_laufender_monat else 0.0
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
) -> dict[tuple[int, int], float]:
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

    basis0 = verbrauch_laufender_monat.umsatz if verbrauch_laufender_monat else 0.0
    schulung = (
        list(schulungsplan.umsatz_je_monat(horizont))
        if schulungsplan is not None
        else [0.0] * len(horizont)
    )
    schulung_basis = [basis0, *([0.0] * (len(horizont) - 1))]
    sockel = [basis0 + schulung[0]] + [
        g + s for g, s in zip(gebucht[1:], schulung[1:], strict=True)
    ]
    prognostiziert = [median[0]] + [m - g for m, g in zip(median[1:], gebucht[1:], strict=True)]

    if any(schulung):
        fig.add_bar(
            x=beschriftungen,
            y=schulung,
            base=schulung_basis,
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
            y=gebucht[1:],
            base=schulung[1:],
            offsetgroup="umsatz",
            marker={"color": SERIE_HELL},
            customdata=[[euro(betrag)] for betrag in gebucht[1:]],
            hovertemplate="<b>%{x}</b><br>Bereits gebucht: %{customdata[0]}<extra></extra>",
            showlegend=False,
            name="Bereits gebucht",
        )

    fig.add_bar(
        x=beschriftungen,
        y=prognostiziert,
        base=sockel,
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
            "arrayminus": [m - p for m, p in zip(median, p95, strict=True)],
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
    kosten: Sequence[float],
    prognose: Prognose | None,
    horizont_kosten: Sequence[float],
    schulungsplan: Schulungsplan | None,
    verbrauch_laufender_monat: Monatsumsatz | None,
) -> tuple[list[str], list[float], list[float], list[float]]:
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

    if prognose is not None and prognose.vorhanden:
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
    prognose: Prognose | None,
    umsatz: Sequence[float],
    ergebnis: Sequence[float],
    deckkraft: Sequence[float],
) -> dict[int, list[tuple[int, float, float, float]]]:
    """Ordnet die parallelen Werte-Listen nach Kalenderjahr, je Jahr chronologisch.

    Gemeinsame Grundlage fuer :func:`gewinn_verlust_je_jahr` und
    :func:`umsatzrendite_kumuliert` - jeder Eintrag ist ``(monat, umsatz, ergebnis,
    deckkraft)``.
    """
    schluessel = [m.schluessel for m in monate]
    if prognose is not None and prognose.vorhanden:
        schluessel += list(prognose.horizontmonate())

    jahre: dict[int, list[tuple[int, float, float, float]]] = {}
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


def _jahreslinien(
    fig: go.Figure,
    jahre: dict[int, list[tuple[int, float, float, float]]],
    *,
    werte: Callable[[list[tuple[int, float, float, float]]], list[float]],
    formatieren: Callable[[float], str],
) -> None:
    """Zeichnet fuer jedes Jahr eine Linie in bis zu drei Abschnitten (siehe
    :data:`_LINIENABSCHNITTE`): Daten (durchgezogen, volle Deckkraft), vorlaeufige
    Daten des laufenden Monats (durchgezogen, mittlere Deckkraft) und simulierte
    Prognose (gestrichelt, gedaempft).

    ``werte`` errechnet aus den Punkten eines Jahres (``monat, umsatz, ergebnis,
    deckkraft``) die y-Werte, ``formatieren`` die Hover-Beschriftung je Wert. Jeder
    Abschnitt beginnt am letzten Punkt des vorigen, damit die Linie ohne Bruch
    weiterlaeuft; fehlt ein Abschnitt fuer ein Jahr (z. B. kein Vorlaeufig-Punkt, weil
    kein Prognosehorizont in dieses Jahr faellt), entfaellt er einfach.
    """
    for index, jahr in enumerate(sorted(jahre)):
        punkte = jahre[jahr]
        farbe = JAHRESFARBEN[index % len(JAHRESFARBEN)]
        beschriftungen = [MONATSNAMEN[monat - 1] for monat, *_rest in punkte]
        y = werte(punkte)
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
                y=y[start:neues_ende],
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


def gewinn_verlust_monatlich(
    monate: Sequence[Monatsumsatz],
    kosten: Sequence[float],
    *,
    prognose: Prognose | None = None,
    horizont_kosten: Sequence[float] = (),
    schulungsplan: Schulungsplan | None = None,
    verbrauch_laufender_monat: Monatsumsatz | None = None,
    hoehe: int = 380,
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
    """
    beschriftungen, _umsatz, ergebnis, deckkraft = _historie_und_horizont_werte(
        monate, kosten, prognose, horizont_kosten, schulungsplan, verbrauch_laufender_monat
    )
    gesamt = sum(ergebnis)
    horizont = prognose.horizontmonate() if prognose is not None and prognose.vorhanden else ()

    untertitel = f"Summe über {len(monate)} Monate: {euro(gesamt, nachkommastellen=0)}"
    fig = figur("Gewinn/Verlust je Monat", untertitel=untertitel, hoehe=hoehe)
    fig.add_bar(
        x=beschriftungen,
        y=ergebnis,
        marker={
            "color": [ERGEBNIS_POSITIV if e >= 0 else ERGEBNIS_NEGATIV for e in ergebnis],
            "opacity": deckkraft,
        },
        customdata=[[euro(betrag)] for betrag in ergebnis],
        hovertemplate="<b>%{x}</b><br>%{customdata[0]}<extra></extra>",
        showlegend=False,
    )
    if prognose is not None and not prognose.vorhanden:
        _keine_prognose_hinweis(fig, prognose)
    if horizont:
        _datensicherheit_legende(fig, vorlaeufig=True, prognose=len(horizont) > 1)
        _horizontale_legende(fig)
    achsen(fig)
    fig.update_layout(bargap=0.3, barcornerradius=4)
    fig.update_yaxes(tickformat=",.0f", ticksuffix=" €")
    fig.update_xaxes(tickangle=0)
    return fig


def gewinn_verlust_je_jahr(
    monate: Sequence[Monatsumsatz],
    kosten: Sequence[float],
    *,
    prognose: Prognose | None = None,
    horizont_kosten: Sequence[float] = (),
    schulungsplan: Schulungsplan | None = None,
    verbrauch_laufender_monat: Monatsumsatz | None = None,
    hoehe: int = 380,
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
    gestrichelt, ohne eigenen Ist-Abschnitt.
    """
    _beschriftungen, umsatz, ergebnis, deckkraft = _historie_und_horizont_werte(
        monate, kosten, prognose, horizont_kosten, schulungsplan, verbrauch_laufender_monat
    )
    jahre = _je_jahr(monate, prognose, umsatz, ergebnis, deckkraft)

    fig = figur("Gewinn/Verlust je Monat und Jahr", hoehe=hoehe)
    _jahreslinien(
        fig,
        jahre,
        werte=lambda punkte: [ergebnis for _monat, _umsatz, ergebnis, _deck in punkte],
        formatieren=euro,
    )
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
    fig.update_xaxes(categoryorder="array", categoryarray=list(MONATSNAMEN), tickangle=0)
    return fig


def umsatzrendite_kumuliert(
    monate: Sequence[Monatsumsatz],
    kosten: Sequence[float],
    *,
    prognose: Prognose | None = None,
    horizont_kosten: Sequence[float] = (),
    schulungsplan: Schulungsplan | None = None,
    verbrauch_laufender_monat: Monatsumsatz | None = None,
    hoehe: int = 380,
) -> go.Figure:
    """Fuer jedes Kalenderjahr die kumulierte Umsatzrendite (Gewinn/Umsatz) je Monat.

    "Kumuliert" heisst hier: kumulierter Gewinn geteilt durch kumulierten Umsatz bis
    zu diesem Monat (eine Year-to-Date-Marge) - nicht die Summe monatlicher
    Prozentwerte, die von unterschiedlich grossen Monatsumsaetzen verzerrt waere.
    Januar zeigt deshalb die Rendite des Monats selbst, Februar die der ersten beiden
    Monate zusammen, und so weiter. Aufbau und Vorausschau-Konvention wie
    :func:`gewinn_verlust_je_jahr`, dort auch die uebrigen Parameter erklaert. Ein
    Monat ganz ohne Umsatz (weder Ist noch Vorausschau) zeigt 0 % statt eines Fehlers.
    """
    _beschriftungen, umsatz, ergebnis, deckkraft = _historie_und_horizont_werte(
        monate, kosten, prognose, horizont_kosten, schulungsplan, verbrauch_laufender_monat
    )
    jahre = _je_jahr(monate, prognose, umsatz, ergebnis, deckkraft)

    def rendite_je_monat(punkte: list[tuple[int, float, float, float]]) -> list[float]:
        kumulierter_umsatz = kumuliertes_ergebnis = 0.0
        werte = []
        for _monat, monatsumsatz, monatsergebnis, _deck in punkte:
            kumulierter_umsatz += monatsumsatz
            kumuliertes_ergebnis += monatsergebnis
            anteil = kumuliertes_ergebnis / kumulierter_umsatz if kumulierter_umsatz else 0.0
            werte.append(anteil * 100)
        return werte

    fig = figur("Kumulierte Umsatzrendite je Jahr", hoehe=hoehe)
    _jahreslinien(
        fig,
        jahre,
        werte=rendite_je_monat,
        formatieren=lambda prozentpunkte: prozent(prozentpunkte / 100, nachkommastellen=1),
    )
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
    fig.update_xaxes(categoryorder="array", categoryarray=list(MONATSNAMEN), tickangle=0)
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
    gesamt = sum(p.restvolumen_prognosewirksam or 0.0 for p in projekte)
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
        werte=[p.restvolumen_prognosewirksam or 0.0 for p in umgekehrt],
        text=[tausend_euro(p.restvolumen_prognosewirksam or 0.0) for p in umgekehrt],
        ticktext=[_achsenbeschriftung(p) for p in umgekehrt],
        customdata=[
            [p.bezeichnung, euro(p.auftragsvolumen or 0.0), euro(p.verbrauchtes_volumen)]
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
    """Verfuegbare Kapazitaet je Person fuer einen Monat, als liegende Balken in Tagen.

    ``kapazitaeten`` kommt bereits absteigend sortiert (siehe
    :meth:`~umsatzprognose.domaene.bestand.Bestand.mitarbeiter_kapazitaet`), analog zu
    :func:`restvolumen_je_projekt`. Angezeigt wird in Personentagen à
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
    zeilen, zeile = [], ""
    for wort in text.split():
        if len(zeile) + len(wort) + 1 > breite:
            zeilen.append(zeile)
            zeile = wort
        else:
            zeile = f"{zeile} {wort}".strip()
    zeilen.append(zeile)
    return "<br>".join(zeilen)


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
