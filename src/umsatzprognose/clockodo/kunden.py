"""Abbildung von ``/v3/customers`` auf :class:`~umsatzprognose.domaene.kunde.Kunde`.

Der Kundenname ist keine Rechengroesse, sondern Beschriftung - ``/v4/projects`` fuehrt
nur ``customers_id``. Ohne Namen waere eine Tabelle aus 44 Zahlen-IDs nicht pruefbar.

Am 24.08.2026 geprueft, welche Version die Kunden liefert: ``/v4/customers`` antwortet
mit 404 ``RouteNotFound``, ``/v2/customers`` mit 410 ``deprecated``, ``/v3/customers``
mit 200 und derselben Form wie ``/v4/projects``::

    {"paging": {…, "count_items": …},
     "data": [{"id": …, "name": …, "number": null, …}]}

Die Kunden passen auf eine Seite von 1000; der Abruf laeuft trotzdem ueber alle Seiten,
weil dieselbe Grenze bei den Projekten schon knapp ist.
"""

from __future__ import annotations

from typing import Any

from umsatzprognose.clockodo.client import ClockodoClient
from umsatzprognose.clockodo.nebenlaeufig import synchron
from umsatzprognose.domaene.kunde import Kunde


class KundenRepository:
    """Laedt die Kunden und gibt sie nach ID aus."""

    def __init__(self, client: ClockodoClient) -> None:
        self._client = client

    def laden(self) -> dict[int, Kunde]:
        """Der Abruf, synchron - fuer den Aufruf ausserhalb eines Event-Loops."""
        return synchron(self.laden_async())

    async def laden_async(self) -> dict[int, Kunde]:
        """Derselbe Abruf als Coroutine, damit er neben den anderen laufen kann."""
        daten, _ = await self._client.customers()
        return abbilden(daten)


def abbilden(daten: list[dict[str, Any]]) -> dict[int, Kunde]:
    """Eine ``/v3/customers``-Antwort als Kunden nach ID."""
    return {
        int(eintrag["id"]): Kunde(id=int(eintrag["id"]), name=_name(eintrag))
        for eintrag in daten
        if eintrag.get("id") is not None
    }


def _name(eintrag: dict) -> str | None:
    name = eintrag.get("name")
    return str(name) if name else None
