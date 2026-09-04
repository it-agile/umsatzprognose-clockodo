"""Abbildung von ``/v4/projects`` und ``/v2/entrygroups`` auf
:class:`~umsatzprognose.domaene.projekt.Projekt`.

Hier laufen zwei Antworten zusammen: das Auftragsvolumen aus ``/v4/projects`` und der
Verbrauch samt Personenanteilen aus ``/v2/entrygroups``.

**Projekte**::

    {"paging": {…, "count_items": …},
     "data": [{"id": …, "customers_id": …, "name": …, "active": …, "budget": …}]}

Der Envelope-Key ist ``data`` (nicht ``projects``), die Projekt-ID heisst ``id``.
``budget`` ist immer als Schluessel vorhanden, oft aber ``null``; ist es gesetzt,
entscheiden ``monetary``, ``interval`` und ``from_subprojects`` darueber, ob ``amount``
ein Euro-Gesamtbudget ist - die Deutung steht bei
:data:`~umsatzprognose.domaene.projekt.Budget` und der Funktion :func:`budget` weiter
unten.

``deadline`` (``date``, ``null`` moeglich) und ``automatic_completion`` (``bool``)
gehoeren zusammen: laut Doku wird das Projekt genau dann automatisch zur ``deadline``
abgeschlossen, wenn ``automatic_completion`` gesetzt ist - eine ``deadline`` allein ist
unverbindlich. Siehe
:attr:`~umsatzprognose.domaene.projekt.Projekt.automatischer_abschluss`.

**Entrygroups** - eine Gruppe sieht so aus (Felder gekuerzt, Werte erfunden)::

    {
        "group": "101",
        "name": "Kunde / Projekt",
        "duration": 2160000,
        "revenue": 60000.0,
        "hourly_rate": null,
        "grouped_by": "projects_id",
        "sub_groups": [
            {
                "group": "301",
                "name": "Person",
                "duration": 1620000,
                "revenue": 45000.0,
                "grouped_by": "users_id",
            }
        ],
    }

ACHTUNG:
* **Die Projekt-ID kommt als String**, nicht als Zahl. Bei den Untergruppen ist es
  genauso.
* **``group == 0``** (dort als Zahl) steht fuer Buchungen auf einen Kunden ohne
  Projekt. Ohne Filter entstuende daraus ein Phantom-Projekt 0; der Umsatz wird
  stattdessen als Hinweis gemeldet, damit er nicht unbemerkt verschwindet.
* **``hourly_rate`` ist als effektiver Stundensatz unbrauchbar** - gesetzt nur bei einer
  Minderheit der Gruppen und dort meist 0. Der Satz wird aus ``revenue`` und
  ``duration`` (**Sekunden**) abgeleitet, siehe
  :attr:`~umsatzprognose.domaene.projekt.Projekt.effektiver_stundensatz`.

``revenue`` deckt die ganze Historie ab, sobald die untere Zeitgrenze weit genug liegt
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

    from .client import ClockodoClient, EntryGroupV2, ProjectV4

from collections.abc import Mapping
from datetime import date

from umsatzprognose.domaene import (
    Budget,
    Gesamtbudget,
    Hinweis,
    IntervallBudget,
    KeinBudget,
    Kunde,
    Mitarbeiter,
    Projekt,
    Projektanteil,
    StundenBudget,
    TeilprojektBudget,
)
from umsatzprognose.domaene.zahlen import euro, stunden

from .client import HISTORIE_VON, SEKUNDEN_JE_STUNDE
from .nebenlaeufig import gleichzeitig, synchron


class ProjektRepository:
    """Laedt Projekte samt Verbrauch und Personenanteilen."""

    def __init__(
        self,
        client: ClockodoClient,
        kunden: Mapping[int, Kunde] | None = None,
        mitarbeiter: Mapping[int, Mitarbeiter] | None = None,
    ) -> None:
        self._client = client
        self._kunden = kunden or {}
        self._mitarbeiter = mitarbeiter or {}
        self.hinweise: tuple[Hinweis, ...] = ()

    def laden(
        self,
        *,
        mit_anteilen: bool = True,
        time_since: str = HISTORIE_VON,
        time_until: str | None = None,
    ) -> tuple[Projekt, ...]:
        """Der Abruf, synchron - fuer den Aufruf ausserhalb eines Event-Loops."""
        return synchron(
            self.laden_async(
                mit_anteilen=mit_anteilen, time_since=time_since, time_until=time_until
            )
        )

    async def laden_async(
        self,
        *,
        mit_anteilen: bool = True,
        time_since: str = HISTORIE_VON,
        time_until: str | None = None,
    ) -> tuple[Projekt, ...]:
        """Alle Projekte der Anlage - auch die inaktiven.

        Gefiltert wird nicht hier, sondern in der Domaene
        (:attr:`~umsatzprognose.domaene.projekt.Projekt.im_prognose_scope`): welche
        Projekte in die Prognose eingehen, ist eine fachliche Frage und keine des
        Datenabrufs.

        Args:
            mit_anteilen: auch die Anteile je Person abbilden.
            time_since: untere Grenze des Verbrauchsfensters.
            time_until: obere Grenze; ohne Angabe das Ende des laufenden Monats.
        """
        projekte, gruppen = await rohdaten(
            self._client, time_since=time_since, time_until=time_until
        )
        return self.abbilden(projekte, gruppen, mit_anteilen=mit_anteilen)

    def abbilden(
        self,
        projekte: list[ProjectV4],
        gruppen: list[EntryGroupV2],
        *,
        mit_anteilen: bool = True,
    ) -> tuple[Projekt, ...]:
        """Stammdaten und Verbrauch zu Projekten verrechnen - setzt :attr:`hinweise`.

        Getrennt vom Abruf, weil die Kunden- und Personennamen aus zwei weiteren
        Antworten stammen: so koennen alle Abrufe gleichzeitig laufen und erst hier
        zusammenkommen (siehe :class:`~umsatzprognose.clockodo.bestand.BestandRepository`).
        """
        verbrauch = self._verbrauch(gruppen)

        gebaut = tuple(
            self._projekt(rohprojekt, verbrauch, mit_anteilen=mit_anteilen)
            for rohprojekt in projekte
        )
        self._melde_verbrauch_ohne_projekt(gruppen)
        self._melde_verbrauch_ohne_stammdaten(verbrauch, gebaut)
        return gebaut

    def _projekt(
        self,
        rohprojekt: ProjectV4,
        verbrauch: Mapping[int, dict[str, Any]],
        *,
        mit_anteilen: bool,
    ) -> Projekt:
        projects_id = projekt_id(rohprojekt)
        gebucht = verbrauch.get(projects_id, {})
        customers_id = rohprojekt.get("customers_id")
        name = rohprojekt.get("name")
        return Projekt(
            id=projects_id,
            name=str(name) if name else None,
            kunde=self._kunden.get(int(customers_id)) if customers_id is not None else None,
            aktiv=bool(rohprojekt.get("active")),
            abgeschlossen=bool(rohprojekt.get("completed")),
            budget=budget(rohprojekt),
            verbrauchtes_volumen=float(gebucht.get("revenue", 0.0)),
            verbrauchte_stunden=float(gebucht.get("stunden", 0.0)),
            anteile=self._anteile(gebucht) if mit_anteilen else (),
            automatischer_abschluss=automatischer_abschluss(rohprojekt),
        )

    def _anteile(self, gebucht: Mapping[str, Any]) -> tuple[Projektanteil, ...]:
        anteile = []
        for untergruppe in gebucht.get("sub_groups") or ():
            users_id = int(untergruppe["group"])
            anteile.append(
                Projektanteil(
                    # Eine Person ohne Stammdatensatz bekommt ein Platzhalterobjekt
                    # statt eines KeyError: ein fehlender Name darf keine Stunde kosten.
                    mitarbeiter=self._mitarbeiter.get(users_id, Mitarbeiter(id=users_id)),
                    stunden=float(untergruppe.get("duration") or 0.0) / SEKUNDEN_JE_STUNDE,
                    umsatz=float(untergruppe.get("revenue") or 0.0),
                )
            )
        return tuple(anteile)

    @staticmethod
    def _verbrauch(gruppen: list[EntryGroupV2]) -> dict[int, dict[str, Any]]:
        """``projects_id`` -> Umsatz, Stunden und Untergruppen; ohne ``group == 0``."""
        verbrauch: dict[int, dict[str, Any]] = {}
        for gruppe in gruppen:
            projects_id = int(gruppe["group"])
            if projects_id == 0:
                continue
            # Summiert statt zugewiesen: eine Gruppierung liefert je Projekt eine
            # Gruppe, ein doppelter Schluessel wuerde sonst still eine Zeile verwerfen.
            eintrag = verbrauch.setdefault(
                projects_id, {"revenue": 0.0, "stunden": 0.0, "sub_groups": []}
            )
            eintrag["revenue"] += float(gruppe.get("revenue") or 0.0)
            eintrag["stunden"] += float(gruppe.get("duration") or 0.0) / SEKUNDEN_JE_STUNDE
            eintrag["sub_groups"].extend(gruppe.get("sub_groups") or [])
        return verbrauch

    def _melde_verbrauch_ohne_projekt(self, gruppen: list[EntryGroupV2]) -> None:
        ohne_projekt = [g for g in gruppen if int(g["group"]) == 0]
        umsatz = sum(float(g.get("revenue") or 0.0) for g in ohne_projekt)
        zeit = sum(float(g.get("duration") or 0.0) for g in ohne_projekt) / SEKUNDEN_JE_STUNDE
        if not (umsatz or zeit):
            return
        self.hinweise += (
            Hinweis(
                f"Auf einen Kunden ohne Projekt gebucht: {stunden(zeit)} und "
                f"{euro(umsatz)} - beides gehört keinem Projekt und damit keiner "
                "Prognose an"
            ),
        )

    def _melde_verbrauch_ohne_stammdaten(
        self, verbrauch: Mapping[int, dict[str, Any]], projekte: tuple[Projekt, ...]
    ) -> None:
        bekannt = {p.id for p in projekte}
        verwaist = sorted(set(verbrauch) - bekannt)
        if verwaist:
            self.hinweise += (
                Hinweis(
                    "Gebuchter Umsatz auf Projekte, die es in den Stammdaten nicht gibt",
                    tuple(str(waise) for waise in verwaist),
                ),
            )


def projekt_id(rohprojekt: Mapping[str, Any]) -> int:
    """Die Projekt-ID aus einer ``/v4/projects``-Antwort.

    ``id`` ist verifiziert; ``projects_id`` bleibt als Rueckfalloption, weil aeltere
    API-Generationen diesen Namen verwenden.
    """
    for key in ("id", "projects_id"):
        if key in rohprojekt:
            return int(rohprojekt[key])
    raise KeyError(f"Keine Projekt-ID gefunden, vorhandene Keys: {sorted(rohprojekt)}")


def budget(rohprojekt: ProjectV4) -> Budget:
    """Das Budget eines Projekts - auch wenn ``budget`` ``null`` ist.

    Nimmt wie :func:`projekt_id` das Projekt und nicht das Teilobjekt: beide gehoeren
    zum selben Aufruf, und ein versehentlich uebergebenes Teilobjekt saehe hier wie
    ein Projekt ohne Budget aus.

    Welche Variante entsteht, richtet sich nach dieser Prioritaet: zuerst
    ``monetary``, dann ``interval``, dann ``from_subprojects`` - in der Praxis
    schliessen sich die Flags gegenseitig aus, die Reihenfolge ist also nur fuer den
    theoretischen Kombinationsfall wichtig.
    """
    rohbudget = rohprojekt.get("budget")
    if not isinstance(rohbudget, Mapping):
        return KeinBudget()
    amount = rohbudget.get("amount")
    if amount is None:
        return KeinBudget()
    betrag = float(amount)
    if rohbudget.get("monetary") is False:
        return StundenBudget(stunden=betrag)
    intervall = rohbudget.get("interval")
    if intervall is not None:
        return IntervallBudget(betrag=betrag, intervall=intervall)
    if rohbudget.get("from_subprojects"):
        return TeilprojektBudget(betrag=betrag)
    return Gesamtbudget(betrag=betrag, hart=bool(rohbudget.get("hard")))


def automatischer_abschluss(rohprojekt: ProjectV4) -> date | None:
    """``deadline`` nur, wenn ``automatic_completion`` gesetzt ist - siehe Moduldocstring."""
    rohe_deadline = rohprojekt.get("deadline")
    if not rohe_deadline or not rohprojekt.get("automatic_completion"):
        return None
    return date.fromisoformat(rohe_deadline)


async def rohdaten(
    client: ClockodoClient,
    *,
    time_since: str = HISTORIE_VON,
    time_until: str | None = None,
) -> tuple[list[ProjectV4], list[EntryGroupV2]]:
    """Die beiden Antworten, aus denen ein Projekt entsteht.

    ``/v4/projects`` traegt das Auftragsvolumen, ``/v2/entrygroups`` den Verbrauch; sie
    haengen nicht voneinander ab, treffen sich aber in
    :meth:`ProjektRepository.abbilden` ueber die Projekt-ID.
    """
    (projekte, _), gruppen = await gleichzeitig(
        client.projects(),
        client.entrygroups_je_projekt_und_person(time_since=time_since, time_until=time_until),
    )
    return projekte, gruppen
