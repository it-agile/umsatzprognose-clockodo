"""Tests zum HTTP-Zugriff.

Gegen einen ``httpx.MockTransport``, nicht gegen die echte Installation - geprueft
wird, ob Paginierung, Parameterform und Fehlerbehandlung dem entsprechen, was am
24.08.2026 per curl verifiziert wurde (siehe Modul-Docstring von
``umsatzprognose.api``).
"""

from __future__ import annotations

import httpx
import pytest

from umsatzprognose.api import ClockodoClient, ClockodoError
from umsatzprognose.config import ClockodoCredentials

CREDS = ClockodoCredentials(
    api_user="user@example.com",
    api_key="key",
    app_name="test",
    app_email="a@b.de",
)


def client_mit(handler) -> tuple[ClockodoClient, list[httpx.Request]]:
    """Ein Client, der statt der API einen Handler befragt; sammelt die Requests."""
    requests: list[httpx.Request] = []

    def aufzeichnen(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    return ClockodoClient(CREDS, transport=httpx.MockTransport(aufzeichnen)), requests


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


def test_entrygroups_schickt_die_verifizierte_parameterform():
    client, requests = client_mit(lambda _: httpx.Response(200, json={"groups": [{"group": "7"}]}))
    groups = client.entrygroups_je_projekt()

    assert groups == [{"group": "7"}]
    # grouping ist ein Array-Parameter; "grouping=projects_id" quittiert die API mit
    # 400 "Array expected.". Zeitgrenzen brauchen die volle ISO-Form mit Uhrzeit.
    params = dict(requests[0].url.params)
    assert params["grouping[]"] == "projects_id"
    assert params["time_since"].endswith("Z") and "T" in params["time_since"]
    assert params["time_until"].endswith("Z") and "T" in params["time_until"]


def test_zugangsdaten_gehen_als_header_mit():
    client, requests = client_mit(lambda _: httpx.Response(200, json={"groups": []}))
    client.entrygroups_je_projekt()

    assert requests[0].headers["X-ClockodoApiUser"] == "user@example.com"
    assert requests[0].headers["X-ClockodoApiKey"] == "key"
    assert requests[0].headers["X-Clockodo-External-Application"] == "test;a@b.de"


def test_fehlerkoerper_steht_in_der_meldung():
    # Der Koerper benennt den beanstandeten Parameter - raise_for_status verwirft ihn.
    koerper = {"error": {"message": "Array expected.", "fields": ["grouping"]}}
    client, _ = client_mit(lambda _: httpx.Response(400, json=koerper))

    with pytest.raises(ClockodoError) as fehler:
        client.entrygroups_je_projekt()

    assert "Array expected." in str(fehler.value)
    assert "grouping" in str(fehler.value)
    assert "400" in str(fehler.value)


def test_kunden_kommen_von_der_v3_route():
    # /v4/customers antwortet mit 404, /v2/customers mit 410 - die Version ist keine
    # freie Wahl, deshalb steht sie hier fest.
    client, requests = client_mit(
        lambda _: httpx.Response(200, json={"data": [{"id": 1, "name": "Kunde"}]})
    )
    kunden, _ = client.customers()

    assert kunden == [{"id": 1, "name": "Kunde"}]
    assert requests[0].url.path == "/api/v3/customers"
