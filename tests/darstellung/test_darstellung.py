"""Tests zu Diagrammen, Tabellen und Dashboard - alle ohne Netzzugriff.

Geprueft wird nicht das Aussehen, sondern was ueberhaupt dargestellt wird: dass die
Zahlen aus der Domaene unveraendert ankommen, dass der laufende Monat abgesetzt bleibt
und dass gleichnamige Projekte nicht zu einem Balken verschmelzen.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from umsatzprognose.clockodo import AuslastungRepository, BestandRepository
from umsatzprognose.darstellung import Dashboard, Ladedauern, diagramme, tabellen
from umsatzprognose.darstellung.dashboard import (
    _abgeschlossene_monate,
    _aktive_mitarbeiter,
    _historie_monate,
    _Stoppuhr,
)
from umsatzprognose.darstellung.gestaltung import (
    ERGEBNIS_NEGATIV,
    ERGEBNIS_POSITIV,
    JAHRESFARBEN,
    KOSTEN,
    KOSTEN_HELL,
    PROGNOSE_DECKKRAFT,
    SCHULUNG,
    SERIE_HELL,
    VORLAEUFIG_DECKKRAFT,
)
from umsatzprognose.domaene import (
    Anmeldung,
    Anmeldungsverlauf,
    Auslastungsmonat,
    Bestand,
    Erfasst,
    Gesamtbudget,
    Hinweis,
    Kostenplan,
    Kostenposten,
    Kunde,
    Mitarbeiter,
    Monatsumsatz,
    Projekt,
    Projektanteil,
    Schulungsplan,
    Schulungstermin,
    Umsatzhistorie,
    Verbrauchsverlauf,
    Wochenarbeitszeit,
)
from umsatzprognose.domaene.projekt import OHNE_BUDGET
from umsatzprognose.domaene.zahlen import STUNDEN_JE_TAG, euro
from umsatzprognose.kosten import KostenRepository
from umsatzprognose.schulungen import SchulungenRepository

STICHTAG = date(2026, 8, 24)
KUNDE = Kunde(id=7, name="Union Asset Management Holding AG")

HISTORIE = Umsatzhistorie.zum_stichtag(
    [Monatsumsatz(2026, 7, 300000.0, 2000.0), Monatsumsatz(2026, 8, 50000.0, 400.0)],
    STICHTAG,
)
PROJEKTE = (
    Projekt(id=1, name="Beispielprojekt Eins", kunde=KUNDE, aktiv=True,
            budget=Gesamtbudget(betrag=50000.0),
            verbrauchtes_volumen=16000.0, verbrauchte_stunden=100.0),
    Projekt(id=2, name="Beispielprojekt Zwei", kunde=KUNDE, aktiv=True,
            budget=Gesamtbudget(betrag=20000.0),
            verbrauchtes_volumen=7000.0, verbrauchte_stunden=50.0),
)  # fmt: skip
BESTAND = Bestand(stichtag=STICHTAG, projekte=PROJEKTE, umsatzhistorie=HISTORIE)
SCHULUNGSPLAN = Schulungsplan(stichtag=STICHTAG, termine=())
KOSTENPLAN = Kostenplan()


def _historie_fuer_abrufquote(quote: float) -> Verbrauchsverlauf:
    """Ein einzelner Beobachtungsmonat, der die Abrufquote-Verteilung auf ``quote`` setzt.

    Dasselbe Muster wie in ``tests/test_simulation.py``: das Projekt liegt ausserhalb
    des Prognose-Scope und traegt selbst keinen Umsatz bei, nur die eine Beobachtung.
    """
    projekt = Projekt(id=900, name="Historie", aktiv=False, budget=Gesamtbudget(betrag=1000.0))
    return Verbrauchsverlauf.fuer(
        projekt, [Monatsumsatz(jahr=2026, monat=6, umsatz=quote * 1000.0, stunden=1.0)]
    )


ANMELDUNGSVERLAUF_KATEGORIEN = {
    "Scrum": ["CSM 2-tägig"],
    "Kanban": ["KSD"],
}


def test_anmeldungsverlauf_zeigt_eine_linie_je_kategorie_sowie_gesamt_und_trend():
    verlauf = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "CSM 2-tägig", 5),
            Anmeldung(2026, 9, "KSD", 2),
            Anmeldung(2026, 9, "Produktmanagement", 1),
            Anmeldung(2026, 10, "CSM 2-tägig", 3),
            Anmeldung(2026, 11, "CSM 2-tägig", 4),
        )
    )
    fig = diagramme.anmeldungsverlauf(verlauf, ANMELDUNGSVERLAUF_KATEGORIEN)

    namen = {spur.name for spur in fig.data}
    assert namen == {"Scrum", "Kanban", "Sonstige", "Gesamt", "Trend"}
    assert all(spur.type == "scatter" for spur in fig.data)
    assert fig.layout.barmode is None

    scrum = next(s for s in fig.data if s.name == "Scrum")
    assert scrum.mode == "lines+markers"
    assert list(scrum.x) == ["Sep 2026", "Okt 2026", "Nov 2026"]
    assert list(scrum.y) == [5, 3, 4]

    kanban = next(s for s in fig.data if s.name == "Kanban")
    assert list(kanban.y) == [2, 0, 0]

    sonstige = next(s for s in fig.data if s.name == "Sonstige")
    assert list(sonstige.y) == [1, 0, 0]

    gesamt = next(s for s in fig.data if s.name == "Gesamt")
    assert list(gesamt.y) == [8, 3, 4]

    # Ausgleichsgerade durch (0, 8), (1, 3), (2, 4) - von Hand nachgerechnet.
    trend = next(s for s in fig.data if s.name == "Trend")
    assert list(trend.y) == pytest.approx([7.0, 5.0, 3.0])


def test_anmeldungsverlauf_ohne_konfigurierte_kategorien_zeigt_nur_sonstige():
    verlauf = Anmeldungsverlauf(anmeldungen=(Anmeldung(2026, 9, "CSM 2-tägig", 5),))
    fig = diagramme.anmeldungsverlauf(verlauf, {})
    namen = {spur.name for spur in fig.data}
    assert namen == {"Sonstige", "Gesamt", "Trend"}


def test_linearer_trend_legt_eine_ausgleichsgerade_durch_die_werte():
    assert diagramme._linearer_trend([8.0, 3.0, 4.0]) == pytest.approx([7.0, 5.0, 3.0])


def test_linearer_trend_mit_einem_wert_bleibt_unveraendert():
    assert diagramme._linearer_trend([8.0]) == [8.0]


def test_linearer_trend_ohne_werte_ist_leer():
    assert diagramme._linearer_trend([]) == []


def test_anmeldungsverlauf_ohne_daten_zeigt_hinweis_statt_balken():
    fig = diagramme.anmeldungsverlauf(Anmeldungsverlauf(), ANMELDUNGSVERLAUF_KATEGORIEN)
    assert fig.data == ()
    assert (
        fig.layout.annotations[0].text == "Keine Anmeldedaten für den gewählten Zeitraum geladen."
    )


def test_umsatzverlauf_zeigt_alle_monate_und_hebt_den_laufenden_hervor():
    fig = diagramme.umsatzverlauf(HISTORIE)
    balken = fig.data[0]

    assert len(balken.x) == 13
    assert balken.x[-1] == "Aug 2026"
    # Der laufende Monat bekommt die hellere Stufe derselben Farbe.
    assert balken.marker.color[-1] != balken.marker.color[-2]


def test_gleichnamige_projekte_bleiben_getrennte_balken():
    # Beide Projekte gehoeren demselben Kunden und beginnen gleich. Waere die
    # Beschriftung die Kategorie, wuerde plotly ihre Betraege addieren.
    doppelt = tuple(p for p in PROJEKTE)
    fig = diagramme.restvolumen_je_projekt(doppelt)
    balken = fig.data[0]

    assert len(balken.x) == 2
    assert sorted(balken.x) == [13000.0, 34000.0]
    assert len(set(balken.y)) == 2


def test_balkenlaenge_bleibt_im_bild():
    fig = diagramme.restvolumen_je_projekt(PROJEKTE)
    assert fig.layout.xaxis.range[1] > max(fig.data[0].x)


def test_kapazitaet_je_mitarbeiter_zeigt_werte_in_tagen():
    anna = Mitarbeiter(id=1, name="Anna", aktiv=True)
    bert = Mitarbeiter(id=2, name="Bert", aktiv=True)
    fig = diagramme.kapazitaet_je_mitarbeiter([(anna, 140.0), (bert, 70.0)])
    balken = fig.data[0]

    # Kleinster Wert unten (Position 0), groesster oben - wie bei restvolumen_je_projekt.
    assert list(balken.x) == [10.0, 20.0]
    assert list(balken.text) == ["10,0 Tage", "20,0 Tage"]


def test_kapazitaet_je_projekt_zeigt_null_bei_pauschalprojekt():
    zeitbasiert = Projekt(id=1, name="Zeitbasiert", aktiv=True, budget=Gesamtbudget(betrag=1000.0))
    pauschal = Projekt(id=2, name="Pauschale", aktiv=True, budget=Gesamtbudget(betrag=1000.0))
    fig = diagramme.kapazitaet_je_projekt([(zeitbasiert, 70.0), (pauschal, 0.0)])
    balken = fig.data[0]

    assert list(balken.x) == [0.0, 10.0]
    assert list(balken.text) == ["0,0 Tage", "10,0 Tage"]


def test_gewinn_verlust_monatlich_faerbt_nach_vorzeichen():
    monate = [Monatsumsatz(2026, 7, 50000.0), Monatsumsatz(2026, 8, 30000.0)]
    fig = diagramme.gewinn_verlust_monatlich(monate, [40000.0, 40000.0])
    balken = fig.data[0]

    assert list(balken.x) == ["Jul 2026", "Aug 2026"]
    assert list(balken.y) == [10000.0, -10000.0]
    assert list(balken.marker.color) == [ERGEBNIS_POSITIV, ERGEBNIS_NEGATIV]


def test_gewinn_verlust_je_jahr_zeigt_monatswerte_nicht_kumuliert():
    monate = [Monatsumsatz(2026, 7, 50000.0), Monatsumsatz(2026, 8, 10000.0)]
    fig = diagramme.gewinn_verlust_je_jahr(monate, [40000.0, 40000.0])
    linie = fig.data[0]

    assert list(linie.x) == ["Jul", "Aug"]
    # Das Ergebnis jedes Monats einzeln (50000-40000, 10000-40000) - keine Summenlinie.
    assert list(linie.y) == [10000.0, -30000.0]
    # Ein einzelnes Jahr bekommt die erste Farbe der Jahrespalette, nicht Gruen/Rot
    # nach Vorzeichen - das gilt nur fuer den einzelnen Ergebnis-Balken.
    assert linie.line.color == JAHRESFARBEN[0]
    assert linie.name == "2026"


def test_gewinn_verlust_monatlich_haengt_prognosehorizont_gedaempft_an():
    historie, prognose = _historie_und_prognose_mit_horizont()
    monate = historie.abgeschlossene()  # nur August - September ist der laufende Monat
    fig = diagramme.gewinn_verlust_monatlich(
        monate,
        [40000.0],
        prognose=prognose,
        horizont_kosten=[15000.0, 12000.0],
        verbrauch_laufender_monat=historie.laufender,
    )
    balken = fig.data[0]
    median = prognose.monatswerte()[0.50]

    assert list(balken.x) == ["Aug 2026", "Sep 2026", "Okt 2026"]
    # September (erster Horizontmonat) traegt zusaetzlich das vor dem Stichtag bereits
    # realisierte historie.laufender.umsatz - dieselbe Rechnung wie im Umsatzverlauf.
    erwartetes_ergebnis = [
        100000.0 - 40000.0,
        (historie.laufender.umsatz + median[0]) - 15000.0,
        median[1] - 12000.0,
    ]
    assert list(balken.y) == pytest.approx(erwartetes_ergebnis)
    # September ist der laufende Monat (erster Horizontmonat) - vorlaeufig, nicht rein
    # simuliert wie Oktober.
    assert list(balken.marker.opacity) == [1.0, VORLAEUFIG_DECKKRAFT, PROGNOSE_DECKKRAFT]


def test_gewinn_verlust_monatlich_ohne_prognose_bleibt_wie_zuvor():
    monate = [Monatsumsatz(2026, 7, 50000.0)]
    fig = diagramme.gewinn_verlust_monatlich(monate, [40000.0])
    assert list(fig.data[0].marker.opacity) == [1.0]
    # Ohne Prognose gibt es nichts zu unterscheiden - keine Sicherheits-Legende.
    assert not any(spur.name == "Daten" for spur in fig.data)


def test_gewinn_verlust_monatlich_zeigt_datensicherheits_legende_mit_prognose():
    historie, prognose = _historie_und_prognose_mit_horizont()
    monate = historie.abgeschlossene()
    fig = diagramme.gewinn_verlust_monatlich(
        monate,
        [40000.0],
        prognose=prognose,
        horizont_kosten=[15000.0, 12000.0],
        verbrauch_laufender_monat=historie.laufender,
    )
    legende = {spur.name: spur.marker.opacity for spur in fig.data if spur.showlegend}
    assert legende == {
        "Daten": 1.0,
        "Vorläufig": VORLAEUFIG_DECKKRAFT,
        "Prognose": PROGNOSE_DECKKRAFT,
    }


def test_gewinn_verlust_je_jahr_setzt_prognose_gestrichelt_und_bruchlos_fort():
    historie, prognose = _historie_und_prognose_mit_horizont()
    monate = historie.abgeschlossene()
    fig = diagramme.gewinn_verlust_je_jahr(
        monate,
        [40000.0],
        prognose=prognose,
        horizont_kosten=[15000.0, 12000.0],
        verbrauch_laufender_monat=historie.laufender,
    )
    # September (erster Horizontmonat) ist derselbe Kalendermonat wie der laufende -
    # vorlaeufig statt rein simuliert, deshalb eine dritte Spur zwischen Ist und
    # Prognose (Oktober).
    ist_spur, vorlaeufig_spur, prognose_spur = fig.data[0], fig.data[1], fig.data[2]

    assert list(ist_spur.x) == ["Aug"]
    assert ist_spur.line.dash is None
    assert ist_spur.opacity == 1.0

    # Die Vorlaeufig-Spur beginnt am letzten Ist-Punkt, damit die Linie ohne Bruch
    # weiterlaeuft - durchgezogen wie die Ist-Spur, aber mit mittlerer Deckkraft.
    assert list(vorlaeufig_spur.x) == ["Aug", "Sep"]
    assert vorlaeufig_spur.y[0] == ist_spur.y[-1]
    assert vorlaeufig_spur.line.dash is None
    assert vorlaeufig_spur.opacity == VORLAEUFIG_DECKKRAFT

    # Die Prognose-Spur beginnt entsprechend am Vorlaeufig-Punkt und ist gestrichelt.
    assert list(prognose_spur.x) == ["Sep", "Okt"]
    assert prognose_spur.y[0] == vorlaeufig_spur.y[-1]
    assert prognose_spur.line.dash == "dot"
    assert prognose_spur.opacity == PROGNOSE_DECKKRAFT

    # Alle drei Spuren gehoeren zum selben Jahr - eine gemeinsame Legende, kein
    # weiterer Eintrag fuer Vorlaeufig/Prognose.
    assert ist_spur.name == vorlaeufig_spur.name == prognose_spur.name == "2026"
    assert ist_spur.showlegend is True
    assert vorlaeufig_spur.showlegend is False
    assert prognose_spur.showlegend is False


def test_gewinn_verlust_je_jahr_teilt_die_monate_nach_kalenderjahr():
    monate = [
        Monatsumsatz(2025, 11, 10000.0),
        Monatsumsatz(2025, 12, 15000.0),
        Monatsumsatz(2026, 1, 30000.0),
        Monatsumsatz(2026, 2, 10000.0),
    ]
    fig = diagramme.gewinn_verlust_je_jahr(monate, [0.0, 0.0, 0.0, 0.0])
    spur_2025, spur_2026 = fig.data[0], fig.data[1]

    assert spur_2025.name == "2025"
    assert list(spur_2025.x) == ["Nov", "Dez"]
    assert list(spur_2025.y) == [10000.0, 15000.0]
    assert spur_2025.line.color == JAHRESFARBEN[0]

    # Eigene Serie ab Januar, unabhaengig von den Werten aus 2025 - kein durchgehendes Fenster.
    assert spur_2026.name == "2026"
    assert list(spur_2026.x) == ["Jan", "Feb"]
    assert list(spur_2026.y) == [30000.0, 10000.0]
    assert spur_2026.line.color == JAHRESFARBEN[1]


def test_gewinn_verlust_je_jahr_prognose_in_neuem_jahr_startet_ohne_ist_abschnitt():
    stichtag = date(2026, 12, 1)
    historie = Umsatzhistorie.zum_stichtag(
        [Monatsumsatz(2026, 11, 30000.0), Monatsumsatz(2026, 12, 5000.0)],
        stichtag,
        abgeschlossene=1,
    )
    monate = historie.abgeschlossene()
    projekt = Projekt(
        id=1, name="Projekt", kunde=KUNDE, aktiv=True,
        budget=Gesamtbudget(betrag=220000.0),
        verbrauchtes_volumen=20000.0, verbrauchte_stunden=200.0,
    )  # fmt: skip
    bestand = Bestand(
        stichtag=stichtag,
        projekte=(projekt,),
        umsatzhistorie=historie,
        verbrauchsverlaeufe=(_historie_fuer_abrufquote(0.2),),
    )
    prognose = bestand.simulieren(monate=2, laeufe=5, zufall=np.random.default_rng(1))
    assert prognose.vorhanden
    assert prognose.horizontmonate() == ((2026, 12), (2027, 1))

    fig = diagramme.gewinn_verlust_je_jahr(
        monate,
        [40000.0],
        prognose=prognose,
        horizont_kosten=[15000.0, 12000.0],
        verbrauch_laufender_monat=historie.laufender,
    )
    # 2026: Ist (November) plus vorlaeufiger Dezember - beide durchgezogen, per
    # Deckkraft unterschieden, keiner davon gestrichelt (Dezember ist derselbe
    # Kalendermonat wie der laufende, kein reines Simulationsergebnis). 2027 (nur
    # Januar) ist rein simuliert und komplett gestrichelt, ohne eigenen Ist-Abschnitt.
    # fig.data enthaelt danach noch unsichtbare Spuren fuer die Daten-Sicherheits-Legende
    # (siehe _datensicherheit_legende) - hier interessieren nur die drei Jahreslinien.
    jahresspuren = fig.data[:3]
    namen_dash_deckkraft = [(spur.name, spur.line.dash, spur.opacity) for spur in jahresspuren]
    assert namen_dash_deckkraft == [
        ("2026", None, 1.0),
        ("2026", None, VORLAEUFIG_DECKKRAFT),
        ("2027", "dot", PROGNOSE_DECKKRAFT),
    ]
    assert jahresspuren[0].showlegend is True
    assert jahresspuren[1].showlegend is False
    assert jahresspuren[2].showlegend is True  # 2027 braucht trotzdem einen Legendeneintrag


def test_gewinn_verlust_je_jahr_zeigt_datensicherheits_legende_mit_prognose():
    historie, prognose = _historie_und_prognose_mit_horizont()
    monate = historie.abgeschlossene()
    fig = diagramme.gewinn_verlust_je_jahr(
        monate,
        [40000.0],
        prognose=prognose,
        horizont_kosten=[15000.0, 12000.0],
        verbrauch_laufender_monat=historie.laufender,
    )
    legende = {spur.name: spur.marker.opacity for spur in fig.data if spur.name not in {"2026"}}
    assert legende == {
        "Daten": 1.0,
        "Vorläufig": VORLAEUFIG_DECKKRAFT,
        "Prognose": PROGNOSE_DECKKRAFT,
    }


def test_umsatzrendite_kumuliert_zeigt_datensicherheits_legende_mit_prognose():
    historie, prognose = _historie_und_prognose_mit_horizont()
    monate = historie.abgeschlossene()
    fig = diagramme.umsatzrendite_kumuliert(
        monate,
        [40000.0],
        prognose=prognose,
        horizont_kosten=[15000.0, 12000.0],
        verbrauch_laufender_monat=historie.laufender,
    )
    legende = {spur.name: spur.marker.opacity for spur in fig.data if spur.name not in {"2026"}}
    assert legende == {
        "Daten": 1.0,
        "Vorläufig": VORLAEUFIG_DECKKRAFT,
        "Prognose": PROGNOSE_DECKKRAFT,
    }


def test_gewinn_verlust_je_jahr_ohne_prognose_zeigt_keine_datensicherheits_legende():
    monate = [Monatsumsatz(2026, 7, 50000.0)]
    fig = diagramme.gewinn_verlust_je_jahr(monate, [40000.0])
    assert not any(spur.name == "Daten" for spur in fig.data)


def test_auslastung_je_mitarbeiter_zeigt_prozent_und_laesst_none_weg():
    vollzeit = Wochenarbeitszeit(
        stunden_je_wochentag=(8.0, 8.0, 8.0, 8.0, 8.0, 0.0, 0.0), gueltig_ab=date(2020, 1, 1)
    )
    anna = Mitarbeiter(id=1, name="Anna", aktiv=True, arbeitszeiten=(vollzeit,))
    bert = Mitarbeiter(id=2, name="Bert", aktiv=True, arbeitszeiten=(vollzeit,))
    ohne_kapazitaet = Mitarbeiter(id=3, name="Clara", aktiv=True)
    auslastungen = [
        Auslastungsmonat(mitarbeiter=anna, jahr=2026, monat=9, abrechenbare_stunden=80.0),
        Auslastungsmonat(mitarbeiter=bert, jahr=2026, monat=9, abrechenbare_stunden=160.0),
        Auslastungsmonat(mitarbeiter=ohne_kapazitaet, jahr=2026, monat=9),
    ]
    fig = diagramme.auslastung_je_mitarbeiter(auslastungen)
    balken = fig.data[0]

    # Clara hat keine verfuegbare Kapazitaet (keine Arbeitszeit hinterlegt) und faellt
    # deshalb heraus, statt mit einer irrefuehrenden 0%-Auslastung zu erscheinen.
    # Kleinster Wert unten (Position 0): Anna (80/176 ≈ 45 %) vor Bert (160/176 ≈ 91 %).
    assert len(balken.x) == 2
    assert list(balken.text) == ["45 %", "91 %"]


def test_umsatzverlauf_ohne_prognose_zeigt_nur_die_historie_balken():
    fig = diagramme.umsatzverlauf(HISTORIE)
    balkenspuren = [spur for spur in fig.data if spur.type == "bar"]
    assert len(balkenspuren) == 1
    assert len(balkenspuren[0].x) == 13


def test_umsatzverlauf_zeigt_legende_fuer_die_farben():
    fig = diagramme.umsatzverlauf(HISTORIE)
    assert fig.layout.showlegend is True
    legende = {spur.name for spur in fig.data if spur.showlegend}
    # Ohne Prognose gibt es nur zwei Farben: abgerechnet und nicht abgerechnet.
    assert legende == {"Abgerechnet", "Nicht abgerechnet"}


def test_umsatzverlauf_nennt_den_grund_ohne_bandbreite():
    fig = diagramme.umsatzverlauf(HISTORIE, BESTAND.simulieren())
    assert any("Abrufquote" in a.text for a in fig.layout.annotations)


def test_umsatzverlauf_haengt_horizont_mit_zwei_farbtoenen_an():
    stichtag = date(2026, 9, 1)
    historie = Umsatzhistorie.zum_stichtag(
        [Monatsumsatz(2026, 8, 100000.0, 800.0), Monatsumsatz(2026, 9, 20000.0, 150.0)],
        stichtag,
        abgeschlossene=1,
    )
    anna = Mitarbeiter(
        id=1,
        name="Anna",
        aktiv=True,
        arbeitszeiten=(
            Wochenarbeitszeit(
                stunden_je_wochentag=(999.0, 999.0, 999.0, 999.0, 999.0, 0.0, 0.0),
                gueltig_ab=date(2020, 1, 1),
            ),
        ),
    )
    projekt = Projekt(
        id=1,
        name="Projekt",
        kunde=KUNDE,
        aktiv=True,
        budget=Gesamtbudget(betrag=220000.0),
        verbrauchtes_volumen=20000.0,
        verbrauchte_stunden=200.0,
        anteile=(Projektanteil(anna, stunden=200.0),),
    )
    # Eine Buchung im zweiten Horizontmonat, damit auch die "Bereits gebucht"-Spur
    # etwas zu zeichnen hat.
    verlauf_projekt = Verbrauchsverlauf.fuer(
        projekt, [Monatsumsatz(jahr=2026, monat=10, umsatz=5000.0, stunden=50.0)]
    )
    bestand = Bestand(
        stichtag=stichtag,
        projekte=(projekt,),
        mitarbeiter=(anna,),
        umsatzhistorie=historie,
        verbrauchsverlaeufe=(_historie_fuer_abrufquote(0.2), verlauf_projekt),
    )
    prognose = bestand.simulieren(monate=2, laeufe=5, zufall=np.random.default_rng(1))
    assert prognose.vorhanden

    fig = diagramme.umsatzverlauf(historie, prognose)
    namen = [spur.name for spur in fig.data]
    assert "Bereits gebucht" in namen
    assert "Prognostiziert" in namen

    gebucht_spur = next(s for s in fig.data if s.name == "Bereits gebucht")
    prognostiziert_spur = next(s for s in fig.data if s.name == "Prognostiziert")
    # "Bereits gebucht" ist ein kuenftiger, aber noch nicht abgerechneter Betrag und
    # teilt sich deshalb die Farbe mit dem laufenden Monat (hell), nicht mit der
    # abgerechneten Historie (satt) - unterscheidbar von "prognostiziert" einzig ueber
    # die Deckkraft.
    assert gebucht_spur.marker.color == SERIE_HELL
    assert prognostiziert_spur.marker.color == SERIE_HELL
    assert prognostiziert_spur.marker.opacity == PROGNOSE_DECKKRAFT
    assert gebucht_spur.marker.opacity in (None, 1.0)

    # Die Legende benennt alle drei Farben, "Bereits gebucht" teilt sich ihre Farbe
    # bewusst mit "Nicht abgerechnet" und bekommt deshalb kein eigenes Feld.
    legende = {spur.name for spur in fig.data if spur.showlegend}
    assert legende == {"Abgerechnet", "Nicht abgerechnet", "Prognostiziert"}


def _historie_und_prognose_mit_horizont():
    """Historie samt Prognose ueber zwei Horizontmonate - Grundlage der Schulungs-Tests."""
    stichtag = date(2026, 9, 1)
    historie = Umsatzhistorie.zum_stichtag(
        [Monatsumsatz(2026, 8, 100000.0, 800.0), Monatsumsatz(2026, 9, 20000.0, 150.0)],
        stichtag,
        abgeschlossene=1,
    )
    projekt = Projekt(
        id=1, name="Projekt", kunde=KUNDE, aktiv=True,
        budget=Gesamtbudget(betrag=220000.0),
        verbrauchtes_volumen=20000.0, verbrauchte_stunden=200.0,
    )  # fmt: skip
    bestand = Bestand(
        stichtag=stichtag,
        projekte=(projekt,),
        umsatzhistorie=historie,
        verbrauchsverlaeufe=(_historie_fuer_abrufquote(0.2),),
    )
    prognose = bestand.simulieren(monate=2, laeufe=5, zufall=np.random.default_rng(1))
    assert prognose.vorhanden
    return historie, prognose


def test_umsatzverlauf_mit_schulungsplan_zeigt_eigenes_segment_und_legende():
    historie, prognose = _historie_und_prognose_mit_horizont()
    schulungsplan = Schulungsplan(
        stichtag=historie.stichtag,
        termine=(Schulungstermin(2026, 9, 3000.0), Schulungstermin(2026, 10, 1500.0)),
    )

    fig = diagramme.umsatzverlauf(historie, prognose, schulungsplan)
    namen = [spur.name for spur in fig.data]
    assert "Schulungsanmeldungen" in namen

    schulung_spur = next(s for s in fig.data if s.name == "Schulungsanmeldungen")
    assert list(schulung_spur.y) == [3000.0, 1500.0]
    assert schulung_spur.marker.color == SCHULUNG

    legende = {spur.name for spur in fig.data if spur.showlegend}
    assert "Schulungsanmeldungen" in legende


def test_umsatzverlauf_ohne_schulungsplan_zeigt_kein_segment():
    fig = diagramme.umsatzverlauf(HISTORIE, BESTAND.simulieren())
    namen = [spur.name for spur in fig.data]
    assert "Schulungsanmeldungen" not in namen


def test_umsatzverlauf_mit_kostenplan_zeigt_balken_fuer_historie_und_horizont():
    historie, prognose = _historie_und_prognose_mit_horizont()
    kostenplan = Kostenplan(
        posten=(
            Kostenposten(2026, 8, 40000.0),
            Kostenposten(2026, 9, 15000.0),
            Kostenposten(2026, 10, 12000.0),
        )
    )

    fig = diagramme.umsatzverlauf(historie, prognose, None, kostenplan)
    kosten_spur = next(s for s in fig.data if s.name == "Kosten")
    assert kosten_spur.type == "bar"
    assert list(kosten_spur.x) == ["Aug 2026", "Sep 2026", "Okt 2026"]
    assert list(kosten_spur.y) == [40000.0, 15000.0, 12000.0]
    # Keiner der Posten hat eine Kostenerfassung -> ueberall die helle Pauschale-Farbe.
    assert list(kosten_spur.marker.color) == [KOSTEN_HELL, KOSTEN_HELL, KOSTEN_HELL]

    median = prognose.monatswerte()[0.50]
    erwartetes_ergebnis = [
        100000.0 - 40000.0,
        (historie.laufender.umsatz + median[0]) - 15000.0,
        median[1] - 12000.0,
    ]
    ergebnis_spur = next(s for s in fig.data if s.name == "Ergebnis")
    assert ergebnis_spur.type == "bar"
    assert list(ergebnis_spur.y) == erwartetes_ergebnis
    assert list(ergebnis_spur.marker.color) == [
        ERGEBNIS_POSITIV if betrag >= 0 else ERGEBNIS_NEGATIV for betrag in erwartetes_ergebnis
    ]

    legende = {spur.name for spur in fig.data if spur.showlegend}
    assert legende == {
        "Abgerechnet",
        "Nicht abgerechnet",
        "Prognostiziert",
        "Kosten (Pauschale)",
        "Ergebnis (positiv)",
        "Ergebnis (negativ)",
    }


def test_umsatzverlauf_mit_kostenerfassung_zeigt_satteres_rot_und_eigene_legende():
    historie, prognose = _historie_und_prognose_mit_horizont()
    kostenplan = Kostenplan(
        posten=(
            Kostenposten(
                2026, 8, pauschale=40000.0, allgemeinkosten=10000.0, erfassung=Erfasst(12000.0)
            ),
            Kostenposten(2026, 9, 15000.0),
            Kostenposten(2026, 10, 12000.0),
        )
    )

    fig = diagramme.umsatzverlauf(historie, prognose, None, kostenplan)
    kosten_spur = next(s for s in fig.data if s.name == "Kosten")
    # Nur der August hat eine Kostenerfassung -> satte Farbe nur dort, sonst hell.
    assert list(kosten_spur.marker.color) == [KOSTEN, KOSTEN_HELL, KOSTEN_HELL]

    legende = {spur.name for spur in fig.data if spur.showlegend}
    assert "Kosten (erfasst)" in legende
    assert "Kosten (Pauschale)" in legende


def test_umsatzverlauf_ohne_kostenplan_zeigt_keine_kosten_und_ergebnis_balken():
    fig = diagramme.umsatzverlauf(HISTORIE, BESTAND.simulieren())
    namen = [spur.name for spur in fig.data]
    assert "Kosten" not in namen
    assert "Ergebnis" not in namen


def test_umsatzverlauf_kostenplan_ohne_werte_zeigt_keine_kosten_und_ergebnis_balken():
    historie, prognose = _historie_und_prognose_mit_horizont()
    fig = diagramme.umsatzverlauf(historie, prognose, None, Kostenplan())
    namen = [spur.name for spur in fig.data]
    assert "Kosten" not in namen
    assert "Ergebnis" not in namen


def test_umsatztabelle_mit_schulungsplan_ergaenzt_spalte_und_summe():
    historie, prognose = _historie_und_prognose_mit_horizont()
    schulungsplan = Schulungsplan(
        stichtag=historie.stichtag,
        termine=(Schulungstermin(2026, 9, 3000.0), Schulungstermin(2026, 10, 1500.0)),
    )

    tabelle = tabellen.umsatztabelle(historie, prognose, schulungsplan)
    sep, okt = tabelle.iloc[1], tabelle.iloc[2]
    assert sep["Schulungsanmeldungen"] == "3.000,00 EUR"
    assert okt["Schulungsanmeldungen"] == "1.500,00 EUR"

    erwartete_sep_summe = historie.laufender.umsatz + prognose.monatswerte()[0.50][0] + 3000.0
    assert sep["Summe"] == euro(erwartete_sep_summe)


def test_umsatztabelle_ohne_schulungsplan_laesst_spalte_leer():
    tabelle = tabellen.umsatztabelle(HISTORIE, BESTAND.simulieren())
    assert (tabelle["Schulungsanmeldungen"] != "").sum() == 0


def test_umsatztabelle_mit_kostenplan_ergaenzt_kosten_und_gewinn_fuer_historie_und_horizont():
    historie, prognose = _historie_und_prognose_mit_horizont()
    kostenplan = Kostenplan(
        posten=(
            Kostenposten(2026, 8, 40000.0),
            Kostenposten(2026, 9, 15000.0),
            Kostenposten(2026, 10, 12000.0),
        )
    )

    tabelle = tabellen.umsatztabelle(historie, prognose, None, kostenplan)
    aug, sep, okt = tabelle.iloc[0], tabelle.iloc[1], tabelle.iloc[2]

    assert aug["Kosten"] == euro(40000.0)
    assert aug["Gewinn"] == euro(100000.0 - 40000.0)

    erwartete_sep_summe = historie.laufender.umsatz + prognose.monatswerte()[0.50][0]
    assert sep["Kosten"] == euro(15000.0)
    assert sep["Gewinn"] == euro(erwartete_sep_summe - 15000.0)

    erwartete_okt_summe = prognose.monatswerte()[0.50][1]
    assert okt["Kosten"] == euro(12000.0)
    assert okt["Gewinn"] == euro(erwartete_okt_summe - 12000.0)


def test_umsatztabelle_ohne_kostenplan_laesst_spalten_leer():
    tabelle = tabellen.umsatztabelle(HISTORIE, BESTAND.simulieren())
    assert (tabelle["Kosten"] != "").sum() == 0
    assert (tabelle["Gewinn"] != "").sum() == 0


def test_dashboard_hinweise_enthaelt_luecken_des_schulungsplans():
    historie, _prognose = _historie_und_prognose_mit_horizont()
    projekt = Projekt(
        id=1,
        name="Projekt",
        kunde=KUNDE,
        aktiv=True,
        budget=Gesamtbudget(betrag=220000.0),
        verbrauchtes_volumen=20000.0,
        verbrauchte_stunden=200.0,
    )
    bestand = Bestand(
        stichtag=historie.stichtag,
        projekte=(projekt,),
        umsatzhistorie=historie,
        verbrauchsverlaeufe=(_historie_fuer_abrufquote(0.2),),
    )
    schulungsplan = Schulungsplan(stichtag=historie.stichtag, termine=())
    dashboard = Dashboard(bestand, schulungsplan, KOSTENPLAN)
    dashboard.prognose = bestand.simulieren(monate=2, laeufe=5, zufall=np.random.default_rng(1))

    hinweise = dashboard.hinweise()
    assert any("Schulungsanmeldung" in text for text in hinweise["Hinweis"])


def test_dashboard_hinweise_enthaelt_luecken_des_kostenplans():
    historie, _prognose = _historie_und_prognose_mit_horizont()
    projekt = Projekt(
        id=1,
        name="Projekt",
        kunde=KUNDE,
        aktiv=True,
        budget=Gesamtbudget(betrag=220000.0),
        verbrauchtes_volumen=20000.0,
        verbrauchte_stunden=200.0,
    )
    bestand = Bestand(
        stichtag=historie.stichtag,
        projekte=(projekt,),
        umsatzhistorie=historie,
        verbrauchsverlaeufe=(_historie_fuer_abrufquote(0.2),),
    )
    schulungsplan = Schulungsplan(stichtag=historie.stichtag, termine=())
    dashboard = Dashboard(bestand, schulungsplan, Kostenplan())
    dashboard.prognose = bestand.simulieren(monate=2, laeufe=5, zufall=np.random.default_rng(1))

    hinweise = dashboard.hinweise()
    assert any("Kostenprognose" in text for text in hinweise["Hinweis"])


def test_dashboard_projekte_ohne_budget_enthaelt_gefilterte_projekte():
    historie, _prognose = _historie_und_prognose_mit_horizont()
    projekt = Projekt(
        id=1,
        name="Projekt ohne Budget",
        kunde=KUNDE,
        aktiv=True,
        budget=OHNE_BUDGET,
        verbrauchtes_volumen=20000.0,
        verbrauchte_stunden=200.0,
    )
    bestand = Bestand(
        stichtag=historie.stichtag,
        projekte=(projekt,),
        umsatzhistorie=historie,
        verbrauchsverlaeufe=(_historie_fuer_abrufquote(0.2),),
    )
    schulungsplan = Schulungsplan(stichtag=historie.stichtag, termine=())
    dashboard = Dashboard(bestand, schulungsplan, KOSTENPLAN)
    dashboard.prognose = bestand.simulieren(monate=2, laeufe=5, zufall=np.random.default_rng(1))

    projekte_ohne_budget = dashboard.projekte_ohne_budget()
    assert any("Projekt ohne Budget" in text for text in projekte_ohne_budget["Projekt"]), (
        projekte_ohne_budget
    )


def test_dashboard_projekte_ohne_budget_filtert_projekte():
    historie, _prognose = _historie_und_prognose_mit_horizont()
    projekt = Projekt(
        id=1,
        name="gefiltertes Projekt ohne Budget",
        kunde=KUNDE,
        aktiv=True,
        budget=OHNE_BUDGET,
        verbrauchtes_volumen=20000.0,
        verbrauchte_stunden=200.0,
    )
    bestand = Bestand(
        stichtag=historie.stichtag,
        projekte=(projekt,),
        umsatzhistorie=historie,
        verbrauchsverlaeufe=(_historie_fuer_abrufquote(0.2),),
    )
    schulungsplan = Schulungsplan(stichtag=historie.stichtag, termine=())
    dashboard = Dashboard(bestand, schulungsplan, KOSTENPLAN)
    dashboard.prognose = bestand.simulieren(monate=2, laeufe=5, zufall=np.random.default_rng(1))

    projekte_ohne_budget = dashboard.projekte_ohne_budget(filter=["kein Match", "gefiltert"])
    assert not any("Projekt ohne Budget" in text for text in projekte_ohne_budget["Projekt"]), (
        projekte_ohne_budget
    )


def test_dashboard_zeigt_horizont_im_umsatzverlauf():
    stichtag = date(2026, 9, 1)
    historie = Umsatzhistorie.zum_stichtag(
        [Monatsumsatz(2026, 9, 20000.0, 150.0)], stichtag, abgeschlossene=0
    )
    bestand = Bestand(
        stichtag=stichtag,
        projekte=(),
        umsatzhistorie=historie,
        verbrauchsverlaeufe=(_historie_fuer_abrufquote(0.2),),
    )
    dashboard = Dashboard(bestand, SCHULUNGSPLAN, KOSTENPLAN)
    dashboard.simuliere(monate=1)
    fig = dashboard.umsatzverlauf()
    # Kein Projekt im Scope - dieselbe Begruendung wie an der Domaene direkt.
    assert any("Abrufquote" in a.text for a in fig.layout.annotations)


def test_kennzahlen_zeigen_eine_kachel_je_eintrag():
    fig = diagramme.kennzahlen([("Umsatz", 1000.0, "EUR"), ("Projekte", 3, "")])
    assert len(fig.data) == 2
    assert fig.data[0].value == 1000.0


def test_umsatztabelle_kennzeichnet_den_laufenden_monat():
    tabelle = tabellen.umsatztabelle(HISTORIE)
    assert len(tabelle) == 13
    assert tabelle.iloc[-1]["Nicht abgerechnet"] == "50.000,00 EUR"
    assert tabelle.iloc[-1]["Abgerechnet"] == ""
    assert tabelle.iloc[-2]["Abgerechnet"] == "300.000,00 EUR"
    assert tabelle.iloc[-2]["Nicht abgerechnet"] == ""


def test_umsatztabelle_verschmilzt_laufenden_monat_mit_der_prognose():
    stichtag = date(2026, 9, 1)
    historie = Umsatzhistorie.zum_stichtag(
        [Monatsumsatz(2026, 8, 100000.0, 800.0), Monatsumsatz(2026, 9, 20000.0, 150.0)],
        stichtag,
        abgeschlossene=1,
    )
    projekt = Projekt(
        id=1, name="Projekt", kunde=KUNDE, aktiv=True,
        budget=Gesamtbudget(betrag=220000.0),
        verbrauchtes_volumen=20000.0, verbrauchte_stunden=200.0,
    )  # fmt: skip
    bestand = Bestand(
        stichtag=stichtag,
        projekte=(projekt,),
        umsatzhistorie=historie,
        verbrauchsverlaeufe=(_historie_fuer_abrufquote(0.2),),
    )
    prognose = bestand.simulieren(monate=2, laeufe=5, zufall=np.random.default_rng(1))
    assert prognose.vorhanden

    tabelle = tabellen.umsatztabelle(historie, prognose)

    # Zwei Historienmonate plus ein zusaetzlicher Horizontmonat - der laufende Monat
    # (Sep) ist derselbe wie der erste Horizontmonat und bekommt keine eigene zweite
    # Zeile mehr, sondern nur eine ergaenzte Prognose-Spalte.
    assert list(tabelle["Monat"]) == ["Aug 2026", "Sep 2026", "Okt 2026"]

    aug, sep, okt = tabelle.iloc[0], tabelle.iloc[1], tabelle.iloc[2]
    assert aug["Abgerechnet"] == "100.000,00 EUR"
    assert aug["Nicht abgerechnet"] == ""
    assert aug["Prognostiziert"] == ""

    assert sep["Abgerechnet"] == ""
    assert sep["Nicht abgerechnet"] == "20.000,00 EUR"
    assert sep["Prognostiziert"] != ""

    assert okt["Abgerechnet"] == ""
    assert okt["Prognostiziert"] != ""

    assert all(wert.endswith("EUR") for wert in tabelle["Summe"])


def test_umsatztabelle_ohne_prognose_bleibt_wie_zuvor():
    tabelle = tabellen.umsatztabelle(HISTORIE, BESTAND.simulieren())
    assert len(tabelle) == 13
    assert (tabelle["Prognostiziert"] != "").sum() == 0


def test_projekttabelle_zeigt_leere_zellen_statt_erfundener_nullen():
    ohne_budget = Projekt(id=3, name="Schulungsprodukt", aktiv=True)
    tabelle = tabellen.projekttabelle([ohne_budget])
    assert tabelle.iloc[0]["Beauftragt"] == ""
    assert tabelle.iloc[0]["Offen"] == ""


def test_hinweistabelle_kuerzt_lange_id_listen():
    hinweis = Hinweis("Viele Projekte", tuple(str(i) for i in range(20)))
    zeile = tabellen.hinweistabelle([hinweis]).iloc[0]
    assert zeile["Betroffen"] == 20
    assert zeile["Projekte"].endswith("…")


def test_dashboard_rechnet_kennzahlen_ohne_den_laufenden_monat():
    dashboard = Dashboard(BESTAND, SCHULUNGSPLAN, KOSTENPLAN)
    kacheln = {k.title.text: k.value for k in dashboard.kennzahlen().data}

    assert kacheln["Umsatz letzte 12 Monate"] == 300000.0
    assert kacheln["Durchschnitt je Monat"] == 25000.0
    assert kacheln["Offenes Auftragsvolumen"] == 47000.0
    assert kacheln["Projekte in der Prognose"] == 2


def test_dashboard_liefert_alle_ansichten_zum_selben_stand():
    dashboard = Dashboard(BESTAND, SCHULUNGSPLAN, KOSTENPLAN)
    assert dashboard.stichtag == STICHTAG
    assert dashboard.umsatzverlauf().data
    assert dashboard.restvolumen_je_projekt(top=1).data[0].x == (34000.0,)
    assert len(dashboard.projekttabelle()) == 2
    assert len(dashboard.umsatztabelle()) == 13


def test_dashboard_kapazitaet_je_mitarbeiter_schliesst_laufenden_monat_aus():
    vollzeit = Wochenarbeitszeit(
        stunden_je_wochentag=(8.0, 8.0, 8.0, 8.0, 8.0, 0.0, 0.0), gueltig_ab=date(2020, 1, 1)
    )
    anna = Mitarbeiter(id=1, name="Anna", aktiv=True, arbeitszeiten=(vollzeit,))
    bestand = Bestand(stichtag=STICHTAG, mitarbeiter=(anna,))  # STICHTAG: 24.08.2026
    auslastung = (
        Auslastungsmonat(mitarbeiter=anna, jahr=2026, monat=7, abrechenbare_stunden=80.0),
        # August ist der laufende (Stichtags-)Monat und faellt heraus.
        Auslastungsmonat(mitarbeiter=anna, jahr=2026, monat=8, abrechenbare_stunden=999.0),
    )
    dashboard = Dashboard(bestand, SCHULUNGSPLAN, KOSTENPLAN, auslastung)

    fig = dashboard.kapazitaet_je_mitarbeiter()

    verfuegbar_juli = anna.verfuegbare_kapazitaet(2026, 7)
    assert fig.data[0].x[0] == pytest.approx(verfuegbar_juli / STUNDEN_JE_TAG)


@pytest.mark.parametrize(
    ("stichtag", "fruehestes_jahr", "erwartet"),
    [
        (date(2026, 9, 15), None, 12),  # keine Konfiguration -> Standardfenster
        (date(2026, 9, 15), 2022, 56),  # Jan 2022 bis Aug 2026
        (date(2026, 1, 15), 2026, 12),  # Untergrenze greift, sonst waeren es 0 Monate
        (date(2026, 9, 15), 2027, 12),  # Jahr in der Zukunft faellt auf die Untergrenze zurueck
    ],
)
def test_abgeschlossene_monate_reicht_bis_januar_des_fruehesten_kosten_jahres(
    stichtag, fruehestes_jahr, erwartet
):
    assert _abgeschlossene_monate(stichtag, fruehestes_jahr) == erwartet


def test_dashboard_gewinn_verlust_monatlich_nutzt_kostenplan():
    historie = Umsatzhistorie.zum_stichtag(
        [Monatsumsatz(2026, 7, 50000.0), Monatsumsatz(2026, 8, 30000.0)], STICHTAG, abgeschlossene=1
    )
    bestand = Bestand(stichtag=STICHTAG, umsatzhistorie=historie)
    kostenplan = Kostenplan(posten=(Kostenposten(2026, 7, 40000.0),))
    dashboard = Dashboard(bestand, SCHULUNGSPLAN, kostenplan)

    fig = dashboard.gewinn_verlust_monatlich(monate=1)
    # abgeschlossene(1) liefert nur Juli (August ist der laufende Monat).
    assert list(fig.data[0].x) == ["Jul 2026"]
    assert list(fig.data[0].y) == [10000.0]  # 50.000 - 40.000, Kostenplan ohne August-Posten


def test_dashboard_gewinn_verlust_je_jahr_nutzt_kostenplan():
    historie = Umsatzhistorie.zum_stichtag(
        [
            Monatsumsatz(2026, 6, 50000.0),
            Monatsumsatz(2026, 7, 10000.0),
            Monatsumsatz(2026, 8, 0.0),
        ],
        STICHTAG,
        abgeschlossene=2,
    )
    bestand = Bestand(stichtag=STICHTAG, umsatzhistorie=historie)
    kostenplan = Kostenplan(posten=(Kostenposten(2026, 6, 40000.0), Kostenposten(2026, 7, 40000.0)))
    dashboard = Dashboard(bestand, SCHULUNGSPLAN, kostenplan)

    fig = dashboard.gewinn_verlust_je_jahr()
    assert list(fig.data[0].y) == [10000.0, -30000.0]


def test_dashboard_umsatzrendite_kumuliert_nutzt_kostenplan():
    historie = Umsatzhistorie.zum_stichtag(
        [
            Monatsumsatz(2026, 6, 50000.0),
            Monatsumsatz(2026, 7, 50000.0),
            Monatsumsatz(2026, 8, 0.0),
        ],
        STICHTAG,
        abgeschlossene=2,
    )
    bestand = Bestand(stichtag=STICHTAG, umsatzhistorie=historie)
    kostenplan = Kostenplan(posten=(Kostenposten(2026, 6, 40000.0), Kostenposten(2026, 7, 30000.0)))
    dashboard = Dashboard(bestand, SCHULUNGSPLAN, kostenplan)

    fig = dashboard.umsatzrendite_kumuliert()
    # Juni: 10.000 / 50.000 = 20 %. Juli kumuliert: (10.000+20.000) / 100.000 = 30 %.
    assert list(fig.data[0].y) == pytest.approx([20.0, 30.0])


def test_dashboard_gewinn_verlust_je_jahr_laesst_jahr_ganz_ohne_kostenerfassung_weg():
    historie = Umsatzhistorie(
        stichtag=STICHTAG,
        monate=(
            Monatsumsatz(2025, 12, 50000.0),
            Monatsumsatz(2026, 7, 60000.0),
            Monatsumsatz(2026, 8, 0.0),
        ),
    )
    bestand = Bestand(stichtag=STICHTAG, umsatzhistorie=historie)
    # Nur 2026 hat ueberhaupt einen Kostenposten - 2025 bleibt vollstaendig ohne Quelle.
    kostenplan = Kostenplan(posten=(Kostenposten(2026, 7, 40000.0),))
    dashboard = Dashboard(bestand, SCHULUNGSPLAN, kostenplan)

    fig = dashboard.gewinn_verlust_je_jahr()
    assert [spur.name for spur in fig.data] == ["2026"]


def test_dashboard_umsatzrendite_kumuliert_laesst_jahr_ganz_ohne_kostenerfassung_weg():
    historie = Umsatzhistorie(
        stichtag=STICHTAG,
        monate=(
            Monatsumsatz(2025, 12, 50000.0),
            Monatsumsatz(2026, 7, 60000.0),
            Monatsumsatz(2026, 8, 0.0),
        ),
    )
    bestand = Bestand(stichtag=STICHTAG, umsatzhistorie=historie)
    kostenplan = Kostenplan(posten=(Kostenposten(2026, 7, 40000.0),))
    dashboard = Dashboard(bestand, SCHULUNGSPLAN, kostenplan)

    fig = dashboard.umsatzrendite_kumuliert()
    # Ohne den Filter waere 2025 (0 Kostenposten) als 100 % Rendite gezeigt worden.
    assert [spur.name for spur in fig.data] == ["2026"]


def test_dashboard_gewinn_verlust_je_jahr_ohne_jede_kostenquelle_zeigt_trotzdem_alles():
    historie = Umsatzhistorie(
        stichtag=STICHTAG,
        monate=(Monatsumsatz(2025, 12, 50000.0), Monatsumsatz(2026, 8, 0.0)),
    )
    bestand = Bestand(stichtag=STICHTAG, umsatzhistorie=historie)
    dashboard = Dashboard(bestand, SCHULUNGSPLAN, KOSTENPLAN)  # KOSTENPLAN: keine Posten

    fig = dashboard.gewinn_verlust_je_jahr()
    # Keine Kostenquelle ueberhaupt konfiguriert - Annahme 0 wie ueberall sonst, nicht wegfiltern.
    assert [spur.name for spur in fig.data] == ["2025"]


def test_dashboard_gewinn_verlust_monatlich_haengt_vorausschau_an_wenn_simuliert():
    historie, prognose = _historie_und_prognose_mit_horizont()
    bestand = Bestand(stichtag=historie.stichtag, umsatzhistorie=historie)
    kostenplan = Kostenplan(
        posten=(
            Kostenposten(2026, 8, 40000.0),
            Kostenposten(2026, 9, 15000.0),
            Kostenposten(2026, 10, 12000.0),
        )
    )
    dashboard = Dashboard(bestand, SCHULUNGSPLAN, kostenplan)
    dashboard.prognose = prognose

    fig = dashboard.gewinn_verlust_monatlich(monate=1)
    assert list(fig.data[0].x) == ["Aug 2026", "Sep 2026", "Okt 2026"]


def test_dashboard_gewinn_verlust_je_jahr_ohne_simulation_bleibt_bei_der_historie():
    historie = Umsatzhistorie.zum_stichtag(
        [Monatsumsatz(2026, 7, 50000.0), Monatsumsatz(2026, 8, 30000.0)], STICHTAG, abgeschlossene=1
    )
    bestand = Bestand(stichtag=STICHTAG, umsatzhistorie=historie)
    dashboard = Dashboard(bestand, SCHULUNGSPLAN, KOSTENPLAN)

    fig = dashboard.gewinn_verlust_je_jahr()
    assert len(fig.data) == 1  # keine zweite (Prognose-)Spur ohne dashboard.simuliere()


def test_dashboard_auslastung_je_mitarbeiter_schliesst_laufenden_monat_aus():
    vollzeit = Wochenarbeitszeit(
        stunden_je_wochentag=(8.0, 8.0, 8.0, 8.0, 8.0, 0.0, 0.0), gueltig_ab=date(2020, 1, 1)
    )
    anna = Mitarbeiter(id=1, name="Anna", aktiv=True, arbeitszeiten=(vollzeit,))
    bestand = Bestand(stichtag=STICHTAG, mitarbeiter=(anna,))  # STICHTAG: 24.08.2026
    auslastung = (
        Auslastungsmonat(mitarbeiter=anna, jahr=2026, monat=7, abrechenbare_stunden=80.0),
        # August ist der laufende (Stichtags-)Monat und faellt heraus, egal wie hoch.
        Auslastungsmonat(mitarbeiter=anna, jahr=2026, monat=8, abrechenbare_stunden=999.0),
    )
    dashboard = Dashboard(bestand, SCHULUNGSPLAN, KOSTENPLAN, auslastung)

    fig = dashboard.auslastung_je_mitarbeiter()

    verfuegbar_juli = anna.verfuegbare_kapazitaet(2026, 7)
    assert fig.data[0].x[0] == pytest.approx(80.0 / verfuegbar_juli)


def test_dashboard_auslastung_je_mitarbeiter_summiert_abgeschlossene_monate():
    vollzeit = Wochenarbeitszeit(
        stunden_je_wochentag=(8.0, 8.0, 8.0, 8.0, 8.0, 0.0, 0.0), gueltig_ab=date(2020, 1, 1)
    )
    anna = Mitarbeiter(id=1, name="Anna", aktiv=True, arbeitszeiten=(vollzeit,))
    bestand = Bestand(stichtag=STICHTAG, mitarbeiter=(anna,))
    auslastung = (
        Auslastungsmonat(mitarbeiter=anna, jahr=2026, monat=6, abrechenbare_stunden=100.0),
        Auslastungsmonat(mitarbeiter=anna, jahr=2026, monat=7, abrechenbare_stunden=80.0),
        Auslastungsmonat(mitarbeiter=anna, jahr=2026, monat=8, abrechenbare_stunden=999.0),
    )
    dashboard = Dashboard(bestand, SCHULUNGSPLAN, KOSTENPLAN, auslastung)

    fig = dashboard.auslastung_je_mitarbeiter()

    verfuegbar = anna.verfuegbare_kapazitaet(2026, 6) + anna.verfuegbare_kapazitaet(2026, 7)
    assert fig.data[0].x[0] == pytest.approx((100.0 + 80.0) / verfuegbar)


def test_dashboard_ohne_auslastung_bleibt_leer():
    dashboard = Dashboard(BESTAND, SCHULUNGSPLAN, KOSTENPLAN)
    assert dashboard.auslastung == ()
    assert list(dashboard.auslastung_je_mitarbeiter().data[0].x) == []


def test_dashboard_ladebericht_zeigt_stand_und_umfang_ohne_ladedauern():
    dashboard = Dashboard(BESTAND, SCHULUNGSPLAN, KOSTENPLAN)
    bericht = dashboard.ladebericht()
    assert "24.08.2026" in bericht
    assert "0 Schulung(en) geladen" in bericht
    assert "0 Monat(e) mit Kostenprognose geladen" in bericht
    assert "0 Auslastungsmonat(e) geladen" in bericht
    assert bericht.count("unbekannter Dauer") == 4


def test_dashboard_ladebericht_zeigt_gemessene_ladedauer_je_repository():
    ladedauern = Ladedauern(
        bestand=timedelta(seconds=95),
        schulungsplan=timedelta(seconds=2),
        kostenplan=timedelta(seconds=1),
        auslastung=timedelta(seconds=3),
    )
    dashboard = Dashboard(BESTAND, SCHULUNGSPLAN, KOSTENPLAN, ladedauern=ladedauern)
    bericht = dashboard.ladebericht()
    assert "Bestand geladen (in 2 Minuten)" in bericht
    assert "Schulung(en) geladen (in 2 Sekunden)" in bericht
    assert "Kostenprognose geladen (in eine Sekunde)" in bericht
    assert "Auslastungsmonat(e) geladen (in 3 Sekunden)" in bericht


def test_dashboard_bestandsbericht_zeigt_zahlen_und_ladezeit_je_repository():
    ladedauern = Ladedauern(kostenplan=timedelta(seconds=1), auslastung=timedelta(seconds=3))
    dashboard = Dashboard(BESTAND, SCHULUNGSPLAN, KOSTENPLAN, ladedauern=ladedauern)
    bericht = dashboard.bestandsbericht()
    assert f"Projekte gesamt:    {len(PROJEKTE)}  (Bestand geladen in unbekannter Dauer)" in bericht
    assert "Kunden mit Projekt: 1" in bericht
    assert "Kostenmonate:       0  (Kostenplan geladen in eine Sekunde)" in bericht
    assert "Auslastungsmonate:  0  (Auslastung geladen in 3 Sekunden)" in bericht


def test_dashboard_kapazitaet_je_projekt_ohne_simulation_ist_leer():
    dashboard = Dashboard(BESTAND, SCHULUNGSPLAN, KOSTENPLAN)
    assert list(dashboard.kapazitaet_je_projekt().data[0].x) == []


def test_dashboard_kapazitaet_je_projekt_zeigt_werte_nach_simulation():
    historie, prognose = _historie_und_prognose_mit_horizont()
    projekt = next(p for p in prognose.kapazitaet_je_projekt())
    bestand = Bestand(
        stichtag=historie.stichtag,
        projekte=(
            Projekt(id=projekt, name="Projekt", aktiv=True, budget=Gesamtbudget(betrag=1.0)),
        ),
        umsatzhistorie=historie,
    )
    dashboard = Dashboard(bestand, SCHULUNGSPLAN, KOSTENPLAN)
    dashboard.prognose = prognose

    fig = dashboard.kapazitaet_je_projekt()
    assert fig.data[0].x[0] == prognose.kapazitaet_je_projekt()[projekt] / 7.0


def test_historie_monate_ohne_umsatzhistorie_ist_leer():
    ohne_historie = Bestand(stichtag=STICHTAG)
    assert _historie_monate(ohne_historie) == ()


def test_aktive_mitarbeiter_filtert_inaktive():
    aktiv = Mitarbeiter(id=1, name="Aktiv", aktiv=True)
    inaktiv = Mitarbeiter(id=2, name="Inaktiv", aktiv=False)
    bestand = Bestand(stichtag=STICHTAG, mitarbeiter=(aktiv, inaktiv))

    assert _aktive_mitarbeiter(bestand) == {1: aktiv}


def test_stoppuhr_misst_eine_dauer():
    with _Stoppuhr() as t:
        pass
    assert t.dauer >= timedelta(0)


def test_dashboard_kennzahlen_ohne_umsatzhistorie_wirft():
    ohne_historie = Dashboard(Bestand(stichtag=STICHTAG), SCHULUNGSPLAN, KOSTENPLAN)
    with pytest.raises(ValueError, match="Umsatzhistorie"):
        ohne_historie.kennzahlen()


def test_dashboard_stundensatz_uebersteuern_wirkt_auf_folgende_ansichten():
    projekt = Projekt(id=1, name="Pauschale", kunde=KUNDE, aktiv=True,
                       budget=Gesamtbudget(betrag=50000.0),
                       verbrauchtes_volumen=20000.0, verbrauchte_stunden=0.0)  # fmt: skip
    bestand = Bestand(stichtag=STICHTAG, projekte=(projekt,), umsatzhistorie=HISTORIE)
    dashboard = Dashboard(bestand, SCHULUNGSPLAN, KOSTENPLAN)
    assert dashboard.bestand.projekte[0].effektiver_stundensatz is None

    dashboard.stundensatz_uebersteuern({"Pauschale": 95.0})

    assert dashboard.bestand.projekte[0].effektiver_stundensatz == 95.0


def test_dashboard_laden_verdrahtet_alle_vier_repositories(monkeypatch):
    """Regressionstest fuer ``Dashboard.laden()`` als ``synchron()`` um ``laden_async()``.

    Alle vier ``mit_automatischen_zugangsdaten()``-Einstiege werden durch Stubs
    ersetzt - kein Netzzugriff, aber echte Ausfuehrung von ``laden()``/``laden_async()``
    inklusive der ``synchron()``-Bruecke zwischen ihnen.
    """

    class _StubBestandRepository:
        def laden(self, **kwargs):
            raise AssertionError("laden() soll fuer Dashboard.laden() nicht aufgerufen werden")

        async def laden_async(self, **kwargs):
            return BESTAND

    class _StubSchulungenRepository:
        def laden(self, **kwargs):
            return SCHULUNGSPLAN

    class _StubKostenRepository:
        fruehestes_konfiguriertes_jahr = None

        def laden(self, **kwargs):
            return KOSTENPLAN

    class _StubAuslastungRepository:
        def laden(self, *args, **kwargs):
            raise AssertionError("laden() soll fuer Dashboard.laden() nicht aufgerufen werden")

        async def laden_async(self, *args, **kwargs):
            return ()

    monkeypatch.setattr(
        BestandRepository, "mit_automatischen_zugangsdaten", lambda: _StubBestandRepository()
    )
    monkeypatch.setattr(
        SchulungenRepository, "mit_automatischen_zugangsdaten", lambda: _StubSchulungenRepository()
    )
    monkeypatch.setattr(
        KostenRepository, "mit_automatischen_zugangsdaten", lambda: _StubKostenRepository()
    )
    monkeypatch.setattr(
        AuslastungRepository, "mit_automatischen_zugangsdaten", lambda: _StubAuslastungRepository()
    )

    dashboard = Dashboard.laden(stichtag=STICHTAG)

    assert dashboard.bestand is BESTAND
    assert dashboard.schulungsplan is SCHULUNGSPLAN
    assert dashboard.kostenplan is KOSTENPLAN
    assert dashboard.auslastung == ()
