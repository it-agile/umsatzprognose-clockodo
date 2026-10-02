"""Tests zur Monte-Carlo-Simulation.

Jede Abrufquote-Verteilung hier hat bewusst nur **einen** Wert: eine Historie mit genau
einem Beobachtungsmonat, dessen Projekt selbst nicht im Prognose-Scope liegt (siehe
:func:`historie`). Eine Ziehung aus einem Einerbett liefert immer denselben Wert -
die Laeufe sind damit exakt vorhersagbar, ohne den Zufallsgenerator zu mocken oder viele
Laeufe statistisch abzuklopfen. Wo mehrere Projekte im selben Bestand einen Wert
brauchen, tragen eigene Bestaende mit eigener Historie ihn getrennt bei, damit sich die
Verteilungen nicht mischen.
"""

from __future__ import annotations

import statistics
from datetime import date
from decimal import Decimal

import numpy as np
import pytest

from umsatzprognose.domaene import (
    Bestand,
    FakturierbareArbeitVerteilung,
    GaussFakturierbareArbeit,
    Gesamtbudget,
    Kunde,
    Mitarbeiter,
    Monatsumsatz,
    OhneBudgetModell,
    Projekt,
    Projektanteil,
    Verbrauchsverlauf,
    WeibullFakturierbareArbeit,
    Wochenarbeitszeit,
)

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


def mitarbeiter(identifier: int, name: str, arbeitszeit: Wochenarbeitszeit = AMPLE) -> Mitarbeiter:
    return Mitarbeiter(id=identifier, name=name, aktiv=True, arbeitszeiten=(arbeitszeit,))


def historie(quote: float, identifier: int = 900) -> Verbrauchsverlauf:
    """Ein einzelner Beobachtungsmonat, der die Verteilung auf genau ``quote`` setzt.

    Das Projekt liegt ausserhalb des Prognose-Scope (``aktiv=False``) und traegt selbst
    keinen Umsatz zur Simulation bei - es liefert nur die eine Beobachtung.
    """
    projekt = Projekt(
        id=identifier,
        name=f"Historie {identifier}",
        aktiv=False,
        budget=Gesamtbudget(betrag=Decimal("1000.0")),
    )
    return Verbrauchsverlauf.fuer(
        projekt,
        [Monatsumsatz(jahr=2026, monat=6, umsatz=Decimal(str(quote * 1000.0)), stunden=1.0)],
    )


def test_ohne_projekte_im_scope_gibt_es_keine_prognose():
    b = Bestand(stichtag=STICHTAG, verbrauchsverlaeufe=(historie(0.5),))
    prognose = b.simulieren(monate=1)
    assert not prognose.vorhanden


def test_monat_muss_mindestens_eins_sein():
    b = Bestand(stichtag=STICHTAG, verbrauchsverlaeufe=(historie(0.5),))
    with pytest.raises(ValueError, match="Horizont"):
        b.simulieren(monate=0)


def test_interne_arbeit_abschlag_muss_zwischen_null_und_eins_liegen():
    b = Bestand(stichtag=STICHTAG, verbrauchsverlaeufe=(historie(0.5),))
    with pytest.raises(ValueError, match="interne_arbeit_abschlag"):
        b.simulieren(monate=1, interne_arbeit_abschlag=1.5)


def test_interne_arbeit_abschlag_kann_kapazitaet_zum_limitierenden_faktor_machen():
    """Wie test_einfacher_lauf_ohne_kapazitaetsdeckel (ueppige Kapazitaet, Quote 0.5,
    volle Nachfrage von 4000 Euro), aber mit einem so hohen Abschlag, dass selbst diese
    ueppige Kapazitaet zum Engpass wird."""
    anna = mitarbeiter(1, "Anna")
    projekt = Projekt(
        id=1,
        name="Projekt",
        kunde=KUNDE,
        aktiv=True,
        budget=Gesamtbudget(betrag=Decimal("10000.0")),
        verbrauchtes_volumen=Decimal("2000.0"),
        verbrauchte_stunden=40.0,  # effektiver Stundensatz 50.0
        anteile=(Projektanteil(anna, stunden=40.0),),
    )
    b = Bestand(
        stichtag=STICHTAG,
        projekte=(projekt,),
        mitarbeiter=(anna,),
        verbrauchsverlaeufe=(historie(0.5),),
    )
    abschlag = 0.999

    prognose = b.simulieren(
        monate=1,
        laeufe=5,
        zufall=np.random.default_rng(1),
        interne_arbeit_abschlag=abschlag,
    )

    kapazitaet = anna.verfuegbare_kapazitaet(2026, 9, interne_arbeit_abschlag=abschlag)
    erwarteter_umsatz = kapazitaet * 50.0
    assert erwarteter_umsatz < 4000.0  # ohne Abschlag waere die volle Nachfrage gedeckt
    for werte in prognose.monatswerte().values():
        assert [float(w) for w in werte] == [pytest.approx(erwarteter_umsatz, abs=0.01)]
    assert prognose.kapazitaet_limitierend_anteil() == 1.0


def test_interne_arbeit_abschlag_und_fakturierbare_arbeit_verteilung_schliessen_sich_aus():
    b = Bestand(stichtag=STICHTAG, verbrauchsverlaeufe=(historie(0.5),))
    verteilung = FakturierbareArbeitVerteilung(werte=(0.5,))

    with pytest.raises(ValueError, match="fakturierbare_arbeit_verteilung"):
        b.simulieren(
            monate=1,
            interne_arbeit_abschlag=0.5,
            fakturierbare_arbeit_verteilung=verteilung,
        )


def test_fakturierbare_arbeit_verteilung_kann_kapazitaet_zum_limitierenden_faktor_machen():
    """Wie test_interne_arbeit_abschlag_kann_kapazitaet_zum_limitierenden_faktor_machen,
    hier mit einer Verteilung aus einem Einerbett statt eines festen Abschlags - eine
    Ziehung aus einem Einerbett liefert immer denselben Wert, macht den Lauf also
    ebenso vorhersagbar wie ein fester Abschlag."""
    anna = mitarbeiter(1, "Anna")
    projekt = Projekt(
        id=1,
        name="Projekt",
        kunde=KUNDE,
        aktiv=True,
        budget=Gesamtbudget(betrag=Decimal("10000.0")),
        verbrauchtes_volumen=Decimal("2000.0"),
        verbrauchte_stunden=40.0,
        anteile=(Projektanteil(anna, stunden=40.0),),
    )
    b = Bestand(
        stichtag=STICHTAG,
        projekte=(projekt,),
        mitarbeiter=(anna,),
        verbrauchsverlaeufe=(historie(0.5),),
    )
    abschlag = 0.999
    # Die Verteilung zieht den Anteil fakturierbarer Arbeit direkt (kein Abschlag) -
    # das Komplement des Abschlags oben, mit dem die Vergleichskapazitaet gerechnet wird.
    verteilung = FakturierbareArbeitVerteilung(werte=(1.0 - abschlag,))

    prognose = b.simulieren(
        monate=1,
        laeufe=5,
        zufall=np.random.default_rng(1),
        fakturierbare_arbeit_verteilung=verteilung,
    )

    kapazitaet = anna.verfuegbare_kapazitaet(2026, 9, interne_arbeit_abschlag=abschlag)
    erwarteter_umsatz = kapazitaet * 50.0
    assert erwarteter_umsatz < 4000.0
    for werte in prognose.monatswerte().values():
        assert [float(w) for w in werte] == [pytest.approx(erwarteter_umsatz, abs=0.01)]
    assert prognose.kapazitaet_limitierend_anteil() == 1.0


def test_fakturierbare_arbeit_verteilung_zieht_je_lauf_unabhaengig():
    """Ein Vorrat aus zwei sehr unterschiedlichen Werten (voll bzw. kaum fakturierbar) -
    unabhaengig je Lauf gezogen erzeugt das ueber genuegend Laeufe eine Mischung aus
    kapazitaetslimitierten und nicht limitierten Laeufen, statt wie ein einzelner
    fester Abschlag entweder alle oder keinen Lauf zu limitieren."""
    anna = mitarbeiter(1, "Anna")
    projekt = Projekt(
        id=1,
        name="Projekt",
        kunde=KUNDE,
        aktiv=True,
        budget=Gesamtbudget(betrag=Decimal("10000.0")),
        verbrauchtes_volumen=Decimal("2000.0"),
        verbrauchte_stunden=40.0,
        anteile=(Projektanteil(anna, stunden=40.0),),
    )
    b = Bestand(
        stichtag=STICHTAG,
        projekte=(projekt,),
        mitarbeiter=(anna,),
        verbrauchsverlaeufe=(historie(0.5),),
    )
    verteilung = FakturierbareArbeitVerteilung(werte=(1.0, 0.001))

    prognose = b.simulieren(
        monate=1,
        laeufe=200,
        zufall=np.random.default_rng(3),
        fakturierbare_arbeit_verteilung=verteilung,
    )

    assert 0.0 < prognose.kapazitaet_limitierend_anteil() < 1.0


def test_weibull_fakturierbare_arbeit_ziehen_array_liefert_angeforderte_form():
    verteilung = WeibullFakturierbareArbeit(formparameter=2.0, skalenparameter=0.2)

    gezogen = verteilung.ziehen_array((3, 4), np.random.default_rng(0))

    assert gezogen.shape == (3, 4)


def test_weibull_fakturierbare_arbeit_ziehen_array_kappt_auf_null_eins():
    # Formparameter 0.3 (rechtsschief) und ein grosser Skalenparameter erzeugen
    # zuverlaessig Werte weit ueber 1.0, ohne Kappung.
    verteilung = WeibullFakturierbareArbeit(formparameter=0.3, skalenparameter=5.0)

    gezogen = verteilung.ziehen_array((1000,), np.random.default_rng(0))

    assert gezogen.min() >= 0.0
    assert gezogen.max() <= 1.0
    assert gezogen.max() == pytest.approx(1.0)  # Kappung tatsaechlich getroffen


def test_weibull_fakturierbare_arbeit_aus_stichprobe_matcht_mittelwert_und_standardabweichung():
    werte = [0.05, 0.1, 0.12, 0.2, 0.3, 0.08, 0.15, 0.25, 0.02, 0.18]

    verteilung = WeibullFakturierbareArbeit.aus_stichprobe(werte)
    gezogen = verteilung.ziehen_array((200_000,), np.random.default_rng(0))

    assert gezogen.mean() == pytest.approx(statistics.fmean(werte), abs=0.01)
    assert gezogen.std() == pytest.approx(statistics.pstdev(werte), abs=0.01)


def test_weibull_fakturierbare_arbeit_aus_stichprobe_braucht_mindestens_zwei_werte():
    with pytest.raises(ValueError, match="mindestens zwei Werte"):
        WeibullFakturierbareArbeit.aus_stichprobe([0.1])


def test_gauss_fakturierbare_arbeit_ziehen_array_liefert_angeforderte_form():
    verteilung = GaussFakturierbareArbeit(mittelwert=0.2, standardabweichung=0.05)

    gezogen = verteilung.ziehen_array((3, 4), np.random.default_rng(0))

    assert gezogen.shape == (3, 4)


def test_gauss_fakturierbare_arbeit_ziehen_array_kappt_auf_null_eins():
    verteilung = GaussFakturierbareArbeit(mittelwert=0.0, standardabweichung=1.0)

    gezogen = verteilung.ziehen_array((1000,), np.random.default_rng(0))

    assert gezogen.min() >= 0.0
    assert gezogen.max() <= 1.0
    assert (gezogen == 0.0).any()  # untere Kappung tatsaechlich getroffen


def test_gauss_fakturierbare_arbeit_aus_stichprobe():
    werte = [0.1, 0.2, 0.3]

    verteilung = GaussFakturierbareArbeit.aus_stichprobe(werte)

    assert verteilung.mittelwert == pytest.approx(statistics.fmean(werte))
    assert verteilung.standardabweichung == pytest.approx(statistics.pstdev(werte))


def test_gauss_fakturierbare_arbeit_aus_stichprobe_mit_einem_wert_hat_keine_streuung():
    verteilung = GaussFakturierbareArbeit.aus_stichprobe([0.2])

    assert verteilung.mittelwert == 0.2
    assert verteilung.standardabweichung == 0.0


def test_gauss_fakturierbare_arbeit_aus_stichprobe_braucht_mindestens_einen_wert():
    with pytest.raises(ValueError, match="mindestens ein Wert"):
        GaussFakturierbareArbeit.aus_stichprobe([])


def test_einfacher_lauf_ohne_kapazitaetsdeckel():
    """Ein Monat, eine Quote von 0.5, ausreichend Kapazitaet: die Rechnung geht exakt auf."""
    anna = mitarbeiter(1, "Anna")
    projekt = Projekt(
        id=1,
        name="Projekt",
        kunde=KUNDE,
        aktiv=True,
        budget=Gesamtbudget(betrag=Decimal("10000.0")),
        verbrauchtes_volumen=Decimal("2000.0"),
        verbrauchte_stunden=40.0,  # effektiver Stundensatz 50.0
        anteile=(Projektanteil(anna, stunden=40.0),),
    )
    b = Bestand(
        stichtag=STICHTAG,
        projekte=(projekt,),
        mitarbeiter=(anna,),
        verbrauchsverlaeufe=(historie(0.5),),
    )

    prognose = b.simulieren(monate=1, laeufe=5, zufall=np.random.default_rng(1))

    assert prognose.vorhanden
    # Restvolumen 8000, Quote 0.5 -> gewuenscht 4000 Euro, bei 50 Euro/h sind das 80h,
    # die Anna mit ihrer ueppigen Kapazitaet vollstaendig liefert.
    for niveau, werte in prognose.monatswerte().items():
        assert [float(w) for w in werte] == [pytest.approx(4000.0)], niveau
    summe = {niveau: float(wert) for niveau, wert in prognose.summe().items()}
    assert summe == {niveau: pytest.approx(4000.0) for niveau in summe}
    assert prognose.kapazitaet_limitierend_anteil() == 0.0
    # 4000 Euro bei 50 Euro/h effektivem Satz sind 80 gelieferte Stunden.
    assert prognose.kapazitaet_je_projekt() == {1: pytest.approx(80.0)}


def test_kapazitaetsdeckel_kuerzt_anteilig_ueber_alle_projekte_einer_person():
    anna = mitarbeiter(1, "Anna", arbeitszeit=KNAPP)
    projekt_a = Projekt(
        id=1,
        name="A",
        aktiv=True,
        budget=Gesamtbudget(betrag=Decimal("10000.0")),
        verbrauchtes_volumen=Decimal("2000.0"),
        verbrauchte_stunden=40.0,  # Satz 50.0, wie oben
        anteile=(Projektanteil(anna, stunden=40.0),),
    )
    projekt_b = Projekt(
        id=2,
        name="B",
        aktiv=True,
        budget=Gesamtbudget(betrag=Decimal("10000.0")),
        verbrauchtes_volumen=Decimal("2000.0"),
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

    prognose = b.simulieren(monate=1, laeufe=5, zufall=np.random.default_rng(2))

    erwarteter_umsatz = kapazitaet * 50.0
    for werte in prognose.monatswerte().values():
        # abs=0.01: die Simulation rundet auf den Cent (siehe simulation._euro()), das
        # allein kann schon in der Groessenordnung der sonst genutzten Standardtoleranz liegen.
        assert [float(w) for w in werte] == [pytest.approx(erwarteter_umsatz, abs=0.01)]
    assert prognose.kapazitaet_limitierend_anteil() == 1.0
    # Beide Projekte wollen gleich viel, der Deckel kuerzt sie deshalb gleich stark -
    # zusammen genau Annas verfuegbare Kapazitaet, je zur Haelfte.
    kapazitaet_je_projekt = prognose.kapazitaet_je_projekt()
    assert kapazitaet_je_projekt[1] == pytest.approx(kapazitaet_je_projekt[2])
    assert kapazitaet_je_projekt[1] + kapazitaet_je_projekt[2] == pytest.approx(kapazitaet)


def test_projekt_ohne_stundensatz_verbraucht_keine_kapazitaet():
    """Umsatz ohne erfasste Zeit geht ungedeckelt ein, siehe Projekt-Docstring."""
    projekt = Projekt(
        id=1,
        name="Pauschale ohne Zeit",
        aktiv=True,
        budget=Gesamtbudget(betrag=Decimal("5000.0")),
        verbrauchtes_volumen=Decimal("1000.0"),
        verbrauchte_stunden=0.0,
    )
    b = Bestand(
        stichtag=STICHTAG,
        projekte=(projekt,),
        verbrauchsverlaeufe=(historie(0.5),),
    )

    prognose = b.simulieren(monate=1, laeufe=3, zufall=np.random.default_rng(3))

    # Restvolumen 4000, Quote 0.5 -> 2000 Euro, direkt geliefert, keine Person beteiligt.
    for werte in prognose.monatswerte().values():
        assert [float(w) for w in werte] == [pytest.approx(2000.0)]
    assert prognose.kapazitaet_limitierend_anteil() == 0.0
    # Ohne ableitbaren Stundensatz kein Stundenbedarf - die Kapazitaetsverteilung
    # zeigt fuer dieses Projekt 0, obwohl es Umsatz liefert.
    assert prognose.kapazitaet_je_projekt() == {1: 0.0}


def test_gezogene_quote_wird_auf_restvolumen_gekappt_und_folgemonat_liefert_nichts():
    anna = mitarbeiter(1, "Anna")
    projekt = Projekt(
        id=1,
        name="Klein mit hoher Quote",
        aktiv=True,
        budget=Gesamtbudget(betrag=Decimal("5000.0")),
        verbrauchtes_volumen=Decimal("1000.0"),  # Restvolumen 4000
        verbrauchte_stunden=20.0,  # Satz 50.0
        anteile=(Projektanteil(anna, stunden=20.0),),
    )
    b = Bestand(
        stichtag=STICHTAG,
        projekte=(projekt,),
        mitarbeiter=(anna,),
        verbrauchsverlaeufe=(historie(3.0),),  # Quote > 1: weiche Budgets
    )

    prognose = b.simulieren(monate=2, laeufe=3, zufall=np.random.default_rng(4))

    for werte in prognose.monatswerte().values():
        # Monat 1: min(4000, 3.0*4000) = 4000, das komplette Restvolumen.
        # Monat 2: nichts mehr uebrig.
        assert [float(w) for w in werte] == [pytest.approx(4000.0), pytest.approx(0.0)]
    for wert in prognose.summe().values():
        assert float(wert) == pytest.approx(4000.0)


def test_deadline_monat_zaehlt_noch_voll_folgemonat_nicht():
    anna = mitarbeiter(1, "Anna")
    projekt = Projekt(
        id=1,
        name="Befristet",
        aktiv=True,
        budget=Gesamtbudget(betrag=Decimal("1000000.0")),
        verbrauchtes_volumen=Decimal("10000.0"),  # Restvolumen 990000, bleibt ueber 2 Monate offen
        verbrauchte_stunden=100.0,  # Satz 100.0
        anteile=(Projektanteil(anna, stunden=100.0),),
        automatischer_abschluss=date(2026, 10, 15),
    )
    b = Bestand(
        stichtag=STICHTAG,  # 2026-09-01, Horizont also Sep/Okt/Nov
        projekte=(projekt,),
        mitarbeiter=(anna,),
        verbrauchsverlaeufe=(historie(0.5),),
    )

    prognose = b.simulieren(monate=3, laeufe=3, zufall=np.random.default_rng(5))

    werte = next(iter(prognose.monatswerte().values()))
    september, oktober, november = (float(w) for w in werte)
    assert september > 0.0
    # Oktober enthaelt die deadline (15.10.) und zaehlt noch voll.
    assert oktober > 0.0
    # November liegt vollstaendig nach der deadline.
    assert november == pytest.approx(0.0)


def test_bereits_gebuchter_betrag_ist_die_untergrenze_in_kuenftigen_monaten():
    anna = mitarbeiter(1, "Anna")
    projekt = Projekt(
        id=1,
        name="Mit Vorabbuchung",
        aktiv=True,
        budget=Gesamtbudget(betrag=Decimal("100500.0")),
        verbrauchtes_volumen=Decimal("500.0"),  # Restvolumen 100000
        verbrauchte_stunden=10.0,  # Satz 50.0
        anteile=(Projektanteil(anna, stunden=10.0),),
    )
    # Die Buchung liegt im zweiten Horizontmonat (Oktober), nicht im Stichtagsmonat -
    # nur dort gilt sie als Untergrenze, siehe der naechste Test.
    verlauf_projekt = Verbrauchsverlauf.fuer(
        projekt,
        [Monatsumsatz(jahr=2026, monat=10, umsatz=Decimal("20000.0"), stunden=400.0)],
    )
    b = Bestand(
        stichtag=STICHTAG,  # 2026-09-01
        projekte=(projekt,),
        mitarbeiter=(anna,),
        verbrauchsverlaeufe=(historie(0.1), verlauf_projekt),
    )

    prognose = b.simulieren(monate=2, laeufe=3, zufall=np.random.default_rng(6))

    # September: min(100000, 0.1*100000) = 10000, unveraendert. Oktober: simulierter
    # Verbrauch waere nur 0.1*90000=9000 - der real gebuchte Betrag von 20000 ist die
    # Untergrenze und ueberschreibt ihn.
    for werte in prognose.monatswerte().values():
        assert [float(w) for w in werte] == [pytest.approx(10000.0), pytest.approx(20000.0)]
    assert [float(g) for g in prognose.gebucht()] == [pytest.approx(0.0), pytest.approx(20000.0)]


def test_verbrauchsplan_verteilt_restvolumen_linear_bis_zielmonat_unabhaengig_vom_zufall():
    """``verbrauchsplan_zielmonat`` ersetzt die gezogene Abrufquote durch einen
    deterministischen, gleichmaessig verteilten Verbrauch bis zu diesem Monat - anders
    als bei einer gezogenen Quote (siehe die anderen Tests hier) liefert derselbe Lauf
    unabhaengig vom Zufallsgenerator dasselbe Ergebnis."""
    anna = mitarbeiter(1, "Anna")
    projekt = Projekt(
        id=1,
        name="Beispielprojekt",
        aktiv=True,
        budget=Gesamtbudget(betrag=Decimal("30500.0")),
        verbrauchtes_volumen=Decimal("500.0"),  # Restvolumen 30000
        verbrauchte_stunden=100.0,  # Satz 5.0
        anteile=(Projektanteil(anna, stunden=100.0),),
        verbrauchsplan_zielmonat=(2026, 11),  # letzter von drei Horizontmonaten (Sep-Nov)
    )
    b = Bestand(
        stichtag=STICHTAG,  # 2026-09-01, Horizont also Sep/Okt/Nov
        projekte=(projekt,),
        mitarbeiter=(anna,),
        # Quote 0.1 wuerde ohne Plan nur einen Bruchteil des Restvolumens ziehen -
        # der Plan ignoriert sie vollstaendig.
        verbrauchsverlaeufe=(historie(0.1),),
    )

    for seed in (10, 20):
        prognose = b.simulieren(monate=3, laeufe=3, zufall=np.random.default_rng(seed))
        assert prognose.kapazitaet_limitierend_anteil() == 0.0
        for werte in prognose.monatswerte().values():
            # 30000 auf 3 Monate verteilt = 10000/Monat.
            assert [float(w) for w in werte] == [pytest.approx(10000.0)] * 3


def test_stichtagsmonat_zaehlt_keine_gebuchten_betraege_als_untergrenze():
    """Verlauf.gebucht() kennt im Stichtagsmonat keine Tagesgrenze und mischt Buchungen
    vor und nach dem Stichtag - als Untergrenze gezaehlt, wuerde der schon vom
    Restvolumen abgezogene Teil vor dem Stichtag ein zweites Mal auftauchen."""
    anna = mitarbeiter(1, "Anna")
    projekt = Projekt(
        id=1,
        name="Mit Buchung im Stichtagsmonat",
        aktiv=True,
        budget=Gesamtbudget(betrag=Decimal("100500.0")),
        verbrauchtes_volumen=Decimal("500.0"),  # Restvolumen 100000
        verbrauchte_stunden=10.0,  # Satz 50.0
        anteile=(Projektanteil(anna, stunden=10.0),),
    )
    # Eine grosse Buchung im Stichtagsmonat selbst - realistisch, weil die Antwort
    # keine Tagesgrenze kennt und Buchungen vor dem Stichtag mitzaehlt.
    verlauf_projekt = Verbrauchsverlauf.fuer(
        projekt,
        [Monatsumsatz(jahr=2026, monat=9, umsatz=Decimal("90000.0"), stunden=1800.0)],
    )
    b = Bestand(
        stichtag=STICHTAG,
        projekte=(projekt,),
        mitarbeiter=(anna,),
        verbrauchsverlaeufe=(historie(0.1), verlauf_projekt),
    )

    prognose = b.simulieren(monate=1, laeufe=3, zufall=np.random.default_rng(7))

    # Ohne den Ausschluss fuer Monat 0 wuerde hier 90000 statt 10000 stehen.
    for werte in prognose.monatswerte().values():
        assert [float(w) for w in werte] == [pytest.approx(10000.0)]
    assert [float(g) for g in prognose.gebucht()] == [pytest.approx(0.0)]


# --- Projekte ohne Budget (domaene.ohne_budget) -------------------------------------

GROSSE_KAPAZITAET = Wochenarbeitszeit(
    stunden_je_wochentag=(20.0, 20.0, 20.0, 20.0, 20.0, 0.0, 0.0),
    gueltig_ab=date(2020, 1, 1),
)
FENSTER = [(2026, 3), (2026, 4), (2026, 5), (2026, 6), (2026, 7), (2026, 8)]


def _bestand_mit_coaching(*, schulung_stunden: float = 0.0) -> Bestand:
    """Ein Budgetprojekt (bei Quote 0.5 genau 4000 Euro / 80 h im Monat) und ein
    Coaching ohne Budget, das in jedem Fenstermonat genau 1000 Euro (10 h) umsetzt."""
    anna = mitarbeiter(1, "Anna", GROSSE_KAPAZITAET)
    budget = Projekt(
        id=1,
        name="Projekt",
        kunde=KUNDE,
        aktiv=True,
        budget=Gesamtbudget(betrag=Decimal("10000.0")),
        verbrauchtes_volumen=Decimal("2000.0"),
        verbrauchte_stunden=40.0,  # effektiver Stundensatz 50.0
        anteile=(Projektanteil(anna, stunden=40.0),),
    )
    coaching = Projekt(
        id=2,
        name="Coaching",
        kunde=KUNDE,
        aktiv=True,
        verbrauchtes_volumen=Decimal("6000.0"),
        verbrauchte_stunden=60.0,  # Satz 100.0
        anteile=(Projektanteil(anna, stunden=60.0),),
    )
    schulung = Projekt(
        id=3,
        name="Schulung",
        kunde=KUNDE,
        aktiv=True,
        anteile=(Projektanteil(anna, stunden=1.0),),
    )
    verlaeufe = [
        historie(0.5),
        Verbrauchsverlauf.fuer(
            coaching,
            [Monatsumsatz(jahr, monat, Decimal("1000.0"), stunden=10.0) for jahr, monat in FENSTER],
        ),
    ]
    if schulung_stunden:
        verlaeufe.append(
            Verbrauchsverlauf.fuer(
                schulung,
                [
                    Monatsumsatz(jahr, monat, Decimal("0"), stunden=schulung_stunden)
                    for jahr, monat in FENSTER
                ],
            ),
        )
    return Bestand(
        stichtag=STICHTAG,
        projekte=(budget, coaching, schulung),
        mitarbeiter=(anna,),
        verbrauchsverlaeufe=tuple(verlaeufe),
    )


def _monatswert(prognose) -> float:
    return float(prognose.monatswerte()[0.5][0])


def test_projekte_ohne_budget_fehlen_ohne_modell_in_der_prognose():
    prognose = _bestand_mit_coaching().simulieren(
        monate=1, laeufe=5, zufall=np.random.default_rng(1)
    )

    assert _monatswert(prognose) == pytest.approx(4000.0)


def test_projekte_ohne_budget_tragen_ihren_historischen_bedarf_bei():
    modell = OhneBudgetModell(schulung=("Schulung",), historie_monate=6)

    prognose = _bestand_mit_coaching().simulieren(
        monate=1, laeufe=5, zufall=np.random.default_rng(1), ohne_budget=modell
    )

    assert _monatswert(prognose) == pytest.approx(5000.0)
    assert prognose.kapazitaet_je_projekt()[2] == pytest.approx(10.0)


def test_ausgeschlossene_projekte_ohne_budget_tragen_nichts_bei():
    modell = OhneBudgetModell(ausschluss=("Coaching",), schulung=("Schulung",))

    prognose = _bestand_mit_coaching().simulieren(
        monate=1, laeufe=5, zufall=np.random.default_rng(1), ohne_budget=modell
    )

    assert _monatswert(prognose) == pytest.approx(4000.0)


@pytest.mark.parametrize(
    ("abschlag", "referenz", "erwartet"),
    [
        (0.5, 0.5, 5000.0),  # angenommener Anteil wie bisher: Faktor 1
        (0.5, 0.25, 6000.0),  # doppelt so viel Kundenzeit wie bisher: Faktor 2
        (0.5, 1.0, 4500.0),  # halb so viel wie bisher: Faktor 0,5
        (0.5, None, 5000.0),  # ohne Referenz keine Skalierung
    ],
)
def test_anteil_fakturierbarer_arbeit_skaliert_den_bedarf_relativ_zur_referenz(
    abschlag, referenz, erwartet
):
    modell = OhneBudgetModell(schulung=("Schulung",))

    prognose = _bestand_mit_coaching().simulieren(
        monate=1,
        laeufe=5,
        zufall=np.random.default_rng(1),
        interne_arbeit_abschlag=abschlag,
        ohne_budget=modell,
        anteil_fakturierbar_referenz=referenz,
    )

    assert _monatswert(prognose) == pytest.approx(erwartet)


def test_schulungsstunden_mindern_die_verfuegbare_kapazitaet():
    """September 2026 hat 22 Arbeitstage = 440 h. Bedarf: 80 h Budgetprojekt + 10 h
    Coaching. Ohne Schulung passt alles hinein; 400 h Schulung lassen nur 40 h uebrig."""
    modell = OhneBudgetModell(schulung=("Schulung",))

    frei = _bestand_mit_coaching().simulieren(
        monate=1, laeufe=5, zufall=np.random.default_rng(1), ohne_budget=modell
    )
    belegt = _bestand_mit_coaching(schulung_stunden=400.0).simulieren(
        monate=1, laeufe=5, zufall=np.random.default_rng(1), ohne_budget=modell
    )

    assert frei.kapazitaet_limitierend_anteil() == 0.0
    assert belegt.kapazitaet_limitierend_anteil() == 1.0
    assert _monatswert(belegt) < _monatswert(frei)


def test_ohne_budget_weist_den_anteil_der_projekte_ohne_budget_je_monat_aus():
    modell = OhneBudgetModell(schulung=("Schulung",))
    b = _bestand_mit_coaching()

    mit = b.simulieren(monate=2, laeufe=5, zufall=np.random.default_rng(1), ohne_budget=modell)
    ohne = b.simulieren(monate=2, laeufe=5, zufall=np.random.default_rng(1))

    # Monat 1 ist der ganze Monat (Stichtag am Monatsanfang), Monat 2 ebenso: 1000 Euro.
    assert [float(w) for w in mit.ohne_budget()] == [pytest.approx(1000.0)] * 2
    assert [float(w) for w in ohne.ohne_budget()] == [0.0, 0.0]
