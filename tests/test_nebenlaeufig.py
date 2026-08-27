"""Tests zur Nebenlaeufigkeit der Abrufe.

Das Mittel dafuer ist eine ``asyncio.Barrier``: jeder Handler wartet dort, bis alle
erwarteten Requests eingetroffen sind. Laufen sie nacheinander, wartet der erste
vergeblich - der Test schlaegt mit einem Timeout fehl statt haengenzubleiben.
"""

from __future__ import annotations

import asyncio
from datetime import date

import httpx
import pytest

from conftest import CREDS, client_mit
from umsatzprognose.clockodo import BestandRepository, ClockodoClient, ClockodoError
from umsatzprognose.clockodo.nebenlaeufig import gleichzeitig, synchron

# Grosszuegig: der Test misst keine Dauer, er soll nur nicht ewig haengen, wenn die
# Abrufe wieder nacheinander laufen.
TIMEOUT = 5.0

# Fester Stichtag statt date.today(): der Dreimonatshorizont ab ihm bleibt im selben
# Jahr, damit die Anzahl der Abwesenheits-Abrufe (einer je Jahr im Horizont) nicht vom
# Tag der Testausfuehrung abhaengt.
STICHTAG = date(2026, 8, 24)

ERWARTETE_ABRUFE = 9
"""Kunden, Personen, Sollzeiten, Abwesenheiten, Feiertage, Projekte, Verbrauch,
Umsatzhistorie, Monatsverbrauch."""


def treffpunkt_fuer(anzahl: int):
    """Ein Handler, der jeden Request warten laesst, bis ``anzahl`` davon offen sind."""
    schranke = asyncio.Barrier(anzahl)

    async def handler(request: httpx.Request, koerper: dict) -> httpx.Response:
        await asyncio.wait_for(schranke.wait(), TIMEOUT)
        return httpx.Response(200, json=koerper)

    return handler


def test_alle_abrufe_eines_bestands_laufen_gleichzeitig(
    projekt_antwort,
    kunden_antwort,
    benutzer_antwort,
    sollzeit_antwort,
    entrygroup_antwort,
    monats_antwort,
    projekt_monats_antwort,
    abwesenheiten_antwort,
    feiertage_antwort,
):
    """Neun Endpunkte, neun offene Requests - keiner wartet auf einen anderen."""
    warten = treffpunkt_fuer(ERWARTETE_ABRUFE)
    antworten = {
        "/v4/projects": projekt_antwort,
        "/v3/customers": kunden_antwort,
        "/v3/users": benutzer_antwort,
        "/targethours": sollzeit_antwort,
        "/v4/absences": abwesenheiten_antwort,
        "/v2/usersNonbusinessDays": feiertage_antwort,
    }
    # Drei der neun Requests gehen an /v2/entrygroups und unterscheiden sich nur in
    # der Gruppierung - Verbrauch je Person, Umsatz je Monat, Verbrauch je Projektmonat.
    nach_gruppierung = {
        ("projects_id", "users_id"): entrygroup_antwort,
        ("month",): monats_antwort,
        ("projects_id", "month"): projekt_monats_antwort,
    }

    def handler(request: httpx.Request):
        pfad = request.url.path.removeprefix("/api")
        if pfad == "/v2/entrygroups":
            koerper = nach_gruppierung[tuple(request.url.params.get_list("grouping[]"))]
        else:
            koerper = antworten[pfad]
        return warten(request, koerper)

    client, requests = client_mit(handler)
    bestand = BestandRepository(client).laden(stichtag=STICHTAG)

    assert len(requests) == ERWARTETE_ABRUFE
    assert len(bestand.projekte) == 3


def test_folgeseiten_einer_paginierung_laufen_gleichzeitig():
    """Seite 1 muss allein kommen, Seite 2 und 3 nicht mehr nacheinander."""
    warten = treffpunkt_fuer(2)

    def handler(request: httpx.Request):
        seite = int(dict(request.url.params)["page"])
        koerper = {"paging": {"current_page": seite, "count_pages": 3}, "data": [{"id": seite}]}
        if seite == 1:
            return httpx.Response(200, json=koerper)
        return warten(request, koerper)

    client, _ = client_mit(handler)
    projekte, _ = synchron(client.projects())

    assert [p["id"] for p in projekte] == [1, 2, 3]


def test_ein_fehler_bricht_die_uebrigen_abrufe_ab():
    """Ein 400 auf einen Endpunkt darf nicht erst nach den anderen Antworten auffallen.

    ``asyncio.gather`` liesse die uebrigen Abrufe weiterlaufen; ihr Ergebnis braucht
    dann niemand mehr, aber der Fehler wuerde bis zur letzten Antwort verschwiegen.
    """
    fertig_gelaufen: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/v2/entrygroups"):
            return httpx.Response(400, json={"error": {"message": "Unknown group option"}})
        await asyncio.sleep(TIMEOUT)
        fertig_gelaufen.append(request.url.path)
        return httpx.Response(200, json={"data": []})

    client, _ = client_mit(handler)

    with pytest.raises(ClockodoError, match="Unknown group option"):
        BestandRepository(client).laden()

    assert fertig_gelaufen == []


def test_laden_funktioniert_in_einem_laufenden_event_loop(
    projekt_antwort,
    kunden_antwort,
    benutzer_antwort,
    sollzeit_antwort,
    monats_antwort,
    abwesenheiten_antwort,
    feiertage_antwort,
):
    """Der Fall Colab: dort laeuft immer schon ein Loop.

    ``asyncio.run`` waere hier ein ``RuntimeError`` - dass ``laden`` trotzdem
    durchlaeuft, ist die halbe Begruendung fuer :func:`synchron`.
    """
    antworten = {
        "/v4/projects": projekt_antwort,
        "/v3/customers": kunden_antwort,
        "/v3/users": benutzer_antwort,
        "/targethours": sollzeit_antwort,
        "/v2/entrygroups": monats_antwort,
        "/v4/absences": abwesenheiten_antwort,
        "/v2/usersNonbusinessDays": feiertage_antwort,
    }
    client, _ = client_mit(
        lambda request: httpx.Response(200, json=antworten[request.url.path.removeprefix("/api")])
    )

    async def wie_in_einer_notebook_zelle():
        return BestandRepository(client).laden(stichtag=STICHTAG)

    bestand = asyncio.run(wie_in_einer_notebook_zelle())
    assert len(bestand.projekte) == 3


def test_gleichzeitig_haelt_die_reihenfolge_der_argumente():
    """Die Antwortreihenfolge ist beliebig, die Ergebnisreihenfolge nicht."""

    async def nach(sekunden: float, wert: str) -> str:
        await asyncio.sleep(sekunden)
        return wert

    assert synchron(gleichzeitig(nach(0.02, "erst"), nach(0.0, "dann"))) == ["erst", "dann"]


def test_zweiter_ladevorgang_laeuft_im_neuen_loop():
    """Jeder synchrone Aufruf bringt einen eigenen Event-Loop mit.

    Deshalb darf nichts Loop-Gebundenes am Client haengen - ein dort gehaltenes
    ``asyncio.Semaphore`` wuerde genau hier mit einem ``RuntimeError`` brechen.
    """
    client = ClockodoClient(
        CREDS, transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"data": []}))
    )
    assert synchron(client.customers()) == ([], {})
    assert synchron(client.customers()) == ([], {})
