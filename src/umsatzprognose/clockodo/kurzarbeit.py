"""Abbildung der Rohdaten fuer den Baustein Kurzarbeitsbereitschaft auf
:class:`~umsatzprognose.domaene.kurzarbeit.Personenmonat`.

**Fachlich blind**: dieses Modul weiss nichts von Rollen,
Schwellenwerten oder der Regel selbst - siehe :mod:`umsatzprognose.domaene.kurzarbeit`
fuer beides.

Fuenf gleichzeitige Abrufe je Zeitfenster (``billable`` kennt nur einen Wert je Abruf,
siehe :mod:`.auslastung`): Personen (``/v3/users``), intern (``billable=0``), extern
(``billable=1`` und ``=2``, ueber
:func:`~umsatzprognose.clockodo.client.stunden_je_person_und_monat` zusammengefasst)
und ein ungefilterter Abruf zur Konsistenzpruefung. Dazu je in
den angefragten Monaten vorkommendem Jahr ein ``/userreports``-Abruf.

**Der kumulierte Ueberstundenstand wird selbst gebildet**, nicht direkt aus
``month_details[].diff`` gelesen: live gegen die echte API verifiziert, ist ``diff``
dort **nicht** kumuliert,
sondern nur die Abweichung des einzelnen Monats. Der Stand zum Ende eines Zielmonats
ist deshalb ``overtime_carryover`` (Saldo zum Jahresbeginn) plus die Summe aller
``month_details[].diff``-Werte von Monat 1 bis einschliesslich des Zielmonats -
gueltig, weil ein Zielmonat und seine Vormonate innerhalb desselben, ueber ``year``
abgefragten Kalenderjahres liegen.
"""

from __future__ import annotations

import json
from datetime import date
from functools import partial
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from umsatzprognose.util import Monat

    from .client import EntryGroupV2, UserReportV1, UserV3
    from .fortschritt import Fortschritt

from dotenv import load_dotenv

from umsatzprognose.domaene.kurzarbeit import Personenmonat, Rollenzuordnung
from umsatzprognose.util import (
    aus_ordnung,
    colab_secret,
    in_colab,
    monatsfolge,
    ordnung,
    umgebungsvariable,
    umgebungsvariable_bool,
    vormonat,
)

from .client import (
    GRUPPIERUNG_MONAT,
    GRUPPIERUNG_PERSON,
    ClockodoClient,
    monatsende,
    stunden_je_person_und_monat,
)
from .config import ClockodoCredentials, MissingCredentialsError
from .nebenlaeufig import gleichzeitig, mit_meldung, synchron

BILLABLE_INTERN = 0
BILLABLE_ABRECHENBAR = 1
BILLABLE_FAKTURIERT = 2

ROLLENZUORDNUNG_VAR = "KURZARBEIT_ROLLENZUORDNUNG"
KURZARBEIT_AKTIV_VAR = "KURZARBEIT_AKTIV"

# Personen, interne/abrechenbare/fakturierte Stunden, Gesamtstunden - die fuenf
# gleichzeitigen Zweige in KurzarbeitRepository.laden_async(), die unabhaengig von
# anzahl_monate immer genau einmal fortschritt() melden (siehe dort und
# anzahl_ladeschritte() unten).
ANZAHL_FESTER_LADESCHRITTE = 5


class KurzarbeitRepository:
    """Laedt die Personenmonat-Rohdaten fuer den Baustein Kurzarbeitsbereitschaft."""

    def __init__(self, client: ClockodoClient) -> None:
        self._client = client

    @classmethod
    def mit_automatischen_zugangsdaten(cls) -> KurzarbeitRepository:
        """Zugangsdaten aus Colab-Secrets oder ``.env``, je nach Umgebung."""
        return cls(ClockodoClient(ClockodoCredentials.automatisch()))

    def laden(
        self, *, stichtag: date, anzahl_monate: int = 1, fortschritt: Fortschritt | None = None
    ) -> dict[Monat, tuple[Personenmonat, ...]]:
        """Der Abruf, synchron - fuer den Aufruf ausserhalb eines Event-Loops."""
        return synchron(
            self.laden_async(
                stichtag=stichtag, anzahl_monate=anzahl_monate, fortschritt=fortschritt
            )
        )

    async def laden_async(
        self, *, stichtag: date, anzahl_monate: int = 1, fortschritt: Fortschritt | None = None
    ) -> dict[Monat, tuple[Personenmonat, ...]]:
        """Die letzten ``anzahl_monate`` **abgeschlossenen** Monate - der laufende
        Monat wird nie bewertet.

        ``fortschritt``, sofern angegeben, meldet sich je einem der fuenf
        gleichzeitigen Zweige (Personen, interne/abrechenbare/fakturierte Stunden,
        Gesamtstunden) sowie je ``/userreports``-Abruf, sobald genau *dieser* Zweig
        fertig ist - nicht erst, wenn alle fertig sind (siehe
        :func:`~.nebenlaeufig.mit_meldung`).
        """
        monate = _abgeschlossene_monate(stichtag, anzahl_monate)
        von = f"{monate[0][0]:04d}-{monate[0][1]:02d}-01T00:00:00Z"
        bis = _monatsende_des_letzten_monats(monate)
        jahre = sorted({jahr for jahr, _ in monate})

        (
            (benutzer, _),
            intern,
            abrechenbar,
            fakturiert,
            ungefiltert,
            *userreports_je_jahr,
        ) = await gleichzeitig(
            mit_meldung(self._client.users(), "Personen geladen", fortschritt),
            mit_meldung(
                self._client.entrygroups_je_person_und_monat(
                    billable=BILLABLE_INTERN, time_since=von, time_until=bis
                ),
                "Interne Stunden geladen",
                fortschritt,
            ),
            mit_meldung(
                self._client.entrygroups_je_person_und_monat(
                    billable=BILLABLE_ABRECHENBAR, time_since=von, time_until=bis
                ),
                "Abrechenbare Stunden geladen",
                fortschritt,
            ),
            mit_meldung(
                self._client.entrygroups_je_person_und_monat(
                    billable=BILLABLE_FAKTURIERT, time_since=von, time_until=bis
                ),
                "Fakturierte Stunden geladen",
                fortschritt,
            ),
            mit_meldung(
                self._client.entrygroups(
                    [GRUPPIERUNG_PERSON, GRUPPIERUNG_MONAT], time_since=von, time_until=bis
                ),
                "Gesamtstunden geladen",
                fortschritt,
            ),
            *(
                mit_meldung(
                    self._client.userreports(year=jahr),
                    f"Überstundenstand {jahr} geladen",
                    fortschritt,
                )
                for jahr in jahre
            ),
        )
        userreports_nach_jahr = dict(zip(jahre, userreports_je_jahr, strict=True))

        return self.abbilden(
            benutzer,
            intern=intern,
            extern=stunden_je_person_und_monat(abrechenbar, fakturiert),
            gesamt=stunden_je_person_und_monat(ungefiltert),
            userreports_nach_jahr=userreports_nach_jahr,
            monate=monate,
        )

    @staticmethod
    def abbilden(
        benutzer: list[UserV3],
        *,
        intern: list[EntryGroupV2],
        extern: dict[tuple[int, Monat], float],
        gesamt: dict[tuple[int, Monat], float],
        userreports_nach_jahr: dict[int, list[UserReportV1]],
        monate: list[Monat],
    ) -> dict[Monat, tuple[Personenmonat, ...]]:
        """Baut je Person aus ``/v3/users`` und je angefragtem Monat einen
        :class:`Personenmonat` - unabhaengig davon, ob ueberhaupt Stunden gebucht
        wurden (um "keine gebuchte Stunde" von "nicht in der Antwort" unterscheiden
        zu koennen)."""
        interne_stunden = stunden_je_person_und_monat(intern)
        ueberstunden = _ueberstundenstaende(userreports_nach_jahr, monate=monate)

        ergebnis: dict[Monat, list[Personenmonat]] = {monat: [] for monat in monate}
        for person in benutzer:
            mitarbeiter_id = person["id"]
            name = person.get("name")
            for monat in monate:
                schluessel = (mitarbeiter_id, monat)
                ergebnis[monat].append(
                    Personenmonat(
                        mitarbeiter_id=mitarbeiter_id,
                        name=name,
                        jahr=monat[0],
                        monat=monat[1],
                        interne_stunden=interne_stunden.get(schluessel, 0.0),
                        externe_stunden=extern.get(schluessel, 0.0),
                        gesamt_stunden=gesamt.get(schluessel, 0.0),
                        ueberstundenstand=ueberstunden.get(schluessel),
                    )
                )
        return {monat: tuple(personen) for monat, personen in ergebnis.items()}


def _abgeschlossene_monate(stichtag: date, anzahl: int) -> list[Monat]:
    """``anzahl`` abgeschlossene Monate bis einschliesslich des Vormonats des
    Stichtags, aelteste zuerst - der Stichtagsmonat selbst wird nie bewertet."""
    letzter = vormonat(stichtag.year, stichtag.month)
    start = aus_ordnung(ordnung(*letzter) - anzahl + 1)
    return monatsfolge(start, anzahl)


def anzahl_ladeschritte(stichtag: date, anzahl_monate: int) -> int:
    """Wie viele ``fortschritt()``-Meldungen :meth:`KurzarbeitRepository.laden_async`
    fuer diese Parameter insgesamt absetzt: die fuenf festen Zweige
    (:data:`ANZAHL_FESTER_LADESCHRITTE`) plus ein ``/userreports``-Abruf je im Horizont
    vorkommendem Kalenderjahr (meist eins, zwei bei einem Jahreswechsel im Horizont).

    Vorab berechenbar, ohne selbst zu laden - fuer eine Fortschrittsanzeige mit
    bekanntem ``total`` statt eines unbestimmten Spinners (siehe ``notebooks/setup.py``,
    Funktion ``kurzarbeit_rohdaten``). Nicht dagegen ueber die Anzahl ``anzahl_monate``
    selbst: die fuenf festen Zweige laufen unabhaengig davon genau einmal, und die
    Monate selbst werden nie einzeln, sondern immer als ganzes Zeitfenster je
    Endpunkt abgerufen - ein Fortschritt "X von Y Monaten" haette also keine
    Entsprechung im tatsaechlichen Ladevorgang.
    """
    jahre = {jahr for jahr, _ in _abgeschlossene_monate(stichtag, anzahl_monate)}
    return ANZAHL_FESTER_LADESCHRITTE + len(jahre)


def _monatsende_des_letzten_monats(monate: list[Monat]) -> str:
    """Obere Zeitgrenze fuer den Abruf - das Ende des juengsten angefragten Monats."""
    letztes_jahr, letzter_monat = monate[-1]
    return monatsende(date(letztes_jahr, letzter_monat, 1))


def _ueberstundenstaende(
    userreports_nach_jahr: dict[int, list[UserReportV1]], *, monate: list[Monat]
) -> dict[tuple[int, Monat], float]:
    """Kumulierter Ueberstundenstand je (Personen-ID, Monat) - siehe Moduldocstring
    fuer die Herleitung aus ``overtime_carryover`` + Summe der Monats-``diff``."""
    ergebnis: dict[tuple[int, Monat], float] = {}
    benoetigte_jahre = {jahr for jahr, _ in monate}
    for jahr in benoetigte_jahre:
        for bericht in userreports_nach_jahr.get(jahr, []):
            details = bericht.get("month_details") or []
            diffs_nach_monat = {d["nr"]: d["diff"] for d in details if d.get("diff") is not None}
            laufende_summe = bericht["overtime_carryover"]
            for monatsnummer in range(1, 13):
                if monatsnummer not in diffs_nach_monat:
                    continue
                laufende_summe += diffs_nach_monat[monatsnummer]
                if (jahr, monatsnummer) in monate:
                    ergebnis[(bericht["users_id"], (jahr, monatsnummer))] = laufende_summe
    return ergebnis


class MissingRollenzuordnungError(MissingCredentialsError):
    """Die Rollenzuordnung fuer den Baustein Kurzarbeit fehlt oder ist ungueltig."""


_umgebungsvariable = partial(umgebungsvariable, fehlerklasse=MissingRollenzuordnungError)
_colab_secret = partial(colab_secret, fehlerklasse=MissingRollenzuordnungError)


def kurzarbeit_aktiv(*, use_dotenv: bool = True) -> bool:
    """Ob der Baustein Kurzarbeitsbereitschaft ueberhaupt aktiv ist.

    Steuert, ob Webapp-Seite/-Navigation, Diagramm-/Tabellen-Export und Wochenbericht
    ueberhaupt etwas zu Kurzarbeit zeigen. Ungesetzt oder "aus" bleibt der Baustein an
    allen drei Stellen vollstaendig unsichtbar - kein Nebenprodukt eines fehlenden
    Zugangsdatums, sondern ein bewusster Schalter (:data:`KURZARBEIT_AKTIV_VAR`).

    Laedt lokal eine ``.env`` (wie ``ClockodoCredentials.aus_umgebung()``/
    ``rollenzuordnung_aus_umgebung()``) - ohne das haette eine dort gesetzte Variable
    nie gewirkt, insbesondere beim einmaligen Modul-Import von ``webapp/app.py``
    (``_KURZARBEIT_AKTIV = kurzarbeit_aktiv()``), lange bevor irgendein anderer
    Codepfad zufaellig schon einmal ``load_dotenv()`` aufgerufen haben koennte.
    """
    if use_dotenv:
        load_dotenv()
    return umgebungsvariable_bool(KURZARBEIT_AKTIV_VAR)


def rollenzuordnung_automatisch() -> Rollenzuordnung:
    """Aus der passenden Quelle: Colab-Secrets in Colab, sonst ``.env``.

    Die Namensliste ist eine personenbezogene Angabe und wird deshalb nie im
    Repository gefuehrt, sondern zur Laufzeit gelesen.
    """
    return rollenzuordnung_aus_colab_secrets() if in_colab() else rollenzuordnung_aus_umgebung()


def rollenzuordnung_aus_umgebung(*, use_dotenv: bool = True) -> Rollenzuordnung:
    """Aus :data:`ROLLENZUORDNUNG_VAR`; lokal wird eine ``.env`` beruecksichtigt."""
    if use_dotenv:
        load_dotenv()
    return Rollenzuordnung(namen=_namen_aus_json(_umgebungsvariable(ROLLENZUORDNUNG_VAR)))


def rollenzuordnung_aus_colab_secrets() -> Rollenzuordnung:
    """Aus der Colab-Secrets-Verwaltung. Keine ``.env`` in Colab."""
    return Rollenzuordnung(namen=_namen_aus_json(_colab_secret(ROLLENZUORDNUNG_VAR)))


def _namen_aus_json(roh: str) -> frozenset[str]:
    try:
        wert = json.loads(roh)
    except json.JSONDecodeError as fehler:
        raise MissingRollenzuordnungError(
            f"{ROLLENZUORDNUNG_VAR} enthaelt kein gueltiges JSON: {fehler}"
        ) from fehler
    if not isinstance(wert, list) or not all(isinstance(name, str) for name in wert):
        raise MissingRollenzuordnungError(
            f"{ROLLENZUORDNUNG_VAR} muss ein JSON-Array von Namen sein."
        )
    return frozenset(wert)
