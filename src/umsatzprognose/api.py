"""HTTP-Zugriff auf die Clockodo-API.

Die Struktur der Antworten und die zulaessigen Query-Parameter sind nicht der Doku
entnommen (``docs.clockodo.com`` ist eine JavaScript-Anwendung und war nicht
auslesbar), sondern am 24.08.2026 per ``curl`` gegen die echte Installation geprueft.
Was dabei herauskam und hier abgebildet ist:

``/v4/projects`` liefert ``{"paging": {...}, "data": [...]}``. ``items_per_page`` setzt
die Seitengroesse, ``page`` waehlt die Seite - mit ``items_per_page=3`` antwortet die API
mit ``count_pages: 299``, und ``page=2`` liefert ``current_page: 2`` samt anderer IDs.
Bei 895 Projekten und einer Standardseite von 1000 ist die Grenze nah, deshalb laeuft
:meth:`ClockodoClient.projects` ueber alle Seiten.

**Unbekannte Query-Parameter werden dort still ignoriert, nicht abgelehnt** (``count=3``
und ``limit=3`` antworten mit 200 und den vollen 895 Projekten). Ein 200 belegt einen
Parameternamen also nicht; dafuer muss das ``paging``-Objekt geprueft werden.

``/v2/entrygroups`` ist umgekehrt streng - ein falscher Parameter fuehrt zu 400. Die
akzeptierte Form, jeder Punkt an einer 400er-Antwort belegt:

* ``grouping`` ist ein Array-Parameter. ``grouping=projects_id`` antwortet mit
  ``{"error":{"message":"Array expected.","fields":["grouping"]}}``; erst
  ``grouping[]=…`` wird akzeptiert. Der Name ist kein gueltiges Python-Schluesselwort,
  deshalb nehmen die Methoden hier ein Params-Dict statt Schluesselwoerter.
* Gueltiger Gruppierungswert ist ``projects_id``, nicht ``projects``
  (``Unknown group option``).
* ``grouping`` und ``time_since`` sind Pflicht (``Missing data: …``).
* Zeitgrenzen brauchen die volle ISO-Form mit Uhrzeit; ein reines Datum gibt
  ``{"error":{"message":"Wrong format","fields":["time_since"]}}``.

Die Antwort hat **kein** ``paging`` - alle Gruppen kommen in einem Rutsch (870 Gruppen
sind rund 800 KB).

**Fehler werden am Koerper diagnostiziert, nicht am Status.** Clockodo begruendet einen
400 in der Form ``{"error": {"message": …, "fields": [...]}}`` und benennt dort den
beanstandeten Parameter. ``httpx.Response.raise_for_status`` zeigt nur Status und URL
und verwirft genau diese Information, deshalb :class:`ClockodoError`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from umsatzprognose.config import BASE_URL, ClockodoCredentials

DEFAULT_TIMEOUT = 30.0

# Zeitfenster fuer den kumulierten Verbrauch. ``revenue_kumuliert`` aus Spec 5.1 ist
# der Gesamtverbrauch eines Projekts, nicht der eines Monats - die untere Grenze muss
# deshalb vor dem aeltesten Eintrag liegen. 2020 schneidet nichts ab: mit
# ``time_since=2010-01-01`` kommen dieselben 870 Gruppen und dieselbe Umsatzsumme.
HISTORIE_VON = "2020-01-01T00:00:00Z"
HISTORIE_BIS = "2026-12-31T23:59:59Z"

# Nur dieser Gruppierungswert wird gebraucht; ``customers_id`` waere die Alternative.
GRUPPIERUNG_PROJEKT = "projects_id"


class ClockodoError(RuntimeError):
    """HTTP-Fehler samt Antwortkoerper.

    Der Koerper ist der eigentliche Inhalt: er benennt bei einem 400 den beanstandeten
    Parameter. Bei einem neuen 400er also die Meldung lesen, statt Parametervarianten
    zu raten.
    """


class ClockodoClient:
    """Lesender Zugriff auf die Endpunkte, die die Prognose braucht.

    Je Aufruf wird ein eigener ``httpx.Client`` geoeffnet und geschlossen. Fuer die
    wenigen Requests einer Prognose ist das ausreichend und erspart im Notebook jede
    Lebenszyklus-Verwaltung.
    """

    def __init__(
        self,
        credentials: ClockodoCredentials,
        *,
        base_url: str = BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.credentials = credentials
        self.base_url = base_url
        self.timeout = timeout
        self._transport = transport

    def get(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        """Ein GET gegen die API. Wirft bei HTTP-Fehlern einen :class:`ClockodoError`."""
        with httpx.Client(
            base_url=self.base_url,
            headers=self.credentials.headers(),
            timeout=self.timeout,
            transport=self._transport,
        ) as client:
            response = client.get(path, params=dict(params) if params else None)
        if response.is_error:
            raise ClockodoError(
                f"{response.status_code} fuer {response.request.url}\n{response.text[:1000]}"
            )
        return response.json()

    def get_paged(
        self, path: str, params: Mapping[str, Any] | None = None
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Alle Seiten eines paginierten Endpunkts einsammeln.

        Returns:
            Die zusammengefuegte ``data``-Liste und das ``paging``-Objekt der letzten
            Seite - daran ist ablesbar, ob wirklich alles geladen wurde.
        """
        seite, alle, paging = 1, [], {}
        while True:
            payload = self.get(path, {**(params or {}), "page": seite})
            alle.extend(payload["data"])
            paging = payload.get("paging") or {}
            if seite >= paging.get("count_pages", 1):
                return alle, paging
            seite += 1

    def projects(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Alle Projekte aus ``/v4/projects``, ueber alle Seiten."""
        return self.get_paged("/v4/projects")

    def customers(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Alle Kunden aus ``/v3/customers``, ueber alle Seiten.

        Nur fuer die Beschriftung der Tabelle: ``/v4/projects`` liefert lediglich
        ``customers_id``, den Kundennamen gibt es hier. Die Version ist keine freie
        Wahl - ``/v4/customers`` antwortet mit 404 ``RouteNotFound``, ``/v2/customers``
        mit 410 ``deprecated`` (geprueft am 24.08.2026). Envelope und ``paging`` haben
        dieselbe Form wie bei ``/v4/projects``.
        """
        return self.get_paged("/v3/customers")

    def entrygroups_je_projekt(
        self,
        *,
        time_since: str = HISTORIE_VON,
        time_until: str = HISTORIE_BIS,
    ) -> list[dict[str, Any]]:
        """Nach Projekt gruppierte Eintraege aus ``/v2/entrygroups``.

        Returns:
            Die ``groups``-Liste. Eine Gruppe traegt die Projekt-ID als String in
            ``group``, den Umsatz in ``revenue`` (Euro) und die Zeit in ``duration``
            (Sekunden).
        """
        payload = self.get(
            "/v2/entrygroups",
            {
                "time_since": time_since,
                "time_until": time_until,
                "grouping[]": GRUPPIERUNG_PROJEKT,
            },
        )
        return payload["groups"]
