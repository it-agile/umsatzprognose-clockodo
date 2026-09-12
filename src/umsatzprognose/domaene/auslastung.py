"""Auslastung - Anteil abrechenbarer Arbeitszeit an der verfuegbaren Kapazitaet.

**Additiv und unabhaengig von der Bestand-Simulation**, wie
:mod:`umsatzprognose.domaene.kosten` und :mod:`umsatzprognose.domaene.schulung`: keine
Bandbreite, kein Monte-Carlo-Lauf. "Abrechenbar" zaehlt Clockodos Billable-Status 1
(abrechenbar, noch nicht fakturiert) und 2 (bereits fakturiert) zusammen - Status 0
(nicht abrechenbar, etwa interne Taetigkeiten) zaehlt nicht mit. Die verfuegbare
Kapazitaet je Monat kommt aus
:meth:`~umsatzprognose.domaene.mitarbeiter.Mitarbeiter.verfuegbare_kapazitaet`.

Zusaetzlich zur Abrechenbarkeit traegt :class:`Auslastungsmonat` seit
:attr:`~Auslastungsmonat.interne_stunden` auch die Billable-Status-0-Zeit - reine
Vergangenheitsbetrachtung (:class:`InterneArbeitBandbreite`,
:func:`durchschnittlicher_anteil_interner_arbeit`), ohne Wirkung auf
:attr:`~Auslastungsmonat.quote` oder die Bestand-Simulation. Ein aus dieser
Beobachtung abgeleiteter Abschlag laesst sich optional an
:meth:`~umsatzprognose.domaene.mitarbeiter.Mitarbeiter.verfuegbare_kapazitaet` uebergeben
- die Verbindung stellt aber der Aufrufer her (siehe
:meth:`~umsatzprognose.darstellung.dashboard.Dashboard.simuliere`), nicht dieses Modul.
Eine Person ganz ohne abrechenbare Stunde in einem Monat (:func:`_ausschliesslich_intern`,
``anteil_interner_arbeit == 1.0``) gilt als Ausreisser und zaehlt weder in
:class:`InterneArbeitBandbreite` noch in :func:`durchschnittlicher_anteil_interner_arbeit`
mit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from umsatzprognose.util import Monat

    from .mitarbeiter import Mitarbeiter

from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Auslastungsmonat:
    """Abrechenbare und intern gebuchte Stunden einer Person in einem Kalendermonat."""

    mitarbeiter: Mitarbeiter
    jahr: int
    monat: int
    abrechenbare_stunden: float = 0.0
    interne_stunden: float = 0.0

    @property
    def verfuegbare_stunden(self) -> float:
        return self.mitarbeiter.verfuegbare_kapazitaet(self.jahr, self.monat)

    @property
    def quote(self) -> float | None:
        """Anteil abrechenbarer Stunden an der verfuegbaren Kapazitaet.

        ``None`` ohne verfuegbare Kapazitaet in diesem Monat, statt einer
        Division durch 0 oder einer irrefuehrenden 0%-Auslastung.
        """
        verfuegbar = self.verfuegbare_stunden
        return None if verfuegbar <= 0 else self.abrechenbare_stunden / verfuegbar

    @property
    def anteil_interner_arbeit(self) -> float | None:
        """Anteil intern gebuchter Zeit an der gesamten gebuchten Zeit (intern +
        abrechenbar) dieses Monats, ``None`` ohne jede gebuchte Stunde - anders als
        :attr:`quote` unabhaengig von der verfuegbaren Kapazitaet."""
        gebucht = self.interne_stunden + self.abrechenbare_stunden
        return self.interne_stunden / gebucht if gebucht else None


@dataclass(frozen=True, slots=True)
class Auslastungssumme:
    """Abrechenbare und verfuegbare Stunden einer Person, aufsummiert ueber mehrere Monate.

    Der einzelne Kalendermonat einer :class:`Auslastungsmonat`-Reihe ist fuer einen
    verlaesslichen Blick auf die Auslastung zu kurz - der laufende Monat etwa ist immer
    unvollstaendig gebucht. :meth:`je_mitarbeiter` fasst deshalb ein ganzes Fenster
    abgeschlossener Monate je Person zu einer Gesamtquote zusammen.
    """

    mitarbeiter: Mitarbeiter
    abrechenbare_stunden: float
    verfuegbare_stunden: float
    interne_stunden: float = 0.0

    @property
    def quote(self) -> float | None:
        """Anteil abrechenbarer an verfuegbaren Stunden ueber den gesamten Zeitraum.

        ``None`` ohne verfuegbare Kapazitaet im Zeitraum, statt einer Division durch 0.
        """
        return (
            None
            if self.verfuegbare_stunden <= 0
            else self.abrechenbare_stunden / self.verfuegbare_stunden
        )

    @property
    def anteil_interner_arbeit(self) -> float | None:
        """Anteil intern gebuchter Zeit an der gesamten gebuchten Zeit ueber den
        gesamten Zeitraum - siehe :attr:`Auslastungsmonat.anteil_interner_arbeit`."""
        gebucht = self.interne_stunden + self.abrechenbare_stunden
        return self.interne_stunden / gebucht if gebucht else None

    @staticmethod
    def je_mitarbeiter(auslastungen: Iterable[Auslastungsmonat]) -> tuple[Auslastungssumme, ...]:
        """Fasst beliebig viele Monate je Person zu einer Gesamtquote zusammen.

        Reihenfolge und Anzahl der Monate je Person sind egal - typischerweise die
        abgeschlossenen Monate eines Beobachtungsfensters, ohne den laufenden Monat.
        """
        gruppen: dict[int, list[Auslastungsmonat]] = {}
        for eintrag in auslastungen:
            gruppen.setdefault(eintrag.mitarbeiter.id, []).append(eintrag)
        return tuple(
            Auslastungssumme(
                mitarbeiter=eintraege[0].mitarbeiter,
                abrechenbare_stunden=sum(e.abrechenbare_stunden for e in eintraege),
                verfuegbare_stunden=sum(e.verfuegbare_stunden for e in eintraege),
                interne_stunden=sum(e.interne_stunden for e in eintraege),
            )
            for eintraege in gruppen.values()
        )


def _ausschliesslich_intern(eintrag: Auslastungsmonat) -> bool:
    """Eine Person ohne jede abrechenbare Stunde in diesem Monat (nur intern gebucht,
    ``anteil_interner_arbeit == 1.0``) - ein Ausreisser, der sowohl die Bandbreite
    (:class:`InterneArbeitBandbreite`) als auch den Durchschnitt
    (:func:`durchschnittlicher_anteil_interner_arbeit`) unverhaeltnismaessig verzerren
    wuerde, etwa bei einem neuen oder ausschliesslich intern taetigen Teammitglied.
    Zaehlt in beiden deshalb so wenig mit wie jemand ganz ohne gebuchte Zeit."""
    return eintrag.abrechenbare_stunden == 0.0 and eintrag.interne_stunden > 0.0


@dataclass(frozen=True, slots=True)
class InterneArbeitBandbreite:
    """Minimum, Durchschnitt und Maximum von
    :attr:`Auslastungsmonat.anteil_interner_arbeit` ueber alle Personen mit gebuchter
    Zeit in einem Kalendermonat - die Kehrseite von
    :meth:`Auslastungssumme.je_mitarbeiter`: hier ueber die Personen aggregiert statt
    ueber die Monate."""

    jahr: int
    monat: int
    minimum: float
    durchschnitt: float
    maximum: float
    anzahl_personen: int

    @staticmethod
    def je_monat(auslastungen: Iterable[Auslastungsmonat]) -> tuple[InterneArbeitBandbreite, ...]:
        """Ein Eintrag je Kalendermonat mit mindestens einer (nicht ausschliesslich
        intern taetigen, siehe :func:`_ausschliesslich_intern`) Person mit gebuchter
        Zeit, chronologisch sortiert. Ein Monat ganz ohne jede gebuchte Stunde (bei
        niemandem) fehlt in der Antwort statt mit einer irrefuehrenden 0%-Bandbreite
        aufzutauchen."""
        gruppen: dict[Monat, list[float]] = defaultdict(list)
        for eintrag in auslastungen:
            anteil = eintrag.anteil_interner_arbeit
            if anteil is not None and not _ausschliesslich_intern(eintrag):
                gruppen[(eintrag.jahr, eintrag.monat)].append(anteil)
        return tuple(
            InterneArbeitBandbreite(
                jahr=jahr,
                monat=monat,
                minimum=min(anteile),
                durchschnitt=sum(anteile) / len(anteile),
                maximum=max(anteile),
                anzahl_personen=len(anteile),
            )
            for (jahr, monat), anteile in sorted(gruppen.items())
        )


def durchschnittlicher_anteil_interner_arbeit(
    auslastungen: Iterable[Auslastungsmonat],
) -> float | None:
    """Gewichteter Durchschnitt von :attr:`Auslastungsmonat.anteil_interner_arbeit`
    ueber alle Personen und Monate zusammen - Gewicht ist die tatsaechlich gebuchte
    Zeit, nicht die Anzahl Personen-Monate, damit ein Monat mit wenig gebuchter Zeit
    keinen unverhaeltnismaessigen Ausschlag gibt. Personen ganz ohne abrechenbare
    Stunde in einem Monat (siehe :func:`_ausschliesslich_intern`) zaehlen darin nicht
    mit - sonst wuerde etwa eine einzelne, ausschliesslich intern taetige Person den
    Durchschnitt trotz Gewichtung unverhaeltnismaessig verzerren. ``None`` ohne jede
    (nicht ausgeschlossene) gebuchte Stunde.

    Vorschlagswert fuer einen Kapazitaetsabschlag in der Simulation (siehe
    :meth:`~umsatzprognose.domaene.mitarbeiter.Mitarbeiter.verfuegbare_kapazitaet`) -
    reine Hilfsfunktion, verrechnet selbst nichts mit der Simulation.
    """
    gesamt_intern = 0.0
    gesamt_gebucht = 0.0
    for eintrag in auslastungen:
        if _ausschliesslich_intern(eintrag):
            continue
        gesamt_intern += eintrag.interne_stunden
        gesamt_gebucht += eintrag.interne_stunden + eintrag.abrechenbare_stunden
    return gesamt_intern / gesamt_gebucht if gesamt_gebucht else None
