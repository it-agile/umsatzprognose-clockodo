"""Lesbare Bezeichnungen je Projekt - Kundenname und Projektname.

Keine Groesse der Spec, sondern reine Beschriftung: die Rechenwege arbeiten mit
``projects_id``, eine Tabelle mit 44 Zahlen-IDs ist aber nicht pruefbar. Deshalb steht
das hier getrennt von den Rechenmodulen und geht nur in die Darstellung ein
(:mod:`umsatzprognose.tabellen`).

Der Projektname steht in ``/v4/projects`` (``name``), der Kundenname nicht - dort gibt
es nur ``customers_id``. Am 24.08.2026 gegen die Installation geprueft, welcher
Endpunkt die Kunden liefert:

* ``/v4/customers`` -> 404 ``RouteNotFound``
* ``/v2/customers`` -> 410 ``This API version has been deprecated``
* ``/v3/customers`` -> 200, Form wie ``/v4/projects``::

      {"paging": {"items_per_page": 1000, "current_page": 1, "count_pages": 1,
                  "count_items": 324},
       "data": [{"id": 1480229, "name": "//Seibert/Media GmbH", "number": null, …}]}

Bei 324 Kunden und einer Standardseite von 1000 passt das derzeit auf eine Seite;
:meth:`umsatzprognose.api.ClockodoClient.customers` laeuft trotzdem ueber alle Seiten,
weil dieselbe Grenze bei den Projekten (895 von 1000) schon knapp ist.

Alle 895 Projekte tragen einen ``name`` und eine ``customers_id``, die sich in den 324
Kunden aufloest - Luecken sind also nicht der Regelfall. Sie brechen hier trotzdem
nichts: eine fehlende Beschriftung bleibt ``None`` und faellt in der Tabelle als leere
Zelle auf, statt einen Abruf mit einem ``KeyError`` zu beenden.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from umsatzprognose.auftragsvolumen import projekt_id


@dataclass(frozen=True)
class ProjektBezeichnung:
    """Kunden- und Projektname eines Projekts, jeweils ``None`` wenn unbekannt."""

    kunde: str | None
    projekt: str | None


def kundennamen(kunden: Iterable[Mapping[str, object]]) -> dict[int, str]:
    """Bildet ``customers_id -> name`` aus der ``data``-Liste von ``/v3/customers`` ab."""
    return {
        int(kunde["id"]): str(kunde["name"])
        for kunde in kunden
        if kunde.get("id") is not None and kunde.get("name")
    }


def bezeichnungen_je_projekt(
    projekte: Iterable[Mapping[str, object]],
    kunden: Iterable[Mapping[str, object]],
) -> dict[int, ProjektBezeichnung]:
    """Bildet ``projects_id -> `` :class:`ProjektBezeichnung` ab.

    Args:
        projekte: die ``data``-Liste aus ``/v4/projects``.
        kunden: die ``data``-Liste aus ``/v3/customers``.

    Returns:
        Ein Eintrag je Projekt - ohne Filter auf ``active``, damit dieselbe Zuordnung
        fuer jede Auswahl von Projekten taugt. Namen, die sich nicht aufloesen lassen,
        sind ``None``.
    """
    namen = kundennamen(kunden)
    bezeichnungen: dict[int, ProjektBezeichnung] = {}

    for projekt in projekte:
        customers_id = projekt.get("customers_id")
        kunde = namen.get(int(customers_id)) if customers_id is not None else None
        name = projekt.get("name")
        bezeichnungen[projekt_id(projekt)] = ProjektBezeichnung(
            kunde=kunde,
            projekt=str(name) if name else None,
        )

    return bezeichnungen
