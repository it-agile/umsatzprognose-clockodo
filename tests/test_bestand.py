"""Tests zum Bestand - den Fragen, die ueber ein einzelnes Objekt hinausgehen."""

from __future__ import annotations

from datetime import date

from umsatzprognose.domaene import (
    Bestand,
    Budget,
    Hinweis,
    Kunde,
    Mitarbeiter,
    Projekt,
    Projektanteil,
)

STICHTAG = date(2026, 8, 24)
ITA = Kunde(id=7, name="Musterkunde GmbH")
ANNA = Mitarbeiter(id=1, name="Anna")
BERT = Mitarbeiter(id=2, name="Bert")

GROSS = Projekt(
    id=1,
    name="Gross",
    kunde=ITA,
    aktiv=True,
    budget=Budget(betrag=100000.0),
    verbrauchtes_volumen=20000.0,
    verbrauchte_stunden=100.0,
    anteile=(Projektanteil(ANNA, stunden=100.0),),
)
KLEIN = Projekt(
    id=2,
    name="Klein",
    kunde=ITA,
    aktiv=True,
    budget=Budget(betrag=50000.0),
    verbrauchtes_volumen=40000.0,
    verbrauchte_stunden=50.0,
    anteile=(Projektanteil(BERT, stunden=50.0),),
)
UEBERZOGEN = Projekt(
    id=3,
    name="Überzogen",
    aktiv=True,
    budget=Budget(betrag=10000.0),
    verbrauchtes_volumen=12000.0,
    verbrauchte_stunden=60.0,
)
OHNE_BUDGET = Projekt(id=4, name="Schulungsprodukt", aktiv=True)
INAKTIV = Projekt(id=5, name="Alt", aktiv=False, budget=Budget(betrag=99999.0))  # fmt: skip


def bestand(*projekte: Projekt, **felder) -> Bestand:
    return Bestand(stichtag=STICHTAG, projekte=projekte, **felder)


def test_prognose_scope_enthaelt_nur_aktive_projekte_mit_budget():
    b = bestand(GROSS, KLEIN, UEBERZOGEN, OHNE_BUDGET, INAKTIV)
    assert [p.id for p in b.im_prognose_scope] == [1, 2, 3]


def test_scope_ist_nach_offenem_volumen_sortiert():
    b = bestand(KLEIN, GROSS)
    assert [p.id for p in b.im_prognose_scope] == [1, 2]


def test_summen_zaehlen_nur_den_scope_und_kappen_ueberschreitungen():
    b = bestand(GROSS, KLEIN, UEBERZOGEN, OHNE_BUDGET, INAKTIV)
    assert b.auftragsvolumen == 160000.0
    assert b.restvolumen_prognosewirksam == 90000.0


def test_projekte_je_kunde_und_je_person():
    b = bestand(GROSS, KLEIN, UEBERZOGEN)
    assert [p.id for p in b.projekte_von_kunde(ITA)] == [1, 2]
    assert [p.id for p in b.projekte_von_mitarbeiter(ANNA)] == [1]


def test_kunden_kommen_ohne_doppelte_und_sortiert():
    b = bestand(GROSS, KLEIN, UEBERZOGEN)
    assert b.kunden == (ITA,)


def test_hinweise_nennen_die_offenen_faelle():
    b = bestand(GROSS, UEBERZOGEN, OHNE_BUDGET)
    texte = {h.text: h.betroffene for h in b.hinweise()}
    assert any("ohne bezifferbares Auftragsvolumen" in t for t in texte)
    assert any("überschrittenem Budget" in t for t in texte)
    ueberschritten = next(v for t, v in texte.items() if "überschrittenem" in t)
    assert ueberschritten == ("Überzogen",)


def test_abgeschlossene_aber_aktive_projekte_werden_gemeldet():
    beendet = Projekt(id=9, aktiv=True, abgeschlossen=True, budget=Budget(betrag=1000.0))
    assert any("abgeschlossen" in h.text for h in bestand(beendet).hinweise())


def test_projekte_ohne_zeit_und_ohne_beteiligte_werden_gemeldet():
    pauschal = Projekt(id=8, aktiv=True, budget=Budget(betrag=1000.0), verbrauchtes_volumen=500.0)
    texte = [h.text for h in bestand(pauschal).hinweise()]
    assert any("ohne erfasste Zeit" in t for t in texte)
    assert any("niemand gebucht" in t for t in texte)


def test_automatischer_abschluss_im_scope_wird_gemeldet():
    frist = date(2026, 9, 30)
    befristet = Projekt(
        id=10,
        name="Befristet",
        aktiv=True,
        budget=Budget(betrag=1000.0),
        deadline=frist,
        automatic_completion=True,
    )
    texte = {h.text: h.betroffene for h in bestand(befristet).hinweise()}
    hinweis = next(t for t in texte if "automatischem Abschluss" in t)
    assert texte[hinweis] == ("Befristet (30.09.2026)",)


def test_deadline_ohne_automatic_completion_wird_nicht_gemeldet():
    # Unverbindlich - siehe Projekt.automatischer_abschluss.
    unverbindlich = Projekt(
        id=11,
        name="Ohne Schalter",
        aktiv=True,
        budget=Budget(betrag=1000.0),
        deadline=date(2026, 9, 30),
        automatic_completion=False,
    )
    assert not any("automatischem Abschluss" in h.text for h in bestand(unverbindlich).hinweise())


def test_stundensatz_null_wird_gemeldet():
    ohne_umsatz = Projekt(
        id=6,
        name="Interne Zeit",
        aktiv=True,
        budget=Budget(betrag=1000.0),
        verbrauchtes_volumen=0.0,
        verbrauchte_stunden=40.0,
    )
    texte = {h.text: h.betroffene for h in bestand(ohne_umsatz).hinweise()}
    stundensatz_hinweis = next(t for t in texte if "Stundensatz 0" in t)
    assert texte[stundensatz_hinweis] == ("Interne Zeit",)


def test_stundensatz_uebersteuerung_nimmt_den_hinweis_zurueck():
    ohne_umsatz = Projekt(
        id=6,
        name="Interne Zeit",
        aktiv=True,
        budget=Budget(betrag=1000.0),
        verbrauchtes_volumen=0.0,
        verbrauchte_stunden=40.0,
    )
    korrigiert = bestand(ohne_umsatz).mit_stundensatz_uebersteuerungen({"Interne Zeit": 95.0})
    assert not any("Stundensatz 0" in h.text for h in korrigiert.hinweise())
    projekt = next(p for p in korrigiert.projekte if p.id == 6)
    assert projekt.effektiver_stundensatz == 95.0


def test_stundensatz_uebersteuerung_laesst_unbenannte_projekte_unveraendert():
    b = bestand(GROSS, KLEIN)
    korrigiert = b.mit_stundensatz_uebersteuerungen({"Nicht vorhanden": 50.0})
    assert korrigiert.projekte == b.projekte


def test_abbildungshinweise_stehen_vor_den_fachlichen():
    aus_der_abbildung = Hinweis("Auf einen Kunden ohne Projekt gebucht")
    b = bestand(OHNE_BUDGET, abbildungshinweise=(aus_der_abbildung,))
    assert b.hinweise()[0] is aus_der_abbildung
    assert len(b.hinweise()) > 1


def test_ohne_projekte_gibt_es_keine_hinweise_und_keine_summen():
    leer = bestand()
    assert leer.hinweise() == ()
    assert leer.restvolumen_prognosewirksam == 0.0


def test_simulation_ohne_abrufquotenverteilung_liefert_noch_keine_prognose():
    prognose = bestand(GROSS).simulieren()
    assert not prognose.vorhanden
    assert "Abrufquote" in prognose.begruendung
    assert prognose.monatswerte() == {}
