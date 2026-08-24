"""Mitarbeiter - die Person, die Zeit auf Projekte bucht.

Zwei Rollen im Modell: die Person ist Traeger des historischen Anteils an einem Projekt
(Spec 5.4, Schritt 3, siehe :mod:`umsatzprognose.domaene.projektanteil`) und sie bringt
die Kapazitaet mit, an der die Prognose gedeckelt wird (5.3).

**Die Spec liegt bei der Sollarbeitszeit falsch.** Abschnitt 4 nennt
``default_target_hours`` aus ``/v3/users``. Das Feld ist ein Boolean-Schalter, keine
Stundenzahl - am 24.08.2026 an der Installation geprueft: 56 mal ``false``, 3 mal
``true``, auch bei aktiven Personen. Die tatsaechliche Sollarbeitszeit steht im
unversionierten Legacy-Endpunkt ``/targethours``, je Person mit Gueltigkeitszeitraum und
Stunden je Wochentag. Details in :mod:`umsatzprognose.clockodo.mitarbeiter`.

Noch nicht hier: die **verfuegbare** Kapazitaet aus 5.3, also Sollarbeitszeit minus
geplante Abwesenheit minus Abschlag fuer ungeplante Abwesenheit. Die geplanten
Abwesenheiten liegen in ``/v4/absences`` (geprueft: ``/absences``, ``/v2`` und ``/v3``
antworten mit 410), der Abschlag ist eine Schaetzgroesse, die die Spec der Kalibrierung
zuordnet und nicht beziffert. Beides gehoert an diese Klasse, sobald die Groessen
feststehen - erfunden wird hier nichts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

WOCHENTAGE = ("montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag", "sonntag")


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

    def __str__(self) -> str:
        return self.name or f"Person {self.id}"

    def wochenarbeitszeit(self, stichtag: date) -> Wochenarbeitszeit | None:
        """Die am Stichtag gueltige Vereinbarung, ``None`` wenn keine vorliegt.

        Bei mehreren gueltigen Eintraegen gewinnt der zuletzt begonnene. In dieser
        Installation trat der Fall nicht auf - jede der 26 aktiven Personen hat genau
        eine laufende Vereinbarung -, aber die Historie fuehrt 186 Eintraege, und ein
        ueberlappender Zeitraum darf nicht von der Reihenfolge der Antwort abhaengen.
        """
        gueltige = [a for a in self.arbeitszeiten if a.gilt_am(stichtag)]
        return max(gueltige, key=lambda a: a.gueltig_ab) if gueltige else None

    def wochenstunden(self, stichtag: date) -> float | None:
        """Vereinbarte Wochenstunden am Stichtag, ``None`` wenn nicht hinterlegt."""
        vereinbarung = self.wochenarbeitszeit(stichtag)
        return vereinbarung.wochenstunden if vereinbarung else None
