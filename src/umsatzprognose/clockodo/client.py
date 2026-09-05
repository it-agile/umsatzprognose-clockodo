"""HTTP-Zugriff auf die Clockodo-API.

**Stand der Clockodo-API: Vier API-Generationen nebeneinander**

===========================  ==========================================================
``/v4/projects``             Auftragsvolumen (``budget``), Paginierung, ``data``-Envelope
``/v3/customers``            Kundennamen. ``/v4`` -> 404, ``/v2`` -> 410 deprecated
``/v3/users``                Personen. ``default_target_hours`` ist ein Schalter!
``/targethours``             Sollarbeitszeit, unversioniert. ``/v2`` und ``/v3`` -> 404
``/v2/entrygroups``          Verbrauch und Umsatz, aggregiert
``/v4/absences``             geplante Abwesenheiten, Jahresfilter als ``filter[year]``.
                              ``/``, ``/v2``, ``/v3`` -> 410 deprecated
``/v2/usersNonbusinessDays``  Feiertage je Person, Jahresfilter als einfaches
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

``/v2/entrygroups`` ist streng - ein falscher Parameter fuehrt zu 400. Die
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

Die Antwort hat **kein** ``paging``.

**Fehler werden über Body diagnostiziert, nicht über Status.** Clockodo begruendet einen
400 in der Form ``{"error": {"message": …, "fields": [...]}}`` und benennt dort den
beanstandeten Parameter. ``httpx.Response.raise_for_status`` zeigt nur Status und URL
und verwirft genau diese Information, deshalb :class:`ClockodoError`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NotRequired, TypedDict, cast

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from typing import Any

    from umsatzprognose.util import Monat

    from .config import ClockodoCredentials

from calendar import monthrange
from datetime import date

import httpx

from umsatzprognose.util import aus_ordnung, ordnung

from . import cache
from .config import BASE_URL
from .nebenlaeufig import gleichzeitig

DEFAULT_TIMEOUT = 60.0

SEKUNDEN_JE_STUNDE = 3600.0

# Untere Grenze des Verbrauchsfensters. ``revenue_kumuliert`` ist der
# Gesamtverbrauch eines Projekts, nicht der eines Monats - die Grenze muss deshalb vor
# dem aeltesten Eintrag liegen. 2021 ist der früheste Zeitraum.
HISTORIE_VON = "2021-01-01T00:00:00Z"

GRUPPIERUNG_PROJEKT = "projects_id"
GRUPPIERUNG_PERSON = "users_id"
GRUPPIERUNG_MONAT = "month"


class BudgetV4(TypedDict):
    """``budget``-Teilobjekt eines ``/v4/projects``-Eintrags, ``null`` moeglich.

    ``interval`` ist ein Integer-Enum (0 wochenweise, 1 monatlich, 2 quartalsweise,
    3 jaehrlich) - siehe :class:`~umsatzprognose.domaene.projekt.IntervallBudget`.
    """

    amount: float | None
    monetary: NotRequired[bool]
    interval: NotRequired[int | None]
    from_subprojects: NotRequired[bool]
    hard: NotRequired[bool]


class ProjectV4(TypedDict):
    """Ein Eintrag aus ``/v4/projects`` - nur die hier verwendeten Felder."""

    id: int
    customers_id: int | None
    name: str | None
    active: bool
    completed: bool
    budget: BudgetV4 | None
    deadline: NotRequired[str | None]
    automatic_completion: NotRequired[bool]


class CustomerV3(TypedDict):
    """Ein Eintrag aus ``/v3/customers``."""

    id: int
    name: str | None


class UserV3(TypedDict):
    """Ein Eintrag aus ``/v3/users``."""

    id: int
    name: str | None
    active: bool


class TargetHourV1(TypedDict):
    """Eine Zeile aus dem unversionierten ``/targethours``, ``type == "weekly"``.

    Die Wochentagsfelder sind hier als optional deklariert, weil nur dieser Typ
    gedeutet wird (siehe Moduldocstring von :mod:`.mitarbeiter`) und ein anderer
    ``type`` (z. B. ``"monthly"``) sie gar nicht traegt.
    """

    users_id: int
    type: str
    date_since: str
    date_until: str | None
    monday: NotRequired[float]
    tuesday: NotRequired[float]
    wednesday: NotRequired[float]
    thursday: NotRequired[float]
    friday: NotRequired[float]
    saturday: NotRequired[float]
    sunday: NotRequired[float]


class AbsenceV4(TypedDict):
    """Ein Eintrag aus ``/v4/absences``."""

    users_id: int
    date_since: str
    date_until: str
    type: int
    status: int


class NonbusinessDayV2(TypedDict):
    """Ein Feiertag innerhalb ``UsersNonbusinessDayV2.days``."""

    evaluated_date: str
    half_day: bool
    name: str | None


class UsersNonbusinessDayV2(TypedDict):
    """Ein Eintrag aus ``/v2/usersNonbusinessDays`` - die Feiertage einer Person."""

    users_id: int
    days: list[NonbusinessDayV2]


class EntryGroupV2(TypedDict):
    """Eine Gruppe aus ``/v2/entrygroups``, rekursiv ueber ``sub_groups``.

    ``group`` ist trotz spec-deklariertem ``string`` teils eine Zahl (``group == 0``
    fuer Buchungen ohne Projekt), ``revenue`` trotz deklariertem ``integer`` ein
    Float - siehe die Modul-Docstrings von :mod:`.projekte` und
    :mod:`.verbrauchsverlauf` fuer die fachlichen Konsequenzen.
    """

    group: str | int
    name: str
    duration: int
    revenue: float
    grouped_by: str
    hourly_rate: NotRequired[float | None]
    sub_groups: NotRequired[list[EntryGroupV2]]


def stunden_je_person_und_monat(
    *gruppenlisten: list[EntryGroupV2],
) -> dict[tuple[int, Monat], float]:
    """Faltet eine oder mehrere Person-x-Monat-Gruppierungen zu Stunden je (Personen-ID, Monat).

    Gemeinsame Auswertung der Antwortform von
    :meth:`ClockodoClient.entrygroups_je_person_und_monat`: die aeussere Gruppe ist die
    Person (``group`` als Zahl), die Untergruppen sind Monate (``group`` als String
    ``"JJJJMM"``). Gedacht fuer mehrere getrennte Abrufe **derselben** Gruppierung, die
    sich nur im ``billable``-Filter unterscheiden (:class:`.auslastung.AuslastungRepository`
    ruft billable 1 und 2 getrennt ab, ein kuenftiger Baustein Kurzarbeit intern/extern) -
    ihre Stunden werden aufaddiert, nicht ersetzt. Eine Personen-ID, die sich nicht als
    Zahl lesen laesst, wird uebersprungen.
    """
    stunden: dict[tuple[int, Monat], float] = {}
    for gruppen in gruppenlisten:
        for person_gruppe in gruppen:
            try:
                mitarbeiter_id = int(person_gruppe["group"])
            except (TypeError, ValueError):
                continue
            for monatsgruppe in person_gruppe.get("sub_groups") or ():
                schluessel = str(monatsgruppe["group"])
                monat: Monat = (int(schluessel[:4]), int(schluessel[4:6]))
                stunden[(mitarbeiter_id, monat)] = (
                    stunden.get((mitarbeiter_id, monat), 0.0)
                    + float(monatsgruppe.get("duration") or 0.0) / SEKUNDEN_JE_STUNDE
                )
    return stunden


def entrygroups_zusammenfuehren(*gruppenlisten: list[EntryGroupV2]) -> list[EntryGroupV2]:
    """Fasst mehrere ``entrygroups``-Antworten disjunkter Zeitfenster zusammen.

    ``duration`` und ``revenue`` werden je Schluessel (``group``) aufsummiert, rekursiv
    auch in ``sub_groups`` - nur korrekt, wenn sich die Zeitfenster der uebergebenen
    Listen nicht ueberlappen. Gedacht fuer den Cache-Schnitt in
    :meth:`ClockodoClient._entrygroups_mit_verlaufscache`: der stabile, gecachte Teil
    der Historie und der immer frisch geholte aktuelle Teil ergeben zusammen dieselbe
    Antwort wie ein einzelner Abruf ueber das volle Fenster.

    Ein innerhalb **eines** Zeitfensters mehrfach vergebener Schluessel (``group == 0``
    fuer Buchungen ohne Projekt, siehe Moduldocstring von :mod:`.projekte`) wird dabei
    ebenfalls zu einer Zeile zusammengefasst - unschaedlich, weil alle bisherigen
    Verwendungen ohnehin nur die Summe ueber diese Zeilen bilden, nie eine einzelne.
    """
    zusammengefasst: dict[str | int, EntryGroupV2] = {}
    reihenfolge: list[str | int] = []
    for gruppen in gruppenlisten:
        for gruppe in gruppen:
            schluessel = gruppe["group"]
            vorhanden = zusammengefasst.get(schluessel)
            if vorhanden is None:
                zusammengefasst[schluessel] = dict(gruppe)  # type: ignore[assignment]
                reihenfolge.append(schluessel)
                continue
            vorhanden["duration"] = vorhanden.get("duration", 0) + gruppe.get("duration", 0)
            vorhanden["revenue"] = vorhanden.get("revenue", 0.0) + gruppe.get("revenue", 0.0)
            neue_untergruppen = entrygroups_zusammenfuehren(
                vorhanden.get("sub_groups") or [], gruppe.get("sub_groups") or []
            )
            if neue_untergruppen:
                vorhanden["sub_groups"] = neue_untergruppen
    return [zusammengefasst[schluessel] for schluessel in reihenfolge]


def verbrauch_bis(stichtag: date | None = None) -> str:
    """Obere Grenze des Verbrauchsfensters: der Stichtag selbst.

    Der Stichtag und **nicht** das Monatsende: Verbrauch ist Vergangenheit. Was
    spaeter datiert ist, liegt im Prognosehorizont und wird dort
    angerechnet, statt vorab vom Restvolumen abgezogen zu werden.

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

    Die dritte obere Zeitgrenze neben :func:`verbrauch_bis` und :func:`monatsende`,
    der Horizont **beginnt mit dem laufenden Monat**, bei
    drei Monaten endet er also zwei Monate nach dem Stichtagsmonat. Gebraucht wird die
    Grenze fuer die Monatsgruppierung je Projekt, die zwei Zwecke bedient:
    die Historie fuer die Abrufquote-Verteilung und die bereits gebuchten Betraege
    im Horizont als Untergrenze der Bandbreite.
    """
    if monate < 1:
        raise ValueError(f"Ein Horizont umfasst mindestens einen Monat, nicht {monate}")
    letzter_monat = aus_ordnung(ordnung(stichtag.year, stichtag.month) + monate - 1)
    return monatsende(date(*letzter_monat, 1))


class ClockodoError(RuntimeError):
    """HTTP-Fehler samt Antwortbody.

    Der Body ist der eigentliche Inhalt: er benennt bei einem 400 den beanstandeten
    Parameter.
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
        geholt statt eine nach der anderen.

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

    async def projects(self) -> tuple[list[ProjectV4], dict[str, Any]]:
        """Alle Projekte aus ``/v4/projects``, ueber alle Seiten."""
        daten, paging = await self.get_paged("/v4/projects")
        return cast("list[ProjectV4]", daten), paging

    async def customers(self) -> tuple[list[CustomerV3], dict[str, Any]]:
        """Alle Kunden aus ``/v3/customers``, ueber alle Seiten."""
        daten, paging = await self.get_paged("/v3/customers")
        return cast("list[CustomerV3]", daten), paging

    async def users(self) -> tuple[list[UserV3], dict[str, Any]]:
        """Alle Personen aus ``/v3/users``, ueber alle Seiten."""
        daten, paging = await self.get_paged("/v3/users")
        return cast("list[UserV3]", daten), paging

    async def targethours(self) -> list[TargetHourV1]:
        """Sollarbeitszeiten aus dem unversionierten ``/targethours``.

        Envelope-Key ist ``targethours``, es gibt kein ``paging``. Die
        Version ist keine freie Wahl: ``/v2/targethours`` und ``/v3/targethours``
        antworten mit 404 ``RouteNotFound``.
        """
        return cast("list[TargetHourV1]", (await self.get("/targethours"))["targethours"])

    async def entrygroups(
        self,
        grouping: Sequence[str],
        *,
        time_since: str = HISTORIE_VON,
        time_until: str | None = None,
        billable: int | None = None,
    ) -> list[EntryGroupV2]:
        """Aggregierte Eintraege aus ``/v2/entrygroups``.

        Args:
            grouping: ein oder mehrere Gruppierungswerte. Bei mehreren haengt die
                zweite Ebene als ``sub_groups`` unter der ersten.
            time_since: untere Zeitgrenze, volle ISO-Form mit Uhrzeit.
            time_until: obere Zeitgrenze, volle ISO-Form mit Uhrzeit. Ohne Angabe der
                heutige Tag (:func:`verbrauch_bis`), aufgeloest **hier** und nicht als
                Default: eine Modulkonstante oder ein Default-Parameter wird beim
                Import einmal berechnet und friert ein.
            billable: ``filter[billable]``, ohne Angabe ungefiltert. Gueltige Werte
                laut ``BillableDistinct`` der API: 0 nicht abrechenbar, 1 abrechenbar,
                2 bereits fakturiert.

        Returns:
            Die ``groups``-Liste.
        """
        params: dict[str, Any] = {
            "time_since": time_since,
            "time_until": time_until or verbrauch_bis(),
            "grouping[]": list(grouping),
        }
        if billable is not None:
            params["filter[billable]"] = billable
        payload = await self.get("/v2/entrygroups", params)
        return cast("list[EntryGroupV2]", payload["groups"])

    async def entrygroups_je_projekt_und_person(
        self,
        *,
        time_since: str = HISTORIE_VON,
        time_until: str | None = None,
        cache_cutoff_monate: int | None = None,
    ) -> list[EntryGroupV2]:
        """Verbrauch je Projekt, darunter die Anteile je Person.

        Ein Abruf statt zweier: die Projektsummen dieser Antwort sind mit denen der
        einfachen Gruppierung identisch, und die Untergruppen summieren sich exakt auf sie. Damit
        sind Verbrauch und Aufteilungsschluessel garantiert konsistent.

        ``cache_cutoff_monate`` siehe :meth:`_entrygroups_mit_verlaufscache` - ohne
        aktivierten Cache (Standardfall) ohne jede Wirkung.
        """
        return await self._entrygroups_mit_verlaufscache(
            [GRUPPIERUNG_PROJEKT, GRUPPIERUNG_PERSON],
            time_since=time_since,
            time_until=time_until or verbrauch_bis(),
            cache_cutoff_monate=cache_cutoff_monate,
        )

    async def entrygroups_je_projekt_und_monat(
        self,
        *,
        time_since: str = HISTORIE_VON,
        time_until: str | None = None,
        cache_cutoff_monate: int | None = None,
    ) -> list[EntryGroupV2]:
        """Verbrauch je Projekt, darunter die Monate.

        Achutng: ``group`` der Untergruppe ist der Monat als String
        ``"JJJJMM"``, und die Untergruppen sind **nach Dauer absteigend** sortiert und
        nicht chronologisch - siehe
        :meth:`~umsatzprognose.domaene.verbrauchsverlauf.Verbrauchsverlauf.fuer`.

        ``cache_cutoff_monate`` siehe :meth:`_entrygroups_mit_verlaufscache` - ohne
        aktivierten Cache (Standardfall) ohne jede Wirkung.
        """
        return await self._entrygroups_mit_verlaufscache(
            [GRUPPIERUNG_PROJEKT, GRUPPIERUNG_MONAT],
            time_since=time_since,
            time_until=time_until or verbrauch_bis(),
            cache_cutoff_monate=cache_cutoff_monate,
        )

    async def _entrygroups_mit_verlaufscache(
        self,
        grouping: Sequence[str],
        *,
        time_since: str,
        time_until: str,
        cache_cutoff_monate: int | None,
    ) -> list[EntryGroupV2]:
        """Wie :meth:`entrygroups`, aber der laengst abgeschlossene Teil darf aus dem
        lokalen Cache kommen (siehe Moduldocstring von :mod:`.cache`).

        Ohne gesetzte Umgebungsvariable :data:`cache.TTL_ENV` (Standardfall)
        unveraendert ein einzelner Abruf ueber das volle Fenster - der Cache ist
        striktes Opt-in. Mit aktiviertem Cache wird die Anfrage am Cutoff
        (:func:`cache.cutoff_datum`) gespalten: der stabile, aeltere Teil kommt aus dem
        Cache oder wird einmalig geladen und abgelegt, der Rest wird immer frisch
        geholt. Beide Teile werden ueber :func:`entrygroups_zusammenfuehren` wieder zu
        einer Antwort vereint, die exakt der eines einzelnen Abrufs entspricht.
        """
        ttl = cache.ttl_sekunden()
        if ttl is None:
            return await self.entrygroups(grouping, time_since=time_since, time_until=time_until)

        cutoff = cache.cutoff_datum(time_until, monate=cache.cutoff_monate(cache_cutoff_monate))
        if cutoff <= time_since:
            return await self.entrygroups(grouping, time_since=time_since, time_until=time_until)

        cache_schluessel = cache.schluessel(grouping, time_since=time_since, time_until=cutoff)
        historisch, aktuell = await gleichzeitig(
            cache.gecacht_oder_neu(
                cache_schluessel,
                ttl=ttl,
                lader=lambda: self.entrygroups(grouping, time_since=time_since, time_until=cutoff),
            ),
            self.entrygroups(grouping, time_since=cutoff, time_until=time_until),
        )
        return entrygroups_zusammenfuehren(historisch, aktuell)

    async def entrygroups_je_monat(self, *, time_since: str, time_until: str) -> list[EntryGroupV2]:
        """Umsatz je Kalendermonat - alle Buchungen, auch die ohne Projektbezug."""
        return await self.entrygroups(
            [GRUPPIERUNG_MONAT], time_since=time_since, time_until=time_until
        )

    async def entrygroups_je_person_und_monat(
        self, *, billable: int, time_since: str, time_until: str
    ) -> list[EntryGroupV2]:
        """Zeit je Person, darunter die Monate, gefiltert auf einen Billable-Status.

        Fuer ein explizit gewaehltes Zeitfenster gedacht (beide Zeitgrenzen deshalb
        Pflicht, wie bei :meth:`entrygroups_je_monat`), nicht fuer die volle Historie.
        """
        return await self.entrygroups(
            [GRUPPIERUNG_PERSON, GRUPPIERUNG_MONAT],
            time_since=time_since,
            time_until=time_until,
            billable=billable,
        )

    async def absences(self, year: int) -> list[AbsenceV4]:
        """Abwesenheiten eines Jahres aus ``/v4/absences``."""
        payload = await self.get("/v4/absences", {"filter[year]": year})
        return cast("list[AbsenceV4]", payload["data"])

    async def users_nonbusiness_days(
        self, year: int
    ) -> tuple[list[UsersNonbusinessDayV2], dict[str, Any]]:
        """Feiertage eines Jahres, fertig je Person zugeordnet.

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
        daten, paging = await self.get_paged("/v2/usersNonbusinessDays", {"year": year})
        return cast("list[UsersNonbusinessDayV2]", daten), paging
