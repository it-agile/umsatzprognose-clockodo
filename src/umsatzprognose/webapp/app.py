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
  die zugehoerige Monatstabelle, offenes Auftragsvolumen je Projekt, dazu zusaetzlich
  der Anteil fakturierbarer Arbeit je Monat
  (:meth:`Dashboard.anteil_fakturierbarer_arbeit`, reine Vergangenheitsbetrachtung)
  samt Verteilung ueber einzelne Personen-Monate
  (:meth:`Dashboard.anteil_fakturierbarer_arbeit_verteilung`) und ein Dropdown
  (:data:`InterneArbeitModus`), das zwischen drei Simulationsverteilungen fuer diesen
  Anteil waehlen laesst: "Pauschal" (Standard, ein fester Wert, vorbelegt mit dem
  historischen Durchschnitt), "Weibull" und "Gauss" (parametrisch, mit aus der Historie
  per Momentenmethode vorbelegten Parametern, siehe :func:`_interne_arbeit_regler_werte`).
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
:meth:`Dashboard.laden_async` selbst ist dagegen **kein** URL-Parameter: obwohl
``/dashboard`` inzwischen etwas zeigt, das von den geladenen Auslastungsmonaten
abhaengt (Anteil fakturierbarer Arbeit, siehe oben), genuegt eine feste
Standardkombination (:data:`STANDARD_AUSLASTUNG_MONATE`) - ein weiteres Dropdown nur
fuer die Fensterbreite dieser einen zusaetzlichen Ansicht waere unverhaeltnismaessig.

Jeder Parameter ist auf eine feste, kuratierte Auswahl beschraenkt statt eines freien
Zahlenbereichs (via ``typing.Literal``, siehe :data:`HorizontMonate` &co.) - das ist
zugleich die Dropdown-Optionsliste (``typing.get_args(...)``) und verhindert einen
unbeschraenkt wachsenden Cache (siehe :mod:`.cache`) durch beliebig viele angefragte
Kombinationen. ``laeufe`` (Anzahl Monte-Carlo-Laeufe, Standard :data:`STANDARD_LAEUFE`)
ist die eine Ausnahme davon: ein freier Schieberegler (1 bis 1.000.000) statt einer
kuratierten Auswahl, weil hier ein kontinuierlicher Kompromiss zwischen Genauigkeit und
Rechenzeit gefragt ist. ``laeufe`` ist deshalb, anders als ``horizont_monate``, auch
kein Teil des ``DashboardCache``-Schluessels (siehe :func:`_simuliertes_dashboard` fuer
die transiente Neusimulation bei abweichendem Wert). In der Weboberflaeche steht
``laeufe`` zusammen mit ``horizont_monate`` im Abschnitt "Simulations-Parameter"
(siehe :func:`_interne_arbeit_regler_werte` und
``_regler.html:interne_arbeit_regler_abschnitt``), weil beide Parameter der Simulation
sind, nicht nur der Anteil fakturierbarer Arbeit.

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

import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal, get_args
from urllib.parse import urlencode

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Mapping
    from datetime import date

    import pandas as pd
    import plotly.graph_objects as go

    from umsatzprognose.domaene import (
        Anmeldungsverlauf,
        FakturierbareArbeitZiehung,
        Kurzarbeitsbewertung,
    )
    from umsatzprognose.domaene.anmeldung import Kategorisierung
    from umsatzprognose.util import Monat

from collections.abc import Sequence
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from functools import partial

import plotly
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from umsatzprognose.clockodo import kurzarbeit_aktiv
from umsatzprognose.darstellung import Dashboard, diagramme
from umsatzprognose.domaene import (
    Anmeldungsknoten,
    GaussFakturierbareArbeit,
    Schwellenwerte,
    WeibullFakturierbareArbeit,
)
from umsatzprognose.domaene.umsatzhistorie import MONATSNAMEN
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

# Anzahl Monte-Carlo-Laeufe je Simulation (siehe Dashboard.simuliere()) - anders als
# horizont_monate & Co. keine kuratierte Auswahl, sondern ein freier Schieberegler
# (1 bis 1.000.000): hier ist ein kontinuierlicher Kompromiss zwischen Genauigkeit und
# Rechenzeit gefragt, keine fachlich diskrete Auswahl. Steht wie horizont_monate im
# Abschnitt "Simulations-Parameter" auf / und /dashboard (siehe
# _regler.html: interne_arbeit_regler_abschnitt()), weil beide Parameter der
# Simulation sind. Anders als horizont_monate ist laeufe aber kein Teil des
# DashboardCache-Schluessels (siehe .cache.DashboardCache) - ein abweichender Wert
# loest stattdessen dieselbe transiente Neusimulation aus wie anteil_fakturierbar/
# interne_arbeit_ziehung (siehe _simuliertes_dashboard()).
Laeufe = Annotated[int, Query(ge=1, le=1_000_000)]
STANDARD_LAEUFE = 10_000

AbJahr = Annotated[int | None, Query(ge=STANDARD_AB_JAHR)]

RestvolumenTop = Annotated[int, Query(ge=1)]

# Freitext-Parameter fuer die beiden unten eingeklappten Konfigurationsabschnitte -
# leer bleibt ohne Wirkung (siehe _verbrauchsplan_aus_text()/_ohne_budget_filter_aus_text()).
Verbrauchsplan = Annotated[str, Query()]
OhneBudgetFilter = Annotated[str, Query()]

# Drei Simulationsverteilungen fuer den Anteil fakturierbarer Arbeit, waehlbar ueber
# ein Dropdown statt eines einzelnen Reglers: "pauschal" (Standard, ein fester Wert
# ueber alle Laeufe gleich, per Regler einstellbar - siehe anteil_fakturierbar_prozent
# unten), "weibull" und "gauss" (parametrische Alternativen, siehe domaene.simulation.
# WeibullFakturierbareArbeit/GaussFakturierbareArbeit) - deren Parameterfelder werden
# nur gezeigt, wenn der jeweilige Modus gewaehlt ist (siehe
# _interne_arbeit_ziehung()/dashboard.html). Anders als bei den uebrigen Dropdowns
# (HorizontMonate & Co.) hat dieses einen festen Standardwert und steht deshalb in
# _STANDARDWERTE_START/_STANDARDWERTE_DASHBOARD.
InterneArbeitModusWert = Literal["pauschal", "weibull", "gauss"]
InterneArbeitModus = Annotated[InterneArbeitModusWert, Query()]
STANDARD_INTERNE_ARBEIT_MODUS: InterneArbeitModusWert = "pauschal"
INTERNE_ARBEIT_MODUS_OPTIONEN = get_args(InterneArbeitModusWert)
INTERNE_ARBEIT_MODUS_BESCHRIFTUNGEN: dict[InterneArbeitModusWert, str] = {
    "pauschal": "Pauschal",
    "weibull": "Weibull-Verteilung",
    "gauss": "Gauss-Verteilung",
}

# Modus "Pauschal": ``None`` (kein Query-Parameter gesetzt) steht fuer "noch nicht
# uebersteuert" - der tatsaechlich verwendete Wert ist dann der historische
# Durchschnitt (siehe _interne_arbeit_ziehung()), kein fester Standardwert wie bei den
# uebrigen Reglern.
AnteilFakturierbarProzent = Annotated[int | None, Query(ge=0, le=100)]

# Modus "Weibull"/"Gauss": dieselbe ``None``-Konvention wie oben - der tatsaechlich
# verwendete Wert ist dann der aus der historischen Verteilung per Momentenmethode
# abgeleitete Vorschlag (siehe _interne_arbeit_regler_werte()).
# Formparameter (k) ist ein dimensionsloser Formfaktor ohne Prozent-Interpretation und
# bleibt deshalb eine reine Fliesskommazahl. Skalenparameter (λ) und Mittelwert (μ)
# leben dagegen in derselben Werte-Domaene wie der Anteil fakturierbarer Arbeit selbst
# (0.0 bis 1.0, bei Skalenparameter je nach Formparameter auch etwas darueber) - als
# Prozentzahl deutlich leichter einzuschaetzen als eine Nachkommazahl, deshalb
# ``*_prozent``-Query-Parameter; die Umrechnung auf den fraktionalen Fachobjekt-Wert
# passiert ausschliesslich in _interne_arbeit_regler_werte(). Standardabweichung (σ)
# bleibt dagegen eine reine Fliesskommazahl (kein ``_prozent``-Parameter): anders als
# ein Anteilswert ist eine Streuung keine intuitiv in Prozent gedachte Groesse.
# Formparameter/Skalenparameter/Standardabweichung sind als Skalen einer Verteilung nie
# negativ; der Mittelwert dagegen schon (0 % ist kein Extremwert). Obere Grenzen sind
# grosszuegig gewaehlte Regler-Bereiche (siehe _regler.html), keine fachliche
# Einschraenkung - ein tatsaechlich ausserhalb liegender Momentenschaetzer wird beim
# Rendern auf den Regler-Bereich gekappt.
InterneArbeitWeibullFormparameter = Annotated[float | None, Query(gt=0)]
InterneArbeitWeibullSkalenparameterProzent = Annotated[float | None, Query(ge=0)]
InterneArbeitGaussMittelwertProzent = Annotated[float | None, Query(ge=0, le=100)]
InterneArbeitGaussStandardabweichung = Annotated[float | None, Query(ge=0, le=0.5)]

# Der Ausreisser-Bereich der Verteilungsgrafik (Dashboard.
# anteil_fakturierbarer_arbeit_verteilung()) als ein Doppel-Schieberegler mit zwei
# Boeppeln (siehe _regler.html: doppel_regler()/basis.html:
# doppelReglerAktualisieren()) - technisch weiterhin zwei unabhaengige Query-Parameter,
# rein darstellend wie restvolumen_top/ohne_budget_filter (siehe unten), kein Teil des
# Cache-Schluessels. le=99/ge=1 statt le=100/ge=0 auf der jeweils anderen Seite: ein
# Bereich braucht mindestens einen Prozentpunkt Breite (siehe die Absicherung in
# dashboard_seite()).
InterneArbeitVerteilungMinProzent = Annotated[int, Query(ge=0, le=99)]
InterneArbeitVerteilungMaxProzent = Annotated[int, Query(ge=1, le=100)]
STANDARD_INTERNE_ARBEIT_VERTEILUNG_MIN_PROZENT = 0
STANDARD_INTERNE_ARBEIT_VERTEILUNG_MAX_PROZENT = 100

# Die drei unabhaengigen Filter-Dropdowns (Mehrfachauswahl) fuer den Anmeldungsverlauf
# auf /schulungen (siehe _anmeldungsreihen()) - anders als HorizontMonate & Co. keine
# Annotated[Literal[...]], weil ihre gueltigen Werte von den geladenen Daten bzw. der
# .env-Konfiguration abhaengen, nicht von einer festen, im Code kuratierten Auswahl.
# jahr_filter gehoert thematisch dazu, wirkt aber (anders als die uebrigen drei sowie
# der fruehere, inzwischen entfernte Kategorie-Filter) nur auf das Diagramm, nicht auf
# die Schulungsdetails-Tabelle darunter - siehe Route.
SchulungFilter = Annotated[Sequence[str], Query()]
FormatFilter = Annotated[Sequence[str], Query()]
DauerFilter = Annotated[Sequence[str], Query()]
JahrFilter = Annotated[Sequence[str], Query()]
# Checkbox-Wert per verstecktem Begleitfeld (siehe schulungen.html/dashboard.html): ein
# einzelnes HTML-Kontrollkaestchen kann seinen "aus"-Zustand nicht selbst senden, ein
# Begleitfeld mit demselben Namen und Wert "aus" tut das immer, das Kontrollkaestchen
# selbst nur zusaetzlich mit Wert "an", wenn angehakt. Wiederverwendet fuer den
# Trendlinien-Regler auf /dashboard (Anteil interner Arbeit), nicht nur /schulungen.
TrendlinienWerte = Annotated[Sequence[str], Query()]

# Umschalter im Anmeldungsverlauf-Diagramm auf /schulungen, nur angezeigt, wenn der
# ausgewaehlte Zeitraum (nach jahr_filter) mehr als ein Jahr umfasst: "zeitverlauf" der
# bisherige durchgehende Zeitraum (diagramme.anmeldungsverlauf_reihen),
# "jahresvergleich" stattdessen eine gemeinsame Januar-Dezember-Achse mit einer Farbe
# je Jahr (diagramme.anmeldungsverlauf_jahresvergleich), wie beim Kalenderjahres-
# vergleich des Umsatzes. Fester Standardwert wie InterneArbeitModus oben, deshalb
# eine kuratierte Annotated[Literal[...]] statt eines freien Werts.
AnsichtWert = Literal["zeitverlauf", "jahresvergleich"]
Ansicht = Annotated[AnsichtWert, Query()]
STANDARD_ANSICHT: AnsichtWert = "zeitverlauf"
ANSICHT_OPTIONEN = get_args(AnsichtWert)
ANSICHT_BESCHRIFTUNGEN: dict[AnsichtWert, str] = {
    "zeitverlauf": "Zeitverlauf",
    "jahresvergleich": "Jahresvergleich",
}

ALLE_SCHULUNGEN = "Alle Schulungen"
ALLE_JAHRE = "Alle Jahre"
ALLE = "Alle"
# Verstecktes Begleitfeld je Filter-Dropdown (siehe schulungen.html) - ohne dieses
# Sentinel-Feld verschwindet ein Mehrfachauswahl-Feld beim Abwaehlen aller
# Kontrollkaestchen komplett aus dem abgeschickten Formular (anders als beim einzelnen
# Trendlinien-Kontrollkaestchen gibt es hier kein festes "aus", das dieselbe Rolle
# uebernehmen koennte), FastAPI faellt dann auf den Query-Default (z. B.
# ``(ALLE_SCHULUNGEN,)``) zurueck - die Auswahl "vergisst" sich selbst und laesst sich
# nicht auf leer stellen. Das Sentinel-Feld wird in _anmeldungsreihen()/der Route
# sofort wieder herausgefiltert.
KEINE_AUSWAHL = "__keine_auswahl__"

# Je Seite die Parameter-Standardwerte (als String, wie sie im Query-String stehen) -
# _anfrage_query() blendet damit auf ihren Standard stehende Parameter aus
# Navigations- und Zuruecksetzen-Links aus, damit die URL beim Seitenwechsel schlank
# bleibt statt unveraendert mitgeschleppter Standardwerte (``ab_jahr`` auf
# /schulungen fehlt hier, weil sein Standard vom aktuellen Datum abhaengt - siehe
# _standard_anzeige_ab_jahr() und die Route selbst).
_STANDARDWERTE_START: dict[str, str] = {
    "horizont_monate": STANDARD_HORIZONT_MONATE,
    "laeufe": str(STANDARD_LAEUFE),
    "gewinn_verlust_monate": STANDARD_GEWINN_VERLUST_MONATE,
    "verbrauchsplan": "",
    "interne_arbeit_modus": STANDARD_INTERNE_ARBEIT_MODUS,
}
_STANDARDWERTE_DASHBOARD: dict[str, str] = {
    "horizont_monate": STANDARD_HORIZONT_MONATE,
    "laeufe": str(STANDARD_LAEUFE),
    "restvolumen_top": str(STANDARD_RESTVOLUMEN_TOP),
    "verbrauchsplan": "",
    "ohne_budget_filter": "",
    "interne_arbeit_modus": STANDARD_INTERNE_ARBEIT_MODUS,
}

# Je Modus die eigenen Parameter - Grundlage sowohl des jeweiligen "Parameter auf
# Historie zuruecksetzen"-Knopfs (setzt nur diese Parameter zurueck, laesst den Modus
# unveraendert) als auch (vereinigt) des uebergreifenden "Zurueck zu 'Pauschal'"-Knopfs
# (setzt zusaetzlich den Modus selbst zurueck) - auf beiden Seiten (``/``/``/dashboard``)
# gleich, deshalb hier gemeinsam definiert statt an jeder Route wiederholt.
_INTERNE_ARBEIT_PAUSCHAL_PARAMETER = frozenset({"anteil_fakturierbar_prozent"})
_INTERNE_ARBEIT_WEIBULL_PARAMETER = frozenset(
    {"interne_arbeit_weibull_formparameter", "interne_arbeit_weibull_skalenparameter_prozent"},
)
_INTERNE_ARBEIT_GAUSS_PARAMETER = frozenset(
    {"interne_arbeit_gauss_mittelwert_prozent", "interne_arbeit_gauss_standardabweichung"},
)
_INTERNE_ARBEIT_PARAMETER = (
    frozenset({"interne_arbeit_modus"})
    | _INTERNE_ARBEIT_PAUSCHAL_PARAMETER
    | _INTERNE_ARBEIT_WEIBULL_PARAMETER
    | _INTERNE_ARBEIT_GAUSS_PARAMETER
)


def _standard_anzeige_ab_jahr(*, heute: date | None = None) -> int:
    """Ohne explizit gewaehlten ``ab_jahr``-Parameter gezeigtes Jahr.

    Das laufende Jahr, wenn davon schon mindestens
    :data:`STANDARD_ANZEIGE_MINDESTMONAT` Monate vorueber sind, sonst zusaetzlich das
    Vorjahr - eine Standardansicht mit nur ein oder zwei Monaten waere zu duenn fuer
    einen sinnvollen Blick auf den Anmeldungsverlauf. Nie vor :data:`STANDARD_AB_JAHR`,
    weiter zurueck ist ohnehin nichts geladen.
    """
    heute = heute or datetime.datetime.now(tz=datetime.UTC).date()
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
async def _vorladen(_app: FastAPI) -> AsyncIterator[None]:
    """Stoesst das Laden der Standardkombination schon beim Start an, ohne zu warten.

    Nicht blockierend (siehe Moduldocstring) - der Server nimmt sofort Anfragen an;
    treffen die ersten Besuchenden frueher ein, als das Vorladen fertig ist, sehen sie
    schlicht dieselbe "Daten werden geladen"-Seite wie bei jeder anderen noch nicht
    gecachten Kombination auch.
    """
    _dashboard_cache.anstossen(
        horizont_monate=int(STANDARD_HORIZONT_MONATE),
        auslastung_monate=STANDARD_AUSLASTUNG_MONATE,
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
        full_html=False,
        include_plotlyjs="/static/plotly/plotly.min.js" if mit_plotlyjs else False,
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
        with suppress(ValueError):
            werte[name] = (int(jahr_text), int(monat_nr_text))
    return werte


def _ohne_budget_filter_aus_text(text: str) -> list[str]:
    """Ein Ausschluss-Begriff je Zeile fuers Textarea der eingeklappten
    Projektfilter-Sektion (siehe ``Bestand.ohne_budget``) - leere Zeilen werden
    uebersprungen."""
    return [zeile.strip() for zeile in text.splitlines() if zeile.strip()]


@dataclass(frozen=True, slots=True)
class _InterneArbeitAnzeige:
    """Ein vollstaendiger Satz Regler-Anzeigewerte - die Prozentgroessen (alle ausser
    ``weibull_formparameter``/``gauss_standardabweichung``) bereits als Prozent (nicht
    als Fachobjekt-Fraktion 0.0-1.0). Dieselbe Form fuer die aktuell wirksamen Werte
    (:attr:`_InterneArbeitReglerWerte.aktuell`) wie fuer die aus der Historie
    abgeleiteten Vorschlagswerte (:attr:`_InterneArbeitReglerWerte.historisch`), damit
    Templates beide identisch behandeln koennen (siehe interne_arbeit_regler_abschnitt()
    in _regler.html)."""

    pauschal_prozent: int
    weibull_formparameter: float
    weibull_skalenparameter_prozent: float
    gauss_mittelwert_prozent: float
    gauss_standardabweichung: float


@dataclass(frozen=True, slots=True)
class _InterneArbeitReglerWerte:
    """Ergebnis von :func:`_interne_arbeit_regler_werte`."""

    weibull: WeibullFakturierbareArbeit
    gauss: GaussFakturierbareArbeit
    aktuell: _InterneArbeitAnzeige
    historisch: _InterneArbeitAnzeige


def _interne_arbeit_regler_werte(
    dashboard: Dashboard,
    *,
    anteil_fakturierbar_prozent: int | None,
    weibull_formparameter: float | None,
    weibull_skalenparameter_prozent: float | None,
    gauss_mittelwert_prozent: float | None,
    gauss_standardabweichung: float | None,
) -> _InterneArbeitReglerWerte:
    """Loest die drei Regler-Parametersaetze zur Anzeige auf - unabhaengig vom
    gewaehlten Modus alle drei berechnet, damit die jeweils nicht gewaehlten Regler
    beim Umschalten nicht auf 0 zurueckfallen, sondern ihren zuletzt aufgeloesten bzw.
    aus der Historie vorgeschlagenen Wert behalten. ``aktuell.weibull``/``.gauss`` (ueber
    :attr:`_InterneArbeitReglerWerte.weibull`/``.gauss``) sind zugleich die
    tatsaechlich zu verwendende Ziehungsquelle, wenn "Weibull"/"Gauss" gewaehlt ist
    (siehe Aufrufstellen) - fuer "Pauschal" gilt das nicht: siehe dort fuer den eigenen
    Cache-Kurzschluss. ``historisch`` traegt denselben Werte-Satz, aber immer aus der
    Historie abgeleitet, unabhaengig von jeder Uebersteuerung - reine Anzeige (Hilfstext
    "Historischer Vorschlag" neben jedem Regler), keine Eingabe der Simulation.

    Ohne eigene Auswahl vorbelegt aus der historischen Verteilung
    (Momentenmethode, siehe ``WeibullFakturierbareArbeit.aus_stichprobe()``/
    ``GaussFakturierbareArbeit.aus_stichprobe()`` bzw. ``Dashboard.
    durchschnittlicher_anteil_fakturierbarer_arbeit()`` fuer "Pauschal", kaufmaennisch
    auf volle Prozent gerundet, 100 % ohne jede gebuchte Stunde). Mit weniger als zwei
    Beobachtungen laesst sich kein Weibull-Formparameter schaetzen; Standard ist dann
    eine Exponentialverteilung (Formparameter 1.0) um den einen beobachteten Wert bzw.
    0.0 ganz ohne jede Beobachtung.
    """
    werte = dashboard.fakturierbare_arbeit_verteilung().werte
    durchschnitt = dashboard.durchschnittlicher_anteil_fakturierbarer_arbeit()
    start_pauschal_prozent = round(durchschnitt * 100) if durchschnitt is not None else 100
    start_weibull = (
        WeibullFakturierbareArbeit.aus_stichprobe(werte)
        if len(werte) >= 2
        else WeibullFakturierbareArbeit(
            formparameter=1.0,
            skalenparameter=werte[0] if werte else 0.0,
        )
    )
    start_gauss = (
        GaussFakturierbareArbeit.aus_stichprobe(werte)
        if werte
        else GaussFakturierbareArbeit(0.0, 0.0)
    )
    pauschal_prozent = (
        anteil_fakturierbar_prozent
        if anteil_fakturierbar_prozent is not None
        else start_pauschal_prozent
    )
    weibull = WeibullFakturierbareArbeit(
        formparameter=(
            weibull_formparameter
            if weibull_formparameter is not None
            else start_weibull.formparameter
        ),
        skalenparameter=(
            weibull_skalenparameter_prozent / 100
            if weibull_skalenparameter_prozent is not None
            else start_weibull.skalenparameter
        ),
    )
    gauss = GaussFakturierbareArbeit(
        mittelwert=(
            gauss_mittelwert_prozent / 100
            if gauss_mittelwert_prozent is not None
            else start_gauss.mittelwert
        ),
        standardabweichung=(
            gauss_standardabweichung
            if gauss_standardabweichung is not None
            else start_gauss.standardabweichung
        ),
    )
    return _InterneArbeitReglerWerte(
        weibull=weibull,
        gauss=gauss,
        aktuell=_InterneArbeitAnzeige(
            pauschal_prozent=pauschal_prozent,
            weibull_formparameter=weibull.formparameter,
            weibull_skalenparameter_prozent=weibull.skalenparameter * 100,
            gauss_mittelwert_prozent=gauss.mittelwert * 100,
            gauss_standardabweichung=gauss.standardabweichung,
        ),
        historisch=_InterneArbeitAnzeige(
            pauschal_prozent=start_pauschal_prozent,
            weibull_formparameter=start_weibull.formparameter,
            weibull_skalenparameter_prozent=start_weibull.skalenparameter * 100,
            gauss_mittelwert_prozent=start_gauss.mittelwert * 100,
            gauss_standardabweichung=start_gauss.standardabweichung,
        ),
    )


def _interne_arbeit_kontext(
    request: Request,
    dashboard: Dashboard,
    standardwerte: dict[str, str],
    *,
    interne_arbeit_modus: InterneArbeitModus,
    anteil_fakturierbar_prozent: int | None,
    weibull_formparameter: float | None,
    weibull_skalenparameter_prozent: float | None,
    gauss_mittelwert_prozent: float | None,
    gauss_standardabweichung: float | None,
    horizont_monate: HorizontMonate,
    laeufe: int,
) -> tuple[float | None, FakturierbareArbeitZiehung | None, dict[str, object]]:
    """Gemeinsamer Kern von ``uebersicht()``/``dashboard_seite()``: loest anhand von
    ``interne_arbeit_modus`` auf, welcher Anteil fakturierbarer Arbeit tatsaechlich zu
    simulieren ist (siehe :func:`_interne_arbeit_regler_werte`), und liefert dazu
    gleich die zugehoerigen Template-Kwargs fuer den Abschnitt
    "Simulations-Parameter" (``_regler.html``), die auf beiden Seiten identisch
    aufgebaut sind."""
    regler = _interne_arbeit_regler_werte(
        dashboard,
        anteil_fakturierbar_prozent=anteil_fakturierbar_prozent,
        weibull_formparameter=weibull_formparameter,
        weibull_skalenparameter_prozent=weibull_skalenparameter_prozent,
        gauss_mittelwert_prozent=gauss_mittelwert_prozent,
        gauss_standardabweichung=gauss_standardabweichung,
    )
    anteil_fakturierbar: float | None
    ziehung: FakturierbareArbeitZiehung | None
    if interne_arbeit_modus == "weibull":
        anteil_fakturierbar, ziehung = None, regler.weibull
    elif interne_arbeit_modus == "gauss":
        anteil_fakturierbar, ziehung = None, regler.gauss
    else:
        anteil_fakturierbar = (
            anteil_fakturierbar_prozent / 100 if anteil_fakturierbar_prozent is not None else None
        )
        ziehung = None
    kontext: dict[str, object] = {
        "interne_arbeit_modus": interne_arbeit_modus,
        "interne_arbeit_modus_optionen": INTERNE_ARBEIT_MODUS_OPTIONEN,
        "interne_arbeit_modus_beschriftungen": INTERNE_ARBEIT_MODUS_BESCHRIFTUNGEN,
        "interne_arbeit_regler_aktuell": regler.aktuell,
        "interne_arbeit_regler_historisch": regler.historisch,
        "interne_arbeit_abschlag_abweichend": (
            interne_arbeit_modus != STANDARD_INTERNE_ARBEIT_MODUS
            or anteil_fakturierbar_prozent is not None
            or horizont_monate != STANDARD_HORIZONT_MONATE
            or laeufe != STANDARD_LAEUFE
        ),
        "interne_arbeit_abschlag_zuruecksetzen_query": _anfrage_query(
            request, standardwerte, ohne=_INTERNE_ARBEIT_PARAMETER
        ),
        "interne_arbeit_pauschal_zuruecksetzen_query": _anfrage_query(
            request, standardwerte, ohne=_INTERNE_ARBEIT_PAUSCHAL_PARAMETER
        ),
        "interne_arbeit_weibull_zuruecksetzen_query": _anfrage_query(
            request, standardwerte, ohne=_INTERNE_ARBEIT_WEIBULL_PARAMETER
        ),
        "interne_arbeit_gauss_zuruecksetzen_query": _anfrage_query(
            request, standardwerte, ohne=_INTERNE_ARBEIT_GAUSS_PARAMETER
        ),
    }
    return anteil_fakturierbar, ziehung, kontext


async def _simuliertes_dashboard(
    dashboard: Dashboard,
    *,
    verbrauchsplan: str,
    horizont_monate: int,
    laeufe: int,
    anteil_fakturierbar: float | None,
    interne_arbeit_ziehung: FakturierbareArbeitZiehung | None,
) -> Dashboard:
    """Liefert bei gesetztem ``verbrauchsplan``/``laeufe``/``anteil_fakturierbar``/
    ``interne_arbeit_ziehung`` ein **transientes** ``Dashboard`` mit angewendeter
    Uebersteuerung und frischer Simulation, sonst unveraendert das uebergebene.

    ``anteil_fakturierbar``/``interne_arbeit_ziehung``: beide ``None`` (Modus
    "Pauschal" ohne eigene Auswahl) uebernimmt unveraendert das Verhalten des
    gecachten Basis-``Dashboard`` (siehe ``DashboardCache.anstossen`` -
    ``Dashboard.simuliere_async()`` zieht dort ohne eigene Argumente bereits
    standardmaessig den historischen Durchschnitt heran, siehe ``Dashboard.
    simuliere``) - eine Neusimulation ist dafuer nicht noetig. Ein gesetzter
    ``anteil_fakturierbar`` (manueller Pauschalwert) oder ein uebergebenes
    ``interne_arbeit_ziehung``-Objekt (``WeibullFakturierbareArbeit``/
    ``GaussFakturierbareArbeit``, siehe :func:`_interne_arbeit_regler_werte`)
    erzwingt dagegen die gewaehlte Verteilung, die die gecachte Simulation
    ueberschreibt. ``laeufe`` folgt derselben Logik: das gecachte ``Dashboard`` wurde
    immer mit ``STANDARD_LAEUFE`` simuliert (``laeufe`` ist kein Teil des
    ``DashboardCache``-Schluessels, anders als ``horizont_monate`` - siehe
    :data:`Laeufe`), ein davon abweichender Regler-Wert erzwingt deshalb ebenfalls
    eine Neusimulation.

    Absichtlich kein ``dashboard.verbrauchsplan_uebersteuern(...)``/
    ``dashboard.simuliere(...)`` auf dem uebergebenen Objekt: dieses ``Dashboard`` ist
    bei einem Treffer im ``DashboardCache`` **derselbe, geteilte** Stand fuer alle
    Besuchenden (siehe Moduldocstring - keine Benutzertrennung). Eine In-Place-
    Uebersteuerung durch eine einzelne Anfrage wuerde bis zum naechsten TTL-Reload
    allen anderen Besuchenden dieselbe uebersteuerte Prognose zeigen. Stattdessen
    entsteht ein neues ``Dashboard`` mit einem neuen, unveraenderlichen ``Bestand``
    (``mit_verbrauchsplan_uebersteuerungen``) und einer eigenen Neusimulation -
    ``schulungsplan``/``kostenplan``/``auslastung`` werden vom Original uebernommen,
    kein erneuter Abruf. ``simuliere_async()`` statt ``simuliere()``: ein direkter,
    blockierender Aufruf wuerde den einzigen Event-Loop-Thread des Servers fuer die
    Dauer dieser Neusimulation einfrieren - je Anfrage mit gesetztem
    ``verbrauchsplan``/``interne_arbeit_ziehung``, nicht nur beim seltenen Neuladen
    des Caches.
    """
    werte = _verbrauchsplan_aus_text(verbrauchsplan)
    if (
        not werte
        and anteil_fakturierbar is None
        and interne_arbeit_ziehung is None
        and laeufe == STANDARD_LAEUFE
    ):
        return dashboard
    bestand = (
        dashboard.bestand.mit_verbrauchsplan_uebersteuerungen(werte) if werte else dashboard.bestand
    )
    uebersteuert = Dashboard(
        bestand,
        dashboard.schulungsplan,
        dashboard.kostenplan,
        dashboard.auslastung,
    )
    await uebersteuert.simuliere_async(
        monate=horizont_monate,
        laeufe=laeufe,
        anteil_fakturierbar=anteil_fakturierbar,
        fakturierbare_arbeit_ziehung=interne_arbeit_ziehung,
    )
    return uebersteuert


@app.get("/", response_class=HTMLResponse)
async def uebersicht(
    request: Request,
    horizont_monate: HorizontMonate = STANDARD_HORIZONT_MONATE,
    laeufe: Laeufe = STANDARD_LAEUFE,
    gewinn_verlust_monate: GewinnVerlustMonate = STANDARD_GEWINN_VERLUST_MONATE,
    verbrauchsplan: Verbrauchsplan = "",
    interne_arbeit_modus: InterneArbeitModus = STANDARD_INTERNE_ARBEIT_MODUS,
    anteil_fakturierbar_prozent: AnteilFakturierbarProzent = None,
    interne_arbeit_weibull_formparameter: InterneArbeitWeibullFormparameter = None,
    interne_arbeit_weibull_skalenparameter_prozent: (
        InterneArbeitWeibullSkalenparameterProzent
    ) = None,
    interne_arbeit_gauss_mittelwert_prozent: InterneArbeitGaussMittelwertProzent = None,
    interne_arbeit_gauss_standardabweichung: InterneArbeitGaussStandardabweichung = None,
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
    anteil_fakturierbar, ziehung, interne_arbeit_kontext = _interne_arbeit_kontext(
        request,
        ergebnis,
        _STANDARDWERTE_START,
        interne_arbeit_modus=interne_arbeit_modus,
        anteil_fakturierbar_prozent=anteil_fakturierbar_prozent,
        weibull_formparameter=interne_arbeit_weibull_formparameter,
        weibull_skalenparameter_prozent=interne_arbeit_weibull_skalenparameter_prozent,
        gauss_mittelwert_prozent=interne_arbeit_gauss_mittelwert_prozent,
        gauss_standardabweichung=interne_arbeit_gauss_standardabweichung,
        horizont_monate=horizont_monate,
        laeufe=laeufe,
    )
    dashboard = await _simuliertes_dashboard(
        ergebnis,
        verbrauchsplan=verbrauchsplan,
        horizont_monate=horizont_zahl,
        laeufe=laeufe,
        anteil_fakturierbar=anteil_fakturierbar,
        interne_arbeit_ziehung=ziehung,
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
        laeufe=laeufe,
        laeufe_zuruecksetzen_query=_anfrage_query(
            request,
            _STANDARDWERTE_START,
            ohne=frozenset({"laeufe"}),
        ),
        gewinn_verlust_monate=gewinn_verlust_monate,
        gewinn_verlust_optionen=HISTORISCHE_MONATE_OPTIONEN,
        verbrauchsplan=verbrauchsplan,
        verbrauchsplan_abweichend=bool(verbrauchsplan.strip()),
        verbrauchsplan_zuruecksetzen_query=_anfrage_query(
            request,
            _STANDARDWERTE_START,
            ohne=frozenset({"verbrauchsplan"}),
        ),
        **interne_arbeit_kontext,
        gewinn_verlust_monatlich=_figur_html(
            dashboard.gewinn_verlust_monatlich(monate=gewinn_verlust_zahl),
            mit_plotlyjs=True,
        ),
        gewinn_verlust_je_jahr=_figur_html(dashboard.gewinn_verlust_je_jahr(), mit_plotlyjs=False),
        umsatzrendite_kumuliert=_figur_html(
            dashboard.umsatzrendite_kumuliert(),
            mit_plotlyjs=False,
        ),
    )


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_seite(
    request: Request,
    horizont_monate: HorizontMonate = STANDARD_HORIZONT_MONATE,
    laeufe: Laeufe = STANDARD_LAEUFE,
    restvolumen_top: RestvolumenTop = STANDARD_RESTVOLUMEN_TOP,
    verbrauchsplan: Verbrauchsplan = "",
    ohne_budget_filter: OhneBudgetFilter = "",
    interne_arbeit_modus: InterneArbeitModus = STANDARD_INTERNE_ARBEIT_MODUS,
    anteil_fakturierbar_prozent: AnteilFakturierbarProzent = None,
    interne_arbeit_weibull_formparameter: InterneArbeitWeibullFormparameter = None,
    interne_arbeit_weibull_skalenparameter_prozent: (
        InterneArbeitWeibullSkalenparameterProzent
    ) = None,
    interne_arbeit_gauss_mittelwert_prozent: InterneArbeitGaussMittelwertProzent = None,
    interne_arbeit_gauss_standardabweichung: InterneArbeitGaussStandardabweichung = None,
    interne_arbeit_trend_werte: TrendlinienWerte = ("an",),
    interne_arbeit_verteilung_min_prozent: InterneArbeitVerteilungMinProzent = (
        STANDARD_INTERNE_ARBEIT_VERTEILUNG_MIN_PROZENT
    ),
    interne_arbeit_verteilung_max_prozent: InterneArbeitVerteilungMaxProzent = (
        STANDARD_INTERNE_ARBEIT_VERTEILUNG_MAX_PROZENT
    ),
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
    anteil_fakturierbar, ziehung, interne_arbeit_kontext = _interne_arbeit_kontext(
        request,
        ergebnis,
        _STANDARDWERTE_DASHBOARD,
        interne_arbeit_modus=interne_arbeit_modus,
        anteil_fakturierbar_prozent=anteil_fakturierbar_prozent,
        weibull_formparameter=interne_arbeit_weibull_formparameter,
        weibull_skalenparameter_prozent=interne_arbeit_weibull_skalenparameter_prozent,
        gauss_mittelwert_prozent=interne_arbeit_gauss_mittelwert_prozent,
        gauss_standardabweichung=interne_arbeit_gauss_standardabweichung,
        horizont_monate=horizont_monate,
        laeufe=laeufe,
    )
    interne_arbeit_trend = "an" in interne_arbeit_trend_werte
    dashboard = await _simuliertes_dashboard(
        ergebnis,
        verbrauchsplan=verbrauchsplan,
        horizont_monate=horizont_zahl,
        laeufe=laeufe,
        anteil_fakturierbar=anteil_fakturierbar,
        interne_arbeit_ziehung=ziehung,
    )
    restvolumen_top_max = len(dashboard.bestand.ohne_budget())
    # Der Slider traegt max="{{ restvolumen_top_max }}", aber Query(ge=1) allein
    # verhindert nicht, dass ein manuell erhoehter URL-Parameter darueber liegt -
    # sonst zeigt der Slider einen Wert ausserhalb seines eigenen Maximalattributs.
    if restvolumen_top_max:
        restvolumen_top = min(restvolumen_top, restvolumen_top_max)
    # Query(ge=0, le=99)/Query(ge=1, le=100) allein verhindern nicht, dass ein manuell
    # gesetztes Minimum ueber (oder gleichauf mit) dem Maximum liegt - ein Bereich
    # braucht mindestens einen Prozentpunkt Breite (siehe
    # diagramme.anteil_fakturierbarer_arbeit_verteilung()s eigene Validierung).
    interne_arbeit_verteilung_max_prozent = max(
        interne_arbeit_verteilung_max_prozent,
        interne_arbeit_verteilung_min_prozent + 1,
    )

    return _antwort(
        request,
        seite="dashboard",
        name="dashboard.html",
        stichtag=dashboard.stichtag,
        standardwerte=_STANDARDWERTE_DASHBOARD,
        horizont_monate=horizont_monate,
        horizont_optionen=PROGNOSE_MONATE_OPTIONEN,
        laeufe=laeufe,
        laeufe_zuruecksetzen_query=_anfrage_query(
            request,
            _STANDARDWERTE_DASHBOARD,
            ohne=frozenset({"laeufe"}),
        ),
        umsatzverlauf=_figur_html(dashboard.umsatzverlauf(), mit_plotlyjs=True),
        umsatztabelle=_tabelle_html(
            dashboard.umsatztabelle(),
            zusatzklasse="spaltenraster",
            element_id="tabelle-monat",
        ),
        restvolumen_top=restvolumen_top,
        restvolumen_top_max=restvolumen_top_max,
        restvolumen_je_projekt=_figur_html(
            dashboard.restvolumen_je_projekt(top=restvolumen_top),
            mit_plotlyjs=False,
        ),
        verbrauchsplan=verbrauchsplan,
        verbrauchsplan_abweichend=bool(verbrauchsplan.strip()),
        verbrauchsplan_zuruecksetzen_query=_anfrage_query(
            request,
            _STANDARDWERTE_DASHBOARD,
            ohne=frozenset({"verbrauchsplan"}),
        ),
        ohne_budget_filter=ohne_budget_filter,
        ohne_budget_filter_abweichend=bool(ohne_budget_filter.strip()),
        ohne_budget_filter_zuruecksetzen_query=_anfrage_query(
            request,
            _STANDARDWERTE_DASHBOARD,
            ohne=frozenset({"ohne_budget_filter"}),
        ),
        projekte_ohne_budget=_tabelle_html(
            dashboard.projekte_ohne_budget(_ohne_budget_filter_aus_text(ohne_budget_filter)),
        ),
        **interne_arbeit_kontext,
        interne_arbeit_trend=interne_arbeit_trend,
        anteil_fakturierbarer_arbeit=_figur_html(
            dashboard.anteil_fakturierbarer_arbeit(mit_trend=interne_arbeit_trend),
            mit_plotlyjs=False,
        ),
        anteil_fakturierbarer_arbeit_tabelle=_tabelle_html(
            dashboard.anteil_fakturierbarer_arbeit_tabelle(),
        ),
        interne_arbeit_verteilung_min_prozent=interne_arbeit_verteilung_min_prozent,
        interne_arbeit_verteilung_max_prozent=interne_arbeit_verteilung_max_prozent,
        anteil_fakturierbarer_arbeit_verteilung=_figur_html(
            dashboard.anteil_fakturierbarer_arbeit_verteilung(
                minimum=interne_arbeit_verteilung_min_prozent / 100,
                maximum=interne_arbeit_verteilung_max_prozent / 100,
            ),
            mit_plotlyjs=False,
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


def _monatswerte_kombiniert(monate: Mapping[Monat, int]) -> list[int]:
    """Teilnehmerzahl je Kalendermonat (Januar-Dezember-Raster, jahresunabhaengig),
    ueber alle im Knoten vorkommenden Jahre aufsummiert - die Werte der eigenen Zeile
    eines Knotens in ``schulungen.html``, egal ob dessen Daten ein oder mehrere Jahre
    umfassen (siehe :func:`_knoten_flach`)."""
    summen = [0] * 12
    for (_jahr, monatsnummer), wert in monate.items():
        summen[monatsnummer - 1] += wert
    return summen


def _monatswerte_jahr(monate: Mapping[Monat, int], jahr: int) -> list[int]:
    """Teilnehmerzahl je Kalendermonat (Januar-Dezember) eines einzelnen Jahres."""
    return [monate.get((jahr, monatsnummer), 0) for monatsnummer in range(1, 13)]


def _zukuenftige_monate(jahr: int, laufender_monat: Monat) -> list[bool]:
    """Je Kalendermonat (Januar-Dezember), ob dieser Monat eines gegebenen Jahres noch
    nicht abgeschlossen ist (>= ``laufender_monat``) - Grundlage fuer die abgehobene
    Darstellung noch bevorstehender Schulungstermine in ``schulungen.html`` (siehe
    :func:`_knoten_flach`). Diese koennen, anders als bereits vergangene, noch neue
    Anmeldungen bekommen."""
    return [(jahr, monatsnummer) >= laufender_monat for monatsnummer in range(1, 13)]


def _knoten_flach(
    knoten: Anmeldungsknoten,
    *,
    laufender_monat: Monat,
    mehrere_jahre_insgesamt: bool,
    tiefe: int = 0,
    pfad: str = "0",
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

    Die Spalten sind ein festes Januar-Dezember-Raster statt einer mit der Anzahl
    betrachteter Jahre wachsenden Spaltenliste - die eigene Zeile eines Knotens zeigt
    dazu die ueber alle vorkommenden Jahre aufsummierten Monatswerte
    (:func:`_monatswerte_kombiniert`). Umfassen die Daten eines Knotens mehr als ein
    Jahr, bekommt er zusaetzliche, ausklappbare Jahr-Zeilen (eine je Jahr, absteigend
    sortiert, mit dessen eigenen Monatswerten) vor seinen eigentlichen Kindern - fuer
    den Jahresvergleich Monat fuer Monat, ohne die Tabelle in die Breite wachsen zu
    lassen. Bei nur einem Jahr im Zeitraum entfaellt diese zusaetzliche Ebene (die
    kombinierte Zeile zeigt dann ohnehin schon genau dessen Werte) - umfasst der
    gesamte Tabellenzeitraum dagegen mehrere Jahre (``mehrere_jahre_insgesamt``), waere
    unklar, welches der beiden Jahre gemeint ist; die kombinierte Zeile traegt ihr
    einziges Jahr dann stattdessen im Namen (z. B. "CSM (2025)").

    ``zukuenftige_monate`` je Zeile (siehe :func:`_zukuenftige_monate`) markiert noch
    nicht abgeschlossene Monate fuer die abgehobene Darstellung in
    ``schulungen.html``. Nur eindeutig einem Kalenderjahr zuordenbare Zeilen (eine
    Jahr-Zeile, oder die kombinierte Zeile bei genau einem Jahr im Zeitraum) bekommen
    echte Markierungen - bei mehreren Jahren wuerde die kombinierte Zeile sonst
    Monate verschiedener Jahre (z. B. ein laengst vergangener Januar und ein noch
    bevorstehender) unter derselben Spalte vermengen; sie bleibt dort unmarkiert,
    der Jahresvergleich in den zugehoerigen Jahr-Zeilen zeigt die Abgrenzung Monat
    fuer Monat weiterhin praezise.
    """
    jahre = sorted({jahr for jahr, _monatsnummer in knoten.monate}, reverse=True)
    mehrere_jahre = len(jahre) > 1
    werte = _monatswerte_kombiniert(knoten.monate)
    knoten_id = f"schulung-zeile-{pfad}"
    jahr_ids = [f"{knoten_id}-jahr-{jahr}" for jahr in jahre] if mehrere_jahre else []
    # Nur bei genau einem Jahr UND mehreren Jahren im gesamten Tabellenzeitraum ist das
    # Jahr sonst nirgends an dieser Zeile ablesbar (siehe Docstring oben).
    name = (
        f"{knoten.name} ({jahre[0]})"
        if mehrere_jahre_insgesamt and len(jahre) == 1
        else knoten.name
    )
    zeile: dict[str, object] = {
        "id": knoten_id,
        "name": name,
        "werte": werte,
        "summe": sum(werte),
        "tiefe": tiefe,
        "hat_kinder": bool(knoten.kinder) or bool(jahr_ids),
        # Direkte Kinder-IDs fuer aria-controls am Auf-/Zuklapp-Knopf - das JS selbst
        # blendet zwar auch tiefer verschachtelte Nachfahren mit ein/aus, aber
        # aria-controls beschreibt nur den unmittelbar gesteuerten Bereich, tiefere
        # Ebenen haben ihren eigenen Knopf mit eigenem aria-controls. Jahr-Zeilen
        # zaehlen dabei als eigene, direkte Kinder, vor den fachlichen Kindern.
        "kinder_ids": [*jahr_ids, *(f"{knoten_id}-{i}" for i in range(len(knoten.kinder)))],
        "zukuenftige_monate": _zukuenftige_monate(jahre[0], laufender_monat)
        if len(jahre) == 1
        else [False] * 12,
    }
    zeilen = [zeile]
    if mehrere_jahre:
        for jahr, jahr_id in zip(jahre, jahr_ids, strict=True):
            jahr_werte = _monatswerte_jahr(knoten.monate, jahr)
            jahr_zeile: dict[str, object] = {
                "id": jahr_id,
                "name": str(jahr),
                "werte": jahr_werte,
                "summe": sum(jahr_werte),
                "tiefe": tiefe + 1,
                "hat_kinder": False,
                "kinder_ids": [],
                # Grundlage fuer eine gedaempfte Darstellung in schulungen.html - die
                # Jahr-Zeile ist eine ergaenzende Aufschluesselung der kombinierten
                # Zeile darueber, nicht eine gleichrangige weitere Kategorie/Basisname/
                # Format/Dauer-Stufe.
                "ist_jahr": True,
                "zukuenftige_monate": _zukuenftige_monate(jahr, laufender_monat),
            }
            zeilen.append(jahr_zeile)
    for i, kind in enumerate(knoten.kinder):
        zeilen.extend(
            _knoten_flach(
                kind,
                laufender_monat=laufender_monat,
                mehrere_jahre_insgesamt=mehrere_jahre_insgesamt,
                tiefe=tiefe + 1,
                pfad=f"{pfad}-{i}",
            )
        )
    return zeilen


def _ohne_sentinel(werte: Sequence[str]) -> tuple[str, ...]:
    """Entfernt :data:`KEINE_AUSWAHL` (siehe dort) aus einer Filter-Auswahl - macht ein
    vollstaendig abgewaehltes Dropdown von einem unberuehrten (Query-Default) unter-
    scheidbar."""
    return tuple(wert for wert in werte if wert != KEINE_AUSWAHL)


def _identitaeten(
    verlauf: Anmeldungsverlauf,
    schulung_filter: Sequence[str],
) -> list[tuple[str, Callable[..., dict[Monat, int]]]]:
    """Je Auswahl im Schulungen-Dropdown eine eigene Identitaet (Name plus an
    ``verlauf.``:meth:`~Anmeldungsverlauf.je_monat_gefiltert` gebundene Filterkriterien,
    als ``functools.partial`` statt eines Kwargs-Dict, damit mypy die Schluesselwort-
    Typen an der Bindungsstelle prueft statt an einem spaeteren ``**kwargs``).
    :data:`ALLE_SCHULUNGEN` steht fuer die ungefilterte Gesamtzahl, dedupliziert bei
    mehrfacher Auswahl (kann in der Praxis nicht vorkommen, das Dropdown bietet den
    Eintrag nur einmal an, aber :func:`_ohne_sentinel` garantiert das nicht)."""
    identitaeten: list[tuple[str, Callable[..., dict[Monat, int]]]] = []
    alle_gesehen = False
    for basisname in schulung_filter:
        if basisname == ALLE_SCHULUNGEN:
            if not alle_gesehen:
                identitaeten.append((ALLE_SCHULUNGEN, verlauf.je_monat_gefiltert))
                alle_gesehen = True
            continue
        identitaeten.append((basisname, partial(verlauf.je_monat_gefiltert, basisname=basisname)))
    return identitaeten


def _slice_werte(filter_werte: Sequence[str]) -> list[tuple[str, str | None]]:
    """Je Auswahl im Format- oder Dauer-Dropdown ein (Label-Bestandteil, Filterwert)-
    Paar - :data:`ALLE` liefert einen leeren Label-Bestandteil und ``None`` als
    Filterwert (keine Einschraenkung auf dieser Achse), dedupliziert falls mehrfach
    gewaehlt. Jede Auswahl kreuzt sich mit jeder Identitaet aus :func:`_identitaeten`
    und mit jeder Auswahl der jeweils anderen Achse (siehe :func:`_anmeldungsreihen`)."""
    ergebnis: list[tuple[str, str | None]] = []
    alle_gesehen = False
    for wert in filter_werte:
        if wert == ALLE:
            if not alle_gesehen:
                ergebnis.append(("", None))
                alle_gesehen = True
            continue
        ergebnis.append((wert, wert))
    return ergebnis


def _anmeldungsreihen(
    verlauf: Anmeldungsverlauf,
    *,
    schulung_filter: Sequence[str],
    format_filter: Sequence[str],
    dauer_filter: Sequence[str],
) -> dict[str, dict[Monat, int]]:
    """Eine Reihe je Kombination aus Identitaet (Schulungen-Auswahl, siehe
    :func:`_identitaeten`) und den gewaehlten Format-/Dauer-Auswahlen (siehe
    :func:`_slice_werte`) - Format und Dauer wirken als kreuzende Achsen statt als
    weitere, nur additive Auswahl: "CSPO" zusammen mit "2-tägig" **und** "3-tägig"
    erzeugt zwei Reihen ("CSPO 2-tägig", "CSPO 3-tägig") statt einer gemeinsamen
    "CSPO"- und einer gemeinsamen Dauer-Reihe. Zusaetzlich :data:`ALLE` in derselben
    Achse gewaehlt erzeugt eine dritte, auf dieser Achse ungefilterte Reihe ("CSPO").
    Eine Achse ohne jede Auswahl (leeres Dropdown, siehe :data:`KEINE_AUSWAHL`)
    schraenkt nicht ein und verzweigt nicht (ein stellvertretender neutraler Eintrag
    genuegt) - sind dagegen **alle drei** Achsen (Identitaet, Format, Dauer) leer, gibt
    es keine einzige Reihe (leeres Diagramm), statt automatisch auf die Gesamtzahl
    zurueckzufallen.
    """
    identitaeten = _identitaeten(verlauf, schulung_filter)
    formate = _slice_werte(format_filter)
    dauern = _slice_werte(dauer_filter)
    if not identitaeten and not formate and not dauern:
        return {}

    reihen: dict[str, dict[Monat, int]] = {}
    for identitaet_name, identitaet_je_monat in identitaeten or [("", verlauf.je_monat_gefiltert)]:
        for format_label, format_wert in formate or [("", None)]:
            for dauer_label, dauer_wert in dauern or [("", None)]:
                teile = [teil for teil in (identitaet_name, format_label, dauer_label) if teil]
                name = " ".join(teile) if teile else ALLE_SCHULUNGEN
                reihen.setdefault(
                    name,
                    identitaet_je_monat(format_wert=format_wert, dauer_wert=dauer_wert),
                )
    return reihen


def _schulung_gruppen(
    verlauf: Anmeldungsverlauf,
    kategorien: Kategorisierung,
) -> list[tuple[str, tuple[str, ...]]]:
    """Die Basisnamen (Dauer-Varianten wie "CSPO 2-tägig"/"CSPO 3-tägig"
    zusammengefasst zu "CSPO", wie im Tabellen-Drilldown - siehe
    :meth:`Anmeldungsverlauf.summe_je_basisname`) mit Anmeldung im aktuellen
    Zeitfenster, gruppiert nach Kategorie und je Gruppe alphabetisch sortiert - der
    Schulungen-Filter ist so nach denselben Kategorien durchsuchbar, die vorher ein
    eigener, inzwischen entfernter Kategorie-Filter bot (siehe Docstring der Route).
    Eine Kategorie ohne Anmeldung in diesem Zeitraum liefert keine eigene Gruppe (die
    Tabelle darunter zeigt sie trotzdem, siehe :meth:`Anmeldungsverlauf.
    gliederung_je_kategorie` - dort dient das leere Vorkommen dem Aufdecken einer
    veralteten Konfiguration, hier waere es nur eine leere, nicht anwaehlbare Gruppe).
    :data:`ALLE_SCHULUNGEN` steht separat davor (siehe ``schulungen.html``), reine
    Anzeige-Konfiguration der Dropdown-Optionen, keine Fachlogik - die eigentliche
    Zuordnung liefert :meth:`Anmeldungsverlauf.basisnamen_je_kategorie`."""
    je_kategorie = verlauf.basisnamen_je_kategorie(kategorien)
    return [
        (kategorie, tuple(sorted(namen, key=str.lower)))
        for kategorie, namen in je_kategorie.items()
        if namen
    ]


@app.get("/schulungen", response_class=HTMLResponse)
async def schulungen(
    request: Request,
    ab_jahr: AbJahr = None,
    schulung_filter: SchulungFilter = (ALLE_SCHULUNGEN,),
    format_filter: FormatFilter = (ALLE,),
    dauer_filter: DauerFilter = (ALLE,),
    jahr_filter: JahrFilter = (ALLE_JAHRE,),
    ansicht: Ansicht = STANDARD_ANSICHT,
    trendlinien_werte: TrendlinienWerte = ("an",),
) -> HTMLResponse:
    """Deckt sich mit notebooks/03_schulungsanmeldungen.ipynb: der Anmeldungsverlauf.

    ``ab_jahr`` filtert den einen geladenen Anmeldungsverlauf nur noch in-memory
    (siehe :class:`~umsatzprognose.webapp.cache.AnmeldungsverlaufCache`) - ein
    engerer Beginn zeigt deshalb sofort ein anderes Ergebnis, ohne neu zu laden. Ohne
    Angabe gilt :func:`_standard_anzeige_ab_jahr` statt starr :data:`STANDARD_AB_JAHR`.

    Die Filter-Dropdowns (Mehrfachauswahl) darueber, was der Anmeldungsverlauf zeigt,
    kombinieren sich zu Reihen im Diagramm (siehe :func:`_anmeldungsreihen`): Format
    und Dauer kreuzen sich mit der Schulungen-Auswahl und miteinander. Ein
    vollstaendig abgewaehltes Dropdown wird ueber :data:`KEINE_AUSWAHL` erkennbar - erst
    :func:`_ohne_sentinel` macht daraus wieder eine echte leere Auswahl statt des
    Query-Defaults. ``trendlinien_werte`` traegt den Checkbox-Zustand ueber ein
    verstecktes Begleitfeld (siehe Docstring von :data:`TrendlinienWerte`).

    ``jahr_filter`` und ``ansicht`` wirken - anders als die uebrigen Filter und ``ab_jahr``
    - nur auf das Diagramm, nicht auf die Schulungsdetails-Tabelle darunter: erst
    engt ``jahr_filter`` (nur bei mehr als einem Jahr im Zeitraum ueberhaupt angezeigt,
    siehe :data:`zeige_jahr_filter` im Template) die im Diagramm gezeigten Jahre ein
    (:meth:`~umsatzprognose.domaene.anmeldung.Anmeldungsverlauf.nur_jahre`), dann
    entscheidet ``ansicht`` (nur bei danach weiterhin mehr als einem Jahr angezeigt),
    ob das Diagramm einen durchgehenden Zeitraum (:func:`diagramme.
    anmeldungsverlauf_reihen`) oder einen Jahresvergleich auf gemeinsamer
    Januar-Dezember-Achse zeigt (:func:`diagramme.anmeldungsverlauf_jahresvergleich`).
    """
    schulung_filter = _ohne_sentinel(schulung_filter)
    format_filter = _ohne_sentinel(format_filter)
    dauer_filter = _ohne_sentinel(dauer_filter)
    jahr_filter = _ohne_sentinel(jahr_filter)
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

    heute = datetime.datetime.now(tz=datetime.UTC).date()
    laufender_monat: Monat = (heute.year, heute.month)

    jahr = ab_jahr if ab_jahr is not None else _standard_anzeige_ab_jahr()
    verlauf_ab_jahr = verlauf.ab_jahr(jahr)

    monatsbeschriftungen = list(MONATSNAMEN)
    kategorien: Kategorisierung = kategorien_automatisch()

    jahre_vorhanden = sorted({jahr for jahr, _monat in verlauf_ab_jahr.monate}, reverse=True)
    zeige_jahr_filter = len(jahre_vorhanden) > 1
    jahre_auswahl = {int(wert) for wert in jahr_filter if wert != ALLE_JAHRE}
    verlauf_diagramm = (
        verlauf_ab_jahr.nur_jahre(jahre_auswahl)
        if jahre_auswahl and ALLE_JAHRE not in jahr_filter
        else verlauf_ab_jahr
    )
    monate_diagramm = verlauf_diagramm.monate
    jahre_diagramm = sorted({jahr for jahr, _monat in monate_diagramm})
    zeige_ansicht_umschalter = len(jahre_diagramm) > 1

    trendlinien = "an" in trendlinien_werte
    reihen = _anmeldungsreihen(
        verlauf_diagramm,
        schulung_filter=schulung_filter,
        format_filter=format_filter,
        dauer_filter=dauer_filter,
    )
    filter_abweichend = (
        list(schulung_filter) != [ALLE_SCHULUNGEN]
        or list(format_filter) != [ALLE]
        or list(dauer_filter) != [ALLE]
        or list(jahr_filter) != [ALLE_JAHRE]
        or ansicht != STANDARD_ANSICHT
        or not trendlinien
    )

    if ansicht == "jahresvergleich" and zeige_ansicht_umschalter:
        anmeldungsverlauf_figur = diagramme.anmeldungsverlauf_jahresvergleich(
            reihen, jahre_diagramm, mit_trend=trendlinien, laufender_monat=laufender_monat
        )
    else:
        anmeldungsverlauf_figur = diagramme.anmeldungsverlauf_reihen(
            reihen, monate_diagramm, mit_trend=trendlinien, laufender_monat=laufender_monat
        )

    gliederung = verlauf_ab_jahr.gliederung_je_kategorie(kategorien)
    kategorie_knoten = [
        _kategorie_knoten(kategorie, kinder) for kategorie, kinder in gliederung.items()
    ]
    kategorie_zeilen = [
        zeile
        for i, knoten in enumerate(kategorie_knoten)
        for zeile in _knoten_flach(
            knoten,
            pfad=str(i),
            laufender_monat=laufender_monat,
            mehrere_jahre_insgesamt=zeige_jahr_filter,
        )
    ]
    gesamt_monate = _monate_summieren(kategorie_knoten)
    gesamt_zeilen = _knoten_flach(
        Anmeldungsknoten("Gesamt", gesamt_monate),
        pfad="gesamt",
        laufender_monat=laufender_monat,
        mehrere_jahre_insgesamt=zeige_jahr_filter,
    )

    return _antwort(
        request,
        seite="schulungen",
        name="schulungen.html",
        stichtag=heute,
        standardwerte=standardwerte,
        ab_jahr=jahr,
        ab_jahr_optionen=tuple(range(STANDARD_AB_JAHR, heute.year + 1)),
        anmeldungsverlauf=_figur_html(anmeldungsverlauf_figur, mit_plotlyjs=True),
        schulung_filter=schulung_filter,
        schulung_alle_schulungen=ALLE_SCHULUNGEN,
        schulung_gruppen=_schulung_gruppen(verlauf_ab_jahr, kategorien),
        format_filter=format_filter,
        format_optionen=[ALLE, *sorted(verlauf_ab_jahr.formate, key=str.lower)],
        dauer_filter=dauer_filter,
        dauer_optionen=[ALLE, *sorted(verlauf_ab_jahr.dauern, key=str.lower)],
        zeige_jahr_filter=zeige_jahr_filter,
        jahr_filter=jahr_filter,
        jahr_optionen=[ALLE_JAHRE, *(str(jahr) for jahr in jahre_vorhanden)],
        zeige_ansicht_umschalter=zeige_ansicht_umschalter,
        ansicht=ansicht,
        ansicht_optionen=ANSICHT_OPTIONEN,
        ansicht_beschriftungen=ANSICHT_BESCHRIFTUNGEN,
        trendlinien=trendlinien,
        filter_abweichend=filter_abweichend,
        filter_zuruecksetzen_query=_anfrage_query(
            request,
            standardwerte,
            ohne=frozenset(
                {
                    "schulung_filter",
                    "format_filter",
                    "dauer_filter",
                    "jahr_filter",
                },
            ),
        ),
        monatsbeschriftungen=monatsbeschriftungen,
        kategorie_zeilen=kategorie_zeilen,
        gesamt_zeilen=gesamt_zeilen,
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
            _kurzarbeit_cache.bereit,
            anzahl_monate=monate_zahl,
            schwellenwerte=schwellenwerte,
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
        stichtag=datetime.datetime.now(tz=datetime.UTC).date(),
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
                },
            ),
        ),
        zeilen=zeilen,
        kurzarbeit_grafik=_figur_html(diagramme.kurzarbeit_grafik(ergebnisse), mit_plotlyjs=True),
    )
