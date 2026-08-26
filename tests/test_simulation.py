"""Tests zur Monte-Carlo-Simulation aus Spec 5.4.

Jede Abrufquote-Verteilung hier hat bewusst nur **einen** Wert: eine Historie mit genau
einem Beobachtungsmonat, dessen Projekt selbst nicht im Prognose-Scope liegt (siehe
:func:`historie`). ``Random.choice`` auf einem Einerbett zieht immer denselben Wert -
die Laeufe sind damit exakt vorhersagbar, ohne den Zufallsgenerator zu mocken oder viele
Laeufe statistisch abzuklopfen. Wo mehrere Projekte im selben Bestand einen Wert
brauchen, tragen eigene Bestaende mit eigener Historie ihn getrennt bei, damit sich die
Verteilungen nicht mischen.
"""

from __future__ import annotations

from datetime import date
from random import Random

import pytest

from umsatzprognose.domaene.bestand import Bestand
from umsatzprognose.domaene.kunde import Kunde
from umsatzprognose.domaene.mitarbeiter import Mitarbeiter, Wochenarbeitszeit
from umsatzprognose.domaene.projekt import Budget, Projekt
from umsatzprognose.domaene.projektanteil import Projektanteil
from umsatzprognose.domaene.umsatzhistorie import Monatsumsatz
from umsatzprognose.domaene.verbrauchsverlauf import Verbrauchsverlauf

KUNDE = Kunde(id=1, name="Musterkunde GmbH")

# Monatsanfang, damit die Skalierung aus Schritt 1 (Anteil verbleibender Arbeitstage)
# in Monat 1 exakt 1.0 ist - der ganze Monat liegt noch vor dem Stichtag.
STICHTAG = date(2026, 9, 1)

AMPLE = Wochenarbeitszeit(
    stunden_je_wochentag=(999.0, 999.0, 999.0, 999.0, 999.0, 0.0, 0.0),
    gueltig_ab=date(2020, 1, 1),
)
KNAPP = Wochenarbeitszeit(
    stunden_je_wochentag=(1.6, 1.6, 1.6, 1.6, 1.6, 0.0, 0.0),
    gueltig_ab=date(2020, 1, 1),
)


def mitarbeiter(id: int, name: str, arbeitszeit: Wochenarbeitszeit = AMPLE) -> Mitarbeiter:
    return Mitarbeiter(id=id, name=name, aktiv=True, arbeitszeiten=(arbeitszeit,))


def historie(quote: float, id: int = 900) -> Verbrauchsverlauf:
    """Ein einzelner Beobachtungsmonat, der die Verteilung auf genau ``quote`` setzt.

    Das Projekt liegt ausserhalb des Prognose-Scope (``aktiv=False``) und traegt selbst
    keinen Umsatz zur Simulation bei - es liefert nur die eine Beobachtung.
    """
    projekt = Projekt(id=id, name=f"Historie {id}", aktiv=False, budget=Budget(betrag=1000.0))
    return Verbrauchsverlauf.fuer(
        projekt, [Monatsumsatz(jahr=2026, monat=6, umsatz=quote * 1000.0, stunden=1.0)]
    )


def test_ohne_projekte_im_scope_gibt_es_keine_prognose():
    b = Bestand(stichtag=STICHTAG, verbrauchsverlaeufe=(historie(0.5),))
    prognose = b.simulieren(1)
    assert not prognose.vorhanden


def test_monat_muss_mindestens_eins_sein():
    b = Bestand(stichtag=STICHTAG, verbrauchsverlaeufe=(historie(0.5),))
    with pytest.raises(ValueError, match="Horizont"):
        b.simulieren(0)


def test_einfacher_lauf_ohne_kapazitaetsdeckel():
    """Ein Monat, eine Quote von 0.5, ausreichend Kapazitaet: die Rechnung geht exakt auf."""
    anna = mitarbeiter(1, "Anna")
    projekt = Projekt(
        id=1,
        name="Projekt",
        kunde=KUNDE,
        aktiv=True,
        budget=Budget(betrag=10000.0),
        verbrauchtes_volumen=2000.0,
        verbrauchte_stunden=40.0,  # effektiver Stundensatz 50.0
        anteile=(Projektanteil(anna, stunden=40.0),),
    )
    b = Bestand(
        stichtag=STICHTAG,
        projekte=(projekt,),
        mitarbeiter=(anna,),
        verbrauchsverlaeufe=(historie(0.5),),
    )

    prognose = b.simulieren(1, laeufe=5, zufall=Random(1))

    assert prognose.vorhanden
    # Restvolumen 8000, Quote 0.5 -> gewuenscht 4000 Euro, bei 50 Euro/h sind das 80h,
    # die Anna mit ihrer ueppigen Kapazitaet vollstaendig liefert.
    for niveau, werte in prognose.monatswerte().items():
        assert werte == [pytest.approx(4000.0)], niveau
    assert prognose.summe() == {niveau: pytest.approx(4000.0) for niveau in prognose.summe()}
    assert prognose.kapazitaet_limitierend_anteil() == 0.0


def test_kapazitaetsdeckel_kuerzt_anteilig_ueber_alle_projekte_einer_person():
    anna = mitarbeiter(1, "Anna", arbeitszeit=KNAPP)
    projekt_a = Projekt(
        id=1,
        name="A",
        aktiv=True,
        budget=Budget(betrag=10000.0),
        verbrauchtes_volumen=2000.0,
        verbrauchte_stunden=40.0,  # Satz 50.0, wie oben
        anteile=(Projektanteil(anna, stunden=40.0),),
    )
    projekt_b = Projekt(
        id=2,
        name="B",
        aktiv=True,
        budget=Budget(betrag=10000.0),
        verbrauchtes_volumen=2000.0,
        verbrauchte_stunden=40.0,
        anteile=(Projektanteil(anna, stunden=40.0),),
    )
    b = Bestand(
        stichtag=STICHTAG,
        projekte=(projekt_a, projekt_b),
        mitarbeiter=(anna,),
        verbrauchsverlaeufe=(historie(0.5),),
    )

    kapazitaet = anna.verfuegbare_kapazitaet(2026, 9)
    # Beide Projekte wollen bei Quote 0.5 je 80h - deutlich mehr, als Annas knappe
    # Wochenarbeitszeit im September hergibt.
    assert kapazitaet < 160.0

    prognose = b.simulieren(1, laeufe=5, zufall=Random(2))

    erwarteter_umsatz = kapazitaet * 50.0
    for werte in prognose.monatswerte().values():
        assert werte == [pytest.approx(erwarteter_umsatz)]
    assert prognose.kapazitaet_limitierend_anteil() == 1.0


def test_projekt_ohne_stundensatz_verbraucht_keine_kapazitaet():
    """Umsatz ohne erfasste Zeit geht ungedeckelt ein (Spec 5.1/5.4), siehe Projekt-Docstring."""
    projekt = Projekt(
        id=1,
        name="Pauschale ohne Zeit",
        aktiv=True,
        budget=Budget(betrag=5000.0),
        verbrauchtes_volumen=1000.0,
        verbrauchte_stunden=0.0,
    )
    b = Bestand(
        stichtag=STICHTAG,
        projekte=(projekt,),
        verbrauchsverlaeufe=(historie(0.5),),
    )

    prognose = b.simulieren(1, laeufe=3, zufall=Random(3))

    # Restvolumen 4000, Quote 0.5 -> 2000 Euro, direkt geliefert, keine Person beteiligt.
    for werte in prognose.monatswerte().values():
        assert werte == [pytest.approx(2000.0)]
    assert prognose.kapazitaet_limitierend_anteil() == 0.0


def test_gezogene_quote_wird_auf_restvolumen_gekappt_und_folgemonat_liefert_nichts():
    anna = mitarbeiter(1, "Anna")
    projekt = Projekt(
        id=1,
        name="Klein mit hoher Quote",
        aktiv=True,
        budget=Budget(betrag=5000.0),
        verbrauchtes_volumen=1000.0,  # Restvolumen 4000
        verbrauchte_stunden=20.0,  # Satz 50.0
        anteile=(Projektanteil(anna, stunden=20.0),),
    )
    b = Bestand(
        stichtag=STICHTAG,
        projekte=(projekt,),
        mitarbeiter=(anna,),
        verbrauchsverlaeufe=(historie(3.0),),  # Quote > 1: weiche Budgets, Spec 5.2
    )

    prognose = b.simulieren(2, laeufe=3, zufall=Random(4))

    for werte in prognose.monatswerte().values():
        # Monat 1: min(4000, 3.0*4000) = 4000, das komplette Restvolumen.
        # Monat 2: nichts mehr uebrig.
        assert werte == [pytest.approx(4000.0), pytest.approx(0.0)]
    for wert in prognose.summe().values():
        assert wert == pytest.approx(4000.0)


def test_deadline_monat_zaehlt_noch_voll_folgemonat_nicht():
    anna = mitarbeiter(1, "Anna")
    projekt = Projekt(
        id=1,
        name="Befristet",
        aktiv=True,
        budget=Budget(betrag=1000000.0),
        verbrauchtes_volumen=10000.0,  # Restvolumen 990000, bleibt ueber 2 Monate offen
        verbrauchte_stunden=100.0,  # Satz 100.0
        anteile=(Projektanteil(anna, stunden=100.0),),
        deadline=date(2026, 10, 15),
        automatic_completion=True,
    )
    b = Bestand(
        stichtag=STICHTAG,  # 2026-09-01, Horizont also Sep/Okt/Nov
        projekte=(projekt,),
        mitarbeiter=(anna,),
        verbrauchsverlaeufe=(historie(0.5),),
    )

    prognose = b.simulieren(3, laeufe=3, zufall=Random(5))

    werte = next(iter(prognose.monatswerte().values()))
    september, oktober, november = werte
    assert september > 0.0
    # Oktober enthaelt die deadline (15.10.) und zaehlt laut Entscheidung noch voll.
    assert oktober > 0.0
    # November liegt vollstaendig nach der deadline.
    assert november == pytest.approx(0.0)


def test_bereits_gebuchter_betrag_ist_die_untergrenze_in_kuenftigen_monaten():
    anna = mitarbeiter(1, "Anna")
    projekt = Projekt(
        id=1,
        name="Mit Vorabbuchung",
        aktiv=True,
        budget=Budget(betrag=100500.0),
        verbrauchtes_volumen=500.0,  # Restvolumen 100000
        verbrauchte_stunden=10.0,  # Satz 50.0
        anteile=(Projektanteil(anna, stunden=10.0),),
    )
    # Die Buchung liegt im zweiten Horizontmonat (Oktober), nicht im Stichtagsmonat -
    # nur dort gilt sie als Untergrenze, siehe der naechste Test.
    verlauf_projekt = Verbrauchsverlauf.fuer(
        projekt, [Monatsumsatz(jahr=2026, monat=10, umsatz=20000.0, stunden=400.0)]
    )
    b = Bestand(
        stichtag=STICHTAG,  # 2026-09-01
        projekte=(projekt,),
        mitarbeiter=(anna,),
        verbrauchsverlaeufe=(historie(0.1), verlauf_projekt),
    )

    prognose = b.simulieren(2, laeufe=3, zufall=Random(6))

    # September: min(100000, 0.1*100000) = 10000, unveraendert. Oktober: simulierter
    # Verbrauch waere nur 0.1*90000=9000 - der real gebuchte Betrag von 20000 ist die
    # Untergrenze und ueberschreibt ihn (Spec 5.4).
    for werte in prognose.monatswerte().values():
        assert werte == [pytest.approx(10000.0), pytest.approx(20000.0)]
    assert prognose.gebucht() == [pytest.approx(0.0), pytest.approx(20000.0)]


def test_stichtagsmonat_zaehlt_keine_gebuchten_betraege_als_untergrenze():
    """Verlauf.gebucht() kennt im Stichtagsmonat keine Tagesgrenze und mischt Buchungen
    vor und nach dem Stichtag - als Untergrenze gezaehlt, wuerde der schon vom
    Restvolumen abgezogene Teil vor dem Stichtag ein zweites Mal auftauchen."""
    anna = mitarbeiter(1, "Anna")
    projekt = Projekt(
        id=1,
        name="Mit Buchung im Stichtagsmonat",
        aktiv=True,
        budget=Budget(betrag=100500.0),
        verbrauchtes_volumen=500.0,  # Restvolumen 100000
        verbrauchte_stunden=10.0,  # Satz 50.0
        anteile=(Projektanteil(anna, stunden=10.0),),
    )
    # Eine grosse Buchung im Stichtagsmonat selbst - realistisch, weil die Antwort
    # keine Tagesgrenze kennt und Buchungen vor dem Stichtag mitzaehlt.
    verlauf_projekt = Verbrauchsverlauf.fuer(
        projekt, [Monatsumsatz(jahr=2026, monat=9, umsatz=90000.0, stunden=1800.0)]
    )
    b = Bestand(
        stichtag=STICHTAG,
        projekte=(projekt,),
        mitarbeiter=(anna,),
        verbrauchsverlaeufe=(historie(0.1), verlauf_projekt),
    )

    prognose = b.simulieren(1, laeufe=3, zufall=Random(7))

    # Ohne den Ausschluss fuer Monat 0 wuerde hier 90000 statt 10000 stehen.
    for werte in prognose.monatswerte().values():
        assert werte == [pytest.approx(10000.0)]
    assert prognose.gebucht() == [pytest.approx(0.0)]
