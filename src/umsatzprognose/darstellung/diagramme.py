"""Die Diagramme des Dashboards.

Jede Funktion nimmt Fachobjekte und gibt eine plotly-Figur zurueck - keine Rechnung,
keine Abrufe. Was dargestellt wird, entscheidet die Domaene; hier steht nur, wie.

Gestaltungsentscheidungen, die sich wiederholen: eine Groesse je Diagramm und deshalb
keine Legende (der Titel benennt sie), Beschriftungen direkt am Balken statt einer
zusaetzlichen Achse, wo es die Menge zulaesst, und Zahlen im Hinweisfenster statt an
jedem Balken. Der laufende Monat ist heller gezeichnet und beschriftet - eine hellere
Stufe derselben Farbe, weil es dieselbe Groesse ist und keine zweite Kategorie.
"""

from __future__ import annotations

from collections.abc import Sequence

import plotly.graph_objects as go

from umsatzprognose.darstellung.gestaltung import (
    ACHSE,
    SERIE,
    SERIE_HELL,
    TINTE,
    TINTE_GEDAEMPFT,
    TINTE_ZWEITRANGIG,
    achsen,
    figur,
)
from umsatzprognose.domaene.prognose import Prognose
from umsatzprognose.domaene.projekt import Projekt
from umsatzprognose.domaene.umsatzhistorie import Umsatzhistorie
from umsatzprognose.domaene.zahlen import euro, tausend_euro

# Getrennte Laengen fuer Kunde und Projekt: der Kundenname ist oft der laengere Teil,
# unterscheidet aber die Zeilen eines Kunden nicht. Wird alles gemeinsam am Ende
# gekuerzt, sehen zwei Projekte desselben Kunden identisch aus.
MAXIMALE_KUNDENLAENGE = 22
MAXIMALE_PROJEKTLAENGE = 38


def umsatzverlauf(historie: Umsatzhistorie, *, hoehe: int = 420) -> go.Figure:
    """Monatsumsatz als Balken, mit Durchschnittslinie und abgesetztem laufendem Monat.

    Der laufende Monat steht bewusst im Bild, obwohl er unvollstaendig ist: er zeigt,
    wie weit der Monat gediehen ist. Damit er nicht als Einbruch missverstanden wird,
    ist er hell gezeichnet und ausdruecklich beschriftet - und er geht in die
    Durchschnittslinie nicht ein.
    """
    monate = historie.monate
    laufender = historie.laufender
    durchschnitt = historie.durchschnitt()

    fig = figur(
        "Umsatz je Monat",
        untertitel=f"Durchschnitt der {len(historie.abgeschlossene())} abgeschlossenen "
        f"Monate: {euro(durchschnitt, nachkommastellen=0)}",
        hoehe=hoehe,
    )
    fig.add_bar(
        x=[m.beschriftung for m in monate],
        y=[m.umsatz for m in monate],
        marker={
            "color": [
                SERIE_HELL if laufender and m.schluessel == laufender.schluessel else SERIE
                for m in monate
            ]
        },
        customdata=[[euro(m.umsatz), f"{m.stunden:,.0f}".replace(",", ".")] for m in monate],
        hovertemplate="<b>%{x}</b><br>%{customdata[0]}<br>%{customdata[1]} Stunden<extra></extra>",
        showlegend=False,
    )
    fig.add_hline(
        y=durchschnitt,
        line={"color": TINTE_GEDAEMPFT, "width": 1, "dash": "dash"},
        annotation={
            "text": "Durchschnitt",
            "font": {"color": TINTE_GEDAEMPFT, "size": 12},
            "yanchor": "bottom",
        },
        annotation_position="top right",
    )
    if laufender:
        fig.add_annotation(
            x=laufender.beschriftung,
            y=laufender.umsatz,
            text="läuft noch",
            showarrow=False,
            yshift=14,
            font={"color": TINTE_ZWEITRANGIG, "size": 12},
        )

    achsen(fig)
    fig.update_layout(bargap=0.45, barcornerradius=4)
    fig.update_yaxes(tickformat=",.0f", ticksuffix=" €", rangemode="tozero")
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


def prognose(prognose: Prognose, *, hoehe: int = 260) -> go.Figure:
    """Die Flaeche, auf der spaeter die Bandbreite steht.

    Solange es keine Prognose gibt, sagt das Diagramm genau das - mit Begruendung.
    Eine leere Flaeche waere ein Fehler, eine erfundene Kurve ein groesserer.
    """
    fig = figur("Prognose der nächsten Monate", hoehe=hoehe)
    fig.add_annotation(
        text=_umgebrochen(prognose.begruendung),
        showarrow=False,
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        font={"color": TINTE_ZWEITRANGIG, "size": 13},
        align="center",
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    fig.update_layout(
        shapes=[
            {
                "type": "rect",
                "xref": "paper",
                "yref": "paper",
                "x0": 0,
                "x1": 1,
                "y0": 0,
                "y1": 1,
                "line": {"color": ACHSE, "width": 1, "dash": "dot"},
            }
        ]
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

    Kein Diagramm, sondern die Zahl selbst - fuer eine einzelne Groesse ohne Verlauf
    ist ein Balken nur Verpackung. Die Zahlen stehen in derselben Figur, damit sie in
    jeder Umgebung nebeneinander bleiben; nebeneinandergestellte Ausgaben tun das im
    Notebook nicht zuverlaessig.
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
