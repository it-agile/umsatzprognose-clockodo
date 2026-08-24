"""Abbildung von ``/v3/customers`` auf :class:`~umsatzprognose.domaene.kunde.Kunde`.

Der Kundenname ist keine Rechengroesse, sondern Beschriftung - ``/v4/projects`` fuehrt
nur ``customers_id``. Ohne Namen waere eine Tabelle aus 44 Zahlen-IDs nicht pruefbar.

Am 24.08.2026 geprueft, welche Version die Kunden liefert: ``/v4/customers`` antwortet
mit 404 ``RouteNotFound``, ``/v2/customers`` mit 410 ``deprecated``, ``/v3/customers``
mit 200 und derselben Form wie ``/v4/projects``::

    {"paging": {…, "count_items": 324},
     "data": [{"id": 1480229, "name": "//Seibert/Media GmbH", "number": null, …}]}

324 Kunden passen auf eine Seite von 1000; der Abruf laeuft trotzdem ueber alle Seiten,
weil dieselbe Grenze bei den Projekten (895 von 1000) schon knapp ist.
"""

from __future__ import annotations

from umsatzprognose.clockodo.client import ClockodoClient
from umsatzprognose.domaene.kunde import Kunde


class KundenRepository:
    """Laedt die Kunden und gibt sie nach ID aus."""

    def __init__(self, client: ClockodoClient) -> None:
        self._client = client

    def laden(self) -> dict[int, Kunde]:
        daten, _ = self._client.customers()
        return {
            int(eintrag["id"]): Kunde(id=int(eintrag["id"]), name=_name(eintrag))
            for eintrag in daten
            if eintrag.get("id") is not None
        }


def _name(eintrag: dict) -> str | None:
    name = eintrag.get("name")
    return str(name) if name else None
