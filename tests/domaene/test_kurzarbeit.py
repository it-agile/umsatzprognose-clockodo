"""Tests fuer domaene.kurzarbeit: reine Fachlogik, ohne Netzzugriff."""

from __future__ import annotations

from umsatzprognose.domaene.kurzarbeit import (
    Personenmonat,
    Rollenzuordnung,
    Schwellenwerte,
    bewerten,
    bewertungen,
)

MONAT = (2026, 9)


def _person(
    mitarbeiter_id: int,
    *,
    name: str | None = None,
    intern: float = 40.0,
    extern: float = 120.0,
    gesamt: float | None = None,
    ueberstunden: float | None = 0.0,
) -> Personenmonat:
    return Personenmonat(
        mitarbeiter_id=mitarbeiter_id,
        name=name,
        jahr=MONAT[0],
        monat=MONAT[1],
        interne_stunden=intern,
        externe_stunden=extern,
        gesamt_stunden=intern + extern if gesamt is None else gesamt,
        ueberstundenstand=ueberstunden,
    )


def test_anteil_interner_arbeit_bezieht_sich_auf_alle_arbeitsstunden():
    # 40h intern von insgesamt 200h (40 intern + 120 extern + 40 unklassifiziert)
    person = _person(1, intern=40.0, extern=120.0, gesamt=200.0)

    assert person.anteil_interner_arbeit == 0.2


def test_anteil_interner_arbeit_ohne_gebuchte_stunden_ist_none():
    person = _person(1, intern=0.0, extern=0.0, gesamt=0.0)

    assert person.anteil_interner_arbeit is None


def test_kurzarbeitsfaehig_bei_ausreichend_interner_arbeit_und_wenig_ueberstunden():
    # 40 / 160 = 25% interne Arbeit (>= 24%), Ueberstundenstand 0 (< 14h)
    person = _person(1, intern=40.0, extern=120.0, ueberstunden=0.0)

    bewertung = bewerten([person], monat=MONAT)

    assert bewertung.anzahl_kurzarbeitsfaehig == 1
    assert bewertung.anzahl_einbezogen == 1
    assert bewertung.quote == 1.0
    assert bewertung.vorbereitet is True


def test_scheitert_an_interner_arbeit_unter_schwelle():
    # 10 / 160 = 6.25% interne Arbeit (< 24%), Ueberstunden ok
    person = _person(1, intern=10.0, extern=150.0, ueberstunden=0.0)

    bewertung = bewerten([person], monat=MONAT)

    assert bewertung.anzahl_kurzarbeitsfaehig == 0
    assert bewertung.anzahl_scheitert_interne_arbeit == 1
    assert bewertung.anzahl_scheitert_ueberstunden == 0
    assert bewertung.anzahl_scheitert_beide == 0


def test_scheitert_an_ueberstunden_ab_schwelle():
    person = _person(1, intern=40.0, extern=120.0, ueberstunden=14.0)  # nicht < 14

    bewertung = bewerten([person], monat=MONAT)

    assert bewertung.anzahl_kurzarbeitsfaehig == 0
    assert bewertung.anzahl_scheitert_ueberstunden == 1


def test_negativer_ueberstundenstand_erfuellt_die_schwelle():
    # Minusstunden gelten ohne Sonderbehandlung als unter der Schwelle
    person = _person(1, intern=40.0, extern=120.0, ueberstunden=-5.0)

    bewertung = bewerten([person], monat=MONAT)

    assert bewertung.anzahl_kurzarbeitsfaehig == 1


def test_scheitert_an_beiden_bedingungen():
    person = _person(1, intern=10.0, extern=150.0, ueberstunden=20.0)

    bewertung = bewerten([person], monat=MONAT)

    assert bewertung.anzahl_scheitert_beide == 1
    assert bewertung.anzahl_scheitert_interne_arbeit == 0
    assert bewertung.anzahl_scheitert_ueberstunden == 0


def test_ausgeschlossene_person_zaehlt_im_nenner_nie_im_zaehler():
    # Erfuellt beide Bedingungen rechnerisch, ist aber laut Rollenzuordnung ausgeschlossen
    geschaeftsfuehrung = _person(1, name="Anna Muster", intern=40.0, extern=120.0, ueberstunden=0.0)
    rollenzuordnung = Rollenzuordnung(namen=frozenset({"Anna Muster"}))

    bewertung = bewerten([geschaeftsfuehrung], monat=MONAT, rollenzuordnung=rollenzuordnung)

    assert bewertung.anzahl_kurzarbeitsfaehig == 0
    assert bewertung.anzahl_ausgeschlossen == 1
    assert bewertung.anzahl_einbezogen == 1  # zaehlt weiterhin im Nenner
    assert bewertung.quote == 0.0
    assert len(bewertung.hinweise) == 1
    assert bewertung.hinweise[0].anzahl == 1


def test_kein_ueberstundenstand_macht_person_vollstaendig_unbestimmbar():
    person = _person(1, intern=40.0, extern=120.0, ueberstunden=None)

    bewertung = bewerten([person], monat=MONAT)

    assert bewertung.anzahl_nicht_bestimmbar == 1
    assert bewertung.anzahl_einbezogen == 0  # weder Zaehler noch Nenner
    assert bewertung.quote is None
    assert bewertung.vorbereitet is None


def test_keine_gebuchte_stunde_macht_person_vollstaendig_unbestimmbar():
    person = _person(1, intern=0.0, extern=0.0, gesamt=0.0, ueberstunden=0.0)

    bewertung = bewerten([person], monat=MONAT)

    assert bewertung.anzahl_nicht_bestimmbar == 1
    assert bewertung.anzahl_einbezogen == 0


def test_unklassifizierte_stunden_erzeugen_hinweis_zaehlen_aber_nur_in_nenner():
    # gesamt 200h, aber nur 40+120=160h klassifiziert -> 40h unklassifiziert
    person = _person(1, intern=40.0, extern=120.0, gesamt=200.0, ueberstunden=0.0)

    bewertung = bewerten([person], monat=MONAT)

    # Anteil interne Arbeit bezieht den Nenner auf alle_arbeitsstunden (200h): 40/200 = 20% < 24%
    assert bewertung.anzahl_scheitert_interne_arbeit == 1
    unklassifiziert_hinweise = [h for h in bewertung.hinweise if "unklassifizierte" in h.text]
    assert len(unklassifiziert_hinweise) == 1
    assert unklassifiziert_hinweise[0].anzahl == 1


def test_quote_und_vorbereitet_ueber_mehrere_personen():
    personen = [
        _person(1, intern=40.0, extern=120.0, ueberstunden=0.0),  # kurzarbeitsfaehig
        _person(2, intern=40.0, extern=120.0, ueberstunden=0.0),  # kurzarbeitsfaehig
        _person(3, intern=40.0, extern=120.0, ueberstunden=0.0),  # kurzarbeitsfaehig
        _person(4, intern=10.0, extern=150.0, ueberstunden=0.0),  # scheitert
    ]

    bewertung = bewerten(personen, monat=MONAT)

    assert bewertung.anzahl_einbezogen == 4
    assert bewertung.quote == 0.75
    assert bewertung.vorbereitet is True  # 75% >= 30%


def test_eigene_schwellenwerte_wirken():
    person = _person(1, intern=20.0, extern=120.0, ueberstunden=0.0)  # 20/140 = 14.3%

    schwelle_streng = Schwellenwerte(anteil_interne_arbeit=0.5)
    schwelle_grosszuegig = Schwellenwerte(anteil_interne_arbeit=0.1)
    streng = bewerten([person], monat=MONAT, schwellenwerte=schwelle_streng)
    grosszuegig = bewerten([person], monat=MONAT, schwellenwerte=schwelle_grosszuegig)

    assert streng.anzahl_kurzarbeitsfaehig == 0
    assert grosszuegig.anzahl_kurzarbeitsfaehig == 1


def test_bewertungen_ruft_bewerten_je_monat_auf():
    monat_1 = (2026, 8)
    monat_2 = (2026, 9)
    daten = {
        monat_1: [_person(1, intern=40.0, extern=120.0, ueberstunden=0.0)],
        monat_2: [_person(1, intern=10.0, extern=150.0, ueberstunden=0.0)],
    }

    ergebnisse = bewertungen(daten)

    assert ergebnisse[monat_1].anzahl_kurzarbeitsfaehig == 1
    assert ergebnisse[monat_2].anzahl_kurzarbeitsfaehig == 0
    assert ergebnisse[monat_2].anzahl_scheitert_interne_arbeit == 1
