"""Mitarbeiter - die Person, die Zeit auf Projekte bucht.

Zwei Rollen im Modell: die Person ist Traeger des historischen Anteils an einem Projekt
(Spec 5.4, Schritt 3, siehe :mod:`umsatzprognose.domaene.projektanteil`) und sie bringt
die Kapazitaet mit, an der die Prognose gedeckelt wird (5.3).

**Die Spec liegt bei der Sollarbeitszeit falsch.** Abschnitt 4 nennt
``default_target_hours`` aus ``/v3/users``. Das Feld ist ein Boolean-Schalter, keine
Stundenzahl - am 24.08.2026 an der Installation geprueft, mit beiden Werten auch bei
aktiven Personen. Die tatsaechliche Sollarbeitszeit steht im
unversionierten Legacy-Endpunkt ``/targethours``, je Person mit Gueltigkeitszeitraum und
Stunden je Wochentag. Details in :mod:`umsatzprognose.clockodo.mitarbeiter`.

Die geplante Abwesenheit (``Abwesenheit``, aus ``/v4/absences``) und die Feiertage
(``Feiertag``, aus ``/v2/usersNonbusinessDays``) sind inzwischen hier - roh, ohne
Deutung. Noch nicht hier: die **verfuegbare** Kapazitaet aus 5.3, also Sollarbeitszeit
minus geplante Abwesenheit minus Feiertage minus Abschlag fuer ungeplante Abwesenheit.
Diese Rechnung entscheidet, welche Typen und Status der Abwesenheit ueberhaupt als
Kapazitaetsabzug zaehlen - eine unbestaetigte (``status`` "Enquired") oder eine
abgelehnte Abwesenheit zaehlt vermutlich nicht mit, und die Typen "Home office" und
"Work out of office" tragen laut Doku ohnehin die geplanten Stunden ("planned hours get
applied"), sind also keine Abwesenheit vom Arbeiten - und was ``Feiertag.halber_tag``
fuer die Sollstunden bedeutet (halbiert oder auf 0 gesetzt, siehe Spec 5.3). Nichts davon
wird hier vorweggenommen; der Abschlag fuer ungeplante Abwesenheit ist zudem eine
Schaetzgroesse, die die Spec der Kalibrierung zuordnet und nicht beziffert.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

WOCHENTAGE = ("montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag", "sonntag")

# AbsenceStatus.Approved laut clocodo-api.yaml (0 Enquired, 1 Approved, 2 Declined,
# 3 ApprovalCancelled, 4 Cancelled).
STATUS_GENEHMIGT = 1

# AbsenceType.OverTimeReduction - der einzige Typ, der als Stundenabwesenheit
# (``count_hours``) statt als Tagesabwesenheit (``count_days``) gefuehrt wird.
TYP_UEBERSTUNDENABBAU = 3


@dataclass(frozen=True)
class Abwesenheit:
    """Eine geplante Abwesenheit einer Person, aus ``/v4/absences`` (Spec 5.3).

    ``typ`` und ``status`` bleiben Clockodos numerische Codes (siehe
    :mod:`umsatzprognose.clockodo.abwesenheiten` fuer ihre Bedeutung) - welche davon in
    den Kapazitaetsdeckel eingehen, ist dort noch nicht entschieden.

    Attributes:
        mitarbeiter_id: die ``users_id``, zu der die Abwesenheit gehoert.
        beginnt: erster Tag der Abwesenheit.
        endet: letzter Tag der Abwesenheit, bei einem eintaegigen Eintrag gleich
            ``beginnt``.
        typ: der Clockodo-``AbsenceType`` (1-15).
        status: der Clockodo-``AbsenceStatus`` (0-4).
    """

    mitarbeiter_id: int
    beginnt: date
    endet: date
    typ: int
    status: int

    @property
    def genehmigt(self) -> bool:
        return self.status == STATUS_GENEHMIGT


@dataclass(frozen=True)
class Feiertag:
    """Ein Feiertag, der fuer eine Person gilt, aus ``/v2/usersNonbusinessDays`` (Spec 5.3).

    Die Zuordnung Person -> Feiertagsgruppe hat Clockodo bereits aufgeloest; das Modell
    kennt nur noch das Ergebnis, keine Gruppe.

    Attributes:
        datum: der Kalendertag (``evaluated_date`` der API).
        halber_tag: ob der Feiertag nur einen halben Tag umfasst. Was das fuer die
            Sollstunden bedeutet, ist noch nicht entschieden - siehe Modul-Docstring.
        name: die Bezeichnung, sofern vorhanden.
    """

    datum: date
    halber_tag: bool
    name: str | None = None


@dataclass(frozen=True)
class Wochenarbeitszeit:
    """Vereinbarte Stunden je Wochentag, gueltig in einem Zeitraum.

    Attributes:
        stunden_je_wochentag: sieben Werte, Montag zuerst.
        gueltig_ab: erster Tag der Gueltigkeit.
        gueltig_bis: letzter Tag, ``None`` fuer eine laufende Vereinbarung.
    """

    stunden_je_wochentag: tuple[float, ...]
    gueltig_ab: date
    gueltig_bis: date | None = None

    @property
    def wochenstunden(self) -> float:
        return float(sum(self.stunden_je_wochentag))

    def gilt_am(self, tag: date) -> bool:
        if tag < self.gueltig_ab:
            return False
        return self.gueltig_bis is None or tag <= self.gueltig_bis


@dataclass(frozen=True)
class Mitarbeiter:
    """Eine Person, die Zeit bucht."""

    id: int
    name: str | None = None
    aktiv: bool = False
    arbeitszeiten: tuple[Wochenarbeitszeit, ...] = ()
    abwesenheiten: tuple[Abwesenheit, ...] = ()
    feiertage: tuple[Feiertag, ...] = ()

    def __str__(self) -> str:
        return self.name or f"Person {self.id}"

    def wochenarbeitszeit(self, stichtag: date) -> Wochenarbeitszeit | None:
        """Die am Stichtag gueltige Vereinbarung, ``None`` wenn keine vorliegt.

        Bei mehreren gueltigen Eintraegen gewinnt der zuletzt begonnene. In dieser
        Installation trat der Fall nicht auf - jede aktive Person hat genau eine
        laufende Vereinbarung -, aber die Historie fuehrt zu jeder Person mehrere
        Eintraege, und ein ueberlappender Zeitraum darf nicht von der Reihenfolge der
        Antwort abhaengen.
        """
        gueltige = [a for a in self.arbeitszeiten if a.gilt_am(stichtag)]
        return max(gueltige, key=lambda a: a.gueltig_ab) if gueltige else None

    def wochenstunden(self, stichtag: date) -> float | None:
        """Vereinbarte Wochenstunden am Stichtag, ``None`` wenn nicht hinterlegt."""
        vereinbarung = self.wochenarbeitszeit(stichtag)
        return vereinbarung.wochenstunden if vereinbarung else None
