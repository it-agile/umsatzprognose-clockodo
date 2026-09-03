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
    from collections.abc import Sequence

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
    KOSTEN,
    KOSTEN_HELL,
    PROGNOSE_DECKKRAFT,
    SCHULUNG,
    SERIE,
    SERIE_HELL,
    TINTE,
    TINTE_GEDAEMPFT,
    TINTE_ZWEITRANGIG,
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


def _historie_und_horizont_ergebnis(
    monate: Sequence[Monatsumsatz],
    kosten: Sequence[float],
    prognose: Prognose | None,
    horizont_kosten: Sequence[float],
    schulungsplan: Schulungsplan | None,
    verbrauch_laufender_monat: Monatsumsatz | None,
) -> tuple[list[str], list[float], list[float]]:
    """Ergebnis (Umsatz minus Kosten) je Monat, Historie gefolgt vom Prognosehorizont.

    Gemeinsame Grundlage fuer :func:`gewinn_verlust_monatlich` und
    :func:`gewinn_verlust_kumuliert`.

    Returns:
        Beschriftungen, Ergebnis je Monat und eine parallele Deckkraft-Liste (1.0 fuer
        die Historie, :data:`~umsatzprognose.darstellung.gestaltung.PROGNOSE_DECKKRAFT`
        fuer den Prognosehorizont) - dieselbe Konvention wie bei
        :func:`_prognosehorizont`: Sicherheit einer Zahl zeigt sich ueber die
        Deckkraft, nicht ueber eine eigene Farbe.
    """
    beschriftungen = [m.beschriftung for m in monate]
    ergebnis = [m.umsatz - k for m, k in zip(monate, kosten, strict=True)]
    deckkraft = [1.0] * len(monate)

    if prognose is not None and prognose.vorhanden:
        horizont = prognose.horizontmonate()
        gesamtumsatz = _horizont_gesamtumsatz(
            prognose,
            verbrauch_laufender_monat=verbrauch_laufender_monat,
            schulungsplan=schulungsplan,
        )
        beschriftungen += [_monatsbeschriftung(jahr, monat) for jahr, monat in horizont]
        ergebnis += [
            gesamtumsatz[schluessel] - k
            for schluessel, k in zip(horizont, horizont_kosten, strict=True)
        ]
        deckkraft += [PROGNOSE_DECKKRAFT] * len(horizont)

    return beschriftungen, ergebnis, deckkraft


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
    Umsatzverlauf. ``verbrauch_laufender_monat`` liefert das vor dem Stichtag bereits
    Realisierte des laufenden Monats, ``schulungsplan`` zusaetzlich additiven Umsatz aus
    bereits geplanten Schulungsterminen - siehe :func:`_horizont_gesamtumsatz`.
    """
    beschriftungen, ergebnis, deckkraft = _historie_und_horizont_ergebnis(
        monate, kosten, prognose, horizont_kosten, schulungsplan, verbrauch_laufender_monat
    )
    gesamt = sum(ergebnis)

    untertitel = f"Summe über {len(monate)} Monate: {euro(gesamt, nachkommastellen=0)}"
    if prognose is not None and prognose.vorhanden and prognose.horizontmonate():
        untertitel += " (gedämpfte Balken: Vorausschau)"
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
    achsen(fig)
    fig.update_layout(bargap=0.3, barcornerradius=4)
    fig.update_yaxes(tickformat=",.0f", ticksuffix=" €")
    fig.update_xaxes(tickangle=0)
    return fig


def gewinn_verlust_kumuliert(
    monate: Sequence[Monatsumsatz],
    kosten: Sequence[float],
    *,
    prognose: Prognose | None = None,
    horizont_kosten: Sequence[float] = (),
    schulungsplan: Schulungsplan | None = None,
    verbrauch_laufender_monat: Monatsumsatz | None = None,
    hoehe: int = 380,
) -> go.Figure:
    """Die ueber die Monate aufsummierte Gewinn/Verlust-Linie, mit Null-Referenzlinie.

    Zeigt, seit wann und wie deutlich ein Gesamtminus (oder -plus) ueber den
    betrachteten Zeitraum besteht - anders als :func:`gewinn_verlust_monatlich`, das
    nur den einzelnen Monat zeigt. Die Null-Referenzlinie ist hier bewusst gesetzt,
    obwohl :func:`~umsatzprognose.darstellung.gestaltung.achsen` sonst keine zeichnet:
    das Ueber-/Unterschreiten der Nulllinie ist hier die Kernaussage.

    Mit ``prognose`` (siehe :func:`gewinn_verlust_monatlich` fuer die uebrigen
    Parameter) setzt sich die Linie ueber den Prognosehorizont fort - gestrichelt und
    gedaempft ab dem letzten Ist-Monat, damit Ist und Vorausschau auf einen Blick
    unterscheidbar bleiben, aber ohne Bruch ineinander uebergehen.
    """
    beschriftungen, ergebnis, _deckkraft = _historie_und_horizont_ergebnis(
        monate, kosten, prognose, horizont_kosten, schulungsplan, verbrauch_laufender_monat
    )
    kumuliert: list[float] = []
    laufend = 0.0
    for betrag in ergebnis:
        laufend += betrag
        kumuliert.append(laufend)

    anzahl_ist = len(monate)
    farbe = ERGEBNIS_POSITIV if kumuliert[-1] >= 0 else ERGEBNIS_NEGATIV

    fig = figur("Kumulierter Gewinn/Verlust", hoehe=hoehe)
    fig.add_scatter(
        x=beschriftungen[:anzahl_ist],
        y=kumuliert[:anzahl_ist],
        mode="lines+markers",
        line={"color": farbe, "width": 2},
        marker={"size": 6},
        customdata=[[euro(betrag)] for betrag in kumuliert[:anzahl_ist]],
        hovertemplate="<b>%{x}</b><br>%{customdata[0]}<extra></extra>",
        showlegend=False,
        name="Ist",
    )
    # Beginnt am letzten Ist-Punkt, damit die Linie ohne Bruch weiterlaeuft.
    if len(beschriftungen) > anzahl_ist:
        start = max(anzahl_ist - 1, 0)
        fig.add_scatter(
            x=beschriftungen[start:],
            y=kumuliert[start:],
            mode="lines+markers",
            line={"color": farbe, "width": 2, "dash": "dot"},
            marker={"size": 6, "opacity": PROGNOSE_DECKKRAFT},
            opacity=PROGNOSE_DECKKRAFT,
            customdata=[[euro(betrag)] for betrag in kumuliert[start:]],
            hovertemplate="<b>%{x}</b><br>%{customdata[0]} (Vorausschau)<extra></extra>",
            showlegend=False,
            name="Vorausschau",
        )
    fig.add_hline(y=0, line={"color": ACHSE, "width": 1})
    achsen(fig)
    fig.update_yaxes(tickformat=",.0f", ticksuffix=" €")
    fig.update_xaxes(tickangle=0)
    return fig


def restvolumen_je_projekt(
    projekte: Sequence[Projekt], *, top: int = 15, hoehe: int | None = None
) -> go.Figure:
    """Die groessten offenen Volumina als liegende Balken, beschriftet mit dem Betrag.

    Liegend, weil die Beschriftung aus Kunde und Projekt besteht und senkrecht
    unlesbar waere. Die Zahl steht am Balkenende - bei hoechstens 15 Zeilen ist das
    ruhiger als eine zusaetzliche Achse.
    """
    gezeigt = list(projekte[:top])
    hoehe = hoehe or max(260, 70 + 30 * len(gezeigt))
    gesamt = sum(p.restvolumen_prognosewirksam or 0.0 for p in projekte)
    rest = len(projekte) - len(gezeigt)

    untertitel = f"{len(projekte)} Projekte mit zusammen {euro(gesamt, nachkommastellen=0)}"
    if rest > 0:
        untertitel += f", gezeigt sind die {len(gezeigt)} größten und {rest} weitere folgen"

    fig = figur("Offenes Auftragsvolumen je Projekt", untertitel=untertitel, hoehe=hoehe)
    # Die Kategorie ist die Position, nicht die Beschriftung: zwei Projekte koennen
    # denselben Namen tragen oder auf denselben gekuerzten Namen fallen, und plotly
    # wuerde sie dann zu einem Balken addieren - eine still falsche Zahl.
    fig.add_bar(
        x=[p.restvolumen_prognosewirksam or 0.0 for p in reversed(gezeigt)],
        y=list(range(len(gezeigt))),
        orientation="h",
        marker={"color": SERIE},
        text=[tausend_euro(p.restvolumen_prognosewirksam or 0.0) for p in reversed(gezeigt)],
        textposition="outside",
        textfont={"color": TINTE_ZWEITRANGIG, "size": 12},
        cliponaxis=False,
        customdata=[
            [p.bezeichnung, euro(p.auftragsvolumen or 0.0), euro(p.verbrauchtes_volumen)]
            for p in reversed(gezeigt)
        ],
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>Offen: %{x:,.0f} €<br>"
            "Beauftragt: %{customdata[1]}<br>Verbraucht: %{customdata[2]}<extra></extra>"
        ),
        showlegend=False,
    )
    achsen(fig, gitter_x=True, gitter_y=False)
    fig.update_layout(bargap=0.4, barcornerradius=4)
    groesster = max((p.restvolumen_prognosewirksam or 0.0 for p in gezeigt), default=0.0)
    # Luft rechts, sonst schneidet der Rand die Beschriftung des laengsten Balkens ab.
    fig.update_xaxes(visible=False, range=[0, groesster * 1.18])
    fig.update_yaxes(
        tickmode="array",
        tickvals=list(range(len(gezeigt))),
        ticktext=[_achsenbeschriftung(p) for p in reversed(gezeigt)],
        tickfont={"color": TINTE, "size": 12},
        automargin=True,
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
    hoehe = hoehe or max(260, 70 + 30 * len(gezeigt))
    gesamt = sum(stunden for _, stunden in kapazitaeten)
    rest = len(kapazitaeten) - len(gezeigt)

    untertitel = f"{len(kapazitaeten)} Personen mit zusammen {tage(gesamt)}"
    if rest > 0:
        untertitel += f", gezeigt sind die {len(gezeigt)} größten und {rest} weitere folgen"

    fig = figur("Verfügbare Kapazität je Person", untertitel=untertitel, hoehe=hoehe)
    fig.add_bar(
        x=[stunden / STUNDEN_JE_TAG for _, stunden in reversed(gezeigt)],
        y=list(range(len(gezeigt))),
        orientation="h",
        marker={"color": SERIE},
        text=[tage(stunden) for _, stunden in reversed(gezeigt)],
        textposition="outside",
        textfont={"color": TINTE_ZWEITRANGIG, "size": 12},
        cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>%{text}<extra></extra>",
        showlegend=False,
    )
    achsen(fig, gitter_x=True, gitter_y=False)
    fig.update_layout(bargap=0.4, barcornerradius=4)
    groesster = max((stunden for _, stunden in gezeigt), default=0.0) / STUNDEN_JE_TAG
    fig.update_xaxes(visible=False, range=[0, groesster * 1.18])
    fig.update_yaxes(
        tickmode="array",
        tickvals=list(range(len(gezeigt))),
        ticktext=[_gekuerzt(str(m), MAXIMALE_PROJEKTLAENGE) for m, _ in reversed(gezeigt)],
        tickfont={"color": TINTE, "size": 12},
        automargin=True,
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
    hoehe = hoehe or max(260, 70 + 30 * len(gezeigt))
    rest = len(mit_quote) - len(gezeigt)

    untertitel = f"{len(mit_quote)} Personen mit hinterlegter Kapazität"
    if rest > 0:
        untertitel += f", gezeigt sind die {len(gezeigt)} größten und {rest} weitere folgen"

    fig = figur("Auslastung je Person", untertitel=untertitel, hoehe=hoehe)
    fig.add_bar(
        x=[quote for _, quote in reversed(gezeigt)],
        y=list(range(len(gezeigt))),
        orientation="h",
        marker={"color": SERIE},
        text=[prozent(quote) for _, quote in reversed(gezeigt)],
        textposition="outside",
        textfont={"color": TINTE_ZWEITRANGIG, "size": 12},
        cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>%{text}<extra></extra>",
        showlegend=False,
    )
    achsen(fig, gitter_x=True, gitter_y=False)
    fig.update_layout(bargap=0.4, barcornerradius=4)
    groesste = max((quote for _, quote in gezeigt), default=0.0)
    fig.update_xaxes(visible=False, range=[0, groesste * 1.18])
    fig.update_yaxes(
        tickmode="array",
        tickvals=list(range(len(gezeigt))),
        ticktext=[
            _gekuerzt(str(a.mitarbeiter), MAXIMALE_PROJEKTLAENGE) for a, _ in reversed(gezeigt)
        ],
        tickfont={"color": TINTE, "size": 12},
        automargin=True,
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
    hoehe = hoehe or max(260, 70 + 30 * len(gezeigt))
    gesamt = sum(stunden for _, stunden in kapazitaeten)
    rest = len(kapazitaeten) - len(gezeigt)

    untertitel = f"{len(kapazitaeten)} Projekte mit zusammen {tage(gesamt)}"
    if rest > 0:
        untertitel += f", gezeigt sind die {len(gezeigt)} größten und {rest} weitere folgen"

    fig = figur("Simulierte Kapazität je Projekt", untertitel=untertitel, hoehe=hoehe)
    fig.add_bar(
        x=[stunden / STUNDEN_JE_TAG for _, stunden in reversed(gezeigt)],
        y=list(range(len(gezeigt))),
        orientation="h",
        marker={"color": SERIE},
        text=[tage(stunden) for _, stunden in reversed(gezeigt)],
        textposition="outside",
        textfont={"color": TINTE_ZWEITRANGIG, "size": 12},
        cliponaxis=False,
        customdata=[[p.bezeichnung] for p, _ in reversed(gezeigt)],
        hovertemplate="<b>%{customdata[0]}</b><br>%{text}<extra></extra>",
        showlegend=False,
    )
    achsen(fig, gitter_x=True, gitter_y=False)
    fig.update_layout(bargap=0.4, barcornerradius=4)
    groesster = max((stunden for _, stunden in gezeigt), default=0.0) / STUNDEN_JE_TAG
    fig.update_xaxes(visible=False, range=[0, groesster * 1.18])
    fig.update_yaxes(
        tickmode="array",
        tickvals=list(range(len(gezeigt))),
        ticktext=[_achsenbeschriftung(p) for p, _ in reversed(gezeigt)],
        tickfont={"color": TINTE, "size": 12},
        automargin=True,
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
