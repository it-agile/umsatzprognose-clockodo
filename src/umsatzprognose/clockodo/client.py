"""HTTP-Zugriff auf die Clockodo-API.

Die Struktur der Antworten und die zulaessigen Query-Parameter sind nicht der Doku
entnommen (``docs.clockodo.com`` ist eine JavaScript-Anwendung und war nicht
auslesbar), sondern per ``curl`` und im Python-Aufruf gegen die echte Installation
geprueft. Was dabei herauskam und hier abgebildet ist:

**Vier API-Generationen nebeneinander**, kein Versehen, sondern Stand der Clockodo-API.
Die Version je Endpunkt ist keine freie Wahl, sondern ausprobiert:

===========================  ==========================================================
``/v4/projects``             Auftragsvolumen (``budget``), Paginierung, ``data``-Envelope
``/v3/customers``            Kundennamen. ``/v4`` -> 404, ``/v2`` -> 410 deprecated
``/v3/users``                Personen. ``default_target_hours`` ist ein Schalter!
``/targethours``             Sollarbeitszeit, unversioniert. ``/v2`` und ``/v3`` -> 404
``/v2/entrygroups``          Verbrauch und Umsatz, aggregiert
``/v4/absences``             geplante Abwesenheiten (5.3). ``/``, ``/v2``, ``/v3`` -> 410
===========================  ==========================================================

**Paginierung** gibt es bei ``/v4/projects``, ``/v3/customers`` und ``/v3/users``:
``items_per_page`` setzt die Seitengroesse, ``page`` waehlt die Seite - mit
``items_per_page=3`` antwortet die API mit ``count_pages: 299``, und ``page=2`` liefert
``current_page: 2`` samt anderer IDs. Bei 895 Projekten und einer Standardseite von 1000
ist die Grenze nah, deshalb laeuft :meth:`ClockodoClient.projects` ueber alle Seiten.

**Unbekannte Query-Parameter werden dort still ignoriert, nicht abgelehnt** (``count=3``
und ``limit=3`` antworten mit 200 und den vollen 895 Projekten). Ein 200 belegt einen
Parameternamen also nicht; dafuer muss das ``paging``-Objekt geprueft werden.

``/v2/entrygroups`` ist umgekehrt streng - ein falscher Parameter fuehrt zu 400. Die
akzeptierte Form, jeder Punkt an einer 400er-Antwort belegt:

* ``grouping`` ist ein Array-Parameter. ``grouping=projects_id`` antwortet mit
  ``{"error":{"message":"Array expected.","fields":["grouping"]}}``; erst
  ``grouping[]=…`` wird akzeptiert. Der Name ist kein gueltiges Python-Schluesselwort,
  deshalb nehmen die Methoden hier ein Params-Dict statt Schluesselwoerter.
* Gueltige Werte fuer Objekte tragen das Suffix ``_id`` (``projects_id``,
  ``customers_id``, ``users_id``); ``projects`` gibt ``Unknown group option``.
  **Zeitgruppierungen tragen es nicht und stehen im Singular**: ``month``, ``year``,
  ``week``, ``day`` sind gueltig, ``months``, ``years`` und ``date`` antworten mit 400.
* ``grouping`` und ``time_since`` sind Pflicht (``Missing data: …``).
* Zeitgrenzen brauchen die volle ISO-Form mit Uhrzeit; ein reines Datum gibt
  ``{"error":{"message":"Wrong format","fields":["time_since"]}}``.
* **Mehrfachgruppierung** ist erlaubt: mit ``grouping[]=projects_id&grouping[]=users_id``
  haengen die Personen als ``sub_groups`` unter dem Projekt.

Die Antwort hat **kein** ``paging`` - alle Gruppen kommen in einem Rutsch (870 Gruppen
mit Personen-Untergruppen sind rund 1,9 MB und brauchen etwa 20 Sekunden).

**Fehler werden am Koerper diagnostiziert, nicht am Status.** Clockodo begruendet einen
400 in der Form ``{"error": {"message": …, "fields": [...]}}`` und benennt dort den
beanstandeten Parameter. ``httpx.Response.raise_for_status`` zeigt nur Status und URL
und verwirft genau diese Information, deshalb :class:`ClockodoError`.
"""

from __future__ import annotations

from calendar import monthrange
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

import httpx

from umsatzprognose.clockodo.config import BASE_URL, ClockodoCredentials

DEFAULT_TIMEOUT = 60.0

# Untere Grenze des Verbrauchsfensters. ``revenue_kumuliert`` aus Spec 5.1 ist der
# Gesamtverbrauch eines Projekts, nicht der eines Monats - die Grenze muss deshalb vor
# dem aeltesten Eintrag liegen. 2020 schneidet nichts ab: mit
# ``time_since=2010-01-01`` kommen dieselben 870 Gruppen und dieselbe Umsatzsumme.
HISTORIE_VON = "2020-01-01T00:00:00Z"

GRUPPIERUNG_PROJEKT = "projects_id"
GRUPPIERUNG_PERSON = "users_id"
GRUPPIERUNG_MONAT = "month"


def historie_bis(tag: date | None = None) -> str:
    """Obere Grenze des Verbrauchsfensters: das Ende des Monats, in dem ``tag`` liegt.

    Monatsende und nicht ``tag`` selbst, weil eine Buchung spaeter in diesem Monat
    datiert sein kann und trotzdem schon Ist ist - dieselbe Grenze zieht die
    Umsatzhistorie fuer den laufenden Balken.

    **Das ist eine Funktion und keine Konstante**, und der Unterschied ist nicht
    kosmetisch: als Modulkonstante wuerde der Wert beim Import einmal berechnet und
    danach einfrieren. Ein Notebook bleibt in Colab tagelang offen; ueber einen
    Monatswechsel hinweg wuerde es Buchungen des neuen Monats stumm abschneiden. Aus
    demselben Grund ist der Wert **nicht** als Default-Parameter eingetragen - Python
    wertet Defaults ebenfalls nur beim Import aus. Die Aufrufer nehmen ``None`` und
    loesen erst hier auf.
    """
    tag = tag or date.today()
    letzter = monthrange(tag.year, tag.month)[1]
    return f"{tag.year:04d}-{tag.month:02d}-{letzter:02d}T23:59:59Z"


class ClockodoError(RuntimeError):
    """HTTP-Fehler samt Antwortkoerper.

    Der Koerper ist der eigentliche Inhalt: er benennt bei einem 400 den beanstandeten
    Parameter. Bei einem neuen 400er also die Meldung lesen, statt Parametervarianten
    zu raten.
    """


class ClockodoClient:
    """Lesender Zugriff auf die Endpunkte, die die Prognose braucht.

    Je Aufruf wird ein eigener ``httpx.Client`` geoeffnet und geschlossen. Fuer die
    halbe Handvoll Requests einer Prognose ist das ausreichend und erspart im Notebook
    jede Lebenszyklus-Verwaltung.
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
        """Alle Kunden aus ``/v3/customers``, ueber alle Seiten."""
        return self.get_paged("/v3/customers")

    def users(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Alle Personen aus ``/v3/users``, ueber alle Seiten (59 in dieser Anlage)."""
        return self.get_paged("/v3/users")

    def targethours(self) -> list[dict[str, Any]]:
        """Sollarbeitszeiten aus dem unversionierten ``/targethours``.

        Envelope-Key ist ``targethours``, es gibt kein ``paging`` (186 Eintraege). Die
        Version ist keine freie Wahl: ``/v2/targethours`` und ``/v3/targethours``
        antworten mit 404 ``RouteNotFound``.
        """
        return self.get("/targethours")["targethours"]

    def entrygroups(
        self,
        grouping: Sequence[str],
        *,
        time_since: str = HISTORIE_VON,
        time_until: str | None = None,
    ) -> list[dict[str, Any]]:
        """Aggregierte Eintraege aus ``/v2/entrygroups``.

        Args:
            grouping: ein oder mehrere Gruppierungswerte. Bei mehreren haengt die
                zweite Ebene als ``sub_groups`` unter der ersten.
            time_since: untere Zeitgrenze, volle ISO-Form mit Uhrzeit.
            time_until: obere Zeitgrenze, volle ISO-Form mit Uhrzeit. Ohne Angabe das
                Ende des laufenden Monats, hier und nicht als Default aufgeloest -
                siehe :func:`historie_bis`.

        Returns:
            Die ``groups``-Liste.
        """
        payload = self.get(
            "/v2/entrygroups",
            {
                "time_since": time_since,
                "time_until": time_until or historie_bis(),
                "grouping[]": list(grouping),
            },
        )
        return payload["groups"]

    def entrygroups_je_projekt_und_person(
        self, *, time_since: str = HISTORIE_VON, time_until: str | None = None
    ) -> list[dict[str, Any]]:
        """Verbrauch je Projekt, darunter die Anteile je Person.

        Ein Abruf statt zweier: die Projektsummen dieser Antwort sind mit denen der
        einfachen Gruppierung identisch (am 24.08.2026 ueber alle 870 Gruppen
        verglichen, keine Abweichung), und die Untergruppen summieren sich exakt auf
        sie. Damit sind Verbrauch und Aufteilungsschluessel garantiert konsistent.
        """
        return self.entrygroups(
            [GRUPPIERUNG_PROJEKT, GRUPPIERUNG_PERSON],
            time_since=time_since,
            time_until=time_until,
        )

    def entrygroups_je_monat(self, *, time_since: str, time_until: str) -> list[dict[str, Any]]:
        """Umsatz je Kalendermonat - alle Buchungen, auch die ohne Projektbezug."""
        return self.entrygroups([GRUPPIERUNG_MONAT], time_since=time_since, time_until=time_until)
