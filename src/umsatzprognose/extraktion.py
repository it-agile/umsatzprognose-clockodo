"""Extraktion der beiden Eingangsgroessen aus den Clockodo-Antworten.

Reine Abbildung von Antwort-JSON auf ``projects_id -> Wert``, ohne HTTP. Die
Regeln hier stammen nicht aus der Doku (``docs.clockodo.com`` ist eine
JavaScript-Anwendung und nicht auslesbar), sondern aus per curl geprueften
Antworten der Installation, verifiziert am 24.08.2026:

``/v4/projects`` - ``budget`` ist immer als Schluessel vorhanden, aber bei 236 von
895 Projekten ``null``. Ist es gesetzt, hat es die Form::

    {"monetary": true, "hard": false, "from_subprojects": false,
     "interval": null, "amount": 11300, "subprojects_budget_total": 0}

Drei dieser Felder entscheiden, ob ``amount`` ueberhaupt ein Euro-Gesamtbudget ist:

* ``monetary`` - bei ``false`` steht in ``amount`` eine Stundenzahl, kein Euro-Betrag
  (in dieser Installation 8 Projekte, alle inaktiv, mit Werten wie 6, 12, 48).
  Als Euro gelesen waere das ein stiller Faktor-Fehler.
* ``interval`` - gesetzt bedeutet ein Budget je Intervall statt eines Gesamtbudgets;
  ``budget.amount - revenue_kumuliert`` aus Spec 5.1 gilt dann nicht.
* ``from_subprojects`` - das Budget kommt aus Teilprojekten, die Summe steht in
  ``subprojects_budget_total``.

Bisher ist keiner der drei Faelle bei einem aktiven Projekt aufgetreten, deshalb ist
keiner an einer echten Antwort durchgerechnet. Statt eine plausible Umrechnung zu
erfinden, bleiben solche Budgets hier unbenutzt und werden als Hinweis gemeldet:
eine sichtbare Untererfassung ist besser als eine still falsche Euro-Zahl.

``/v2/entrygroups`` mit ``grouping[]=projects_id`` - die Projekt-ID steht als
**String** in ``group``, und der Wert ``0`` (dort als Zahl) steht fuer Buchungen ohne
Projekt. Ohne Filter entstuende daraus ein Phantom-Projekt 0.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class BudgetAuszug:
    """Budgets je Projekt plus die Projekte, deren Budget nicht verwertbar war."""

    budgets: dict[int, float | None] = field(default_factory=dict)
    nicht_monetaer: list[int] = field(default_factory=list)
    mit_intervall: list[int] = field(default_factory=list)
    aus_teilprojekten: list[int] = field(default_factory=list)

    @property
    def unbenutzbar(self) -> list[int]:
        """Alle Projekte, deren Budget nicht als Euro-Gesamtbudget gelesen wurde."""
        return sorted({*self.nicht_monetaer, *self.mit_intervall, *self.aus_teilprojekten})


def projekt_id(projekt: Mapping[str, object]) -> int:
    """Die Projekt-ID aus einer ``/v4/projects``-Antwort.

    ``id`` ist verifiziert; ``projects_id`` bleibt als Rueckfalloption, weil aeltere
    API-Generationen diesen Namen verwenden.
    """
    for key in ("id", "projects_id"):
        if key in projekt:
            return int(projekt[key])  # type: ignore[arg-type]
    raise KeyError(f"Keine Projekt-ID gefunden, vorhandene Keys: {sorted(projekt)}")


def budgets_je_projekt(
    projekte: Iterable[Mapping[str, object]],
    *,
    nur_aktive: bool = True,
) -> BudgetAuszug:
    """Bildet ``projects_id -> budget.amount`` in Euro ab.

    Args:
        projekte: die ``data``-Liste aus ``/v4/projects``.
        nur_aktive: nur Projekte mit ``active == True`` beruecksichtigen. Fuer eine
            Prognose kuenftiger Umsaetze zaehlen laufende Projekte; die Spec deckt
            diese Abgrenzung nicht ab.

    Returns:
        Einen :class:`BudgetAuszug`. ``None`` als Wert heisst "kein verwertbares
        Euro-Gesamtbudget" - entweder weil keines gesetzt ist oder weil eines der
        drei Sonderfelder greift; letztere sind zusaetzlich einzeln aufgefuehrt.
    """
    auszug = BudgetAuszug()

    for projekt in projekte:
        if nur_aktive and not projekt.get("active"):
            continue

        pid = projekt_id(projekt)
        budget = projekt.get("budget") or {}
        betrag = budget.get("amount") if isinstance(budget, Mapping) else None

        if betrag is None:
            auszug.budgets[pid] = None
            continue

        verwertbar = True
        if budget.get("monetary") is False:
            auszug.nicht_monetaer.append(pid)
            verwertbar = False
        if budget.get("interval") is not None:
            auszug.mit_intervall.append(pid)
            verwertbar = False
        if budget.get("from_subprojects"):
            auszug.aus_teilprojekten.append(pid)
            verwertbar = False

        auszug.budgets[pid] = float(betrag) if verwertbar else None

    return auszug


def revenue_je_projekt(
    gruppen: Iterable[Mapping[str, object]],
) -> tuple[dict[int, float], list[Mapping[str, object]]]:
    """Bildet ``projects_id -> kumuliertes revenue`` aus ``/v2/entrygroups`` ab.

    Args:
        gruppen: die ``groups``-Liste einer Abfrage mit ``grouping[]=projects_id``.

    Returns:
        Den Verbrauch je Projekt sowie die Gruppen ohne Projektbezug (``group == 0``),
        damit deren Umsatz nicht unbemerkt verschwindet.
    """
    revenue: dict[int, float] = {}
    ohne_projekt: list[Mapping[str, object]] = []

    for gruppe in gruppen:
        pid = int(gruppe["group"])  # type: ignore[arg-type]
        if pid == 0:
            ohne_projekt.append(gruppe)
            continue
        # Summiert statt zugewiesen: eine Gruppierung liefert je Projekt eine Gruppe,
        # ein doppelter Schluessel wuerde sonst still eine Zeile verwerfen.
        revenue[pid] = revenue.get(pid, 0.0) + float(gruppe.get("revenue") or 0.0)

    return revenue, ohne_projekt
