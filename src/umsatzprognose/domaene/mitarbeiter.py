"""Mitarbeiter - die Person, die Zeit auf Projekte bucht.

Zwei Rollen im Modell: die Person ist Traeger des historischen Anteils an einem Projekt
siehe :mod:`umsatzprognose.domaene.projektanteil`) und sie bringt
die Kapazitaet mit, an der die Prognose gedeckelt wird.

**Nur Urlaub und Krankheit zählen als ``typ`` als Abwesenheit vom Arbeiten
.** ``Abwesenheit.gilt_als_abwesend`` prueft das. Alle anderen
Typen - Sonderurlaub, Ueberstundenabbau, Fortbildung, Mutterschutz, Home office, Work
out of office, Quarantaene, Wehr-/Ersatzdienst - zaehlen
**nicht**, auch dort, wo das fachlich diskutabel ist (etwa Quarantaene).

**Eine Abwesenheit zaehlt schon
ab "beantragt", nicht erst ab "genehmigt".** ``Enquired`` und ``Approved`` zaehlen also
beide, ``Declined``, ``ApprovalCancelled`` und ``Cancelled`` nicht - das sind keine reale
Abwesenheit (mehr). ``Abwesenheit.zaehlt_als_kapazitaetsabzug`` kombiniert diese
Status-Regel mit ``gilt_als_abwesend``.

**Der Abschlag fuer ungeplante Abwesenheit wird ignoriert** - keine Schaetzung, kein Abzug.
Damit ist die **verfuegbare** Kapazitaet vollstaendig berechenbar:
:meth:`Mitarbeiter.verfuegbare_kapazitaet` zieht
Feiertage und zaehlende Abwesenheit von den Sollstunden eines Monats ab, taggenau und
ohne einen Tag doppelt abzuziehen, wenn sich beide ueberschneiden (etwa Urlaub ueber
Weihnachten, der auch die Feiertage einschliesst).
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta

WOCHENTAGE = ("montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag", "sonntag")

# AbsenceStatus.Approved laut clocodo-api.yaml (0 Enquired, 1 Approved, 2 Declined,
# 3 ApprovalCancelled, 4 Cancelled).
STATUS_GENEHMIGT = 1

# AbsenceStatus-Codes, die als geplante Abwesenheit zaehlen: Enquired (beantragt) und
# Approved (genehmigt). Der Status zaehlt schon ab
# "beantragt", nicht erst ab "genehmigt"; Declined, ApprovalCancelled und Cancelled
# sind keine reale Abwesenheit (mehr).
STATUS_GEPLANT = frozenset({0, STATUS_GENEHMIGT})

# AbsenceType.OverTimeReduction - der einzige Typ, der als Stundenabwesenheit
# (``count_hours``) statt als Tagesabwesenheit (``count_days``) gefuehrt wird.
TYP_UEBERSTUNDENABBAU = 3

# AbsenceType.RegularHoliday laut clocodo-api.yaml - "Holiday from the quota", der
# reguläre Urlaub aus dem Kontingent (nicht Typ 2 "SpecialLeave"/Sonderurlaub).
TYP_URLAUB = 1

# AbsenceType-Codes, die Krankheit sind: SickSelf, SickChild, SickSelfUnpaid,
# SickChildUnpaid, SickSelfWithCertificate - eigene und Kind, bezahlt/unbezahlt, mit
# Attest gehen alle als Krankheit ein.
TYPEN_KRANKHEIT = frozenset({4, 5, 11, 12, 15})

# Nur Urlaub und Krankheit zaehlen als Abwesenheit vom
# Arbeiten - siehe Modul-Docstring.
TYPEN_ABWESEND = frozenset({TYP_URLAUB}) | TYPEN_KRANKHEIT


@dataclass(frozen=True)
class Abwesenheit:
    """Eine geplante Abwesenheit einer Person, aus ``/v4/absences``.

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
        """Ob ``typ`` als Abwesenheit vom Arbeiten zaehlt.

        Nur Urlaub und Krankheit - siehe Modul-Docstring fuer die Begruendung und die
        Liste der ausgeschlossenen Typen. Sagt nichts ueber ``status`` - siehe
        :attr:`zaehlt_als_kapazitaetsabzug`.
        """
        return self.typ in TYPEN_ABWESEND

    @property
    def zaehlt_als_kapazitaetsabzug(self) -> bool:
        """Ob diese Abwesenheit den Kapazitaetsdeckel mindert.

        Kombiniert Typ (:attr:`gilt_als_abwesend`) und Status (:data:`STATUS_GEPLANT` -
        zaehlt schon ab "beantragt", nicht erst ab "genehmigt"). Eine abgelehnte, zurueckgezogene
        oder stornierte Abwesenheit zaehlt nicht, auch wenn ihr Typ passt.
        """
        return self.gilt_als_abwesend and self.status in STATUS_GEPLANT


@dataclass(frozen=True)
class Feiertag:
    """Ein Feiertag, der fuer eine Person gilt, aus ``/v2/usersNonbusinessDays``.

    Die Zuordnung Person -> Feiertagsgruppe hat Clockodo bereits aufgeloest; das Modell
    kennt nur noch das Ergebnis, keine Gruppe.

    Attributes:
        datum: der Kalendertag (``evaluated_date`` der API).
        halber_tag: ob der Feiertag nur einen halben Tag umfasst. Fuer
            :meth:`Mitarbeiter.feiertagsstunden` ohne Wirkung); als Rohwert der API bleibt er
            erhalten.
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

        Bei mehreren gueltigen Eintraegen gewinnt der zuletzt begonnene.Jede aktive Person hat genau
        eine laufende Vereinbarung -, aber die Historie fuehrt zu jeder Person mehrere
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
        """Sollstunden-Abzug durch Feiertage in diesem Monat.

        Jeder Feiertag - ganz oder halb - setzt die Sollstunden seines Wochentags auf 0;
        ``halber_tag`` geht nicht ein.
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

    def verfuegbare_kapazitaet(self, jahr: int, monat: int) -> float:
        """Verfuegbare Kapazitaet in diesem Monat.

        ``Sollstunden - Feiertage - geplante Abwesenheit`` - der Abschlag fuer
        ungeplante Abwesenheit fehlt hier bewusst, er wird im MVP ignoriert.

        Gerechnet wird **taggenau**, nicht als drei separate Summen: jeder Kalendertag
        des Monats zaehlt hoechstens einmal als belegt, auch wenn ein Feiertag und eine
        zaehlende Abwesenheit (:attr:`Abwesenheit.zaehlt_als_kapazitaetsabzug`) sich
        ueberschneiden - etwa Urlaub ueber Weihnachten, der die Feiertage einschliesst.
        Drei getrennte Abzuege wuerden einen solchen Tag doppelt abziehen. Ein
        Abwesenheitszeitraum wird an den Monatsgrenzen gekappt, ein Tag ohne
        hinterlegte Wochenarbeitszeit traegt 0 bei.
        """
        erster_tag = date(jahr, monat, 1)
        letzter_tag = date(jahr, monat, monthrange(jahr, monat)[1])

        belegte_tage = {
            f.datum for f in self.feiertage if f.datum.year == jahr and f.datum.month == monat
        }
        for abwesenheit in self.abwesenheiten:
            if not abwesenheit.zaehlt_als_kapazitaetsabzug:
                continue
            start = max(abwesenheit.beginnt, erster_tag)
            ende = min(abwesenheit.endet, letzter_tag)
            tag = start
            while tag <= ende:
                belegte_tage.add(tag)
                tag += timedelta(days=1)

        stunden = 0.0
        tag = erster_tag
        while tag <= letzter_tag:
            if tag not in belegte_tage:
                arbeitszeit = self.wochenarbeitszeit(tag)
                if arbeitszeit is not None:
                    stunden += arbeitszeit.stunden_je_wochentag[tag.weekday()]
            tag += timedelta(days=1)
        return stunden
