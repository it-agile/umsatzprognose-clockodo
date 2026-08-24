"""Tests zu Budget und Projekt - den Groessen aus Spec 5.1.

Die Faelle sind nicht ausgedacht: jeder steht fuer eine Konstellation, die in dieser
Clockodo-Installation vorkommt und die eine Euro-Zahl verfaelschen wuerde, wenn man sie
uebersieht.
"""

from __future__ import annotations

from umsatzprognose.domaene.kunde import Kunde
from umsatzprognose.domaene.mitarbeiter import Mitarbeiter
from umsatzprognose.domaene.projekt import Budget, Projekt
from umsatzprognose.domaene.projektanteil import Projektanteil


def projekt(**felder) -> Projekt:
    standard = {"id": 1, "aktiv": True, "budget": Budget(betrag=100000.0)}
    return Projekt(**{**standard, **felder})


def test_budget_ohne_betrag_ist_kein_auftragsvolumen():
    ohne = Budget()
    assert not ohne.gesetzt
    assert not ohne.verwertbar
    assert ohne.auftragsvolumen is None
    assert ohne.sonderfall is None


def test_stundenbudget_wird_nicht_als_euro_gelesen():
    # monetary=false heisst: in "amount" steht eine Stundenzahl. Als Euro gelesen
    # waere das ein stiller Faktor-Fehler.
    stunden = Budget(betrag=48.0, monetaer=False)
    assert stunden.auftragsvolumen is None
    assert "Stunden" in stunden.sonderfall


def test_intervallbudget_und_teilprojektbudget_bleiben_unbenutzt():
    assert Budget(betrag=1000.0, intervall="monthly").auftragsvolumen is None
    assert Budget(betrag=1000.0, aus_teilprojekten=True).auftragsvolumen is None


def test_restvolumen_ist_budget_minus_verbrauch():
    p = projekt(verbrauchtes_volumen=30000.0)
    assert p.restvolumen_roh == 70000.0
    assert p.restvolumen_prognosewirksam == 70000.0
    assert not p.budget_ueberschritten


def test_ueberschreitung_bleibt_roh_sichtbar_und_wird_prognostisch_gekappt():
    # budget.hard ist false, der Verbrauch kann das Budget uebersteigen. Fuer die
    # Prognose gilt trotzdem: kein zukuenftiger Umsatz (Spec 5.1 seit v0.5).
    p = projekt(verbrauchtes_volumen=130000.0)
    assert p.restvolumen_roh == -30000.0
    assert p.restvolumen_prognosewirksam == 0.0
    assert p.budget_ueberschritten


def test_ohne_budget_gibt_es_kein_restvolumen_und_keine_null():
    p = projekt(budget=Budget(), verbrauchtes_volumen=5000.0)
    assert p.restvolumen_roh is None
    assert p.restvolumen_prognosewirksam is None
    assert not p.budget_ueberschritten
    assert not p.im_prognose_scope


def test_prognose_scope_verlangt_aktiv_und_verwertbares_budget():
    assert projekt().im_prognose_scope
    assert not projekt(aktiv=False).im_prognose_scope
    assert not projekt(budget=Budget(betrag=48.0, monetaer=False)).im_prognose_scope


def test_effektiver_stundensatz_aus_umsatz_und_zeit():
    p = projekt(verbrauchtes_volumen=15000.0, verbrauchte_stunden=100.0)
    assert p.effektiver_stundensatz == 150.0


def test_pauschalleistung_ohne_zeit_hat_keinen_stundensatz():
    # Acht Gruppen dieser Installation haben Umsatz bei duration == 0. Eine Division
    # durch null waere hier kein Randfall, sondern der Regelfall fuer Pauschalen.
    pauschal = projekt(verbrauchtes_volumen=5000.0, verbrauchte_stunden=0.0)
    assert pauschal.effektiver_stundensatz is None


def test_anteile_je_person_summieren_sich_zu_eins():
    anna, bert = Mitarbeiter(id=1, name="Anna"), Mitarbeiter(id=2, name="Bert")
    p = projekt(
        anteile=(Projektanteil(anna, stunden=75.0), Projektanteil(bert, stunden=25.0)),
        verbrauchte_stunden=100.0,
    )
    assert p.anteil_je_mitarbeiter() == {anna: 0.75, bert: 0.25}
    assert p.beteiligte == (anna, bert)


def test_ohne_erfasste_stunden_gibt_es_keinen_aufteilungsschluessel():
    # Gleichverteilen waere eine Erfindung: niemand hat auf dem Projekt gebucht.
    anna = Mitarbeiter(id=1, name="Anna")
    p = projekt(anteile=(Projektanteil(anna, stunden=0.0),))
    assert p.anteil_je_mitarbeiter() == {}


def test_bezeichnung_nennt_kunde_und_projekt():
    p = projekt(name="Kanban Coaching", kunde=Kunde(id=7, name="it-agile GmbH"))
    assert p.bezeichnung == "it-agile GmbH / Kanban Coaching"
    assert projekt(id=42).bezeichnung == "Projekt 42"
