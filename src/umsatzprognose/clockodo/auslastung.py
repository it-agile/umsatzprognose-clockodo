"""Abbildung der Doppelgruppierung Person x Monat, gefiltert nach Billable-Status, auf
:class:`~umsatzprognose.domaene.auslastung.Auslastungsmonat`.

Form::

    GET /v2/entrygroups?time_since=…&time_until=…&grouping[]=users_id&grouping[]=month
        &filter[billable]=1
    → {"groups": [{"group": "7", "name": "Anna",
                   "duration": 288000, "revenue": 8000.0,
                   "sub_groups": [{"group": "202609", "name": "202609",
                                   "duration": 144000, "revenue": 4000.0,
                                   "grouped_by": "month"}]}]}

* ``filter[billable]`` kennt laut ``BillableDistinct`` der API drei Werte: 0 nicht
  abrechenbar (etwa interne Taetigkeiten), 1 abrechenbar (noch nicht fakturiert),
  2 bereits fakturiert. **Abrechenbar heisst hier 1 und 2 zusammen** - beide sind Zeit,
  die einem Kunden in Rechnung gestellt werden kann oder wurde, der Fakturierungsstand
  selbst ist fuer die Auslastung ohne Belang. Der Filter erlaubt nur einen Wert je
  Abruf, deshalb zwei Abrufe statt eines mit einer Werteliste.
* Aufbau der Antwort sonst wie bei der Projekt-x-Monat-Gruppierung
  (:mod:`.verbrauchsverlauf`): ``group`` der aeusseren Ebene ist hier die Personen-ID,
  ``group`` der Untergruppe der Monat als String ``"JJJJMM"``.
* Eigenstaendiger, additiver Ladepfad, unabhaengig von
  :class:`~umsatzprognose.clockodo.bestand.BestandRepository` - Auslastung ist keiner
  der Bausteine, die die Umsatzprognose braucht, deshalb kein Teil von dessen sieben
  gleichzeitigen Abrufen.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import date

    from umsatzprognose.domaene import Mitarbeiter

    from .client import EntryGroupV2

from umsatzprognose.domaene import Auslastungsmonat
from umsatzprognose.util import Monat, aus_ordnung, monatsfolge, ordnung

from .client import SEKUNDEN_JE_STUNDE, ClockodoClient, verbrauch_bis
from .config import ClockodoCredentials
from .nebenlaeufig import gleichzeitig, synchron

BILLABLE_ABRECHENBAR = 1
BILLABLE_FAKTURIERT = 2


class AuslastungRepository:
    """Laedt den Anteil abrechenbarer Stunden an der verfuegbaren Kapazitaet je Person."""

    def __init__(self, client: ClockodoClient) -> None:
        self._client = client

    @classmethod
    def mit_automatischen_zugangsdaten(cls) -> AuslastungRepository:
        """Zugangsdaten aus Colab-Secrets oder ``.env``, je nach Umgebung."""
        return cls(ClockodoClient(ClockodoCredentials.automatisch()))

    def laden(
        self, mitarbeiter: Mapping[int, Mitarbeiter], *, stichtag: date, monate: int = 12
    ) -> tuple[Auslastungsmonat, ...]:
        """Der Abruf, synchron - fuer den Aufruf ausserhalb eines Event-Loops."""
        return synchron(self.laden_async(mitarbeiter, stichtag=stichtag, monate=monate))

    async def laden_async(
        self, mitarbeiter: Mapping[int, Mitarbeiter], *, stichtag: date, monate: int = 12
    ) -> tuple[Auslastungsmonat, ...]:
        """Die letzten ``monate`` Monate bis einschliesslich des Stichtagsmonats.

        Zwei gleichzeitige Abrufe - abrechenbar und bereits fakturiert - weil
        ``filter[billable]`` nur einen Wert je Abruf zulaesst.
        """
        zeitraum = _letzte_monate(stichtag, monate)
        von = f"{zeitraum[0][0]:04d}-{zeitraum[0][1]:02d}-01T00:00:00Z"
        abrechenbar, fakturiert = await gleichzeitig(
            self._client.entrygroups_je_person_und_monat(
                billable=BILLABLE_ABRECHENBAR, time_since=von, time_until=verbrauch_bis(stichtag)
            ),
            self._client.entrygroups_je_person_und_monat(
                billable=BILLABLE_FAKTURIERT, time_since=von, time_until=verbrauch_bis(stichtag)
            ),
        )
        return self.abbilden(abrechenbar, fakturiert, mitarbeiter, monate=zeitraum)

    @staticmethod
    def abbilden(
        abrechenbar: list[EntryGroupV2],
        fakturiert: list[EntryGroupV2],
        mitarbeiter: Mapping[int, Mitarbeiter],
        *,
        monate: list[Monat],
    ) -> tuple[Auslastungsmonat, ...]:
        """Abrechenbare und fakturierte Stunden je Person und Monat zusammenfassen.

        Personen-IDs ohne bekannten Mitarbeiter (etwa laengst inaktive Accounts, die
        nicht mehr aus ``/v3/users`` geladen wurden) werden uebersprungen, analog zu
        :meth:`~umsatzprognose.clockodo.verbrauchsverlauf.VerbrauchsverlaufRepository.abbilden`.
        Monate ohne jede abrechenbare Buchung fehlen in der Antwort und werden hier mit
        0 aufgefuellt, damit jede Person fuer jeden angefragten Monat einen Wert traegt.
        """
        stunden: dict[tuple[int, Monat], float] = {}
        for gruppen in (abrechenbar, fakturiert):
            for person_gruppe in gruppen:
                try:
                    mitarbeiter_id = int(person_gruppe["group"])
                except (TypeError, ValueError):
                    continue
                for monatsgruppe in person_gruppe.get("sub_groups") or ():
                    schluessel = str(monatsgruppe["group"])
                    monat: Monat = (int(schluessel[:4]), int(schluessel[4:6]))
                    stunden[(mitarbeiter_id, monat)] = (
                        stunden.get((mitarbeiter_id, monat), 0.0)
                        + float(monatsgruppe.get("duration") or 0.0) / SEKUNDEN_JE_STUNDE
                    )

        return tuple(
            Auslastungsmonat(
                mitarbeiter=person,
                jahr=jahr,
                monat=monat_nr,
                abrechenbare_stunden=stunden.get((person.id, (jahr, monat_nr)), 0.0),
            )
            for person in mitarbeiter.values()
            for jahr, monat_nr in monate
        )


def _letzte_monate(stichtag: date, anzahl: int) -> list[Monat]:
    """``anzahl`` Monate bis einschliesslich des Stichtagsmonats, aelteste zuerst."""
    start = aus_ordnung(ordnung(stichtag.year, stichtag.month) - anzahl + 1)
    return monatsfolge(start, anzahl)
