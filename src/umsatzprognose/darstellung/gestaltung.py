"""Ein gemeinsames Erscheinungsbild fuer alle Diagramme.

**Deutsche Zahlen ohne locale**: ``separators=",."`` in jedem Layout sagt plotly, dass
Komma das Dezimal- und Punkt das Tausendertrennzeichen ist. Damit stimmen auch die
Zahlen in den Hinweisfenstern, die plotly selbst formatiert.
"""

from __future__ import annotations

from typing import Any

import plotly.graph_objects as go

SERIE = "#2a78d6"
SERIE_HELL = "#86b6ef"
# Eigene Farbfamilie fuer den Baustein Schulungsanmeldungen - additiv und von einer
# anderen Quelle als der Bestand-Umsatz, deshalb bewusst nicht nur eine weitere
# Saettigung von SERIE (siehe Moduldocstring).
SCHULUNG = "#d68a2c"
# Eigene Farbfamilie fuer die Kostenprognose - aus derselben Ueberlegung: eine andere
# Quelle als der Umsatz, keine weitere Saettigung von SERIE.
KOSTEN = "#b3423f"
# Farben fuer den Ergebnis-Balken (Umsatz minus Kosten): Vorzeichen entscheidet die
# Farbe, nicht die Quelle - deshalb ein eigenes Grün/Rot-Paar statt einer Saettigung
# von SERIE oder KOSTEN. ERGEBNIS_NEGATIV ist bewusst ein anderer Farbton als KOSTEN,
# damit beide Balken nebeneinander unterscheidbar bleiben.
ERGEBNIS_POSITIV = "#3f7d54"
ERGEBNIS_NEGATIV = "#8c2f2f"
FLAECHE = "#fcfcfb"
TINTE = "#0b0b0b"
TINTE_ZWEITRANGIG = "#52514e"
TINTE_GEDAEMPFT = "#898781"
GITTER = "#e1e0d9"
ACHSE = "#c3c2b7"

# Fuer den prognostizierten (noch nicht realen) Teil eines Balkens: dieselbe Farbfamilie,
# aber gedaempft - Sicherheit einer Zahl druecken wir ueber die Deckkraft aus, nicht ueber
# eine zweite Farbe (siehe Moduldocstring).
PROGNOSE_DECKKRAFT = 0.4

SCHRIFT = 'system-ui, -apple-system, "Segoe UI", sans-serif'


def figur(titel: str, *, untertitel: str = "", hoehe: int = 420, **layout: Any) -> go.Figure:
    """Eine leere Figur im gemeinsamen Erscheinungsbild."""
    fig = go.Figure()
    fig.update_layout(
        title={
            "text": f"<b>{titel}</b>" + (f"<br><sup>{untertitel}</sup>" if untertitel else ""),
            "font": {"size": 17, "color": TINTE},
            "x": 0,
            "xanchor": "left",
        },
        height=hoehe,
        margin={"l": 12, "r": 24, "t": 70 if untertitel else 56, "b": 12},
        paper_bgcolor=FLAECHE,
        plot_bgcolor=FLAECHE,
        font={"family": SCHRIFT, "size": 13, "color": TINTE_ZWEITRANGIG},
        separators=",.",
        showlegend=False,
        hoverlabel={"font": {"family": SCHRIFT, "size": 13}},
        **layout,
    )
    return fig


def achsen(fig: go.Figure, *, gitter_x: bool = False, gitter_y: bool = True) -> go.Figure:
    """Zurueckhaltende Achsen: duenne Gitterlinien, keine Rahmen, keine Nulllinie."""
    gemeinsam = {
        "showline": False,
        "zeroline": False,
        "ticks": "",
        "tickfont": {"color": TINTE_GEDAEMPFT, "size": 12},
        "gridcolor": GITTER,
        "gridwidth": 1,
    }
    fig.update_xaxes(showgrid=gitter_x, **gemeinsam)
    fig.update_yaxes(showgrid=gitter_y, **gemeinsam)
    return fig
