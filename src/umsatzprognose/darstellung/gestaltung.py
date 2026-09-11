"""Ein gemeinsames Erscheinungsbild fuer alle Diagramme.

**Deutsche Zahlen ohne locale**: ``separators=",."`` in jedem Layout sagt plotly, dass
Komma das Dezimal- und Punkt das Tausendertrennzeichen ist. Damit stimmen auch die
Zahlen in den Hinweisfenstern, die plotly selbst formatiert.
"""

from __future__ import annotations

from typing import NotRequired, TypedDict, Unpack

import plotly.graph_objects as go

SERIE = "#2a78d6"
SERIE_HELL = "#86b6ef"
# Eigene Farbfamilie fuer den Baustein Schulungsanmeldungen - additiv und von einer
# anderen Quelle als der Bestand-Umsatz, deshalb bewusst nicht nur eine weitere
# Saettigung von SERIE (siehe Moduldocstring).
SCHULUNG = "#d68a2c"
# Eigene Farbfamilie fuer die Kostenprognose - aus derselben Ueberlegung: eine andere
# Quelle als der Umsatz, keine weitere Saettigung von SERIE. Wie bei SERIE/SERIE_HELL
# zeigt die Saettigung die Sicherheit: KOSTEN (satt) fuer Monate mit einer tatsaechlich
# erfassten Kostenerfassung, KOSTEN_HELL fuer Monate, die noch auf der geschaetzten
# Kostenpauschale beruhen (siehe Kostenposten.kosten).
KOSTEN = "#b3423f"
KOSTEN_HELL = "#d9a09f"
# Farben fuer den Ergebnis-Balken (Umsatz minus Kosten): Vorzeichen entscheidet die
# Farbe, nicht die Quelle - deshalb ein eigenes Grün/Rot-Paar statt einer Saettigung
# von SERIE oder KOSTEN. ERGEBNIS_NEGATIV ist bewusst ein anderer Farbton als KOSTEN,
# damit beide Balken nebeneinander unterscheidbar bleiben.
ERGEBNIS_POSITIV = "#3f7d54"
ERGEBNIS_NEGATIV = "#8c2f2f"
# Trendlinie (lineare Ausgleichsgerade): dunkelrot wie die Trendlinie der internen
# ZDF-Praesentation (dort exponentiell geglaettet, hier linear - Farbe unveraendert
# uebernommen). Ein eigener Farbton statt ERGEBNIS_NEGATIV, weil die Bedeutung eine
# andere ist - Trend, nicht das Vorzeichen eines Ergebnisses.
TREND = "#7a1f1f"
FLAECHE = "#fcfcfb"
TINTE = "#0b0b0b"
TINTE_ZWEITRANGIG = "#52514e"
TINTE_GEDAEMPFT = "#898781"
GITTER = "#e1e0d9"
ACHSE = "#c3c2b7"
# Spaltenraster fuer breite Tabellen im Bildexport (siehe tabelle_als_grafik) - dieselbe
# Idee wie das Spaltenraster der Webapp (basis.html): jede zweite Spalte einen Hauch
# dunkler als FLAECHE, damit sich eine Zahl in einer vielspaltigen Tabelle leichter
# ihrer Spalte zuordnen laesst.
TABELLE_SPALTE_GERADE = "#f2f1ee"
# Die Spalte, die die Zeile zusammenfasst (Summe/Gewinn, siehe tabelle_als_grafik) -
# staerker abgehoben als das Spaltenraster, analog zur "Gesamt"-Zeile der Webapp.
TABELLE_SPALTE_ZUSAMMENFASSUNG = "#eae9e4"

# Fuer den prognostizierten (noch nicht realen) Teil eines Balkens: dieselbe Farbfamilie,
# aber gedaempft - Sicherheit einer Zahl druecken wir ueber die Deckkraft aus, nicht ueber
# eine zweite Farbe (siehe Moduldocstring).
PROGNOSE_DECKKRAFT = 0.4
# Zwischenstufe fuer den laufenden Monat in den Gewinn/Verlust-Ansichten: weder voll
# abgeschlossene Daten noch reine Simulation, sondern eine Mischung aus bereits
# gebuchtem Umsatz und dem simulierten Rest des Monats - liegt deshalb zwischen 1.0
# und PROGNOSE_DECKKRAFT.
VORLAEUFIG_DECKKRAFT = 0.7

# Kategoriale Palette fuer den Gewinn/Verlust-Jahresvergleich: eine Farbe je Kalenderjahr,
# statt Vorzeichen wie beim einzelnen Ergebnis-Balken. Feste Reihenfolge, zugewiesen nach
# aufsteigendem Jahr, nie neu gemischt - das ist die CVD-Sicherheit dieser acht Farbtoene
# (naeheres siehe die Farbmethodik der dataviz-Skill-Referenz). Bei mehr als acht
# gleichzeitig gezeigten Jahren beginnt die Zuordnung von vorn.
JAHRESFARBEN = (
    "#2a78d6",  # blau
    "#eb6834",  # orange
    "#1baf7a",  # tuerkis
    "#eda100",  # gelb
    "#e87ba4",  # magenta
    "#008300",  # gruen
    "#4a3aa7",  # violett
    "#e34948",  # rot
)

SCHRIFT = 'system-ui, -apple-system, "Segoe UI", sans-serif'


class _GridSpec(TypedDict):
    rows: int
    columns: int
    pattern: str


class _FigurLayoutKwargs(TypedDict):
    grid: NotRequired[_GridSpec]


def figur(
    titel: str, *, untertitel: str = "", hoehe: int = 420, **layout: Unpack[_FigurLayoutKwargs]
) -> go.Figure:
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


# Monatsbeschriftungen ("Sep 2025") auf der x-Achse stehen schraeg statt waagerecht,
# unabhaengig von der Anzahl Kategorien: bei ueblichen Notebook-/Browserbreiten
# ueberlappen sich waagerechte Monatsnamen schon in der gewoehnlichen Standardansicht
# (z. B. 12 Historienmonate), nicht erst bei einem langen Zeitraum. Negativer Winkel
# (statt +30), damit die Beschriftung von unten links nach oben rechts ansteigt - die
# ueblichere Leserichtung fuer schraege Achsenbeschriftungen.
TICKWINKEL = -30

# Kurzarbeitsbereitschaft: ob die Schwelle je Monat erreicht wurde, ist ein reiner
# Zustand, keine Wertung (siehe Moduldocstring von domaene.kurzarbeit) - "erreicht"
# bedeutet, dass die Organisation Kurzarbeit haette anmelden koennen, nicht, dass das
# wuenschenswert waere. Deshalb bewusst nicht ERGEBNIS_POSITIV/ERGEBNIS_NEGATIV
# (gruen/rot, an anderer Stelle fuer ein tatsaechliches Vorzeichen reserviert) und auch
# kein Tuerkis (zu nah an Gruen, liest sich noch als "gut") - stattdessen ein gedaempft-
# sachliches Sandbraun/Taupe neben Violett, keines von beiden aus der Kategorial-
# Palette JAHRESFARBEN, um dort keine zweite Bedeutung fuer dieselben Farbtoene zu
# erzeugen, und ohne Blau (schon fuer die Balken in
# :func:`~umsatzprognose.darstellung.diagramme.kurzarbeit_grafik` vergeben).
KURZARBEIT_SCHWELLE_ERREICHT = "#8a6d4f"  # sandbraun/taupe
KURZARBEIT_SCHWELLE_NICHT_ERREICHT = "#4a3aa7"  # violett
