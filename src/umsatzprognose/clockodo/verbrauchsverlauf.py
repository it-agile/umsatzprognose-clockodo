"""Abbildung der Doppelgruppierung Projekt x Monat auf
:class:`~umsatzprognose.domaene.verbrauchsverlauf.Verbrauchsverlauf`.

Der Abruf, den Spec 11.1 fuer die Abrufquote-Verteilung verlangt. Am 26.08.2026 gegen
die Installation geprueft::

    GET /v2/entrygroups?time_since=…&time_until=…&grouping[]=projects_id&grouping[]=month
    → {"groups": [{"group": "1231087", "name": "it-agile GmbH / Moneypenny",
                   "duration": 4360500, "revenue": 0,
                   "sub_groups": [{"group": "202606", "name": "202606",
                                   "duration": 1755900, "revenue": 0,
                                   "restrictions": {"projects_id": "1231087"},
                                   "grouped_by": "month"}]}]}

870 Gruppen mit zusammen 5.467 Projekt-Monaten, 01/2021 bis 11/2026, rund 23 Sekunden.
Was dabei aufgefallen ist:

* **Die Monate kommen nach Dauer absteigend**, nicht chronologisch - bei allen 667
  Gruppen mit mehr als einem Monat, ohne Ausnahme. Die Rueckrechnung des Restvolumens
  aus Spec 5.2 lebt von der Reihenfolge, sortiert wird deshalb beim Bauen des Verlaufs.
  Bei der Personengruppierung fiel das nie auf, weil Personen keine Reihenfolge haben.
* **Der Monat kommt als String** ``"JJJJMM"``, wie bei der einfachen Monatsgruppierung.
  Gelesen wird er darum mit derselben Funktion (:func:`.umsatz.monatsumsatz`).
* **Die Monatssummen gehen nur auf den Cent auf.** Bei 31 Projekten weicht die Summe der
  Monate von der Projektsumme ab, um hoechstens 0,06 EUR und in der Gesamtsumme um
  0,63 EUR auf 30,6 Mio. - Clockodo rundet jede Gruppe einzeln. Die Zeitsummen stimmen
  exakt. Ein Vergleich auf Gleichheit waere hier also ein Fehlalarm.
* **Die Projektsummen sind mit der einfachen Gruppierung identisch**, ueber alle 870
  Gruppen ohne Abweichung - dieselbe Zusicherung wie bei der Personengruppierung.
* **``group == 0`` kommt mehrfach vor** - zweimal in dieser Anlage, je Kunde ohne
  Projekt einmal, und das ist der einzige mehrfach vergebene Schluessel (869
  verschiedene auf 870 Gruppen). Buchungen ohne Projekt gehoeren keinem Budget an und
  damit keiner Abrufquote; gemeldet werden sie bereits von
  :class:`~umsatzprognose.clockodo.projekte.ProjektRepository`. Zusammengefasst wird
  trotzdem je Projekt-ID: bei einem echten Projekt waere ein doppelter Schluessel sonst
  ein zweiter Verlauf und damit dieselben Monate zweimal in der Verteilung.

Das Fenster reicht bis zum **Ende des Horizonts** und nicht bis zum Stichtag: dieselbe
Antwort traegt laut Spec 11.1 die bereits gebuchten Betraege der Horizontmonate, die
Untergrenze der Bandbreite aus 5.4. Welche Monate davon Historie sind, entscheidet die
Domaene am Stichtag, nicht der Abruf.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date
from typing import Any

from umsatzprognose.clockodo.client import HISTORIE_VON, ClockodoClient, horizontende
from umsatzprognose.clockodo.nebenlaeufig import synchron
from umsatzprognose.clockodo.umsatz import monatsumsatz
from umsatzprognose.domaene.projekt import Projekt
from umsatzprognose.domaene.verbrauchsverlauf import Verbrauchsverlauf


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
    ) -> tuple[Verbrauchsverlauf, ...]:
        """Der Abruf, synchron - fuer den Aufruf ausserhalb eines Event-Loops."""
        return synchron(
            self.laden_async(
                projekte,
                stichtag=stichtag,
                horizont_monate=horizont_monate,
                time_since=time_since,
            )
        )

    async def laden_async(
        self,
        projekte: Iterable[Projekt],
        *,
        stichtag: date | None = None,
        horizont_monate: int = 3,
        time_since: str = HISTORIE_VON,
    ) -> tuple[Verbrauchsverlauf, ...]:
        """Die Verlaeufe zu den uebergebenen Projekten.

        Args:
            projekte: die Projekte, deren Verlauf gebaut wird. Sie tragen das Budget,
                ohne das sich kein Restvolumen zurueckrechnen laesst.
            stichtag: bestimmt ueber den Horizont die obere Zeitgrenze; ohne Angabe
                heute.
            horizont_monate: Laenge des Prognosehorizonts (Spec 5.4: 1 bis 3).
            time_since: untere Grenze der Historie.
        """
        gruppen = await rohdaten(
            self._client,
            stichtag=stichtag,
            horizont_monate=horizont_monate,
            time_since=time_since,
        )
        return self.abbilden(gruppen, projekte)

    @staticmethod
    def abbilden(
        gruppen: list[dict[str, Any]], projekte: Iterable[Projekt]
    ) -> tuple[Verbrauchsverlauf, ...]:
        """Die Antwort auf die Projekte verteilen - groesster Verbrauch zuerst.

        Projekte ohne jede Buchung kommen in der Antwort nicht vor und bekommen auch
        keinen leeren Verlauf: ohne einen einzigen gebuchten Monat gibt es kein
        Beobachtungsfenster (Spec 5.2), und ein leerer Verlauf saehe wie ein Projekt
        aus, das nichts abgerufen hat.
        """
        nach_id: Mapping[int, Projekt] = {projekt.id: projekt for projekt in projekte}
        untergruppen: dict[int, list[dict[str, Any]]] = {}
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
) -> list[dict[str, Any]]:
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
    )
