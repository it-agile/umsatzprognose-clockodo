"""Tests zum HTTP-Zugriff.

Die Methoden des Clients sind Coroutinen; hier steht deshalb ``synchron`` darum - wie
in den ``laden``-Methoden der Repositories. Das erspart eine Testabhaengigkeit auf
``pytest-asyncio`` und prueft die Bruecke gleich mit.
"""

from __future__ import annotations

from datetime import date

import httpx
import pytest

from conftest import CREDS, client_mit
from umsatzprognose.clockodo import ClockodoClient, ClockodoCredentials, ClockodoError
from umsatzprognose.clockodo.client import horizontende, monatsende, verbrauch_bis
from umsatzprognose.clockodo.nebenlaeufig import synchron


def test_alle_seiten_werden_eingesammelt():
    """Seite 1 zuerst - erst ihr ``paging`` nennt ``count_pages``; der Rest gleichzeitig."""

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
    projekte, paging = synchron(client.projects())

    assert [p["id"] for p in projekte] == [1, 2, 3]
    assert paging["current_page"] == 3
    # Die erste Seite muss allein kommen, die uebrigen duerfen in beliebiger
    # Reihenfolge eintreffen - eingesammelt werden sie in Seitenreihenfolge.
    assert dict(requests[0].url.params)["page"] == "1"
    assert sorted(dict(r.url.params)["page"] for r in requests) == ["1", "2", "3"]


def test_ohne_paging_bleibt_es_bei_einer_seite():
    client, requests = client_mit(lambda _: httpx.Response(200, json={"data": [{"id": 7}]}))
    projekte, paging = synchron(client.projects())

    assert [p["id"] for p in projekte] == [7]
    assert paging == {}
    assert len(requests) == 1


def test_alle_drei_pflichtheader_gehen_mit():
    client, requests = client_mit(lambda _: httpx.Response(200, json={"data": []}))
    synchron(client.projects())

    header = requests[0].headers
    assert header["X-ClockodoApiUser"] == CREDS.api_user
    assert header["X-ClockodoApiKey"] == CREDS.api_key
    assert header["X-Clockodo-External-Application"] == "test;a@b.de"


def test_entrygroups_verlangen_arrayform_und_volle_zeitangabe():
    # grouping=… ohne Klammern antwortet mit "Array expected.", ein reines Datum mit
    # "Wrong format" - beides an 400ern belegt.
    client, requests = client_mit(lambda _: httpx.Response(200, json={"groups": []}))
    synchron(client.entrygroups_je_projekt_und_person())

    params = requests[0].url.params
    assert params.get_list("grouping[]") == ["projects_id", "users_id"]
    assert params["time_since"].endswith("T00:00:00Z")
    assert params["time_until"].endswith("T23:59:59Z")


def test_monatsgruppierung_heisst_month_im_singular():
    client, requests = client_mit(lambda _: httpx.Response(200, json={"groups": []}))
    synchron(
        client.entrygroups_je_monat(
            time_since="2025-09-01T00:00:00Z", time_until="2026-08-31T23:59:59Z"
        )
    )

    assert requests[0].url.params.get_list("grouping[]") == ["month"]


def test_doppelgruppierung_nach_projekt_und_monat():
    # die zuerst genannte Gruppierung ist die aeussere Ebene.
    client, requests = client_mit(lambda _: httpx.Response(200, json={"groups": []}))
    synchron(client.entrygroups_je_projekt_und_monat(time_until="2026-10-31T23:59:59Z"))

    params = requests[0].url.params
    assert params.get_list("grouping[]") == ["projects_id", "month"]
    assert params["time_until"] == "2026-10-31T23:59:59Z"


def test_horizontende_ist_die_dritte_obere_zeitgrenze():
    """der Horizont beginnt mit dem laufenden Monat.

    Drei Monate ab dem 24.08.2026 enden damit am 31.10.2026 - nicht am 24.11. und nicht
    am 30.11. Verbrauchsgrenze und Historienfenster liegen beide woanders.
    """
    assert horizontende(date(2026, 8, 24), 3) == "2026-10-31T23:59:59Z"
    assert horizontende(date(2026, 8, 24), 1) == "2026-08-31T23:59:59Z"
    # Ueber die Jahresgrenze hinweg.
    assert horizontende(date(2026, 12, 3), 3) == "2027-02-28T23:59:59Z"
    with pytest.raises(ValueError, match="mindestens einen Monat"):
        horizontende(date(2026, 8, 24), 0)


def test_sollarbeitszeit_kommt_vom_unversionierten_endpunkt():
    client, requests = client_mit(lambda _: httpx.Response(200, json={"targethours": []}))
    synchron(client.targethours())

    # Die Basis-URL endet auf /api, der Endpunkt haengt ohne Versionsteil daran.
    assert requests[0].url.path == "/api/targethours"


def test_abwesenheiten_filtern_ueber_deepobject_jahresparameter():
    # filter[year], nicht year direkt - deepObject-Form wie bei grouping[].
    client, requests = client_mit(lambda _: httpx.Response(200, json={"data": []}))
    synchron(client.absences(2026))

    assert requests[0].url.path == "/api/v4/absences"
    assert requests[0].url.params["filter[year]"] == "2026"


def test_feiertage_filtern_ueber_einfaches_jahr_und_sind_paginiert():
    # year direkt, kein deepObject wie bei absences - und mit paging, anders als dort.
    client, requests = client_mit(
        lambda _: httpx.Response(
            200,
            json={
                "paging": {"current_page": 1, "count_pages": 1, "count_items": 0},
                "data": [],
            },
        )
    )
    synchron(client.users_nonbusiness_days(2026))

    assert requests[0].url.path == "/api/v2/usersNonbusinessDays"
    assert requests[0].url.params["year"] == "2026"


def test_fehler_traegt_den_antwortkoerper():
    # raise_for_status wuerde genau die Begruendung verwerfen, die den beanstandeten
    # Parameter benennt.
    koerper = {"error": {"message": "Unknown group option", "fields": ["grouping"]}}
    client, _ = client_mit(lambda _: httpx.Response(400, json=koerper))

    with pytest.raises(ClockodoError) as fehler:
        synchron(client.entrygroups(["projects"]))

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


def test_verbrauchsfenster_endet_am_stichtag_nicht_am_monatsende():
    """Verbrauch ist Vergangenheit.

    Was spaeter datiert ist, liegt im Horizont und wird dort angerechnet
    """
    assert verbrauch_bis(date(2026, 8, 24)) == "2026-08-24T23:59:59Z"
    assert monatsende(date(2026, 8, 24)) == "2026-08-31T23:59:59Z"


@pytest.mark.parametrize(
    ("tag", "erwartet"),
    [
        (date(2026, 8, 24), "2026-08-31T23:59:59Z"),
        (date(2026, 2, 1), "2026-02-28T23:59:59Z"),
        (date(2028, 2, 15), "2028-02-29T23:59:59Z"),
        (date(2026, 12, 31), "2026-12-31T23:59:59Z"),
    ],
)
def test_monatsende_traegt_die_laenge_des_monats(tag, erwartet):
    assert monatsende(tag) == erwartet


def test_obere_zeitgrenze_wird_je_aufruf_bestimmt():
    """Kein eingefrorener Wert."""
    client, requests = client_mit(lambda _: httpx.Response(200, json={"groups": []}))
    synchron(client.entrygroups(["projects_id"]))
    assert dict(requests[0].url.params)["time_until"] == verbrauch_bis()
