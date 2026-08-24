"""Abbildung von ``/v4/projects`` und ``/v2/entrygroups`` auf
:class:`~umsatzprognose.domaene.projekt.Projekt`.

Hier laufen zwei Antworten zusammen: das Auftragsvolumen aus ``/v4/projects`` und der
Verbrauch samt Personenanteilen aus ``/v2/entrygroups``.

**Projekte** (verifiziert am 24.08.2026 an 895 Projekten)::

    {"paging": {…, "count_items": 895},
     "data": [{"id": …, "customers_id": …, "name": …, "active": …, "budget": …}]}

Der Envelope-Key ist ``data`` (nicht ``projects``), die Projekt-ID heisst ``id``.
``budget`` ist immer als Schluessel vorhanden, bei 236 Projekten aber ``null``; ist es
gesetzt, entscheiden ``monetary``, ``interval`` und ``from_subprojects`` darueber, ob
``amount`` ein Euro-Gesamtbudget ist - die Deutung steht bei
:class:`~umsatzprognose.domaene.projekt.Budget`.

**Entrygroups** - eine Gruppe sieht so aus (Felder gekuerzt)::

    {"group": "1375839", "name": "Kunde / Projekt", "duration": 27314640,
     "revenue": 1132440.7, "hourly_rate": null, "grouped_by": "projects_id",
     "sub_groups": [{"group": "143323", "name": "Carmen Rudolph", "duration": 4111200,
                     "revenue": 0, "grouped_by": "users_id"}]}

Drei Fallen darin, alle an den 870 Gruppen dieser Installation belegt:

* **Die Projekt-ID kommt als String** (``"1375839"``), nicht als Zahl. Bei den
  Untergruppen ist es genauso.
* **``group == 0``** (dort als Zahl) steht fuer Buchungen auf einen Kunden ohne
  Projekt. Ohne Filter entstuende daraus ein Phantom-Projekt 0; der Umsatz wird
  stattdessen als Hinweis gemeldet, damit er nicht unbemerkt verschwindet.
* **``hourly_rate`` ist als effektiver Stundensatz unbrauchbar** - gesetzt nur bei 92
  von 870 Gruppen und dort meist 0. Der Satz wird aus ``revenue`` und ``duration``
  (**Sekunden**) abgeleitet, siehe
  :attr:`~umsatzprognose.domaene.projekt.Projekt.effektiver_stundensatz`.

``revenue`` deckt die ganze Historie ab, sobald die untere Zeitgrenze weit genug liegt:
``time_since=2010-01-01`` liefert dieselben 870 Gruppen und dieselbe Umsatzsumme wie
``2020-01-01``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from umsatzprognose.clockodo.client import HISTORIE_BIS, HISTORIE_VON, ClockodoClient
from umsatzprognose.domaene.hinweis import Hinweis
from umsatzprognose.domaene.kunde import Kunde
from umsatzprognose.domaene.mitarbeiter import Mitarbeiter
from umsatzprognose.domaene.projekt import Budget, Projekt
from umsatzprognose.domaene.projektanteil import Projektanteil
from umsatzprognose.domaene.zahlen import euro, stunden

SEKUNDEN_JE_STUNDE = 3600.0


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
        time_until: str = HISTORIE_BIS,
    ) -> tuple[Projekt, ...]:
        """Alle Projekte der Anlage - auch die inaktiven.

        Gefiltert wird nicht hier, sondern in der Domaene
        (:attr:`~umsatzprognose.domaene.projekt.Projekt.im_prognose_scope`): welche
        Projekte in die Prognose eingehen, ist eine fachliche Frage und keine des
        Datenabrufs.

        Args:
            mit_anteilen: auch die Anteile je Person laden. Kostet nichts extra an
                Requests, aber Zeit: die Antwort waechst von rund 800 KB auf 1,9 MB
                und braucht etwa 20 statt 10 Sekunden.
        """
        projekte, _ = self._client.projects()
        gruppen = self._client.entrygroups_je_projekt_und_person(
            time_since=time_since, time_until=time_until
        )
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
        rohprojekt: Mapping[str, Any],
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
    def _verbrauch(gruppen: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
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

    def _melde_verbrauch_ohne_projekt(self, gruppen: list[dict[str, Any]]) -> None:
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
                    tuple(verwaist),
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


def budget(rohprojekt: Mapping[str, Any]) -> Budget:
    """Das Budget eines Projekts - auch wenn ``budget`` ``null`` ist.

    Nimmt wie :func:`projekt_id` das Projekt und nicht das Teilobjekt: beide gehoeren
    zum selben Aufruf, und ein versehentlich uebergebenes Teilobjekt saehe hier wie
    ein Projekt ohne Budget aus - eine still zu niedrige Zahl.
    """
    rohbudget = rohprojekt.get("budget")
    if not isinstance(rohbudget, Mapping):
        return Budget()
    return Budget(
        betrag=None if rohbudget.get("amount") is None else float(rohbudget["amount"]),
        monetaer=rohbudget.get("monetary") is not False,
        hart=bool(rohbudget.get("hard")),
        intervall=rohbudget.get("interval"),
        aus_teilprojekten=bool(rohbudget.get("from_subprojects")),
    )
