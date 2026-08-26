"""Abbildung von ``/v3/users`` und ``/targethours`` auf
:class:`~umsatzprognose.domaene.mitarbeiter.Mitarbeiter`.

**Hier weicht die Umsetzung bewusst von der Spec ab.** Abschnitt 4 nennt
``default_target_hours`` aus ``/v3/users`` als Sollarbeitszeit. Das Feld ist ein
Boolean-Schalter - am 24.08.2026 an allen 59 Personen geprueft: 56 mal ``false``,
3 mal ``true``, ohne Zusammenhang zu ``active``. Es sagt aus, ob die Person die
Standard-Sollzeit der Anlage nutzt, und nicht, wie viel sie arbeitet. Wer es als
Stundenzahl liest, bekommt 0 oder 1.

Die Sollarbeitszeit steht im unversionierten Legacy-Endpunkt ``/targethours``, je
Person und Gueltigkeitszeitraum::

    {"id": 336993, "users_id": 143323, "type": "weekly",
     "date_since": "2023-06-14", "date_until": null,
     "monday": 7, "tuesday": 7, "wednesday": 7, "thursday": 7, "friday": 7,
     "saturday": 0, "sunday": 0, "compensation_daily": 0, "compensation_monthly": 0}

186 Eintraege, alle mit ``type: "weekly"``; 160 davon sind mit ``date_until``
abgeschlossen, die 26 offenen entsprechen genau den 26 aktiven Personen - je eine.
Die Wochenstunden liegen zwischen 20 und 35. Ein anderer ``type`` als ``weekly`` ist
nie aufgetreten und wird deshalb nicht gedeutet, sondern uebersprungen und gemeldet -
raten waere hier besonders teuer, weil eine falsche Sollzeit den Kapazitaetsdeckel
(Spec 5.3) still verschiebt.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from umsatzprognose.clockodo.client import ClockodoClient
from umsatzprognose.clockodo.nebenlaeufig import gleichzeitig, synchron
from umsatzprognose.domaene.hinweis import Hinweis
from umsatzprognose.domaene.mitarbeiter import Mitarbeiter, Wochenarbeitszeit

# Reihenfolge wie in Wochenarbeitszeit.stunden_je_wochentag: Montag zuerst.
WOCHENTAG_FELDER = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
TYP_WOECHENTLICH = "weekly"


class MitarbeiterRepository:
    """Laedt Personen samt ihrer vereinbarten Arbeitszeiten."""

    def __init__(self, client: ClockodoClient) -> None:
        self._client = client
        self.hinweise: tuple[Hinweis, ...] = ()

    def laden(self) -> dict[int, Mitarbeiter]:
        """Der Abruf, synchron - fuer den Aufruf ausserhalb eines Event-Loops."""
        return synchron(self.laden_async())

    async def laden_async(self) -> dict[int, Mitarbeiter]:
        """Personen und Sollzeiten gleichzeitig holen.

        Zwei Endpunkte, aber keine Abhaengigkeit zwischen ihnen: ``/v3/users`` nennt die
        Personen, ``/targethours`` ihre Wochenstunden. Verknuepft werden sie erst hier
        ueber die ``users_id``.
        """
        (personen, _), sollzeiten = await gleichzeitig(
            self._client.users(), self._client.targethours()
        )
        return self.abbilden(personen, sollzeiten)

    def abbilden(
        self, personen: list[dict[str, Any]], sollzeiten: list[dict[str, Any]]
    ) -> dict[int, Mitarbeiter]:
        """Beide Antworten zu Personen nach ID - setzt :attr:`hinweise`."""
        arbeitszeiten = self._arbeitszeiten(sollzeiten)
        return {
            int(person["id"]): Mitarbeiter(
                id=int(person["id"]),
                name=str(person["name"]) if person.get("name") else None,
                aktiv=bool(person.get("active")),
                arbeitszeiten=tuple(arbeitszeiten.get(int(person["id"]), ())),
            )
            for person in personen
            if person.get("id") is not None
        }

    def _arbeitszeiten(
        self, sollzeiten: list[dict[str, Any]]
    ) -> dict[int, list[Wochenarbeitszeit]]:
        je_person: dict[int, list[Wochenarbeitszeit]] = defaultdict(list)
        andere_typen: list[int] = []

        for eintrag in sollzeiten:
            users_id = int(eintrag["users_id"])
            if eintrag.get("type") != TYP_WOECHENTLICH:
                andere_typen.append(users_id)
                continue
            je_person[users_id].append(
                Wochenarbeitszeit(
                    stunden_je_wochentag=tuple(
                        float(eintrag.get(tag) or 0.0) for tag in WOCHENTAG_FELDER
                    ),
                    gueltig_ab=date.fromisoformat(eintrag["date_since"]),
                    gueltig_bis=_datum(eintrag.get("date_until")),
                )
            )

        if andere_typen:
            self.hinweise = (
                Hinweis(
                    "Personen mit einer Sollarbeitszeit, die nicht wöchentlich "
                    "vereinbart ist - ihre Kapazität ist nicht hinterlegt",
                    tuple(sorted(set(andere_typen))),
                ),
            )
        return je_person


def _datum(wert: object) -> date | None:
    return date.fromisoformat(str(wert)) if wert else None
