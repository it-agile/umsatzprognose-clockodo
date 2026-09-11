"""FastAPI-Anwendung - das zweite Frontend neben den Notebooks.

Serverseitig gerendert statt als eigene JS-Anwendung: die vorhandenen
Plotly-Figuren aus :mod:`umsatzprognose.darstellung.diagramme` und die
pandas-Tabellen aus :mod:`umsatzprognose.darstellung.tabellen` lassen sich
unveraendert per ``to_html()`` einbetten, ohne eine eigene JSON-API und einen
eigenen Client-Baustein zu brauchen. Siehe Moduldocstring von
:mod:`umsatzprognose.webapp` fuer die Abgrenzung zu den Notebooks.

Drei Seiten, je mit dem Inhalt einer Notebook-Zelle statt mit einer eigenen Auswahl:

- ``/`` deckt sich mit ``notebooks/00_datencheck.ipynb`` - Gewinn/Verlust je Monat,
  Gewinn/Verlust je Jahr, kumulierte Umsatzrendite je Jahr.
- ``/dashboard`` deckt sich mit ``notebooks/01_dashboard.ipynb`` - Umsatzverlauf,
  die zugehoerige Monatstabelle, offenes Auftragsvolumen je Projekt.
- ``/schulungen`` deckt sich mit ``notebooks/03_schulungsanmeldungen.ipynb`` - der
  Anmeldungsverlauf oeffentlicher Schulungen.

**Parameter der Notebook-Ladezellen sind hier URL-Parameter, waehlbar ueber ein
Dropdown** statt Notebook-Variablen (``stichtag`` bleibt bewusst aussen vor - anders
als die anderen gibt es dafuer keinen sinnvollen Standard fuer alle Besuchenden
gleichzeitig): ``horizont_monate`` (Prognosehorizont, auf ``/`` und ``/dashboard``,
weil beide denselben geladenen :class:`Dashboard` zeigen; Optionen
:data:`PROGNOSE_MONATE_OPTIONEN`), ``gewinn_verlust_monate`` (historisches Fenster,
nur auf ``/``; Optionen :data:`HISTORISCHE_MONATE_OPTIONEN`, inklusive ``"alle"``) und
``ab_jahr`` (nur auf ``/schulungen``, filtert einen unabhaengig geladenen
``Anmeldungsverlauf`` nur noch in-memory - siehe Klassendocstring von
:class:`~umsatzprognose.webapp.cache.AnmeldungsverlaufCache` fuer den Unterschied
zu ``horizont_monate``, das tatsaechlich neu laedt). ``auslastung_monate`` aus
:meth:`Dashboard.laden_async` ist
dagegen **kein** URL-Parameter mehr: keine der drei Seiten zeigt etwas, das davon
abhaengt (die Auslastungs-Ansichten selbst sind bislang auf keiner Webapp-Seite
vertreten) - eine feste Standardkombination genuegt, ein Dropdown ohne sichtbare
Wirkung waere nur verwirrend.

Jeder Parameter ist auf eine feste, kuratierte Auswahl beschraenkt statt eines freien
Zahlenbereichs (via ``typing.Literal``, siehe :data:`HorizontMonate` &co.) - das ist
zugleich die Dropdown-Optionsliste (``typing.get_args(...)``) und verhindert einen
unbeschraenkt wachsenden Cache (siehe :mod:`.cache`) durch beliebig viele angefragte
Kombinationen.

**Nicht blockierend geladen**: ``/``, ``/dashboard`` und ``/schulungen`` prüfen über
``DashboardCache.bereit()``/``AnmeldungsverlaufCache.bereit()``, ob die angefragte
Kombination schon geladen ist. Falls nicht, stossen sie das Laden im Hintergrund an
(``anstossen()``) und liefern sofort eine schlichte "Daten werden geladen"-Seite
(``laedt.html``, per Meta-Refresh alle paar Sekunden), statt die Anfrage bis zum
fertigen Ergebnis offenzuhalten - ein voller Ladevorgang (Clockodo-Abruf,
Monte-Carlo-Simulation, beim allerersten Start auch der einmalige interaktive
Google-Login, siehe Moduldocstring von :mod:`umsatzprognose.google_sheets.client`)
braucht spuerbar lange. :func:`_vorladen` stoesst die Standardkombination zusaetzlich
schon beim Start an, damit sie im ueblichen Fall laengst fertig ist, bevor die ersten
Besuchenden eintreffen.

Start lokal (nach ``uv sync --extra web``)::

    uv run uvicorn umsatzprognose.webapp.app:app

**Bewusst ohne ``--reload``** (auch als Standard von ``uvx tox -e web``, siehe
``[tool.tox.env.web]`` in ``pyproject.toml``): ``--reload`` startet zusaetzlich zum
eigentlichen Serverprozess einen Reloader-Prozess, der beim Start denselben schweren
Modulimport (FastAPI/Pydantic, pandas, googleapiclient - insgesamt gut eine Sekunde)
ein zweites Mal durchlaeuft und den Start dadurch spuerbar verlangsamt, ohne dass die
meisten Besuchenden je von der Auto-Reload-Funktion profitieren. Fuer aktive
Entwicklung an ``webapp/`` laesst sich ``--reload --reload-dir
src/umsatzprognose/webapp`` weiterhin ueber Posargs anhaengen (z. B. ``uvx tox -e web
-- --reload --reload-dir src/umsatzprognose/webapp``) - ohne ``--reload-dir``
beobachtet ``--reload`` sonst das gesamte Arbeitsverzeichnis, einschliesslich z. B.
``.tox/``, was bei parallel laufendem ``uvx tox`` zu staendigen Neustarts fuehrt.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal, get_args
from urllib.parse import urlencode

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

    import pandas as pd
    import plotly.graph_objects as go

    from umsatzprognose.domaene import Anmeldungsverlauf, Kurzarbeitsbewertung
    from umsatzprognose.domaene.anmeldung import Kategorisierung
    from umsatzprognose.util import Monat

from collections.abc import Sequence
from contextlib import asynccontextmanager
from functools import partial

import plotly
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from umsatzprognose.clockodo import kurzarbeit_aktiv
from umsatzprognose.darstellung import Dashboard, diagramme, tabellen
from umsatzprognose.domaene import Anmeldungsknoten, Schwellenwerte
from umsatzprognose.domaene.anmeldung import KATEGORIE_SONSTIGE
from umsatzprognose.domaene.zahlen import betrag_parsen
from umsatzprognose.schulungen import kategorien_automatisch

from .cache import AnmeldungsverlaufCache, DashboardCache, KurzarbeitCache

# Deckt sich mit derselben Notebook-Zelle ("projekte_ohne_auftragsvolumen" in
# notebooks/01_dashboard.ipynb) - dort ein fester Wert, hier per Slider einstellbar
# (siehe RestvolumenTop unten). Kein statisches "le=": das sinnvolle Maximum (Anzahl
# Projekte ohne Budget, siehe dashboard_seite()) haengt vom geladenen Bestand ab.
STANDARD_RESTVOLUMEN_TOP = 20


# Feste, kuratierte Optionen statt eines freien Zahlenbereichs - siehe Moduldocstring.
# "alle" bei den historischen Monaten steht fuer die gesamte geladene Historie (siehe
# Dashboard.gewinn_verlust_monatlich). Die Literal-Typen tragen die Optionen nur
# einmal; PROGNOSE_MONATE_OPTIONEN/HISTORISCHE_MONATE_OPTIONEN lesen sie fuers
# Dropdown zurueck, statt sie ein zweites Mal aufzuschreiben.
_HorizontMonateWert = Literal["3", "4", "5", "6"]
_GewinnVerlustMonateWert = Literal["3", "6", "12", "24", "alle"]
_KurzarbeitMonateWert = Literal["1", "3", "6", "12"]
HorizontMonate = Annotated[_HorizontMonateWert, Query()]
GewinnVerlustMonate = Annotated[_GewinnVerlustMonateWert, Query()]
KurzarbeitMonate = Annotated[_KurzarbeitMonateWert, Query()]
PROGNOSE_MONATE_OPTIONEN = get_args(_HorizontMonateWert)
HISTORISCHE_MONATE_OPTIONEN = get_args(_GewinnVerlustMonateWert)
KURZARBEIT_MONATE_OPTIONEN = get_args(_KurzarbeitMonateWert)
KURZARBEIT_MONATE_BESCHRIFTUNGEN: dict[_KurzarbeitMonateWert, str] = {
    "1": "1 Monat",
    "3": "3 Monate",
    "6": "6 Monate",
    "12": "1 Jahr",
}

STANDARD_HORIZONT_MONATE: _HorizontMonateWert = "3"
STANDARD_AUSLASTUNG_MONATE = 12
STANDARD_GEWINN_VERLUST_MONATE: _GewinnVerlustMonateWert = "12"
STANDARD_AB_JAHR = 2022
# Ab diesem Monat gilt das laufende Jahr als eigenstaendig aussagekraeftig genug fuer
# die Standardansicht (siehe _standard_anzeige_ab_jahr()) - vorher wird zusaetzlich
# das Vorjahr gezeigt.
STANDARD_ANZEIGE_MINDESTMONAT = 6
STANDARD_KURZARBEIT_MONATE: _KurzarbeitMonateWert = "6"
# KurzarbeitCache laedt immer diese (groesste) Kombination und schneidet engere
# Anfragen nur noch in-memory heraus (siehe Klassendocstring) - ein Dropdown-Wechsel
# loest so nie einen erneuten Ladevorgang bei Clockodo aus.
MAXIMALE_KURZARBEIT_MONATE = max(int(wert) for wert in KURZARBEIT_MONATE_OPTIONEN)

AbJahr = Annotated[int | None, Query(ge=STANDARD_AB_JAHR)]

RestvolumenTop = Annotated[int, Query(ge=1)]

# Freitext-Parameter fuer die beiden unten eingeklappten Konfigurationsabschnitte -
# leer bleibt ohne Wirkung (siehe _verbrauchsplan_aus_text()/_ohne_budget_filter_aus_text()).
Verbrauchsplan = Annotated[str, Query()]
OhneBudgetFilter = Annotated[str, Query()]

# Die vier unabhaengigen Filter-Dropdowns (Mehrfachauswahl) fuer den Anmeldungsverlauf
# auf /schulungen (siehe _anmeldungsreihen()) - anders als HorizontMonate & Co. keine
# Annotated[Literal[...]], weil ihre gueltigen Werte von den geladenen Daten bzw. der
# .env-Konfiguration abhaengen, nicht von einer festen, im Code kuratierten Auswahl.
KategorieFilter = Annotated[Sequence[str], Query()]
SchulungFilter = Annotated[Sequence[str], Query()]
FormatFilter = Annotated[Sequence[str], Query()]
DauerFilter = Annotated[Sequence[str], Query()]
# Checkbox-Wert per verstecktem Begleitfeld (siehe schulungen.html): ein einzelnes
# HTML-Kontrollkaestchen kann seinen "aus"-Zustand nicht selbst senden, ein
# Begleitfeld mit demselben Namen und Wert "aus" tut das immer, das Kontrollkaestchen
# selbst nur zusaetzlich mit Wert "an", wenn angehakt.
TrendlinienWerte = Annotated[Sequence[str], Query()]

ALLE_KATEGORIEN = "Alle Kategorien"
ALLE_SCHULUNGEN = "Alle Schulungen"
ALLE = "Alle"

# Je Seite die Parameter-Standardwerte (als String, wie sie im Query-String stehen) -
# _anfrage_query() blendet damit auf ihren Standard stehende Parameter aus
# Navigations- und Zuruecksetzen-Links aus, damit die URL beim Seitenwechsel schlank
# bleibt statt unveraendert mitgeschleppter Standardwerte (``ab_jahr`` auf
# /schulungen fehlt hier, weil sein Standard vom aktuellen Datum abhaengt - siehe
# _standard_anzeige_ab_jahr() und die Route selbst).
_STANDARDWERTE_START: dict[str, str] = {
    "horizont_monate": STANDARD_HORIZONT_MONATE,
    "gewinn_verlust_monate": STANDARD_GEWINN_VERLUST_MONATE,
    "verbrauchsplan": "",
}
_STANDARDWERTE_DASHBOARD: dict[str, str] = {
    "horizont_monate": STANDARD_HORIZONT_MONATE,
    "restvolumen_top": str(STANDARD_RESTVOLUMEN_TOP),
    "verbrauchsplan": "",
    "ohne_budget_filter": "",
}


def _standard_anzeige_ab_jahr(*, heute: date | None = None) -> int:
    """Ohne explizit gewaehlten ``ab_jahr``-Parameter gezeigtes Jahr.

    Das laufende Jahr, wenn davon schon mindestens
    :data:`STANDARD_ANZEIGE_MINDESTMONAT` Monate vorueber sind, sonst zusaetzlich das
    Vorjahr - eine Standardansicht mit nur ein oder zwei Monaten waere zu duenn fuer
    einen sinnvollen Blick auf den Anmeldungsverlauf. Nie vor :data:`STANDARD_AB_JAHR`,
    weiter zurueck ist ohnehin nichts geladen.
    """
    heute = heute or date.today()
    jahr = heute.year if heute.month >= STANDARD_ANZEIGE_MINDESTMONAT else heute.year - 1
    return max(jahr, STANDARD_AB_JAHR)


# Die drei Schwellenwerte der Kurzarbeit-Regel (siehe domaene.kurzarbeit.Schwellenwerte)
# als Regler in der Weboberflaeche. Anteil interne Arbeit/Quote der Organisation sind
# Prozentangaben - volle Prozentpunkte (step=1) genuegen, ein Nachkommawert waere
# Schein-Praezision.
# Ueberstundenstand ist keine Prozentangabe, aber ebenfalls in vollen Stunden sinnvoll.
# 0-100 % ist der volle, unstrittige Wertebereich; bei den Ueberstunden ist 0-40 Std.
# grosszuegig um den Standard (14 Std.) herum bemessen, ohne den Regler unhandlich zu
# machen.
AnteilInterneArbeitProzent = Annotated[int, Query(ge=0, le=100)]
QuoteOrganisationProzent = Annotated[int, Query(ge=0, le=100)]
UeberstundenStunden = Annotated[int, Query(ge=0, le=40)]

STANDARD_ANTEIL_INTERNE_ARBEIT_PROZENT = 24
STANDARD_QUOTE_ORGANISATION_PROZENT = 30
STANDARD_UEBERSTUNDEN_STUNDEN = 14

_STANDARDWERTE_KURZARBEIT: dict[str, str] = {
    "anzahl_monate": STANDARD_KURZARBEIT_MONATE,
    "anteil_interne_arbeit_prozent": str(STANDARD_ANTEIL_INTERNE_ARBEIT_PROZENT),
    "ueberstunden_stunden": str(STANDARD_UEBERSTUNDEN_STUNDEN),
    "quote_organisation_prozent": str(STANDARD_QUOTE_ORGANISATION_PROZENT),
}

_dashboard_cache = DashboardCache()
_anmeldungsverlauf_cache = AnmeldungsverlaufCache(ab_jahr=STANDARD_AB_JAHR)
_kurzarbeit_cache = KurzarbeitCache(maximale_monate=MAXIMALE_KURZARBEIT_MONATE)
_templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

# Einmal beim Import gelesen (siehe umsatzprognose.clockodo.kurzarbeit_aktiv) - steuert
# Navigation, die /kurzarbeit-Route und das Vorladen unten gemeinsam.
_KURZARBEIT_AKTIV = kurzarbeit_aktiv()


@asynccontextmanager
async def _vorladen(app: FastAPI) -> AsyncIterator[None]:
    """Stoesst das Laden der Standardkombination schon beim Start an, ohne zu warten.

    Nicht blockierend (siehe Moduldocstring) - der Server nimmt sofort Anfragen an;
    treffen die ersten Besuchenden frueher ein, als das Vorladen fertig ist, sehen sie
    schlicht dieselbe "Daten werden geladen"-Seite wie bei jeder anderen noch nicht
    gecachten Kombination auch.
    """
    _dashboard_cache.anstossen(
        horizont_monate=int(STANDARD_HORIZONT_MONATE), auslastung_monate=STANDARD_AUSLASTUNG_MONATE
    )
    _anmeldungsverlauf_cache.anstossen()
    if _KURZARBEIT_AKTIV:
        _kurzarbeit_cache.anstossen()
    yield


app = FastAPI(title="Umsatzprognose", lifespan=_vorladen)
# Reihenfolge wichtig: Starlette prueft Mounts in Registrierungsreihenfolge, das
# allgemeinere "/static" wuerde sonst auch "/static/plotly/..." abfangen, bevor das
# speziellere Mount darunter je zum Zug kaeme.
#
# plotly.js selbst ausliefern statt von einem Drittanbieter-CDN zu laden - die interne
# Anwendung soll nicht von der Erreichbarkeit von cdn.plot.ly abhaengen. Gemountet aus
# dem installierten Paket statt eingecheckt (die Datei ist mehrere MB gross und bleibt
# so automatisch mit der in pyproject.toml gepinnten plotly-Version synchron).
app.mount(
    "/static/plotly",
    StaticFiles(directory=str(Path(plotly.__file__).parent / "package_data")),
    name="plotly",
)
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")


def _figur_html(figur: go.Figure, *, mit_plotlyjs: bool) -> str:
    return figur.to_html(
        full_html=False, include_plotlyjs="/static/plotly/plotly.min.js" if mit_plotlyjs else False
    )


# Spalten, die (einen Teil) der Zeile zusammenfassen - siehe _tabelle_html().
_SPALTEN_ZUSAMMENFASSUNG = {"Summe", "Gewinn"}
_SPALTE_GEWINN = "Gewinn"


def _gewinn_eingefaerbt(wert: str) -> str:
    """Ein schon als Text formatierter Gewinn-Betrag (siehe ``tabellen.umsatztabelle``),
    rot bei negativem und gruen bei positivem Vorzeichen eingefaerbt. Eine 0 (kein
    Kostenplan geladen, oder ein Monat tatsaechlich exakt ausgeglichen) bleibt bewusst
    ungefaerbt, weil weder ein Gewinn noch ein Verlust vorliegt.
    """
    betrag = betrag_parsen(wert)
    if betrag > 0:
        return f'<span class="gewinn-positiv">{wert}</span>'
    if betrag < 0:
        return f'<span class="gewinn-negativ">{wert}</span>'
    return wert


def _tabelle_html(tabelle: pd.DataFrame, *, zusatzklasse: str = "", element_id: str = "") -> str:
    # to_html() liefert Header-Zellen ohne scope="col"; mit index=False bestehen im
    # erzeugten Fragment ausschliesslich die Header-Zellen aus <th>, Datenzellen sind
    # <td> - ein gezielter Ersatz reicht deshalb ohne den Index faelschlich zu treffen.
    hat_gewinnspalte = _SPALTE_GEWINN in tabelle.columns
    anzeige = tabelle.copy()
    if hat_gewinnspalte:
        anzeige[_SPALTE_GEWINN] = anzeige[_SPALTE_GEWINN].map(_gewinn_eingefaerbt)
    html = anzeige.to_html(
        index=False,
        border=0,
        classes=f"tabelle {zusatzklasse}".strip(),
        na_rep="",
        # Nur bei eingefaerbtem Gewinn noetig - die injizierten <span>-Tags duerften
        # sonst nicht als Markup durchgereicht werden. Alle anderen Zellwerte dieser
        # Tabellen sind intern erzeugte, bereits formatierte Zahlen/Bezeichnungen ohne
        # HTML-Sonderzeichen, das Abschalten des Escapings ist dafuer unbedenklich.
        escape=not hat_gewinnspalte,
    )
    html = html.replace("<th>", '<th scope="col">')
    if not element_id:
        return html
    html = html.replace("<table ", f'<table id="{element_id}" ', 1)
    # Anders als der Kategorie-Drilldown (schulungen.html), dessen Summe-Spalte immer
    # die letzte ist und deshalb per CSS-Klasse ueber :last-child abgehoben wird
    # (siehe .spalte-zusammenfassung in basis.html), steht "Summe" in der
    # Monatstabelle mitten in der Tabelle - eine reine CSS-Klasse kann eine bestimmte
    # Spalte unabhaengig von ihrer Position nicht treffen. Deshalb hier stattdessen
    # eine gezielte, auf die Spaltenposition zugeschnittene :nth-child-Regel je
    # Zusammenfassungsspalte, ueber dieselben CSS-Variablen wie .spalte-zusammenfassung
    # (keine doppelt gepflegten Werte).
    spalten = list(tabelle.columns)
    zusammenfassung = [name for name in spalten if name in _SPALTEN_ZUSAMMENFASSUNG]
    if not zusammenfassung:
        return html
    # Fettung nur fuer Gewinn (das Endergebnis, zusaetzlich gruen/rot eingefaerbt) -
    # der Summenwert selbst muss sich nicht zusaetzlich durch Fettschrift abheben.
    regeln = "".join(
        f"#{element_id} th:nth-child({spalten.index(name) + 1}),"
        f" #{element_id} td:nth-child({spalten.index(name) + 1})"
        " { border-left: var(--spalte-grenze); background: var(--spalte-grenze-flaeche);"
        f"{' font-weight: 600;' if name == _SPALTE_GEWINN else ''} }}"
        for name in zusammenfassung
    )
    return f"{html}<style>{regeln}</style>"


def _anfrage_query(
    request: Request,
    standardwerte: dict[str, str] | None = None,
    *,
    ohne: frozenset[str] = frozenset(),
) -> str:
    """Query-String der aktuellen Anfrage fuer Navigations- und Zuruecksetzen-Links.

    Ein Parameter faellt weg, wenn er in ``ohne`` steht oder seinem Standardwert
    entspricht (``standardwerte``) - sonst wuerden beim Seitenwechsel bzw.
    Zuruecksetzen unveraendert auf dem Standard stehende Parameter mitgeschleppt,
    statt die URL schlank zu halten.
    """
    paare = [
        (schluessel, wert)
        for schluessel, wert in request.query_params.multi_items()
        if schluessel not in ohne and (not standardwerte or standardwerte.get(schluessel) != wert)
    ]
    return f"?{urlencode(paare)}" if paare else ""


def _antwort(
    request: Request,
    *,
    seite: str,
    name: str,
    stichtag: date | None,
    standardwerte: dict[str, str] | None = None,
    **kontext: object,
) -> HTMLResponse:
    return _templates.TemplateResponse(
        request=request,
        name=name,
        context={
            "aktive_seite": seite,
            "stichtag": stichtag,
            "anfrage_query": _anfrage_query(request, standardwerte),
            "kurzarbeit_aktiv": _KURZARBEIT_AKTIV,
            **kontext,
        },
    )


def _ladeseite(
    request: Request,
    *,
    seite: str,
    fortschritt: list[str],
    fehler: str | None = None,
    standardwerte: dict[str, str] | None = None,
) -> HTMLResponse:
    """Kurze Zwischenseite, waehrend :mod:`.cache` im Hintergrund laedt - siehe Moduldocstring.

    ``fortschritt`` zeigt die bisher gemeldeten Statuszeilen des laufenden
    Ladevorgangs (siehe ``DashboardCache.fortschritt``/``AnmeldungsverlaufCache.
    fortschritt``) - dieselbe Sicht wie in den Notebooks, nur per Meta-Refresh
    nachgeholt statt live nachgeschoben (siehe Moduldocstring von ``.cache``).

    ``fehler``, sofern angegeben, macht einen zuletzt gescheiterten Ladeversuch
    sichtbar (siehe ``_TTLCache.fehler``) - ohne das sah ein wiederholt scheiternder
    Ladevorgang von aussen genauso aus wie ein noch laufender ("Daten werden
    geladen", endlos), die eigentliche Meldung stand nur auf der Server-Konsole. Der
    naechste Seitenaufruf (per Meta-Refresh) loest ohnehin automatisch einen neuen
    Versuch aus.
    """
    return _antwort(
        request,
        seite=seite,
        name="laedt.html",
        stichtag=None,
        standardwerte=standardwerte,
        fortschritt=fortschritt,
        fehler=fehler,
    )


def _bereit_oder_ladeseite[T](
    request: Request,
    *,
    seite: str,
    bereit: Callable[[], T | None],
    anstossen: Callable[[], None],
    fortschritt: Callable[[], list[str]],
    fehler: Callable[[], str | None],
    standardwerte: dict[str, str] | None = None,
) -> T | HTMLResponse:
    """Liefert den gecachten Wert, sonst stoesst sie das Laden im Hintergrund an und
    liefert die Ladeseite - das gemeinsame "nicht blockierend geladen"-Muster aller
    vier Seiten (siehe Moduldocstring). ``bereit``/``anstossen``/``fortschritt``/
    ``fehler`` sind parameterlose Callables - ein Aufrufer mit mehreren
    Cache-Schluesseln (z. B. ``DashboardCache`` ueber ``horizont_monate``/
    ``auslastung_monate``) bindet diese vorher per :func:`functools.partial`."""
    wert = bereit()
    if wert is not None:
        return wert
    anstossen()
    return _ladeseite(
        request,
        seite=seite,
        fortschritt=fortschritt(),
        fehler=fehler(),
        standardwerte=standardwerte,
    )


def _dashboard_oder_ladeseite(
    request: Request,
    *,
    seite: str,
    horizont_monate: int,
    auslastung_monate: int,
    standardwerte: dict[str, str] | None = None,
) -> Dashboard | HTMLResponse:
    """Liefert das gecachte ``Dashboard`` fuer diese Parameterkombination, sonst die
    Ladeseite - gemeinsam fuer ``uebersicht()`` und ``dashboard_seite()``, die beide
    denselben ``DashboardCache``-Schluessel (``horizont_monate``, ``auslastung_monate``)
    verwenden. Bindet diese beiden Schluesselwerte einmal per :func:`~functools.partial`
    und delegiert an :func:`_bereit_oder_ladeseite`."""
    return _bereit_oder_ladeseite(
        request,
        seite=seite,
        bereit=partial(
            _dashboard_cache.bereit,
            horizont_monate=horizont_monate,
            auslastung_monate=auslastung_monate,
        ),
        anstossen=partial(
            _dashboard_cache.anstossen,
            horizont_monate=horizont_monate,
            auslastung_monate=auslastung_monate,
        ),
        fortschritt=partial(
            _dashboard_cache.fortschritt,
            horizont_monate=horizont_monate,
            auslastung_monate=auslastung_monate,
        ),
        fehler=partial(
            _dashboard_cache.fehler,
            horizont_monate=horizont_monate,
            auslastung_monate=auslastung_monate,
        ),
        standardwerte=standardwerte,
    )


def _verbrauchsplan_aus_text(text: str) -> dict[str, tuple[int, int]]:
    """Eine Zeile je Projekt, Format ``Projektname: JJJJ-MM`` - fuers Textarea der
    eingeklappten Verbrauchsplan-Sektion. Leere oder nicht passende Zeilen werden
    uebersprungen statt die Seite mit einem Fehler abzubrechen."""
    werte: dict[str, tuple[int, int]] = {}
    for zeile in text.splitlines():
        if ":" not in zeile:
            continue
        name, monat_text = zeile.split(":", 1)
        name = name.strip()
        if not name or "-" not in monat_text:
            continue
        jahr_text, monat_nr_text = monat_text.strip().split("-", 1)
        try:
            werte[name] = (int(jahr_text), int(monat_nr_text))
        except ValueError:
            continue
    return werte


def _ohne_budget_filter_aus_text(text: str) -> list[str]:
    """Ein Ausschluss-Begriff je Zeile fuers Textarea der eingeklappten
    Projektfilter-Sektion (siehe ``Bestand.ohne_budget``) - leere Zeilen werden
    uebersprungen."""
    return [zeile.strip() for zeile in text.splitlines() if zeile.strip()]


async def _mit_verbrauchsplan(
    dashboard: Dashboard, *, verbrauchsplan: str, horizont_monate: int
) -> Dashboard:
    """Liefert bei gesetztem ``verbrauchsplan`` ein **transientes** ``Dashboard`` mit
    angewendeter Uebersteuerung und frischer Simulation, sonst unveraendert das
    uebergebene.

    Absichtlich kein ``dashboard.verbrauchsplan_uebersteuern(...)`` auf dem
    uebergebenen Objekt: dieses ``Dashboard`` ist bei einem Treffer im
    ``DashboardCache`` **derselbe, geteilte** Stand fuer alle Besuchenden (siehe
    Moduldocstring - keine Benutzertrennung). Eine In-Place-Uebersteuerung durch eine
    einzelne Anfrage wuerde bis zum naechsten TTL-Reload allen anderen Besuchenden
    dieselbe uebersteuerte Prognose zeigen. Stattdessen entsteht ein neues
    ``Dashboard`` mit einem neuen, unveraenderlichen ``Bestand``
    (``mit_verbrauchsplan_uebersteuerungen``) und einer eigenen Neusimulation -
    ``schulungsplan``/``kostenplan``/``auslastung`` werden vom Original uebernommen,
    kein erneuter Abruf. ``simuliere_async()`` statt ``simuliere()``: ein direkter,
    blockierender Aufruf wuerde den einzigen Event-Loop-Thread des Servers fuer die
    Dauer dieser Neusimulation einfrieren - je Anfrage mit gesetztem
    ``verbrauchsplan``, nicht nur beim seltenen Neuladen des Caches.
    """
    werte = _verbrauchsplan_aus_text(verbrauchsplan)
    if not werte:
        return dashboard
    uebersteuert = Dashboard(
        dashboard.bestand.mit_verbrauchsplan_uebersteuerungen(werte),
        dashboard.schulungsplan,
        dashboard.kostenplan,
        dashboard.auslastung,
    )
    await uebersteuert.simuliere_async(monate=horizont_monate)
    return uebersteuert


@app.get("/", response_class=HTMLResponse)
async def uebersicht(
    request: Request,
    horizont_monate: HorizontMonate = STANDARD_HORIZONT_MONATE,
    gewinn_verlust_monate: GewinnVerlustMonate = STANDARD_GEWINN_VERLUST_MONATE,
    verbrauchsplan: Verbrauchsplan = "",
) -> HTMLResponse:
    """Deckt sich mit notebooks/00_datencheck.ipynb: Gewinn/Verlust und Umsatzrendite."""
    horizont_zahl = int(horizont_monate)
    ergebnis = _dashboard_oder_ladeseite(
        request,
        seite="start",
        horizont_monate=horizont_zahl,
        auslastung_monate=STANDARD_AUSLASTUNG_MONATE,
        standardwerte=_STANDARDWERTE_START,
    )
    if isinstance(ergebnis, HTMLResponse):
        return ergebnis
    dashboard = await _mit_verbrauchsplan(
        ergebnis, verbrauchsplan=verbrauchsplan, horizont_monate=horizont_zahl
    )

    gewinn_verlust_zahl = None if gewinn_verlust_monate == "alle" else int(gewinn_verlust_monate)
    return _antwort(
        request,
        seite="start",
        name="datencheck.html",
        stichtag=dashboard.stichtag,
        standardwerte=_STANDARDWERTE_START,
        horizont_monate=horizont_monate,
        horizont_optionen=PROGNOSE_MONATE_OPTIONEN,
        gewinn_verlust_monate=gewinn_verlust_monate,
        gewinn_verlust_optionen=HISTORISCHE_MONATE_OPTIONEN,
        verbrauchsplan=verbrauchsplan,
        verbrauchsplan_abweichend=bool(verbrauchsplan.strip()),
        verbrauchsplan_zuruecksetzen_query=_anfrage_query(
            request, _STANDARDWERTE_START, ohne=frozenset({"verbrauchsplan"})
        ),
        gewinn_verlust_monatlich=_figur_html(
            dashboard.gewinn_verlust_monatlich(monate=gewinn_verlust_zahl), mit_plotlyjs=True
        ),
        gewinn_verlust_je_jahr=_figur_html(dashboard.gewinn_verlust_je_jahr(), mit_plotlyjs=False),
        umsatzrendite_kumuliert=_figur_html(
            dashboard.umsatzrendite_kumuliert(), mit_plotlyjs=False
        ),
    )


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_seite(
    request: Request,
    horizont_monate: HorizontMonate = STANDARD_HORIZONT_MONATE,
    restvolumen_top: RestvolumenTop = STANDARD_RESTVOLUMEN_TOP,
    verbrauchsplan: Verbrauchsplan = "",
    ohne_budget_filter: OhneBudgetFilter = "",
) -> HTMLResponse:
    """Deckt sich mit notebooks/01_dashboard.ipynb: Umsatzverlauf und offenes Volumen."""
    horizont_zahl = int(horizont_monate)
    ergebnis = _dashboard_oder_ladeseite(
        request,
        seite="dashboard",
        horizont_monate=horizont_zahl,
        auslastung_monate=STANDARD_AUSLASTUNG_MONATE,
        standardwerte=_STANDARDWERTE_DASHBOARD,
    )
    if isinstance(ergebnis, HTMLResponse):
        return ergebnis
    dashboard = await _mit_verbrauchsplan(
        ergebnis, verbrauchsplan=verbrauchsplan, horizont_monate=horizont_zahl
    )
    restvolumen_top_max = len(dashboard.bestand.ohne_budget())
    # Der Slider traegt max="{{ restvolumen_top_max }}", aber Query(ge=1) allein
    # verhindert nicht, dass ein manuell erhoehter URL-Parameter darueber liegt -
    # sonst zeigt der Slider einen Wert ausserhalb seines eigenen Maximalattributs.
    if restvolumen_top_max:
        restvolumen_top = min(restvolumen_top, restvolumen_top_max)

    return _antwort(
        request,
        seite="dashboard",
        name="dashboard.html",
        stichtag=dashboard.stichtag,
        standardwerte=_STANDARDWERTE_DASHBOARD,
        horizont_monate=horizont_monate,
        horizont_optionen=PROGNOSE_MONATE_OPTIONEN,
        umsatzverlauf=_figur_html(dashboard.umsatzverlauf(), mit_plotlyjs=True),
        umsatztabelle=_tabelle_html(
            dashboard.umsatztabelle(), zusatzklasse="spaltenraster", element_id="tabelle-monat"
        ),
        restvolumen_top=restvolumen_top,
        restvolumen_top_max=restvolumen_top_max,
        restvolumen_je_projekt=_figur_html(
            dashboard.restvolumen_je_projekt(top=restvolumen_top), mit_plotlyjs=False
        ),
        verbrauchsplan=verbrauchsplan,
        verbrauchsplan_abweichend=bool(verbrauchsplan.strip()),
        verbrauchsplan_zuruecksetzen_query=_anfrage_query(
            request, _STANDARDWERTE_DASHBOARD, ohne=frozenset({"verbrauchsplan"})
        ),
        ohne_budget_filter=ohne_budget_filter,
        ohne_budget_filter_abweichend=bool(ohne_budget_filter.strip()),
        ohne_budget_filter_zuruecksetzen_query=_anfrage_query(
            request, _STANDARDWERTE_DASHBOARD, ohne=frozenset({"ohne_budget_filter"})
        ),
        projekte_ohne_budget=_tabelle_html(
            dashboard.projekte_ohne_budget(_ohne_budget_filter_aus_text(ohne_budget_filter))
        ),
    )


def _monate_summieren(knoten: Sequence[Anmeldungsknoten]) -> dict[Monat, int]:
    """Monatswerte mehrerer Geschwister-Knoten aufsummiert - Grundlage fuer den
    virtuellen Wurzelknoten einer Kategorie (:func:`_kategorie_knoten`) und die
    Gesamt-Zeile ueber alle Kategorien."""
    summen: dict[Monat, int] = {}
    for kind in knoten:
        for monat, wert in kind.monate.items():
            summen[monat] = summen.get(monat, 0) + wert
    return summen


def _kategorie_knoten(name: str, kinder: tuple[Anmeldungsknoten, ...]) -> Anmeldungsknoten:
    """Ein virtueller Wurzelknoten fuer eine Kategorie, mit ihren Basisname-Knoten als
    Kinder - dieselbe Knotenform wie darunter, damit :func:`_knoten_ansicht` die
    Kategorie-Zeile und ihre Unterzeilen einheitlich behandeln kann."""
    return Anmeldungsknoten(name, _monate_summieren(kinder), kinder)


def _knoten_flach(
    knoten: Anmeldungsknoten, monate: Sequence[Monat], *, tiefe: int = 0, pfad: str = "0"
) -> list[dict[str, object]]:
    """Wandelt einen :class:`~umsatzprognose.domaene.Anmeldungsknoten`-Baum in eine
    flache, in Vorordnung sortierte Liste von Jinja-tauglichen Zeilen um - Grundlage
    fuer echte ``<tr>``-Zeilen in ``schulungen.html`` statt verschachtelter
    ``<details>``-Elemente.

    Ein verschachteltes ``<details>`` haette (auch mit ``display: contents`` auf dem
    Element selbst) in der Praxis keine verlaessliche gemeinsame Tabellen-
    Spaltenberechnung mit der Wurzel ergeben: der Inhaltsbereich eines ``<details>``
    (alles ausser ``<summary>``) bildet in aktuellen Browsern einen eigenen, davon
    unabhaengigen Block, in dem eine tiefer verschachtelte Zeile ihre eigene, isolierte
    Spaltenbreite bekommt statt der Monatsspalten der Wurzel - beobachtet an einer
    aufgeklappten Unterkategorie, deren Zahlen dann nicht mehr unter den
    Monatsspalten, sondern zusammengequetscht direkt hinter dem Pfeil auftauchen. Eine
    echte ``<table>`` berechnet ihre Spaltenbreiten dagegen immer ueber alle (auch
    unsichtbaren) Zeilen hinweg korrekt; das Auf-/Zuklappen blendet Zeilen deshalb nur
    noch per ``style.display`` ein/aus (siehe ``kategorieZeileUmschalten()`` in
    ``schulungen.html``), ohne die Spaltenberechnung zu beeinflussen.
    """
    werte = [knoten.monate.get(monat, 0) for monat in monate]
    knoten_id = f"schulung-zeile-{pfad}"
    zeile: dict[str, object] = {
        "id": knoten_id,
        "name": knoten.name,
        "werte": werte,
        "summe": sum(werte),
        "tiefe": tiefe,
        "hat_kinder": bool(knoten.kinder),
        # Direkte Kinder-IDs fuer aria-controls am Auf-/Zuklapp-Knopf - das JS selbst
        # blendet zwar auch tiefer verschachtelte Nachfahren mit ein/aus, aber
        # aria-controls beschreibt nur den unmittelbar gesteuerten Bereich, tiefere
        # Ebenen haben ihren eigenen Knopf mit eigenem aria-controls.
        "kinder_ids": [f"{knoten_id}-{i}" for i in range(len(knoten.kinder))],
    }
    zeilen = [zeile]
    for i, kind in enumerate(knoten.kinder):
        zeilen.extend(_knoten_flach(kind, monate, tiefe=tiefe + 1, pfad=f"{pfad}-{i}"))
    return zeilen


def _anmeldungsreihen(
    verlauf: Anmeldungsverlauf,
    kategorien: Kategorisierung,
    *,
    kategorie_filter: Sequence[str],
    schulung_filter: Sequence[str],
    format_filter: Sequence[str],
    dauer_filter: Sequence[str],
) -> dict[str, dict[Monat, int]]:
    """Eine Reihe je ausgewaehltem Filterkriterium, ueber alle vier Dropdowns hinweg -
    nicht nur eine je Kategorie: jede Auswahl (Kategorie, Basisname, Format oder Dauer)
    erzeugt ihre eigene Linie im Diagramm (siehe
    :func:`~umsatzprognose.darstellung.diagramme.anmeldungsverlauf_reihen`), auch wenn
    mehrere Dropdowns gleichzeitig etwas auswaehlen. :data:`ALLE_KATEGORIEN` (im
    Kategorie-Dropdown), :data:`ALLE_SCHULUNGEN` (im Schulungen-Dropdown) und
    :data:`ALLE` (in Format- oder Dauer-Dropdown) meinen dieselbe Gesamtzahl -
    unabhaengig davon, in welchem Dropdown oder wie oft gewaehlt, liefert das genau
    eine Reihe (``dict.setdefault``).
    """
    reihen: dict[str, dict[Monat, int]] = {}
    je_kategorie: dict[str, dict[Monat, int]] | None = None
    for name in kategorie_filter:
        if name == ALLE_KATEGORIEN:
            reihen.setdefault(ALLE_SCHULUNGEN, verlauf.je_monat())
            continue
        if je_kategorie is None:
            je_kategorie = verlauf.je_monat_und_kategorie(kategorien)
        reihen.setdefault(name, je_kategorie.get(name, {}))
    for basisname in schulung_filter:
        if basisname == ALLE_SCHULUNGEN:
            reihen.setdefault(ALLE_SCHULUNGEN, verlauf.je_monat())
        else:
            reihen.setdefault(basisname, verlauf.je_monat_und_basisname(basisname))
    for format_wert in format_filter:
        if format_wert == ALLE:
            reihen.setdefault(ALLE_SCHULUNGEN, verlauf.je_monat())
        else:
            reihen.setdefault(format_wert, verlauf.je_monat_und_format(format_wert))
    for dauer_wert in dauer_filter:
        if dauer_wert == ALLE:
            reihen.setdefault(ALLE_SCHULUNGEN, verlauf.je_monat())
        else:
            reihen.setdefault(dauer_wert, verlauf.je_monat_und_dauer(dauer_wert))
    return reihen


def _schulung_optionen(
    verlauf: Anmeldungsverlauf, kategorien: Kategorisierung, *, kategorie_filter: Sequence[str]
) -> list[str]:
    """Die Basisnamen (Dauer-Varianten wie "CSPO 2-tägig"/"CSPO 3-tägig"
    zusammengefasst zu "CSPO", wie im Tabellen-Drilldown - siehe
    :meth:`Anmeldungsverlauf.summe_je_basisname`) mit Anmeldung im aktuellen
    Zeitfenster, alphabetisch sortiert und mit :data:`ALLE_SCHULUNGEN` vorangestellt -
    eingeschraenkt auf die gewaehlten Kategorien, falls ``kategorie_filter`` (ohne
    :data:`ALLE_KATEGORIEN`) nicht leer ist, sonst ungefiltert. Reine Anzeige-
    Konfiguration der Dropdown-Optionen, keine Fachlogik - die eigentliche Zuordnung
    liefert :meth:`Anmeldungsverlauf.basisnamen_je_kategorie`."""
    gewaehlte_kategorien = [name for name in kategorie_filter if name != ALLE_KATEGORIEN]
    if not gewaehlte_kategorien:
        return [ALLE_SCHULUNGEN, *sorted(verlauf.basisnamen, key=str.lower)]
    je_kategorie = verlauf.basisnamen_je_kategorie(kategorien)
    erlaubt = {
        name for kategorie in gewaehlte_kategorien for name in je_kategorie.get(kategorie, ())
    }
    return [
        ALLE_SCHULUNGEN,
        *sorted((name for name in verlauf.basisnamen if name in erlaubt), key=str.lower),
    ]


@app.get("/schulungen", response_class=HTMLResponse)
async def schulungen(
    request: Request,
    ab_jahr: AbJahr = None,
    kategorie_filter: KategorieFilter = (ALLE_KATEGORIEN,),
    schulung_filter: SchulungFilter = (ALLE_SCHULUNGEN,),
    format_filter: FormatFilter = (ALLE,),
    dauer_filter: DauerFilter = (ALLE,),
    trendlinien_werte: TrendlinienWerte = ("an",),
) -> HTMLResponse:
    """Deckt sich mit notebooks/03_schulungsanmeldungen.ipynb: der Anmeldungsverlauf.

    ``ab_jahr`` filtert den einen geladenen Anmeldungsverlauf nur noch in-memory
    (siehe :class:`~umsatzprognose.webapp.cache.AnmeldungsverlaufCache`) - ein
    engerer Beginn zeigt deshalb sofort ein anderes Ergebnis, ohne neu zu laden. Ohne
    Angabe gilt :func:`_standard_anzeige_ab_jahr` statt starr :data:`STANDARD_AB_JAHR`.

    Die vier Filter-Dropdowns (Mehrfachauswahl) darueber, was der Anmeldungsverlauf
    zeigt, sind unabhaengige Auswahlkriterien statt einer Filterkette: jede Auswahl
    erzeugt ihre eigene Linie (siehe :func:`_anmeldungsreihen`), das Diagramm zeigt
    also die Vereinigung aller vier Dropdowns. ``trendlinien_werte`` traegt den
    Checkbox-Zustand ueber ein verstecktes Begleitfeld (siehe Docstring von
    :data:`TrendlinienWerte`).
    """
    standardwerte = {"ab_jahr": str(_standard_anzeige_ab_jahr())}
    ergebnis = _bereit_oder_ladeseite(
        request,
        seite="schulungen",
        bereit=_anmeldungsverlauf_cache.bereit,
        anstossen=_anmeldungsverlauf_cache.anstossen,
        fortschritt=_anmeldungsverlauf_cache.fortschritt,
        fehler=_anmeldungsverlauf_cache.fehler,
        standardwerte=standardwerte,
    )
    if isinstance(ergebnis, HTMLResponse):
        return ergebnis
    verlauf = ergebnis

    jahr = ab_jahr if ab_jahr is not None else _standard_anzeige_ab_jahr()
    verlauf_ab_jahr = verlauf.ab_jahr(jahr)

    monate = verlauf_ab_jahr.monate
    monatsbeschriftungen = [tabellen.monatsbeschriftung(monat) for monat in monate]
    kategorien: Kategorisierung = kategorien_automatisch()

    trendlinien = "an" in trendlinien_werte
    reihen = _anmeldungsreihen(
        verlauf_ab_jahr,
        kategorien,
        kategorie_filter=kategorie_filter,
        schulung_filter=schulung_filter,
        format_filter=format_filter,
        dauer_filter=dauer_filter,
    )
    filter_abweichend = (
        list(kategorie_filter) != [ALLE_KATEGORIEN]
        or list(schulung_filter) != [ALLE_SCHULUNGEN]
        or list(format_filter) != [ALLE]
        or list(dauer_filter) != [ALLE]
        or not trendlinien
    )

    gliederung = verlauf_ab_jahr.gliederung_je_kategorie(kategorien)
    kategorie_knoten = [
        _kategorie_knoten(kategorie, kinder) for kategorie, kinder in gliederung.items()
    ]
    kategorie_zeilen = [
        zeile
        for i, knoten in enumerate(kategorie_knoten)
        for zeile in _knoten_flach(knoten, monate, pfad=str(i))
    ]
    gesamt_monate = _monate_summieren(kategorie_knoten)
    gesamt_werte = [gesamt_monate.get(monat, 0) for monat in monate]

    return _antwort(
        request,
        seite="schulungen",
        name="schulungen.html",
        stichtag=date.today(),
        standardwerte=standardwerte,
        ab_jahr=jahr,
        ab_jahr_optionen=tuple(range(STANDARD_AB_JAHR, date.today().year + 1)),
        anmeldungsverlauf=_figur_html(
            diagramme.anmeldungsverlauf_reihen(reihen, monate, mit_trend=trendlinien),
            mit_plotlyjs=True,
        ),
        kategorie_filter=kategorie_filter,
        kategorie_optionen=[
            ALLE_KATEGORIEN,
            *sorted([*kategorien, KATEGORIE_SONSTIGE], key=str.lower),
        ],
        schulung_filter=schulung_filter,
        schulung_optionen=_schulung_optionen(
            verlauf_ab_jahr, kategorien, kategorie_filter=kategorie_filter
        ),
        format_filter=format_filter,
        format_optionen=[ALLE, *sorted(verlauf_ab_jahr.formate, key=str.lower)],
        dauer_filter=dauer_filter,
        dauer_optionen=[ALLE, *sorted(verlauf_ab_jahr.dauern, key=str.lower)],
        trendlinien=trendlinien,
        filter_abweichend=filter_abweichend,
        filter_zuruecksetzen_query=_anfrage_query(
            request,
            standardwerte,
            ohne=frozenset(
                {
                    "kategorie_filter",
                    "schulung_filter",
                    "format_filter",
                    "dauer_filter",
                    "trendlinien_werte",
                }
            ),
        ),
        monatsbeschriftungen=monatsbeschriftungen,
        kategorie_zeilen=kategorie_zeilen,
        gesamt_werte=gesamt_werte,
        gesamt_summe=sum(gesamt_werte),
    )


# Deckt sich mit MONATSNAMEN in notebooks/04_kurzarbeit.ipynb. Bewusst hier dupliziert
# statt aus darstellung.umsatzhistorie importiert - der Baustein Kurzarbeit bleibt
# unabhaengig von pandas/darstellung.
_KURZARBEIT_MONATSNAMEN = (
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
)  # fmt: skip


def _kurzarbeit_status_text(bewertung: Kurzarbeitsbewertung) -> str:
    if bewertung.vorbereitet is None:
        return "keine Auswertung möglich"
    return "Voraussetzung erfüllt" if bewertung.vorbereitet else "Voraussetzung nicht erfüllt"


def _kurzarbeit_status_klasse(bewertung: Kurzarbeitsbewertung) -> str:
    """CSS-Klasse fuer die Statusanzeige - dieselbe (nicht wertende) Farbfamilie wie
    KURZARBEIT_SCHWELLE_ERREICHT/KURZARBEIT_SCHWELLE_NICHT_ERREICHT in der Grafik
    (siehe .status-erfuellt/.status-nicht-erfuellt in basis.html), damit Text und
    Grafik dieselbe Unterscheidung erfuellt/nicht erfuellt zeigen - bewusst kein
    Gruen/Rot, weil "erfuellt" hier kein gutes Ergebnis ist (siehe
    darstellung/gestaltung.py). Leer ohne Quote - "keine Auswertung
    möglich" ist ein dritter, unentschiedener Zustand und soll nicht wie "nicht
    erfuellt" gefaerbt erscheinen."""
    if bewertung.vorbereitet is None:
        return ""
    return "status-erfuellt" if bewertung.vorbereitet else "status-nicht-erfuellt"


def _kurzarbeit_quote_text(bewertung: Kurzarbeitsbewertung) -> str:
    return f"{bewertung.quote:.1%}" if bewertung.quote is not None else "n/a"


@app.get("/kurzarbeit", response_class=HTMLResponse)
async def kurzarbeit(
    request: Request,
    anzahl_monate: KurzarbeitMonate = STANDARD_KURZARBEIT_MONATE,
    anteil_interne_arbeit_prozent: AnteilInterneArbeitProzent = (
        STANDARD_ANTEIL_INTERNE_ARBEIT_PROZENT
    ),
    ueberstunden_stunden: UeberstundenStunden = STANDARD_UEBERSTUNDEN_STUNDEN,
    quote_organisation_prozent: QuoteOrganisationProzent = STANDARD_QUOTE_ORGANISATION_PROZENT,
) -> HTMLResponse:
    """Deckt sich mit notebooks/04_kurzarbeit.ipynb: die Kurzarbeitsbereitschaft je Monat.

    Die drei Schwellenwerte sind hier ueber Regler waehlbar -
    reine In-Memory-Neubewertung derselben geladenen Rohdaten (siehe Klassendocstring
    von :class:`~.cache.KurzarbeitCache`), kein erneuter Clockodo-Abruf. Vollstaendig
    unabhaengig von :class:`DashboardCache` - kein Bezug zur Umsatzprognose.
    Zeigt ausschliesslich Aggregatzahlen, keine Einzelwerte je Person.

    Liefert 404, solange der Baustein per :data:`_KURZARBEIT_AKTIV` ausgeschaltet ist -
    dieselbe Bedingung, die auch den Navigationslink verbirgt (siehe ``basis.html``)
    und das Vorladen unten unterlaesst.
    """
    if not _KURZARBEIT_AKTIV:
        raise HTTPException(status_code=404)
    monate_zahl = int(anzahl_monate)
    schwellenwerte = Schwellenwerte(
        anteil_interne_arbeit=anteil_interne_arbeit_prozent / 100,
        ueberstunden_stunden=float(ueberstunden_stunden),
        quote_organisation=quote_organisation_prozent / 100,
    )
    ergebnis = _bereit_oder_ladeseite(
        request,
        seite="kurzarbeit",
        bereit=partial(
            _kurzarbeit_cache.bereit, anzahl_monate=monate_zahl, schwellenwerte=schwellenwerte
        ),
        anstossen=_kurzarbeit_cache.anstossen,
        fortschritt=_kurzarbeit_cache.fortschritt,
        fehler=_kurzarbeit_cache.fehler,
        standardwerte=_STANDARDWERTE_KURZARBEIT,
    )
    if isinstance(ergebnis, HTMLResponse):
        return ergebnis
    ergebnisse = ergebnis

    monate = sorted(ergebnisse)
    zeilen = [
        {
            "bezeichnung": f"{_KURZARBEIT_MONATSNAMEN[monat[1] - 1]} {monat[0]}",
            "status": _kurzarbeit_status_text(ergebnisse[monat]),
            "status_klasse": _kurzarbeit_status_klasse(ergebnisse[monat]),
            "quote": _kurzarbeit_quote_text(ergebnisse[monat]),
            "bewertung": ergebnisse[monat],
        }
        for monat in monate
    ]
    # Bleibt aufgeklappt, sobald einer der Regler vom Standard abweicht - sonst
    # verschwaende die eigene Auswahl nach jedem Neuladen der Seite (onchange).
    schwellenwerte_abweichend = (
        anteil_interne_arbeit_prozent != STANDARD_ANTEIL_INTERNE_ARBEIT_PROZENT
        or ueberstunden_stunden != STANDARD_UEBERSTUNDEN_STUNDEN
        or quote_organisation_prozent != STANDARD_QUOTE_ORGANISATION_PROZENT
    )

    return _antwort(
        request,
        seite="kurzarbeit",
        name="kurzarbeit.html",
        stichtag=date.today(),
        standardwerte=_STANDARDWERTE_KURZARBEIT,
        anzahl_monate=anzahl_monate,
        anzahl_monate_optionen=KURZARBEIT_MONATE_OPTIONEN,
        anzahl_monate_beschriftungen=KURZARBEIT_MONATE_BESCHRIFTUNGEN,
        anteil_interne_arbeit_prozent=anteil_interne_arbeit_prozent,
        ueberstunden_stunden=ueberstunden_stunden,
        quote_organisation_prozent=quote_organisation_prozent,
        schwellenwerte_abweichend=schwellenwerte_abweichend,
        schwellenwerte_zuruecksetzen_query=_anfrage_query(
            request,
            _STANDARDWERTE_KURZARBEIT,
            ohne=frozenset(
                {
                    "anteil_interne_arbeit_prozent",
                    "ueberstunden_stunden",
                    "quote_organisation_prozent",
                }
            ),
        ),
        zeilen=zeilen,
        kurzarbeit_grafik=_figur_html(diagramme.kurzarbeit_grafik(ergebnisse), mit_plotlyjs=True),
    )
