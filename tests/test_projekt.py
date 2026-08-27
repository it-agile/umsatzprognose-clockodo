"""Tests zu Budget und Projekt
"""

from __future__ import annotations

from datetime import date

from umsatzprognose.domaene import Budget, Kunde, Mitarbeiter, Projekt, Projektanteil


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
    # interval ist laut clocodo-api.yaml ein Integer-Enum: 0 wochenweise, 1 monatlich,
    # 2 quartalsweise, 3 jaehrlich.
    assert Budget(betrag=1000.0, intervall=1).auftragsvolumen is None
    assert Budget(betrag=1000.0, aus_teilprojekten=True).auftragsvolumen is None


def test_wochenbudget_faellt_nicht_durch_die_null():
    # 0 ist ein gueltiges Intervall und falsy - eine Pruefung auf den Wahrheitswert
    # wuerde das Wochenbudget still als Gesamtbudget lesen.
    wochenbudget = Budget(betrag=1000.0, intervall=0)
    assert wochenbudget.sonderfall == "Budget je Intervall statt Gesamtbudget"
    assert wochenbudget.auftragsvolumen is None


def test_restvolumen_ist_budget_minus_verbrauch():
    p = projekt(verbrauchtes_volumen=30000.0)
    assert p.restvolumen_roh == 70000.0
    assert p.restvolumen_prognosewirksam == 70000.0
    assert not p.budget_ueberschritten


def test_ueberschreitung_bleibt_roh_sichtbar_und_wird_prognostisch_gekappt():
    # budget.hard ist false, der Verbrauch kann das Budget uebersteigen. Fuer die
    # Prognose gilt trotzdem: kein zukuenftiger Umsatz.
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


def test_abgeschlossenes_projekt_faellt_aus_dem_scope_trotz_aktiv():
    """``completed`` schliesst aus, auch wenn ``active`` gesetzt ist.

    Die Kombination kommt in der Installation vor. Ihr offenes Restvolumen bleibt
    lesbar - nur prognostisch zaehlt es nicht mehr.
    """
    p = projekt(aktiv=True, abgeschlossen=True)
    assert not p.im_prognose_scope
    assert p.restvolumen_prognosewirksam is not None


def test_automatischer_abschluss_nur_mit_automatic_completion():
    # Eine deadline allein ist laut Doku unverbindlich - erst automatic_completion
    # macht sie zu einem festen Endedatum.
    frist = date(2026, 9, 30)
    mit_schalter = projekt(deadline=frist, automatic_completion=True)
    ohne_schalter = projekt(deadline=frist, automatic_completion=False)
    assert mit_schalter.automatischer_abschluss == frist
    assert ohne_schalter.automatischer_abschluss is None


def test_ohne_deadline_gibt_es_keinen_automatischen_abschluss():
    assert projekt().automatischer_abschluss is None
    assert projekt(automatic_completion=True).automatischer_abschluss is None


def test_effektiver_stundensatz_aus_umsatz_und_zeit():
    p = projekt(verbrauchtes_volumen=15000.0, verbrauchte_stunden=100.0)
    assert p.effektiver_stundensatz == 150.0


def test_pauschalleistung_ohne_zeit_hat_keinen_stundensatz():
    # Acht Gruppen dieser Installation haben Umsatz bei duration == 0. Eine Division
    # durch null waere hier kein Randfall, sondern der Regelfall fuer Pauschalen.
    pauschal = projekt(verbrauchtes_volumen=5000.0, verbrauchte_stunden=0.0)
    assert pauschal.effektiver_stundensatz is None


def test_gebuchte_zeit_ohne_umsatz_ergibt_stundensatz_null():
    # Anders als der Pauschalfall: hier ist verbrauchte_stunden > 0, nur der Umsatz
    # ist 0. Das waere eine Division durch null.
    ohne_umsatz = projekt(verbrauchtes_volumen=0.0, verbrauchte_stunden=40.0)
    assert ohne_umsatz.effektiver_stundensatz == 0.0


def test_stundensatz_uebersteuerung_hat_vorrang_vor_dem_abgeleiteten_wert():
    ohne_umsatz = projekt(
        verbrauchtes_volumen=0.0, verbrauchte_stunden=40.0, stundensatz_uebersteuerung=95.0
    )
    assert ohne_umsatz.effektiver_stundensatz == 95.0


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
    p = projekt(name="Beispielprojekt", kunde=Kunde(id=7, name="Musterkunde GmbH"))
    assert p.bezeichnung == "Musterkunde GmbH / Beispielprojekt"
    assert projekt(id=42).bezeichnung == "Projekt 42"
