"""Abbildung von ``/v3/users``, ``/targethours`` und ``/v4/absences`` auf
:class:`~umsatzprognose.domaene.mitarbeiter.Mitarbeiter`.

**Hier weicht die Umsetzung bewusst von der Spec ab.** Abschnitt 4 nennt
``default_target_hours`` aus ``/v3/users`` als Sollarbeitszeit. Das Feld ist ein
Boolean-Schalter - am 24.08.2026 an allen Personen der Installation geprueft, ohne
Zusammenhang zu ``active``. Es sagt aus, ob die Person die Standard-Sollzeit der Anlage
nutzt, und nicht, wie viel sie arbeitet. Wer es als Stundenzahl liest, bekommt 0 oder 1.

Die Sollarbeitszeit steht im unversionierten Legacy-Endpunkt ``/targethours``, je
Person und Gueltigkeitszeitraum::

    {"id": 1, "users_id": 301, "type": "weekly",
     "date_since": "2023-06-14", "date_until": null,
     "monday": 7, "tuesday": 7, "wednesday": 7, "thursday": 7, "friday": 7,
     "saturday": 0, "sunday": 0, "compensation_daily": 0, "compensation_monthly": 0}

Die Historie fuehrt zu jeder Person mehrere Zeilen; abgeschlossene tragen ein
``date_until``, offene nicht. In dieser Anlage hat jede aktive Person genau eine offene
Zeile. Ein anderer ``type`` als ``weekly`` ist nie aufgetreten und wird deshalb nicht
gedeutet, sondern uebersprungen und gemeldet - raten waere hier besonders teuer, weil
eine falsche Sollzeit den Kapazitaetsdeckel (Spec 5.3) still verschiebt.

**Abwesenheiten kommen dazu, ungefiltert.** ``/v4/absences`` nimmt einen Jahresfilter
(``filter[year]``, kein einfacher ``year``-Parameter); wer den Kapazitaetsdeckel spaeter
baut, ruft :meth:`laden_async` deshalb mit den Jahren, die der Horizont ueberspannt.
Ohne ``jahre`` bleibt ``Mitarbeiter.abwesenheiten`` leer - das ist der Stand vor diesem
Schritt und bleibt fuer Aufrufer ohne Kapazitaetsbedarf ohne zusaetzlichen Abruf.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from typing import Any

from umsatzprognose.clockodo.client import ClockodoClient
from umsatzprognose.clockodo.nebenlaeufig import gleichzeitig, synchron
from umsatzprognose.domaene.hinweis import Hinweis
from umsatzprognose.domaene.mitarbeiter import Abwesenheit, Mitarbeiter, Wochenarbeitszeit

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
    """Laedt Personen samt ihrer vereinbarten Arbeitszeiten und Abwesenheiten."""

    def __init__(self, client: ClockodoClient) -> None:
        self._client = client
        self.hinweise: tuple[Hinweis, ...] = ()

    def laden(self, *, jahre: Sequence[int] = ()) -> dict[int, Mitarbeiter]:
        """Der Abruf, synchron - fuer den Aufruf ausserhalb eines Event-Loops."""
        return synchron(self.laden_async(jahre=jahre))

    async def laden_async(self, *, jahre: Sequence[int] = ()) -> dict[int, Mitarbeiter]:
        """Personen, Sollzeiten und Abwesenheiten gleichzeitig holen.

        Drei Zwecke, keine Abhaengigkeit zwischen ihnen: ``/v3/users`` nennt die
        Personen, ``/targethours`` ihre Wochenstunden, ``/v4/absences`` ihre geplanten
        Abwesenheiten - je ein Abruf pro Jahr in ``jahre``. Verknuepft werden alle drei
        erst hier ueber die ``users_id``.

        Args:
            jahre: die Kalenderjahre, fuer die Abwesenheiten geladen werden - der
                Aufrufer kennt den Horizont, hier ist er nicht bekannt. Leer bleibt
                ``Mitarbeiter.abwesenheiten`` ungeladen, ohne zusaetzlichen Abruf.
        """
        (personen, _), sollzeiten, abwesenheiten_je_jahr = await gleichzeitig(
            self._client.users(),
            self._client.targethours(),
            gleichzeitig(*(self._client.absences(jahr) for jahr in jahre)),
        )
        abwesenheiten = [eintrag for jahr in abwesenheiten_je_jahr for eintrag in jahr]
        return self.abbilden(personen, sollzeiten, abwesenheiten)

    def abbilden(
        self,
        personen: list[dict[str, Any]],
        sollzeiten: list[dict[str, Any]],
        abwesenheiten: list[dict[str, Any]] = (),
    ) -> dict[int, Mitarbeiter]:
        """Alle drei Antworten zu Personen nach ID - setzt :attr:`hinweise`."""
        arbeitszeiten = self._arbeitszeiten(sollzeiten)
        abwesenheiten_je_person = self._abwesenheiten(abwesenheiten)
        return {
            int(person["id"]): Mitarbeiter(
                id=int(person["id"]),
                name=str(person["name"]) if person.get("name") else None,
                aktiv=bool(person.get("active")),
                arbeitszeiten=tuple(arbeitszeiten.get(int(person["id"]), ())),
                abwesenheiten=tuple(abwesenheiten_je_person.get(int(person["id"]), ())),
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

    def _abwesenheiten(self, abwesenheiten: list[dict[str, Any]]) -> dict[int, list[Abwesenheit]]:
        """Rohe Abwesenheiten zu Personen - ungefiltert nach Typ und Status.

        Welche Typen und Status als Kapazitaetsabzug zaehlen, ist Teil des noch zu
        bauenden Deckels (Spec 5.3) und wird hier nicht entschieden - siehe
        :mod:`umsatzprognose.domaene.mitarbeiter`.
        """
        je_person: dict[int, list[Abwesenheit]] = defaultdict(list)
        for eintrag in abwesenheiten:
            users_id = int(eintrag["users_id"])
            je_person[users_id].append(
                Abwesenheit(
                    mitarbeiter_id=users_id,
                    beginnt=date.fromisoformat(eintrag["date_since"]),
                    endet=date.fromisoformat(eintrag["date_until"]),
                    typ=int(eintrag["type"]),
                    status=int(eintrag["status"]),
                )
            )
        return je_person


def _datum(wert: object) -> date | None:
    return date.fromisoformat(str(wert)) if wert else None
