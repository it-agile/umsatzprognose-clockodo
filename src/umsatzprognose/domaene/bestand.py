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

from dataclasses import dataclass, field
from datetime import date

from umsatzprognose.domaene.hinweis import Hinweis
from umsatzprognose.domaene.kunde import Kunde
from umsatzprognose.domaene.mitarbeiter import Mitarbeiter
from umsatzprognose.domaene.prognose import NochKeinePrognose, Prognose
from umsatzprognose.domaene.projekt import Projekt
from umsatzprognose.domaene.umsatzhistorie import Umsatzhistorie


@dataclass(frozen=True)
class Bestand:
    """Alle Projekte, Personen und Umsaetze zu einem Stichtag.

    Attributes:
        abbildungshinweise: Befunde aus dem Lesen der Clockodo-Antworten. Die
            fachlichen Befunde kommen in :meth:`hinweise` dazu.
    """

    stichtag: date
    projekte: tuple[Projekt, ...] = ()
    mitarbeiter: tuple[Mitarbeiter, ...] = ()
    umsatzhistorie: Umsatzhistorie | None = None
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
                    tuple(p.id for p in ohne_budget),
                )
            )

        ueberschritten = [p for p in self.aktive_projekte if p.budget_ueberschritten]
        if ueberschritten:
            gefunden.append(
                Hinweis(
                    "Aktive Projekte mit überschrittenem Budget - sie tragen 0 zur Prognose bei",
                    tuple(p.id for p in ueberschritten),
                )
            )

        beendet = [p for p in self.aktive_projekte if p.abgeschlossen]
        if beendet:
            gefunden.append(
                Hinweis(
                    "Projekte, die als abgeschlossen markiert und trotzdem aktiv sind",
                    tuple(p.id for p in beendet),
                )
            )

        ohne_satz = [p for p in self.im_prognose_scope if p.effektiver_stundensatz is None]
        if ohne_satz:
            gefunden.append(
                Hinweis(
                    "Projekte im Prognose-Scope ohne erfasste Zeit - für sie lässt sich "
                    "kein Stundensatz ableiten",
                    tuple(p.id for p in ohne_satz),
                )
            )

        ohne_beteiligte = [p for p in self.im_prognose_scope if not p.anteile]
        if ohne_beteiligte:
            gefunden.append(
                Hinweis(
                    "Projekte im Prognose-Scope, auf die im Betrachtungszeitraum "
                    "niemand gebucht hat",
                    tuple(p.id for p in ohne_beteiligte),
                )
            )

        return tuple(gefunden)

    def simulieren(self, monate: int = 3) -> Prognose:
        """Die Monte-Carlo-Simulation aus Spec 5.4 - noch nicht gebaut.

        Args:
            monate: Laenge des Prognosehorizonts; die Spec sieht 1 bis 3 vor.
        """
        return NochKeinePrognose()
