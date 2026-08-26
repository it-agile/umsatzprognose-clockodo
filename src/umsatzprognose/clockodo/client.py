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
``/v4/absences``             geplante Abwesenheiten (5.3), Jahresfilter als ``filter[year]``.
                              ``/``, ``/v2``, ``/v3`` -> 410 deprecated
``/v2/usersNonbusinessDays``  Feiertage je Person (5.3), Jahresfilter als einfaches
                              ``year``. Paginiert wie ``/v4/projects``
===========================  ==========================================================

**Paginierung** gibt es bei ``/v4/projects``, ``/v3/customers`` und ``/v3/users``:
``items_per_page`` setzt die Seitengroesse, ``page`` waehlt die Seite - mit einer
kleinen Seitengroesse antwortet die API mit entsprechend vielen ``count_pages``, und
``page=2`` liefert ``current_page: 2`` samt anderer IDs. Die Projektzahl liegt nah an
der Standardseite von 1000, deshalb laeuft :meth:`ClockodoClient.projects` ueber alle
Seiten.

**Alle Methoden sind Coroutinen**, weil die Abrufe einer Prognose voneinander unabhaengig
sind und sich ihre Wartezeiten sonst addieren (siehe
:mod:`umsatzprognose.clockodo.nebenlaeufig`). Wer einzeln und synchron abrufen will,
legt :func:`~umsatzprognose.clockodo.nebenlaeufig.synchron` darum - genau das tun die
``laden``-Methoden der Repositories.

**Unbekannte Query-Parameter werden dort still ignoriert, nicht abgelehnt** (``count=3``
und ``limit=3`` antworten mit 200 und der vollen, ungekuerzten Liste). Ein 200 belegt
einen Parameternamen also nicht; dafuer muss das ``paging``-Objekt geprueft werden.

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
  haengen die Personen als ``sub_groups`` unter dem Projekt, mit
  ``grouping[]=projects_id&grouping[]=month`` die Monate. Die aeussere Ebene ist die
  zuerst genannte.
* **Die Untergruppen kommen nach Dauer absteigend, nicht chronologisch.** Bei der
  Monatsgruppierung gilt das fuer jedes Projekt mit mehr als einem Monat, ohne eine
  Ausnahme (geprueft am 26.08.2026). Wer die Reihenfolge uebernimmt, rechnet eine
  Rueckrechnung ueber die Historie falsch, ohne dass etwas abbricht.

Die Antwort hat **kein** ``paging`` - alle Gruppen kommen in einem Rutsch (mit
Personen-Untergruppen rund 1,9 MB und etwa 20 Sekunden).

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
from umsatzprognose.clockodo.nebenlaeufig import gleichzeitig

DEFAULT_TIMEOUT = 60.0

# Untere Grenze des Verbrauchsfensters. ``revenue_kumuliert`` aus Spec 5.1 ist der
# Gesamtverbrauch eines Projekts, nicht der eines Monats - die Grenze muss deshalb vor
# dem aeltesten Eintrag liegen. 2020 schneidet nichts ab: mit
# ``time_since=2010-01-01`` kommen dieselben Gruppen und dieselbe Umsatzsumme.
HISTORIE_VON = "2020-01-01T00:00:00Z"

GRUPPIERUNG_PROJEKT = "projects_id"
GRUPPIERUNG_PERSON = "users_id"
GRUPPIERUNG_MONAT = "month"


def verbrauch_bis(stichtag: date | None = None) -> str:
    """Obere Grenze des Verbrauchsfensters: der Stichtag selbst (Spec 5.1).

    Der Stichtag und **nicht** das Monatsende: Verbrauch ist streng Vergangenheit. Was
    spaeter datiert ist, liegt im Prognosehorizont und wird laut Spec 5.4 dort
    angerechnet, statt vorab vom Restvolumen abgezogen zu werden - sonst waere der
    Umsatz weder in der Historie noch in der Bandbreite zu finden. Der Fall tritt in
    dieser Installation regelmaessig auf und ist kein Randfall.

    Nicht zu verwechseln mit :func:`monatsende`, das die Umsatzhistorie zieht: dort ist
    der laufende Kalendermonat der Balken, hier der Schnitt zwischen Ist und Prognose.
    """
    return f"{(stichtag or date.today()).isoformat()}T23:59:59Z"


def monatsende(tag: date | None = None) -> str:
    """Letzter Tag des Monats, in dem ``tag`` liegt - das Fenster der Umsatzhistorie.

    Monatsende und nicht ``tag`` selbst, weil eine spaeter in diesem Monat datierte
    Buchung in den laufenden Balken gehoert; dass der Monat unvollstaendig ist, fuehrt
    die Historie getrennt.
    """
    tag = tag or date.today()
    letzter = monthrange(tag.year, tag.month)[1]
    return f"{tag.year:04d}-{tag.month:02d}-{letzter:02d}T23:59:59Z"


def horizontende(stichtag: date, monate: int = 3) -> str:
    """Letzter Tag des letzten Horizontmonats - die obere Grenze des Prognosefensters.

    Die dritte obere Zeitgrenze neben :func:`verbrauch_bis` und :func:`monatsende`, und
    wieder eine andere: der Horizont **beginnt mit dem laufenden Monat** (Spec 5.4), bei
    drei Monaten endet er also zwei Monate nach dem Stichtagsmonat. Gebraucht wird die
    Grenze fuer die Monatsgruppierung je Projekt, die laut Spec 11.1 zwei Zwecke bedient:
    die Historie fuer die Abrufquote-Verteilung (5.2) und die bereits gebuchten Betraege
    im Horizont als Untergrenze der Bandbreite (5.4).
    """
    if monate < 1:
        raise ValueError(f"Ein Horizont umfasst mindestens einen Monat, nicht {monate}")
    ordnung = stichtag.year * 12 + (stichtag.month - 1) + (monate - 1)
    return monatsende(date(ordnung // 12, ordnung % 12 + 1, 1))


class ClockodoError(RuntimeError):
    """HTTP-Fehler samt Antwortkoerper.

    Der Koerper ist der eigentliche Inhalt: er benennt bei einem 400 den beanstandeten
    Parameter. Bei einem neuen 400er also die Meldung lesen, statt Parametervarianten
    zu raten.
    """


class ClockodoClient:
    """Lesender Zugriff auf die Endpunkte, die die Prognose braucht.

    Je Aufruf wird ein eigener ``httpx.AsyncClient`` geoeffnet und geschlossen. Fuer die
    halbe Handvoll Requests einer Prognose ist das ausreichend und erspart im Notebook
    jede Lebenszyklus-Verwaltung; auch ein gemeinsamer Verbindungspool haette fuer
    gleichzeitige Abrufe je eine eigene Verbindung aufgebaut.
    """

    def __init__(
        self,
        credentials: ClockodoCredentials,
        *,
        base_url: str = BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.credentials = credentials
        self.base_url = base_url
        self.timeout = timeout
        self._transport = transport

    async def get(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        """Ein GET gegen die API. Wirft bei HTTP-Fehlern einen :class:`ClockodoError`."""
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.credentials.headers(),
            timeout=self.timeout,
            transport=self._transport,
        ) as client:
            response = await client.get(path, params=dict(params) if params else None)
        if response.is_error:
            raise ClockodoError(
                f"{response.status_code} fuer {response.request.url}\n{response.text[:1000]}"
            )
        return response.json()

    async def get_paged(
        self, path: str, params: Mapping[str, Any] | None = None
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Alle Seiten eines paginierten Endpunkts einsammeln.

        Die erste Seite muss allein kommen - erst ihr ``paging`` nennt ``count_pages``.
        Danach steht die Seitenzahl fest, und die restlichen Seiten werden gleichzeitig
        geholt statt eine nach der anderen. Solange alles auf eine Seite passt, aendert
        das nichts; es wirkt an dem Tag, an dem die Grenze faellt.

        Returns:
            Die zusammengefuegte ``data``-Liste in Seitenreihenfolge und das
            ``paging``-Objekt der letzten Seite - daran ist ablesbar, ob wirklich alles
            geladen wurde.
        """
        erste = await self.get(path, {**(params or {}), "page": 1})
        paging = erste.get("paging") or {}
        seiten = int(paging.get("count_pages") or 1)
        alle = list(erste["data"])
        if seiten <= 1:
            return alle, paging

        weitere = await gleichzeitig(
            *(self.get(path, {**(params or {}), "page": seite}) for seite in range(2, seiten + 1))
        )
        for payload in weitere:
            alle.extend(payload["data"])
            paging = payload.get("paging") or paging
        return alle, paging

    async def projects(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Alle Projekte aus ``/v4/projects``, ueber alle Seiten."""
        return await self.get_paged("/v4/projects")

    async def customers(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Alle Kunden aus ``/v3/customers``, ueber alle Seiten."""
        return await self.get_paged("/v3/customers")

    async def users(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Alle Personen aus ``/v3/users``, ueber alle Seiten."""
        return await self.get_paged("/v3/users")

    async def targethours(self) -> list[dict[str, Any]]:
        """Sollarbeitszeiten aus dem unversionierten ``/targethours``.

        Envelope-Key ist ``targethours``, es gibt kein ``paging``. Die
        Version ist keine freie Wahl: ``/v2/targethours`` und ``/v3/targethours``
        antworten mit 404 ``RouteNotFound``.
        """
        return (await self.get("/targethours"))["targethours"]

    async def entrygroups(
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
            time_until: obere Zeitgrenze, volle ISO-Form mit Uhrzeit. Ohne Angabe der
                heutige Tag (:func:`verbrauch_bis`), aufgeloest **hier** und nicht als
                Default: eine Modulkonstante oder ein Default-Parameter wird beim
                Import einmal berechnet und friert ein. Ein Colab-Notebook bleibt
                tagelang offen und schnitte ueber einen Tageswechsel hinweg stumm ab.

        Returns:
            Die ``groups``-Liste.
        """
        payload = await self.get(
            "/v2/entrygroups",
            {
                "time_since": time_since,
                "time_until": time_until or verbrauch_bis(),
                "grouping[]": list(grouping),
            },
        )
        return payload["groups"]

    async def entrygroups_je_projekt_und_person(
        self, *, time_since: str = HISTORIE_VON, time_until: str | None = None
    ) -> list[dict[str, Any]]:
        """Verbrauch je Projekt, darunter die Anteile je Person.

        Ein Abruf statt zweier: die Projektsummen dieser Antwort sind mit denen der
        einfachen Gruppierung identisch (am 24.08.2026 ueber alle Gruppen verglichen,
        keine Abweichung), und die Untergruppen summieren sich exakt auf sie. Damit sind
        Verbrauch und Aufteilungsschluessel garantiert konsistent.
        """
        return await self.entrygroups(
            [GRUPPIERUNG_PROJEKT, GRUPPIERUNG_PERSON],
            time_since=time_since,
            time_until=time_until,
        )

    async def entrygroups_je_projekt_und_monat(
        self, *, time_since: str = HISTORIE_VON, time_until: str | None = None
    ) -> list[dict[str, Any]]:
        """Verbrauch je Projekt, darunter die Monate - die Kombination aus Spec 11.1.

        Am 26.08.2026 gegen die Installation geprueft, rund 23 Sekunden. Die
        Projektsummen stimmen mit denen der einfachen Gruppierung exakt ueberein; die
        Monatssummen weichen bei einigen Projekten um **Cent** davon ab - Clockodo
        rundet jede Gruppe einzeln. Die Zeitsummen stimmen ueberall exakt.

        Zwei Fallen, beide belegt: ``group`` der Untergruppe ist der Monat als String
        ``"JJJJMM"``, und die Untergruppen sind **nach Dauer absteigend** sortiert und
        nicht chronologisch - siehe
        :meth:`~umsatzprognose.domaene.verbrauchsverlauf.Verbrauchsverlauf.fuer`.
        """
        return await self.entrygroups(
            [GRUPPIERUNG_PROJEKT, GRUPPIERUNG_MONAT],
            time_since=time_since,
            time_until=time_until,
        )

    async def entrygroups_je_monat(
        self, *, time_since: str, time_until: str
    ) -> list[dict[str, Any]]:
        """Umsatz je Kalendermonat - alle Buchungen, auch die ohne Projektbezug."""
        return await self.entrygroups(
            [GRUPPIERUNG_MONAT], time_since=time_since, time_until=time_until
        )

    async def absences(self, year: int) -> list[dict[str, Any]]:
        """Abwesenheiten eines Jahres aus ``/v4/absences`` (Spec 5.3).

        Die Legacy-Pfade ``/absences``, ``/v2/absences`` und ``/v3/absences``
        antworten mit 410 ``deprecated`` - ``/v4`` ist keine freie Wahl. Der
        Jahresfilter ist ein ``deepObject``-Parameter (``filter[year]``, nicht
        ``year`` direkt), analog zu ``grouping[]`` bei ``/v2/entrygroups``. Die
        Antwort traegt kein ``paging`` - Envelope-Key ist ``data``.

        Der Abruf ist ungefiltert nach Status und Typ: welche der beiden fuer den
        Kapazitaetsdeckel zaehlen (etwa ob eine unbestaetigte oder eine abgelehnte
        Abwesenheit mitzaehlt), ist Teil des noch zu bauenden Deckels und wird nicht
        hier vorweggenommen.
        """
        payload = await self.get("/v4/absences", {"filter[year]": year})
        return payload["data"]

    async def users_nonbusiness_days(
        self, year: int
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Feiertage eines Jahres, fertig je Person zugeordnet (Spec 5.3).

        ``/v2/usersNonbusinessDays`` erspart die eigene Zuordnung ueber die
        Feiertagsgruppe (``/v3/usersNonbusinessGroups``) und damit den Fehler, dafuer
        die heutige Zuordnung statt der zu einem vergangenen Stichtag zu benutzen.

        **``year`` ist hier ein einfacher Query-Parameter**, kein ``deepObject`` wie
        ``filter[year]`` bei :meth:`absences` - beide Endpunkte filtern nach Jahr, aber
        nicht auf dieselbe Art. Anders als bei ``absences`` traegt die Antwort ein
        ``paging``-Objekt (analog zu ``/v4/projects``), deshalb ueber
        :meth:`get_paged`.

        Returns:
            Je Seite zusammengefuegt: ``{"users_id": …, "days": [...]}`` - die
            ``days`` je Eintrag sind die Feiertage dieser Person in diesem Jahr.
        """
        return await self.get_paged("/v2/usersNonbusinessDays", {"year": year})
