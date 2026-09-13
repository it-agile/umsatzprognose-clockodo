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
Vergangenheitsbetrachtung fuer :class:`FakturierbareArbeitBandbreite` und
:func:`durchschnittlicher_anteil_fakturierbarer_arbeit`, ohne Wirkung auf
:attr:`~Auslastungsmonat.quote`. Modelliert wird bewusst der **fakturierbare** Anteil
(:attr:`~Auslastungsmonat.anteil_fakturierbarer_arbeit`, ``abrechenbare_stunden /
gebucht``), nicht sein Komplement "Anteil interner Arbeit" - dieselbe Groesse, aber mit
der Perspektive der Fachexpert:innen, fuer die "wie viel ist fakturierbar" die
gebraeuchlichere Frage ist als "wie viel ist intern". Ein aus dieser Beobachtung
abgeleiteter fester Abschlag (``1 - anteil_fakturierbarer_arbeit``) laesst sich optional
an :meth:`~umsatzprognose.domaene.mitarbeiter.Mitarbeiter.verfuegbare_kapazitaet`
uebergeben - die Verbindung stellt der Aufrufer her (siehe
:meth:`~umsatzprognose.darstellung.dashboard.Dashboard.simuliere`), nicht dieses Modul.
Eine Person ganz ohne abrechenbare Stunde in einem Monat
(:func:`_ausschliesslich_nicht_fakturierbar`, ``anteil_fakturierbarer_arbeit == 0.0``)
gilt fuer diese beiden Aggregatzahlen als Ausreisser und zaehlt in keiner von beiden mit
- ein einzelner solcher Monat wuerde Minimum/Durchschnitt/Maximum bzw. den gewichteten
Gesamtdurchschnitt unverhaeltnismaessig verzerren.

:class:`FakturierbareArbeitVerteilung` (samt der ihr zugrunde liegenden, unaggregierten
:func:`anteile_fakturierbarer_arbeit`) traegt diesen Ausreisser dagegen bewusst
**unveraendert mit** - anders als die beiden Aggregatzahlen oben ist sie kein einzelner
Kennwert, den ein Ausreisser verzerren koennte, sondern der Vorrat, aus dem eine
Monte-Carlo-Simulation ziehen kann (siehe
:func:`~umsatzprognose.domaene.simulation.simulieren`): ein seltener, tatsaechlich
vorgekommener 0-%-fakturierbar-Monat soll dort mit seinem eigenen, kleinen Anteil
auftauchen koennen, statt vorab herausgefiltert zu werden.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from umsatzprognose.util import Monat

    from .mitarbeiter import Mitarbeiter

from collections import defaultdict
from dataclasses import dataclass
from functools import cached_property

import numpy as np


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
    def anteil_fakturierbarer_arbeit(self) -> float | None:
        """Anteil abrechenbar gebuchter Zeit an der gesamten gebuchten Zeit (abrechenbar
        + intern) dieses Monats, ``None`` ohne jede gebuchte Stunde - anders als
        :attr:`quote` unabhaengig von der verfuegbaren Kapazitaet."""
        gebucht = self.interne_stunden + self.abrechenbare_stunden
        return self.abrechenbare_stunden / gebucht if gebucht else None


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
    def anteil_fakturierbarer_arbeit(self) -> float | None:
        """Anteil abrechenbar gebuchter Zeit an der gesamten gebuchten Zeit ueber den
        gesamten Zeitraum - siehe :attr:`Auslastungsmonat.anteil_fakturierbarer_arbeit`."""
        gebucht = self.interne_stunden + self.abrechenbare_stunden
        return self.abrechenbare_stunden / gebucht if gebucht else None

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


def _ausschliesslich_nicht_fakturierbar(eintrag: Auslastungsmonat) -> bool:
    """Eine Person ohne jede abrechenbare Stunde in diesem Monat (nur intern gebucht,
    ``anteil_fakturierbarer_arbeit == 0.0``) - ein Ausreisser, der sowohl die Bandbreite
    (:class:`FakturierbareArbeitBandbreite`) als auch den Durchschnitt
    (:func:`durchschnittlicher_anteil_fakturierbarer_arbeit`) unverhaeltnismaessig
    verzerren wuerde, etwa bei einem neuen oder ausschliesslich intern taetigen
    Teammitglied. Zaehlt in beiden deshalb so wenig mit wie jemand ganz ohne gebuchte
    Zeit."""
    return eintrag.abrechenbare_stunden == 0.0 and eintrag.interne_stunden > 0.0


@dataclass(frozen=True, slots=True)
class FakturierbareArbeitBandbreite:
    """Minimum, Durchschnitt und Maximum von
    :attr:`Auslastungsmonat.anteil_fakturierbarer_arbeit` ueber alle Personen mit
    gebuchter Zeit in einem Kalendermonat - die Kehrseite von
    :meth:`Auslastungssumme.je_mitarbeiter`: hier ueber die Personen aggregiert statt
    ueber die Monate."""

    jahr: int
    monat: int
    minimum: float
    durchschnitt: float
    maximum: float
    anzahl_personen: int

    @staticmethod
    def je_monat(
        auslastungen: Iterable[Auslastungsmonat],
    ) -> tuple[FakturierbareArbeitBandbreite, ...]:
        """Ein Eintrag je Kalendermonat mit mindestens einer (nicht ausschliesslich
        internen, siehe :func:`_ausschliesslich_nicht_fakturierbar`) Person mit
        gebuchter Zeit, chronologisch sortiert. Ein Monat ganz ohne jede gebuchte Stunde
        (bei niemandem) fehlt in der Antwort statt mit einer irrefuehrenden
        0%-Bandbreite aufzutauchen."""
        gruppen: dict[Monat, list[float]] = defaultdict(list)
        for eintrag in auslastungen:
            anteil = eintrag.anteil_fakturierbarer_arbeit
            if anteil is not None and not _ausschliesslich_nicht_fakturierbar(eintrag):
                gruppen[(eintrag.jahr, eintrag.monat)].append(anteil)
        return tuple(
            FakturierbareArbeitBandbreite(
                jahr=jahr,
                monat=monat,
                minimum=min(anteile),
                durchschnitt=sum(anteile) / len(anteile),
                maximum=max(anteile),
                anzahl_personen=len(anteile),
            )
            for (jahr, monat), anteile in sorted(gruppen.items())
        )


def anteile_fakturierbarer_arbeit(auslastungen: Iterable[Auslastungsmonat]) -> tuple[float, ...]:
    """Die einzelnen Werte von :attr:`Auslastungsmonat.anteil_fakturierbarer_arbeit` je
    Person und Monat, unaggregiert - Grundlage sowohl einer Verteilungsdarstellung
    (siehe :func:`~umsatzprognose.darstellung.diagramme.anteil_fakturierbarer_arbeit_verteilung`)
    als auch der Ziehung in der Monte-Carlo-Simulation
    (:class:`FakturierbareArbeitVerteilung`), im Unterschied zu
    :meth:`FakturierbareArbeitBandbreite.je_monat` (aggregiert je Kalendermonat) und
    :func:`durchschnittlicher_anteil_fakturierbarer_arbeit` (ein einzelner Gesamtwert).

    Nur Personen ganz ohne gebuchte Zeit (``anteil_fakturierbarer_arbeit is None``)
    fehlen darin - anders als bei den beiden Aggregatzahlen oben bleiben ausschliesslich
    intern taetige Personen-Monate (siehe :func:`_ausschliesslich_nicht_fakturierbar`)
    hier bewusst enthalten, siehe Moduldocstring."""
    werte = []
    for eintrag in auslastungen:
        anteil = eintrag.anteil_fakturierbarer_arbeit
        if anteil is not None:
            werte.append(anteil)
    return tuple(werte)


def durchschnittlicher_anteil_fakturierbarer_arbeit(
    auslastungen: Iterable[Auslastungsmonat],
) -> float | None:
    """Gewichteter Durchschnitt von :attr:`Auslastungsmonat.anteil_fakturierbarer_arbeit`
    ueber alle Personen und Monate zusammen - Gewicht ist die tatsaechlich gebuchte
    Zeit, nicht die Anzahl Personen-Monate, damit ein Monat mit wenig gebuchter Zeit
    keinen unverhaeltnismaessigen Ausschlag gibt. Personen ganz ohne abrechenbare
    Stunde in einem Monat (siehe :func:`_ausschliesslich_nicht_fakturierbar`) zaehlen
    darin nicht mit - sonst wuerde etwa eine einzelne, ausschliesslich intern taetige
    Person den Durchschnitt trotz Gewichtung unverhaeltnismaessig verzerren. ``None``
    ohne jede (nicht ausgeschlossene) gebuchte Stunde.

    Vorschlagswert fuer den Modus "Pauschal" in der Simulation (siehe
    :meth:`~umsatzprognose.domaene.mitarbeiter.Mitarbeiter.verfuegbare_kapazitaet`) -
    reine Hilfsfunktion, verrechnet selbst nichts mit der Simulation.
    """
    gesamt_fakturierbar = 0.0
    gesamt_gebucht = 0.0
    for eintrag in auslastungen:
        if _ausschliesslich_nicht_fakturierbar(eintrag):
            continue
        gesamt_fakturierbar += eintrag.abrechenbare_stunden
        gesamt_gebucht += eintrag.interne_stunden + eintrag.abrechenbare_stunden
    return gesamt_fakturierbar / gesamt_gebucht if gesamt_gebucht else None


@dataclass(frozen=True)  # kein slots=True: cached_property unten braucht ein Instanz-__dict__
class FakturierbareArbeitVerteilung:
    """Die empirische Verteilung von :attr:`Auslastungsmonat.anteil_fakturierbarer_arbeit`
    ueber alle Personen-Monate - dieselbe Idee wie
    :class:`~umsatzprognose.domaene.abrufquote.Abrufquotenverteilung`: ein Vorrat an
    tatsaechlich beobachteten Anteilen, aus dem eine Monte-Carlo-Simulation mit
    Zuruecklegen ziehen kann (siehe :func:`~umsatzprognose.domaene.simulation.simulieren`).
    Kein Modell mit Parametern - sie kann nichts liefern, was nicht schon einmal vorkam.

    **Portfolioweit gebildet, nicht je Person** - aus demselben Grund wie bei der
    Abrufquote: eine einzelne Person hat zu wenige Monate fuer eine eigene Verteilung.
    """

    werte: tuple[float, ...] = ()

    @classmethod
    def aus_auslastungen(
        cls,
        auslastungen: Iterable[Auslastungsmonat],
    ) -> FakturierbareArbeitVerteilung:
        """Die Verteilung aus den geladenen Auslastungsmonaten, siehe
        :func:`anteile_fakturierbarer_arbeit`."""
        return cls(anteile_fakturierbarer_arbeit(auslastungen))

    @property
    def anzahl(self) -> int:
        return len(self.werte)

    @property
    def vorhanden(self) -> bool:
        """Ob ueberhaupt gezogen werden kann."""
        return bool(self.werte)

    # cached_property schreibt in ``__dict__`` und umgeht damit ``__setattr__`` - das
    # funktioniert auch an einer frozen dataclass, siehe
    # Abrufquotenverteilung._werte_array fuer dieselbe Begruendung.
    @cached_property
    def _werte_array(self) -> np.ndarray:
        return np.array(self.werte)

    def ziehen_array(self, form: tuple[int, ...], zufall: np.random.Generator) -> np.ndarray:
        """``form`` unabhaengig gezogene Anteile mit Zuruecklegen, als Array beliebiger
        Form - fuer die Monte-Carlo-Simulation, dieselbe Idee wie
        :meth:`~umsatzprognose.domaene.abrufquote.Abrufquotenverteilung.ziehen_array`."""
        if not self.werte:
            raise ValueError("Aus einer leeren Verteilung kann nicht gezogen werden")
        return zufall.choice(self._werte_array, size=form)
