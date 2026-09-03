"""Abbildung der Monatsgruppierung von ``/v2/entrygroups`` auf
:class:`~umsatzprognose.domaene.umsatzhistorie.Umsatzhistorie`.

Form::

    GET /v2/entrygroups?time_since=…&time_until=…&grouping[]=month
    → {"groups": [{"group": "202509", "name": "202509", "duration": 3600000,
                   "revenue": 300000.0, "grouped_by": "month"}]}

* Der Gruppierungswert heisst ``month``, im Singular und ohne ``_id``-Suffix - anders
  als bei Objekten (``projects_id``). ``months`` und ``date`` antworten mit 400.
* ``group`` traegt den Monat als String ``"JJJJMM"``. Bei ``grouping[]=year`` kommt
  stattdessen eine **Zahl**; auf den Typ ist also kein Verlass, deshalb ``str()`` vor
  dem Zerlegen.
* Die Antwort enthaelt **alle** Buchungen des Monats, auch die auf einen Kunden ohne
  Projekt.

Monate ohne Buchungen tauchen in der Antwort nicht auf; aufgefuellt werden sie in
:meth:`~umsatzprognose.domaene.umsatzhistorie.Umsatzhistorie.zum_stichtag`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date

    from .client import ClockodoClient, EntryGroupV2

from umsatzprognose.domaene import Monatsumsatz, Umsatzhistorie

from .client import monatsende
from .nebenlaeufig import synchron

SEKUNDEN_JE_STUNDE = 3600.0


class UmsatzRepository:
    """Laedt den Umsatz je Kalendermonat."""

    def __init__(self, client: ClockodoClient) -> None:
        self._client = client

    def laden(self, stichtag: date, *, abgeschlossene: int = 12) -> Umsatzhistorie:
        """Der Abruf, synchron - fuer den Aufruf ausserhalb eines Event-Loops."""
        return synchron(self.laden_async(stichtag, abgeschlossene=abgeschlossene))

    async def laden_async(self, stichtag: date, *, abgeschlossene: int = 12) -> Umsatzhistorie:
        """Die letzten ``abgeschlossene`` vollen Monate plus den laufenden.

        Das Fenster endet am letzten Tag des laufenden Monats und nicht am Stichtag:
        eine Buchung, die spaeter in diesem Monat datiert ist, gehoert in den laufenden
        Balken. Dass dieser Monat unvollstaendig ist, bleibt davon unberuehrt - die
        Historie fuehrt ihn getrennt.
        """
        monate = await self._client.entrygroups_je_monat(
            time_since=_monatsanfang(stichtag, minus=abgeschlossene),
            time_until=monatsende(stichtag),
        )
        return Umsatzhistorie.zum_stichtag(
            (monatsumsatz(gruppe) for gruppe in monate),
            stichtag,
            abgeschlossene=abgeschlossene,
        )


def monatsumsatz(gruppe: EntryGroupV2) -> Monatsumsatz:
    """Eine Monatsgruppe als :class:`Monatsumsatz`."""
    schluessel = str(gruppe["group"])
    return Monatsumsatz(
        jahr=int(schluessel[:4]),
        monat=int(schluessel[4:6]),
        umsatz=float(gruppe.get("revenue") or 0.0),
        stunden=float(gruppe.get("duration") or 0.0) / SEKUNDEN_JE_STUNDE,
    )


def _monatsanfang(stichtag: date, *, minus: int = 0) -> str:
    jahr, monat = stichtag.year, stichtag.month
    monate_gesamt = jahr * 12 + (monat - 1) - minus
    return f"{monate_gesamt // 12:04d}-{monate_gesamt % 12 + 1:02d}-01T00:00:00Z"
