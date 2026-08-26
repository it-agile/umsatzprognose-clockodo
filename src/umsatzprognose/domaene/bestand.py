"""Bestand - das Portfolio als Ganzes, und der Ort der Simulation.

Der Baustein Bestand aus der Spec: alle in Clockodo angelegten Projekte, die Personen,
die darauf buchen, und der Umsatz, der daraus bisher entstanden ist. Das Aggregat
beantwortet alles, was ueber ein einzelnes Objekt hinausgeht - welche Projekte in die
Prognose eingehen, welche Projekte zu einem Kunden gehoeren, wie viel Volumen insgesamt
noch abrufbar ist.

**Die Simulation gehoert hierher, nicht an das Projekt.** Spec 5.4 Schritt 4 deckelt den
Bedarf je Person ueber alle ihre Projekte und kuerzt bei Ueberschreitung anteilig; ein
Projekt allein kann diesen Deckel nicht kennen. Und ein Lauf ist eine Ziehung ueber das
gesamte Portfolio - die Summe aus 44 unabhaengig gerechneten Projektverteilungen ergibt
nicht die Portfolio-Bandbreite, und die Kennzahl "Anteil der Laeufe mit Kapazitaet als
limitierendem Faktor" (5.5) entsteht ueberhaupt erst auf dieser Ebene.

Zu beachten, wenn :meth:`simulieren` gebaut wird: die Objekte hier sind
unveraenderlich, und das mit Absicht. Bei 10.000 Laeufen existieren 10.000 verschiedene
Restvolumen-Verlaeufe gleichzeitig; ein ``projekt.restvolumen -= verbrauch`` im
Simulationsschritt wuerde die Stammdaten zum Lauf-Zustand machen und beim zweiten Lauf
falsche Zahlen liefern. Der Lauf-Zustand gehoert neben die Objekte, nicht in sie.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import date
from random import Random

from umsatzprognose.domaene.abrufquote import Abrufquotenverteilung
from umsatzprognose.domaene.hinweis import Hinweis
from umsatzprognose.domaene.kunde import Kunde
from umsatzprognose.domaene.mitarbeiter import Mitarbeiter
from umsatzprognose.domaene.prognose import Prognose
from umsatzprognose.domaene.projekt import Projekt
from umsatzprognose.domaene.simulation import simulieren
from umsatzprognose.domaene.umsatzhistorie import Umsatzhistorie
from umsatzprognose.domaene.verbrauchsverlauf import Verbrauchsverlauf
from umsatzprognose.domaene.zahlen import euro


@dataclass(frozen=True)
class Bestand:
    """Alle Projekte, Personen und Umsaetze zu einem Stichtag.

    Attributes:
        verbrauchsverlaeufe: je Projekt der monatliche Verbrauch - die Beobachtungen,
            aus denen die Abrufquote-Verteilung entsteht (Spec 5.2). Leer, wenn sie
            nicht mitgeladen wurden.
        abbildungshinweise: Befunde aus dem Lesen der Clockodo-Antworten. Die
            fachlichen Befunde kommen in :meth:`hinweise` dazu.
    """

    stichtag: date
    projekte: tuple[Projekt, ...] = ()
    mitarbeiter: tuple[Mitarbeiter, ...] = ()
    umsatzhistorie: Umsatzhistorie | None = None
    verbrauchsverlaeufe: tuple[Verbrauchsverlauf, ...] = field(default_factory=tuple)
    abbildungshinweise: tuple[Hinweis, ...] = field(default_factory=tuple)

    @property
    def kunden(self) -> tuple[Kunde, ...]:
        """Alle Kunden mit mindestens einem Projekt, nach Namen sortiert."""
        gefunden = {p.kunde.id: p.kunde for p in self.projekte if p.kunde}
        return tuple(sorted(gefunden.values(), key=lambda k: str(k)))

    @property
    def aktive_projekte(self) -> tuple[Projekt, ...]:
        return tuple(p for p in self.projekte if p.aktiv)

    @property
    def im_prognose_scope(self) -> tuple[Projekt, ...]:
        """Die Projekte, die in die Prognose eingehen - groesstes Restvolumen zuerst."""
        scope = [p for p in self.projekte if p.im_prognose_scope]
        return tuple(
            sorted(scope, key=lambda p: p.restvolumen_prognosewirksam or 0.0, reverse=True)
        )

    @property
    def auftragsvolumen(self) -> float:
        """Summe der Auftragsvolumina im Prognose-Scope."""
        return sum(p.auftragsvolumen or 0.0 for p in self.im_prognose_scope)

    @property
    def restvolumen_prognosewirksam(self) -> float:
        """Summe des noch abrufbaren Volumens - die Ausgangsgroesse der Simulation."""
        return sum(p.restvolumen_prognosewirksam or 0.0 for p in self.im_prognose_scope)

    def projekte_von_kunde(self, kunde: Kunde) -> tuple[Projekt, ...]:
        return tuple(p for p in self.projekte if p.kunde and p.kunde.id == kunde.id)

    def projekte_von_mitarbeiter(self, mitarbeiter: Mitarbeiter) -> tuple[Projekt, ...]:
        """Alle Projekte, auf die eine Person gebucht hat.

        Die Rueckrichtung des Aufteilungsschluessels und damit die Grundlage des
        Kapazitaetsdeckels aus 5.4 Schritt 4, der je Person ueber alle Projekte wirkt.
        """
        return tuple(
            p for p in self.projekte if any(a.mitarbeiter.id == mitarbeiter.id for a in p.anteile)
        )

    def mit_stundensatz_uebersteuerungen(self, werte: Mapping[str, float]) -> Bestand:
        """Neuer Bestand mit von Hand hinterlegten Stundensätzen für benannte Projekte.

        Fachobjekte bleiben unveränderlich - diese Methode ersetzt deshalb keinen
        Zustand, sondern liefert einen neuen :class:`Bestand` mit den betroffenen
        Projekten ausgetauscht. ``werte`` schlüsselt über denselben Bezeichner wie die
        Hinweistabelle: den Projektnamen, oder die ID als Text, wenn das Projekt
        keinen Namen hat. Gedacht für Projekte mit Stundensatz 0 (siehe
        :attr:`~umsatzprognose.domaene.projekt.Projekt.effektiver_stundensatz`); wer in
        ``werte`` nicht genannt ist, bleibt unverändert.
        """

        def schluessel(p: Projekt) -> str:
            return p.name if p.name else str(p.id)

        aktualisiert = tuple(
            replace(p, stundensatz_uebersteuerung=werte[schluessel(p)])
            if schluessel(p) in werte
            else p
            for p in self.projekte
        )
        return replace(self, projekte=aktualisiert)

    def hinweise(self) -> tuple[Hinweis, ...]:
        """Alle Befunde: die aus der Abbildung und die fachlichen aus dem Bestand."""
        return self.abbildungshinweise + self._fachliche_hinweise()

    def _fachliche_hinweise(self) -> tuple[Hinweis, ...]:
        gefunden: list[Hinweis] = []

        ohne_budget = [p for p in self.aktive_projekte if not p.budget.verwertbar]
        if ohne_budget:
            gefunden.append(
                Hinweis(
                    "Aktive Projekte ohne bezifferbares Auftragsvolumen - sie gehen "
                    "nicht in die Prognose ein",
                    tuple(p.name if p.name else str(p.id) for p in ohne_budget),
                )
            )

        ueberschritten = [p for p in self.aktive_projekte if p.budget_ueberschritten]
        if ueberschritten:
            gefunden.append(
                Hinweis(
                    "Aktive Projekte mit überschrittenem Budget - sie tragen 0 zur Prognose bei",
                    tuple(p.name if p.name else str(p.id) for p in ueberschritten),
                )
            )

        beendet = [p for p in self.aktive_projekte if p.abgeschlossen]
        if beendet:
            gefunden.append(
                Hinweis(
                    "Projekte, die als abgeschlossen markiert und trotzdem aktiv sind - "
                    "sie gehen nicht in die Prognose ein",
                    tuple(p.name if p.name else str(p.id) for p in beendet),
                )
            )

        ohne_satz = [p for p in self.im_prognose_scope if p.effektiver_stundensatz is None]
        if ohne_satz:
            gefunden.append(
                Hinweis(
                    "Projekte im Prognose-Scope ohne erfasste Zeit - für sie lässt sich "
                    "kein Stundensatz ableiten",
                    tuple(p.name if p.name else str(p.id) for p in ohne_satz),
                )
            )

        stundensatz_null = [p for p in self.im_prognose_scope if p.effektiver_stundensatz == 0.0]
        if stundensatz_null:
            gefunden.append(
                Hinweis(
                    "Projekte im Prognose-Scope mit Stundensatz 0 - gebuchte Zeit ohne "
                    "Umsatz; ohne Korrektur würde Spec 5.4 Schritt 3 dort durch null "
                    "teilen. Mit Dashboard.stundensatz_uebersteuern() lässt sich für "
                    "diese Projekte von Hand ein Stundensatz hinterlegen",
                    tuple(p.name if p.name else str(p.id) for p in stundensatz_null),
                )
            )

        mit_automatischem_abschluss = [
            p for p in self.im_prognose_scope if p.automatischer_abschluss is not None
        ]
        if mit_automatischem_abschluss:
            gefunden.append(
                Hinweis(
                    "Projekte im Prognose-Scope mit automatischem Abschluss zu einem "
                    "festen Datum - sie tragen ab diesem Datum keinen Umsatz mehr bei "
                    "(Spec 5.4); die Simulation berücksichtigt das noch nicht",
                    tuple(
                        f"{p.name if p.name else str(p.id)} "
                        f"({p.automatischer_abschluss.strftime('%d.%m.%Y')})"
                        for p in mit_automatischem_abschluss
                    ),
                )
            )

        ohne_beteiligte = [p for p in self.im_prognose_scope if not p.anteile]
        if ohne_beteiligte:
            gefunden.append(
                Hinweis(
                    "Projekte im Prognose-Scope, auf die im Betrachtungszeitraum "
                    "niemand gebucht hat",
                    tuple(p.name if p.name else str(p.id) for p in ohne_beteiligte),
                )
            )

        gefunden.extend(self._hinweise_zur_abrufquote())
        return tuple(gefunden)

    def _hinweise_zur_abrufquote(self) -> tuple[Hinweis, ...]:
        """Was zur geschaetzten Verteilung und zu den Buchungen im Horizont zu sagen ist."""
        if not self.verbrauchsverlaeufe:
            return ()

        gefunden: list[Hinweis] = []
        verteilung = self.abrufquotenverteilung()
        if not verteilung.vorhanden:
            gefunden.append(
                Hinweis(
                    "Die Abrufquote-Verteilung konnte nicht geschätzt werden - kein "
                    "Projekt-Monat mit offenem Restvolumen zu Monatsbeginn"
                )
            )
        else:
            gefunden.append(
                Hinweis(
                    f"Die Abrufquote-Verteilung ist aus {verteilung.anzahl} Projekt-Monaten "
                    f"geschätzt (Median {verteilung.median:.2f}, "
                    f"{verteilung.anteil_ohne_abruf:.0%} davon ohne Abruf). Das Budget ist "
                    "nur in seinem heutigen Stand bekannt - nachträglich erhöhte Budgets "
                    "lassen ältere Quoten zu niedrig ausfallen"
                )
            )

        # Buchungen in Monaten nach dem Stichtagsmonat sind laut Spec 5.4 die Untergrenze
        # der Bandbreite und kein Verbrauch - sie sind vom Restvolumen nicht abgezogen.
        kuenftig = {
            verlauf.projekt: summe
            for verlauf in self.verbrauchsverlaeufe
            if (
                summe := sum(
                    monat.umsatz
                    for monat in verlauf.monate
                    if monat.schluessel > (self.stichtag.year, self.stichtag.month)
                )
            )
        }
        if kuenftig:
            gefunden.append(
                Hinweis(
                    "Nach dem Stichtagsmonat datierte Buchungen über "
                    f"{euro(sum(kuenftig.values()))} - sie sind Untergrenze der Bandbreite "
                    "(Spec 5.4) und nicht Verbrauch",
                    tuple(projekt.bezeichnung for projekt in kuenftig),
                )
            )
        return tuple(gefunden)

    def abrufquotenverteilung(self) -> Abrufquotenverteilung:
        """Die empirische Verteilung der Abrufquote (Spec 5.2).

        **Portfolioweit gebildet und nicht je Projekt** - so legt es 5.2 fest, und
        deshalb steht sie hier und nicht am Projekt: ein einzelnes Projekt hat zu wenige
        Monate fuer eine eigene Verteilung, Referenzklassen sind zurueckgestellt.

        Die Beobachtungen liefert jeder Verlauf zu seinem eigenen Projekt
        (:meth:`~umsatzprognose.domaene.verbrauchsverlauf.Verbrauchsverlauf.abrufquoten`);
        welche Monate dabei zaehlen, haengt am Stichtag des Bestands. Ein Bestand zu
        einem vergangenen Stichtag schaetzt damit die Verteilung, die damals zu schaetzen
        gewesen waere.
        """
        return Abrufquotenverteilung.aus_quoten(
            quote
            for verlauf in self.verbrauchsverlaeufe
            for quote in verlauf.abrufquoten(self.stichtag)
        )

    def simulieren(
        self, monate: int = 3, *, laeufe: int = 10000, zufall: Random | None = None
    ) -> Prognose:
        """Die Monte-Carlo-Simulation aus Spec 5.4.

        Delegiert an :func:`umsatzprognose.domaene.simulation.simulieren` - der Bestand
        ist der fachlich richtige Einstieg (siehe Moduldocstring), die Rechnung selbst
        steht in einem eigenen Modul, weil sie den Lauf-Zustand neben die unveraenderlichen
        Fachobjekte stellt statt in sie hinein.

        Args:
            monate: Laenge des Prognosehorizonts; die Spec sieht 1 bis 3 vor.
            laeufe: Anzahl der Monte-Carlo-Laeufe, 10.000 laut Spec.
            zufall: der Zufallsgenerator; ungesetzt erzeugt jeder Aufruf einen neuen.
        """
        return simulieren(self, monate, laeufe=laeufe, zufall=zufall)
