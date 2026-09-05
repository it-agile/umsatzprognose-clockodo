"""Abbildung der Doppelgruppierung Projekt x Monat auf
:class:`~umsatzprognose.domaene.verbrauchsverlauf.Verbrauchsverlauf`.

Form::

    GET /v2/entrygroups?time_since=…&time_until=…&grouping[]=projects_id&grouping[]=month
    → {"groups": [{"group": "101", "name": "Kunde / Projekt",
                   "duration": 2340000, "revenue": 65000.0,
                   "sub_groups": [{"group": "202606", "name": "202606",
                                   "duration": 720000, "revenue": 20000.0,
                                   "restrictions": {"projects_id": "101"},
                                   "grouped_by": "month"}]}]}

* **Die Monate kommen nach Dauer absteigend**, nicht chronologisch - bei jeder Gruppe
  mit mehr als einem Monat, ohne Ausnahme. Die Rueckrechnung des Restvolumens
  lebt von der Reihenfolge, sortiert wird deshalb beim Bauen des Verlaufs.
* **Der Monat kommt als String** ``"JJJJMM"``, wie bei der einfachen Monatsgruppierung.
  Gelesen wird er darum mit derselben Funktion (:func:`.umsatz.monatsumsatz`).
* **Die Monatssummen gehen nur auf den Cent auf.** Bei einer Reihe von Projekten weicht
  die Summe der Monate von der Projektsumme um Cent-Betraege ab - Clockodo rundet jede
  Gruppe einzeln. Die Zeitsummen stimmen exakt.
* **Die Projektsummen sind mit der einfachen Gruppierung identisch**, ueber alle
  Gruppen ohne Abweichung - dieselbe Zusicherung wie bei der Personengruppierung.
* **``group == 0`` kommt mehrfach vor** - je Kunde ohne Projekt einmal, und das ist der
  einzige mehrfach vergebene Schluessel. Buchungen ohne Projekt gehoeren keinem Budget
  an und damit keiner Abrufquote; gemeldet werden sie bereits von
  :class:`~umsatzprognose.clockodo.projekte.ProjektRepository`. Zusammengefasst wird
  trotzdem je Projekt-ID: bei einem echten Projekt waere ein doppelter Schluessel sonst
  ein zweiter Verlauf und damit dieselben Monate zweimal in der Verteilung.

Das Fenster reicht bis zum **Ende des Horizonts** und nicht bis zum Stichtag: dieselbe
Antwort traegt die bereits gebuchten Betraege der Horizontmonate, die
Untergrenze der Bandbreite. Welche Monate davon Historie sind, entscheidet die
Domaene am Stichtag, nicht der Abruf.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from umsatzprognose.domaene import Projekt

    from .client import ClockodoClient, EntryGroupV2

from datetime import date

from umsatzprognose.domaene import Verbrauchsverlauf

from .client import HISTORIE_VON, horizontende
from .nebenlaeufig import synchron
from .umsatz import monatsumsatz


class VerbrauchsverlaufRepository:
    """Laedt je Projekt den monatlichen Verbrauch."""

    def __init__(self, client: ClockodoClient) -> None:
        self._client = client

    def laden(
        self,
        projekte: Iterable[Projekt],
        *,
        stichtag: date | None = None,
        horizont_monate: int = 3,
        time_since: str = HISTORIE_VON,
        cache_cutoff_monate: int | None = None,
    ) -> tuple[Verbrauchsverlauf, ...]:
        """Der Abruf, synchron - fuer den Aufruf ausserhalb eines Event-Loops."""
        return synchron(
            self.laden_async(
                projekte,
                stichtag=stichtag,
                horizont_monate=horizont_monate,
                time_since=time_since,
                cache_cutoff_monate=cache_cutoff_monate,
            )
        )

    async def laden_async(
        self,
        projekte: Iterable[Projekt],
        *,
        stichtag: date | None = None,
        horizont_monate: int = 3,
        time_since: str = HISTORIE_VON,
        cache_cutoff_monate: int | None = None,
    ) -> tuple[Verbrauchsverlauf, ...]:
        """Die Verlaeufe zu den uebergebenen Projekten.

        Args:
            projekte: die Projekte, deren Verlauf gebaut wird. Sie tragen das Budget,
                ohne das sich kein Restvolumen zurueckrechnen laesst.
            stichtag: bestimmt ueber den Horizont die obere Zeitgrenze; ohne Angabe
                heute.
            horizont_monate: Laenge des Prognosehorizonts.
            time_since: untere Grenze der Historie.
            cache_cutoff_monate: siehe
                :meth:`~umsatzprognose.clockodo.client.ClockodoClient.entrygroups_je_projekt_und_monat`.
        """
        gruppen = await rohdaten(
            self._client,
            stichtag=stichtag,
            horizont_monate=horizont_monate,
            time_since=time_since,
            cache_cutoff_monate=cache_cutoff_monate,
        )
        return self.abbilden(gruppen, projekte)

    @staticmethod
    def abbilden(
        gruppen: list[EntryGroupV2], projekte: Iterable[Projekt]
    ) -> tuple[Verbrauchsverlauf, ...]:
        """Die Antwort auf die Projekte verteilen - groesster Verbrauch zuerst.

        Projekte ohne jede Buchung kommen in der Antwort nicht vor und bekommen auch
        keinen leeren Verlauf: ohne einen einzigen gebuchten Monat gibt es kein
        Beobachtungsfenster, und ein leerer Verlauf saehe wie ein Projekt
        aus, das nichts abgerufen hat.
        """
        nach_id: Mapping[int, Projekt] = {projekt.id: projekt for projekt in projekte}
        untergruppen: dict[int, list[EntryGroupV2]] = {}
        for gruppe in gruppen:
            projects_id = int(gruppe["group"])
            # group == 0 sind Buchungen auf einen Kunden ohne Projekt: kein Budget, kein
            # Restvolumen, keine Abrufquote. Unbekannte IDs meldet das ProjektRepository.
            if projects_id == 0 or projects_id not in nach_id:
                continue
            untergruppen.setdefault(projects_id, []).extend(gruppe.get("sub_groups") or ())

        verlaeufe = [
            Verbrauchsverlauf.fuer(
                nach_id[projects_id],
                (monatsumsatz(untergruppe) for untergruppe in gefunden),
            )
            for projects_id, gefunden in untergruppen.items()
        ]
        return tuple(sorted(verlaeufe, key=lambda v: v.verbrauch, reverse=True))


async def rohdaten(
    client: ClockodoClient,
    *,
    stichtag: date | None = None,
    horizont_monate: int = 3,
    time_since: str = HISTORIE_VON,
    cache_cutoff_monate: int | None = None,
) -> list[EntryGroupV2]:
    """Nur die Antwort - damit der Abruf neben den anderen laufen kann.

    Getrennt von :meth:`VerbrauchsverlaufRepository.abbilden`, weil die Verlaeufe die
    fertigen Projekte brauchen: das Budget entscheidet ueber das Restvolumen. Der Abruf
    selbst haengt von nichts ab und gehoert deshalb in dasselbe Fach wie die uebrigen
    (:class:`~umsatzprognose.clockodo.bestand.BestandRepository`). Eine freie Funktion
    wie :func:`umsatzprognose.clockodo.projekte.rohdaten` und keine Methode: hier ist
    kein Repository im Spiel, nur ein Request.
    """
    return await client.entrygroups_je_projekt_und_monat(
        time_since=time_since,
        time_until=horizontende(stichtag or date.today(), horizont_monate),
        cache_cutoff_monate=cache_cutoff_monate,
    )
