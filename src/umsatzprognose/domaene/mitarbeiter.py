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
(``Feiertag``, aus ``/v2/usersNonbusinessDays``) sind inzwischen hier.
:meth:`Mitarbeiter.feiertagsstunden` zieht daraus den Sollstunden-Abzug eines Monats
(Entscheidung 26.08.2026): ein Feiertag setzt die Sollstunden seines Wochentags auf 0,
**auch wenn er nur ein halber ist** - Spec 5.3 nennt eine Halbierung als Annahme, in der
Praxis nehmen die Kollegen den Rest eines halben Feiertags aber in aller Regel als
Urlaub, und eine Halbierung wuerde diesen Tag doppelt und uneinheitlich erfassen: einmal
ueber den Feiertag, einmal ueber die Abwesenheit. ``Feiertag.halber_tag`` bleibt am
Objekt erhalten, geht aber nicht mehr in die Rechnung ein.

**Welcher ``typ`` als Abwesenheit vom Arbeiten zaehlt, ist entschieden (26.08.2026):
nur Urlaub und Krankheit.** ``Abwesenheit.gilt_als_abwesend`` prueft das. Alle anderen
Typen - Sonderurlaub, Ueberstundenabbau, Fortbildung, Mutterschutz, Home office, Work
out of office, Quarantaene, Wehr-/Ersatzdienst - zaehlen nach dieser Entscheidung
**nicht**, auch dort, wo das fachlich diskutabel ist (etwa Quarantaene). Noch offen:
welcher ``status`` dazukommen muss - ob z. B. eine erst beantragte (``Enquired``)
Abwesenheit schon zaehlt, oder erst eine genehmigte (siehe ``Abwesenheit.genehmigt``).

Noch nicht hier: die **verfuegbare** Kapazitaet aus 5.3, also Sollarbeitszeit minus
Feiertage minus geplante Abwesenheit minus Abschlag fuer ungeplante Abwesenheit. Der
Abschlag ist zudem eine Schaetzgroesse, die die Spec der Kalibrierung zuordnet und nicht
beziffert.
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

# AbsenceType.RegularHoliday laut clocodo-api.yaml - "Holiday from the quota", der
# reguläre Urlaub aus dem Kontingent (nicht Typ 2 "SpecialLeave"/Sonderurlaub).
TYP_URLAUB = 1

# AbsenceType-Codes, die Krankheit sind: SickSelf, SickChild, SickSelfUnpaid,
# SickChildUnpaid, SickSelfWithCertificate - eigene und Kind, bezahlt/unbezahlt, mit
# Attest gehen laut Entscheidung 26.08.2026 alle als Krankheit ein.
TYPEN_KRANKHEIT = frozenset({4, 5, 11, 12, 15})

# Entscheidung 26.08.2026: nur Urlaub und Krankheit zaehlen als Abwesenheit vom
# Arbeiten - siehe Modul-Docstring.
TYPEN_ABWESEND = frozenset({TYP_URLAUB}) | TYPEN_KRANKHEIT


@dataclass(frozen=True)
class Abwesenheit:
    """Eine geplante Abwesenheit einer Person, aus ``/v4/absences`` (Spec 5.3).

    ``typ`` und ``status`` bleiben Clockodos numerische Codes (siehe
    :mod:`umsatzprognose.clockodo.abwesenheiten` fuer ihre Bedeutung).

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

    @property
    def gilt_als_abwesend(self) -> bool:
        """Ob ``typ`` als Abwesenheit vom Arbeiten zaehlt (Entscheidung 26.08.2026).

        Nur Urlaub und Krankheit - siehe Modul-Docstring fuer die Begruendung und die
        Liste der ausgeschlossenen Typen. Sagt nichts ueber ``status``: ob z. B. eine
        erst beantragte Abwesenheit schon zaehlen soll, ist separat zu klaeren
        (:attr:`genehmigt`).
        """
        return self.typ in TYPEN_ABWESEND


@dataclass(frozen=True)
class Feiertag:
    """Ein Feiertag, der fuer eine Person gilt, aus ``/v2/usersNonbusinessDays`` (Spec 5.3).

    Die Zuordnung Person -> Feiertagsgruppe hat Clockodo bereits aufgeloest; das Modell
    kennt nur noch das Ergebnis, keine Gruppe.

    Attributes:
        datum: der Kalendertag (``evaluated_date`` der API).
        halber_tag: ob der Feiertag nur einen halben Tag umfasst. Fuer
            :meth:`Mitarbeiter.feiertagsstunden` ohne Wirkung (Entscheidung
            26.08.2026, siehe Modul-Docstring); als Rohwert der API bleibt er erhalten.
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

    def feiertagsstunden(self, jahr: int, monat: int) -> float:
        """Sollstunden-Abzug durch Feiertage in diesem Monat (Spec 5.3).

        Jeder Feiertag - ganz oder halb - setzt die Sollstunden seines Wochentags auf 0
        (Entscheidung 26.08.2026, siehe Modul-Docstring); ``halber_tag`` geht nicht ein.
        Ein Feiertag auf einen Wochentag ohne Sollstunden (etwa ein Wochenende) wirkt
        von selbst nicht, weil dort nichts abzuziehen ist. Die Wochenarbeitszeit wird je
        Feiertag einzeln nachgeschlagen, nicht einmal fuer den Monat: eine Vereinbarung
        kann mitten im Monat wechseln.

        ``0.0`` sowohl ohne Feiertage im Monat als auch ohne hinterlegte
        Wochenarbeitszeit - beides ist von hier aus nicht unterscheidbar und muss es
        auch nicht sein: in beiden Faellen gibt es nichts abzuziehen.
        """
        abzug = 0.0
        for feiertag in self.feiertage:
            if feiertag.datum.year != jahr or feiertag.datum.month != monat:
                continue
            arbeitszeit = self.wochenarbeitszeit(feiertag.datum)
            if arbeitszeit is None:
                continue
            abzug += arbeitszeit.stunden_je_wochentag[feiertag.datum.weekday()]
        return abzug
