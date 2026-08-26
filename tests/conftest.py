"""Gemeinsame Bausteine fuer die Tests.

Kein Test spricht mit der echten API. Die Antworten sind **nachgebaute** Ausschnitte:
Struktur, Typen und Sonderfaelle sind die der echten Antworten (Projekt-ID als String,
``group == 0``, ``default_target_hours`` als Schalter), IDs, Namen und Betraege sind
frei erfunden. Aus der Installation gelesene Werte stehen in keiner Datei dieses
Repositories. Wer die *Struktur* erfindet, testet die eigene Annahme - deshalb bleibt
sie so, wie die API sie liefert.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from umsatzprognose.clockodo.client import ClockodoClient
from umsatzprognose.clockodo.config import ClockodoCredentials

CREDS = ClockodoCredentials(
    api_user="user@example.com",
    api_key="key",
    app_name="test",
    app_email="a@b.de",
)


def client_mit(handler: Callable[[httpx.Request], httpx.Response]):
    """Ein Client, der statt der API einen Handler befragt; sammelt die Requests."""
    requests: list[httpx.Request] = []

    def aufzeichnen(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    return ClockodoClient(CREDS, transport=httpx.MockTransport(aufzeichnen)), requests


def client_mit_routen(routen: dict[str, object]):
    """Ein Client, der je Pfad eine feste Antwort liefert.

    Args:
        routen: Pfad -> Antwortkoerper, oder Pfad -> Funktion, die den Request nimmt.
            Die zweite Form wird bei ``/v2/entrygroups`` gebraucht: derselbe Pfad
            antwortet je nach ``grouping[]`` voellig verschieden. Ein unbekannter Pfad
            ist ein Testfehler und fuehrt zu einem 404, damit er auffaellt.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        # Die Basis-URL endet auf /api; die Routen sind ohne dieses Praefix notiert.
        koerper = routen.get(request.url.path.removeprefix("/api"))
        if koerper is None:
            return httpx.Response(404, json={"error": {"message": request.url.path}})
        if callable(koerper):
            koerper = koerper(request)
        return httpx.Response(200, json=koerper)

    return client_mit(handler)


@pytest.fixture
def projekt_antwort() -> dict:
    """Zwei aktive Projekte, eines mit und eines ohne Budget, plus ein inaktives."""
    return {
        "paging": {"current_page": 1, "count_pages": 1, "count_items": 3},
        "data": [
            {
                "id": 101,
                "customers_id": 201,
                "name": "Beispielprojekt",
                "active": True,
                "completed": False,
                "budget": {
                    "monetary": True,
                    "hard": False,
                    "from_subprojects": False,
                    "interval": None,
                    "amount": 160000,
                    "subprojects_budget_total": 0,
                },
                "deadline": "2026-09-30",
                "automatic_completion": True,
            },
            {
                "id": 102,
                "customers_id": 201,
                "name": "Schulungsprodukt",
                "active": True,
                "completed": False,
                "budget": None,
            },
            {
                "id": 103,
                "customers_id": 202,
                "name": "Altprojekt",
                "active": False,
                "completed": True,
                "budget": {"monetary": False, "amount": 48, "interval": None},
            },
        ],
    }


@pytest.fixture
def kunden_antwort() -> dict:
    return {
        "paging": {"current_page": 1, "count_pages": 1, "count_items": 2},
        "data": [
            {"id": 201, "name": "Musterkunde GmbH"},
            {"id": 202, "name": "Beispiel AG"},
        ],
    }


@pytest.fixture
def benutzer_antwort() -> dict:
    """``default_target_hours`` ist ein Schalter, keine Stundenzahl - siehe Modul-Doc."""
    return {
        "paging": {"current_page": 1, "count_pages": 1, "count_items": 2},
        "data": [
            {"id": 301, "name": "Beispielperson", "active": True,
             "default_target_hours": False},
            {"id": 302, "name": "Ehemalige Person", "active": False,
             "default_target_hours": True},
        ],
    }  # fmt: skip


@pytest.fixture
def sollzeit_antwort() -> dict:
    """Eine abgeloeste und eine laufende Vereinbarung derselben Person."""
    return {
        "targethours": [
            {
                "id": 1,
                "users_id": 301,
                "type": "weekly",
                "date_since": "2020-01-01",
                "date_until": "2023-06-13",
                "monday": 8, "tuesday": 8, "wednesday": 8, "thursday": 8, "friday": 8,
                "saturday": 0, "sunday": 0,
            },
            {
                "id": 2,
                "users_id": 301,
                "type": "weekly",
                "date_since": "2023-06-14",
                "date_until": None,
                "monday": 7, "tuesday": 7, "wednesday": 7, "thursday": 7, "friday": 7,
                "saturday": 0, "sunday": 0,
            },
        ]
    }  # fmt: skip


@pytest.fixture
def entrygroup_antwort() -> dict:
    """Verbrauch je Projekt mit Personen-Untergruppen, inklusive ``group == 0``."""
    return {
        "groups": [
            {
                "group": "101",
                "name": "Musterkunde GmbH / Beispielprojekt",
                "duration": 2160000,
                "revenue": 60000.0,
                "grouped_by": "projects_id",
                "sub_groups": [
                    {"group": "301", "name": "Beispielperson", "duration": 1620000,
                     "revenue": 45000.0, "grouped_by": "users_id"},
                    {"group": "399", "name": "Ohne Stammdatensatz", "duration": 540000,
                     "revenue": 15000.0, "grouped_by": "users_id"},
                ],
            },
            {
                "group": 0,
                "name": "Ohne Projekt",
                "duration": 21600,
                "revenue": 0,
                "grouped_by": "projects_id",
                "sub_groups": [],
            },
        ]
    }  # fmt: skip


@pytest.fixture
def projekt_monats_antwort() -> dict:
    """Verbrauch je Projekt mit Monats-Untergruppen - die Antwort aus Spec 11.1.

    Traegt die Eigenheiten, die an der echten Antwort aufgefallen sind:

    * Die Monate kommen **nach Dauer absteigend**, nicht chronologisch.
    * ``202606`` fehlt: ein Monat ohne Buchung steht nicht in der Antwort.
    * ``202609`` liegt **nach** dem Stichtag (24.08.2026) - Untergrenze der Bandbreite
      (Spec 5.4) und kein Verbrauch.
    * Die Monatssummen gehen nur auf den Cent auf (hier 65.000,00 gegen 64.999,99 an
      der Gruppe) - Clockodo rundet jede Gruppe einzeln.
    * ``group == 0`` kommt **zweimal** vor, je Kunde ohne Projekt einmal.

    Die Monate bis zum Stichtag summieren sich auf denselben Verbrauch, den
    :func:`entrygroup_antwort` fuer dieses Projekt fuehrt - so haengen beide Fixtures
    zusammen.
    """
    return {
        "groups": [
            {
                "group": "101",
                "name": "Musterkunde GmbH / Beispielprojekt",
                "duration": 2340000,
                "revenue": 64999.99,
                "grouped_by": "projects_id",
                "sub_groups": [
                    {"group": "202604", "name": "202604", "duration": 720000,
                     "revenue": 20000.0, "grouped_by": "month"},
                    {"group": "202605", "name": "202605", "duration": 648000,
                     "revenue": 18000.0, "grouped_by": "month"},
                    {"group": "202607", "name": "202607", "duration": 540000,
                     "revenue": 15000.0, "grouped_by": "month"},
                    {"group": "202608", "name": "202608", "duration": 252000,
                     "revenue": 7000.0, "grouped_by": "month"},
                    {"group": "202609", "name": "202609", "duration": 180000,
                     "revenue": 5000.0, "grouped_by": "month"},
                ],
            },
            {
                "group": 0,
                "name": "Ohne Projekt",
                "duration": 14400,
                "revenue": 0,
                "grouped_by": "projects_id",
                "sub_groups": [
                    {"group": "202605", "name": "202605", "duration": 14400,
                     "revenue": 0, "grouped_by": "month"},
                ],
            },
            {
                "group": 0,
                "name": "Zweiter Kunde ohne Projekt",
                "duration": 7200,
                "revenue": 0,
                "grouped_by": "projects_id",
                "sub_groups": [
                    {"group": "202607", "name": "202607", "duration": 7200,
                     "revenue": 0, "grouped_by": "month"},
                ],
            },
        ]
    }  # fmt: skip


@pytest.fixture
def monats_antwort() -> dict:
    """Zwei Monate; der dazwischenliegende fehlt und muss aufgefuellt werden."""
    return {
        "groups": [
            {"group": "202606", "name": "202606", "duration": 3600000, "revenue": 300000.0,
             "grouped_by": "month"},
            {"group": "202608", "name": "202608", "duration": 1800000, "revenue": 150000.0,
             "grouped_by": "month"},
        ]
    }  # fmt: skip
