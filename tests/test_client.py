"""Tests zum HTTP-Zugriff.

Gegen einen ``httpx.MockTransport``, nicht gegen die echte Installation - geprueft
wird, ob Paginierung, Parameterform und Fehlerbehandlung dem entsprechen, was am
24.08.2026 gegen die Installation verifiziert wurde (siehe Modul-Docstring von
``umsatzprognose.clockodo.client``).
"""

from __future__ import annotations

import httpx
import pytest

from conftest import CREDS, client_mit
from umsatzprognose.clockodo.client import ClockodoClient, ClockodoError
from umsatzprognose.clockodo.config import ClockodoCredentials


def test_alle_seiten_werden_eingesammelt():
    def handler(request):
        seite = int(dict(request.url.params)["page"])
        return httpx.Response(
            200,
            json={
                "paging": {"current_page": seite, "count_pages": 3},
                "data": [{"id": seite}],
            },
        )

    client, requests = client_mit(handler)
    projekte, paging = client.projects()

    assert [p["id"] for p in projekte] == [1, 2, 3]
    assert paging["current_page"] == 3
    assert [dict(r.url.params)["page"] for r in requests] == ["1", "2", "3"]


def test_ohne_paging_bleibt_es_bei_einer_seite():
    client, requests = client_mit(lambda _: httpx.Response(200, json={"data": [{"id": 7}]}))
    projekte, paging = client.projects()

    assert [p["id"] for p in projekte] == [7]
    assert paging == {}
    assert len(requests) == 1


def test_alle_drei_pflichtheader_gehen_mit():
    client, requests = client_mit(lambda _: httpx.Response(200, json={"data": []}))
    client.projects()

    header = requests[0].headers
    assert header["X-ClockodoApiUser"] == CREDS.api_user
    assert header["X-ClockodoApiKey"] == CREDS.api_key
    assert header["X-Clockodo-External-Application"] == "test;a@b.de"


def test_entrygroups_verlangen_arrayform_und_volle_zeitangabe():
    # grouping=… ohne Klammern antwortet mit "Array expected.", ein reines Datum mit
    # "Wrong format" - beides an 400ern belegt.
    client, requests = client_mit(lambda _: httpx.Response(200, json={"groups": []}))
    client.entrygroups_je_projekt_und_person()

    params = requests[0].url.params
    assert params.get_list("grouping[]") == ["projects_id", "users_id"]
    assert params["time_since"].endswith("T00:00:00Z")
    assert params["time_until"].endswith("T23:59:59Z")


def test_monatsgruppierung_heisst_month_im_singular():
    client, requests = client_mit(lambda _: httpx.Response(200, json={"groups": []}))
    client.entrygroups_je_monat(
        time_since="2025-09-01T00:00:00Z", time_until="2026-08-31T23:59:59Z"
    )

    assert requests[0].url.params.get_list("grouping[]") == ["month"]


def test_sollarbeitszeit_kommt_vom_unversionierten_endpunkt():
    client, requests = client_mit(lambda _: httpx.Response(200, json={"targethours": []}))
    client.targethours()

    # Die Basis-URL endet auf /api, der Endpunkt haengt ohne Versionsteil daran.
    assert requests[0].url.path == "/api/targethours"


def test_fehler_traegt_den_antwortkoerper():
    # raise_for_status wuerde genau die Begruendung verwerfen, die den beanstandeten
    # Parameter benennt.
    koerper = {"error": {"message": "Unknown group option", "fields": ["grouping"]}}
    client, _ = client_mit(lambda _: httpx.Response(400, json=koerper))

    with pytest.raises(ClockodoError) as fehler:
        client.entrygroups(["projects"])

    assert "400" in str(fehler.value)
    assert "Unknown group option" in str(fehler.value)


def test_zu_lange_anwendungskennung_wird_abgelehnt():
    # Clockodo begrenzt "name;email" auf 50 Zeichen.
    with pytest.raises(ValueError, match="50"):
        ClockodoCredentials(
            api_user="u@example.com",
            api_key="k",
            app_name="eine-sehr-lange-anwendungskennung-die-nicht-passt",
            app_email="noch.laenger@example.com",
        )


def test_client_nimmt_eine_abweichende_basis_url():
    client = ClockodoClient(CREDS, base_url="https://example.test/api")
    assert client.base_url == "https://example.test/api"
