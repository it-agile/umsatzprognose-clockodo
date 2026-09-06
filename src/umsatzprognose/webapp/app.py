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

    uv run uvicorn umsatzprognose.webapp.app:app --reload

``--reload`` beobachtet dabei standardmaessig das gesamte Arbeitsverzeichnis,
einschliesslich z. B. ``.tox/`` - laeuft dort parallel ``uvx tox``, startet das
staendig neu. Fuer aktive Entwicklung an ``webapp/`` deshalb besser
``--reload-dir src/umsatzprognose/webapp``; wer nur die Seiten ansehen will, laesst
``--reload`` ganz weg.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal, get_args

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import pandas as pd
    import plotly.graph_objects as go

from contextlib import asynccontextmanager

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from umsatzprognose.darstellung import diagramme

from .cache import AnmeldungsverlaufCache, DashboardCache

# Deckt sich mit derselben Notebook-Zelle ("projekte_ohne_auftragsvolumen" in
# notebooks/01_dashboard.ipynb).
RESTVOLUMEN_TOP = 20

# Deckt sich mit "KATEGORIEN" in notebooks/03_schulungsanmeldungen.ipynb - dieselbe,
# von Hand gepflegte Zuordnung Schulungstyp -> Kategorie fuer denselben Verlauf.
KATEGORIEN: dict[str, list[str]] = {
    "Scrum": [
        "A-CSD",
        "A-CSM",
        "A-CSPO",
        "CSD",
        "CSM 2-tägig",
        "CSM 3-tägig",
        "CSP-PO",
        "CSP-SM",
        "CSPO 2-tägig",
        "CSPO 3-tägig",
        "CAL 2",
        "CAL ETO",
    ],
    "Kanban": [
        "KCP",
        "KMM",
        "KSD",
        "KSI",
        "KSI 2-tägig",
        "KSI 3-tägig",
        "SBK",
    ],
}

# Feste, kuratierte Optionen statt eines freien Zahlenbereichs - siehe Moduldocstring.
# "alle" bei den historischen Monaten steht fuer die gesamte geladene Historie (siehe
# Dashboard.gewinn_verlust_monatlich). Die Literal-Typen tragen die Optionen nur
# einmal; PROGNOSE_MONATE_OPTIONEN/HISTORISCHE_MONATE_OPTIONEN lesen sie fuers
# Dropdown zurueck, statt sie ein zweites Mal aufzuschreiben.
_HorizontMonateWert = Literal["3", "4", "5", "6"]
_GewinnVerlustMonateWert = Literal["3", "6", "12", "24", "alle"]
HorizontMonate = Annotated[_HorizontMonateWert, Query()]
GewinnVerlustMonate = Annotated[_GewinnVerlustMonateWert, Query()]
PROGNOSE_MONATE_OPTIONEN = get_args(_HorizontMonateWert)
HISTORISCHE_MONATE_OPTIONEN = get_args(_GewinnVerlustMonateWert)

STANDARD_HORIZONT_MONATE: _HorizontMonateWert = "3"
STANDARD_AUSLASTUNG_MONATE = 12
STANDARD_GEWINN_VERLUST_MONATE: _GewinnVerlustMonateWert = "12"
STANDARD_AB_JAHR = 2022

AbJahr = Annotated[int, Query(ge=STANDARD_AB_JAHR, le=date.today().year)]
AB_JAHR_OPTIONEN = tuple(range(STANDARD_AB_JAHR, date.today().year + 1))

_dashboard_cache = DashboardCache()
_anmeldungsverlauf_cache = AnmeldungsverlaufCache(ab_jahr=STANDARD_AB_JAHR)
_templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


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
    yield


app = FastAPI(title="Umsatzprognose", lifespan=_vorladen)


def _figur_html(figur: go.Figure, *, mit_plotlyjs: bool) -> str:
    return figur.to_html(full_html=False, include_plotlyjs="cdn" if mit_plotlyjs else False)


def _tabelle_html(tabelle: pd.DataFrame) -> str:
    return tabelle.to_html(index=False, border=0, classes="tabelle", na_rep="")


def _anfrage_query(request: Request) -> str:
    query = str(request.url.query)
    return f"?{query}" if query else ""


def _antwort(
    request: Request, *, seite: str, name: str, stichtag: date | None, **kontext
) -> HTMLResponse:
    return _templates.TemplateResponse(
        request=request,
        name=name,
        context={
            "aktive_seite": seite,
            "stichtag": stichtag,
            "anfrage_query": _anfrage_query(request),
            **kontext,
        },
    )


def _ladeseite(request: Request, *, seite: str) -> HTMLResponse:
    """Kurze Zwischenseite, waehrend :mod:`.cache` im Hintergrund laedt - siehe Moduldocstring."""
    return _antwort(request, seite=seite, name="laedt.html", stichtag=None)


@app.get("/", response_class=HTMLResponse)
async def uebersicht(
    request: Request,
    horizont_monate: HorizontMonate = STANDARD_HORIZONT_MONATE,
    gewinn_verlust_monate: GewinnVerlustMonate = STANDARD_GEWINN_VERLUST_MONATE,
) -> HTMLResponse:
    """Deckt sich mit notebooks/00_datencheck.ipynb: Gewinn/Verlust und Umsatzrendite."""
    horizont_zahl = int(horizont_monate)
    dashboard = _dashboard_cache.bereit(
        horizont_monate=horizont_zahl, auslastung_monate=STANDARD_AUSLASTUNG_MONATE
    )
    if dashboard is None:
        _dashboard_cache.anstossen(
            horizont_monate=horizont_zahl, auslastung_monate=STANDARD_AUSLASTUNG_MONATE
        )
        return _ladeseite(request, seite="start")

    gewinn_verlust_zahl = None if gewinn_verlust_monate == "alle" else int(gewinn_verlust_monate)
    return _antwort(
        request,
        seite="start",
        name="datencheck.html",
        stichtag=dashboard.stichtag,
        horizont_monate=horizont_monate,
        horizont_optionen=PROGNOSE_MONATE_OPTIONEN,
        gewinn_verlust_monate=gewinn_verlust_monate,
        gewinn_verlust_optionen=HISTORISCHE_MONATE_OPTIONEN,
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
    request: Request, horizont_monate: HorizontMonate = STANDARD_HORIZONT_MONATE
) -> HTMLResponse:
    """Deckt sich mit notebooks/01_dashboard.ipynb: Umsatzverlauf und offenes Volumen."""
    horizont_zahl = int(horizont_monate)
    dashboard = _dashboard_cache.bereit(
        horizont_monate=horizont_zahl, auslastung_monate=STANDARD_AUSLASTUNG_MONATE
    )
    if dashboard is None:
        _dashboard_cache.anstossen(
            horizont_monate=horizont_zahl, auslastung_monate=STANDARD_AUSLASTUNG_MONATE
        )
        return _ladeseite(request, seite="dashboard")

    return _antwort(
        request,
        seite="dashboard",
        name="dashboard.html",
        stichtag=dashboard.stichtag,
        horizont_monate=horizont_monate,
        horizont_optionen=PROGNOSE_MONATE_OPTIONEN,
        umsatzverlauf=_figur_html(dashboard.umsatzverlauf(), mit_plotlyjs=True),
        umsatztabelle=_tabelle_html(dashboard.umsatztabelle()),
        restvolumen_je_projekt=_figur_html(
            dashboard.restvolumen_je_projekt(top=RESTVOLUMEN_TOP), mit_plotlyjs=False
        ),
    )


@app.get("/schulungen", response_class=HTMLResponse)
async def schulungen(request: Request, ab_jahr: AbJahr = STANDARD_AB_JAHR) -> HTMLResponse:
    """Deckt sich mit notebooks/03_schulungsanmeldungen.ipynb: der Anmeldungsverlauf.

    ``ab_jahr`` filtert den einen geladenen Anmeldungsverlauf nur noch in-memory
    (siehe :class:`~umsatzprognose.webapp.cache.AnmeldungsverlaufCache`) - ein
    engerer Beginn zeigt deshalb sofort ein anderes Ergebnis, ohne neu zu laden.
    """
    verlauf = _anmeldungsverlauf_cache.bereit()
    if verlauf is None:
        _anmeldungsverlauf_cache.anstossen()
        return _ladeseite(request, seite="schulungen")

    verlauf_ab_jahr = verlauf.ab_jahr(ab_jahr)
    return _antwort(
        request,
        seite="schulungen",
        name="schulungen.html",
        stichtag=date.today(),
        ab_jahr=ab_jahr,
        ab_jahr_optionen=AB_JAHR_OPTIONEN,
        anmeldungsverlauf=_figur_html(
            diagramme.anmeldungsverlauf(verlauf_ab_jahr, KATEGORIEN), mit_plotlyjs=True
        ),
    )
