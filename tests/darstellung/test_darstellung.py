"""Tests zu Diagrammen, Tabellen und Dashboard - alle ohne Netzzugriff.

Geprueft wird nicht das Aussehen, sondern was ueberhaupt dargestellt wird: dass die
Zahlen aus der Domaene unveraendert ankommen, dass der laufende Monat abgesetzt bleibt
und dass gleichnamige Projekte nicht zu einem Balken verschmelzen.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

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
    TICKWINKEL,
    TINTE,
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
    Kurzarbeitsbewertung,
    Mitarbeiter,
    Monatsumsatz,
    Projekt,
    Projektanteil,
    Schulungsplan,
    Schulungstermin,
    Schwellenwerte,
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
    [
        Monatsumsatz(2026, 7, Decimal("300000.0"), 2000.0),
        Monatsumsatz(2026, 8, Decimal("50000.0"), 400.0),
    ],
    STICHTAG,
)
PROJEKTE = (
    Projekt(
        id=1,
        name="Beispielprojekt Eins",
        kunde=KUNDE,
        aktiv=True,
        budget=Gesamtbudget(betrag=Decimal("50000.0")),
        verbrauchtes_volumen=Decimal("16000.0"),
        verbrauchte_stunden=100.0,
    ),
    Projekt(
        id=2,
        name="Beispielprojekt Zwei",
        kunde=KUNDE,
        aktiv=True,
        budget=Gesamtbudget(betrag=Decimal("20000.0")),
        verbrauchtes_volumen=Decimal("7000.0"),
        verbrauchte_stunden=50.0,
    ),
)
BESTAND = Bestand(stichtag=STICHTAG, projekte=PROJEKTE, umsatzhistorie=HISTORIE)
SCHULUNGSPLAN = Schulungsplan(stichtag=STICHTAG, termine=())
KOSTENPLAN = Kostenplan()


@pytest.fixture
def dashboard_repository_stubs(monkeypatch):
    """Patcht alle vier ``mit_automatischen_zugangsdaten()``-Einstiege durch Stubs, die
    ``BESTAND``/``SCHULUNGSPLAN``/``KOSTENPLAN``/eine leere Auslastung liefern - fuer
    Tests, die nur pruefen, WIE ``Dashboard.laden()``/``laden_async()`` diese vier
    Repositories aufruft (Fortschritt, Reihenfolge, Durchreichung), nicht was sie
    fachlich liefern. Gibt die an ``BestandRepository.laden_async()`` uebergebenen
    ``kwargs`` je Aufruf zurueck, fuer Tests, die diese pruefen wollen.
    """
    bestand_aufrufe: list[dict] = []

    class _StubBestandRepository:
        async def laden_async(self, **kwargs):
            bestand_aufrufe.append(kwargs)
            return BESTAND

    class _StubSchulungenRepository:
        def laden(self, **kwargs):
            return SCHULUNGSPLAN

    class _StubKostenRepository:
        fruehestes_konfiguriertes_jahr = None

        def laden(self, **kwargs):
            return KOSTENPLAN

    class _StubAuslastungRepository:
        async def laden_async(self, *args, **kwargs):
            return ()

    monkeypatch.setattr(BestandRepository, "mit_automatischen_zugangsdaten", _StubBestandRepository)
    monkeypatch.setattr(
        SchulungenRepository, "mit_automatischen_zugangsdaten", _StubSchulungenRepository
    )
    monkeypatch.setattr(KostenRepository, "mit_automatischen_zugangsdaten", _StubKostenRepository)
    monkeypatch.setattr(
        AuslastungRepository, "mit_automatischen_zugangsdaten", _StubAuslastungRepository
    )
    return bestand_aufrufe


def _historie_fuer_abrufquote(quote: float) -> Verbrauchsverlauf:
    """Ein einzelner Beobachtungsmonat, der die Abrufquote-Verteilung auf ``quote`` setzt.

    Dasselbe Muster wie in ``tests/domaene/test_simulation.py``: das Projekt liegt ausserhalb
    des Prognose-Scope und traegt selbst keinen Umsatz bei, nur die eine Beobachtung.
    """
    projekt = Projekt(
        id=900, name="Historie", aktiv=False, budget=Gesamtbudget(betrag=Decimal("1000.0"))
    )
    return Verbrauchsverlauf.fuer(
        projekt,
        [Monatsumsatz(jahr=2026, monat=6, umsatz=Decimal(str(quote * 1000.0)), stunden=1.0)],
    )


def test_anmeldungsverlauf_zeigt_gesamtzahl_und_trend():
    verlauf = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "CSM 2-tägig", 5),
            Anmeldung(2026, 9, "KSD", 2),
            Anmeldung(2026, 9, "Produktmanagement", 1),
            Anmeldung(2026, 10, "CSM 2-tägig", 3),
            Anmeldung(2026, 11, "CSM 2-tägig", 4),
        )
    )
    fig = diagramme.anmeldungsverlauf(verlauf)

    namen = {spur.name for spur in fig.data}
    assert namen == {"Anmeldungen", "Trend"}
    assert all(spur.type == "scatter" for spur in fig.data)
    assert fig.layout.barmode is None

    gesamt = next(s for s in fig.data if s.name == "Anmeldungen")
    assert gesamt.mode == "lines+markers"
    assert list(gesamt.x) == ["Sep 2026", "Okt 2026", "Nov 2026"]
    assert list(gesamt.y) == [8, 3, 4]

    # Ausgleichsgerade durch (0, 8), (1, 3), (2, 4) - von Hand nachgerechnet.
    trend = next(s for s in fig.data if s.name == "Trend")
    assert list(trend.y) == pytest.approx([7.0, 5.0, 3.0])


def test_linearer_trend_legt_eine_ausgleichsgerade_durch_die_werte():
    assert diagramme._linearer_trend([8.0, 3.0, 4.0]) == pytest.approx([7.0, 5.0, 3.0])


def test_linearer_trend_mit_einem_wert_bleibt_unveraendert():
    assert diagramme._linearer_trend([8.0]) == [8.0]


def test_linearer_trend_ohne_werte_ist_leer():
    assert diagramme._linearer_trend([]) == []


def test_anmeldungsverlauf_ohne_daten_zeigt_hinweis_statt_balken():
    fig = diagramme.anmeldungsverlauf(Anmeldungsverlauf())
    assert fig.data == ()
    assert (
        fig.layout.annotations[0].text == "Keine Anmeldedaten für den gewählten Zeitraum geladen."
    )


def _anmeldungsverlauf_ueber_monate(anzahl: int) -> Anmeldungsverlauf:
    anmeldungen = []
    jahr, monat = 2024, 1
    for _ in range(anzahl):
        anmeldungen.append(Anmeldung(jahr, monat, "CSM 2-tägig", 1))
        monat += 1
        if monat > 12:
            monat = 1
            jahr += 1
    return Anmeldungsverlauf(anmeldungen=tuple(anmeldungen))


def test_anmeldungsverlauf_beschriftung_steht_immer_schraeg():
    fig = diagramme.anmeldungsverlauf(_anmeldungsverlauf_ueber_monate(3))
    assert fig.layout.xaxis.tickangle == TICKWINKEL


def test_anmeldungsverlauf_reihen_zeichnet_eine_spur_je_reihe():
    monate = ((2026, 9), (2026, 10))
    reihen = {
        "Alle Schulungen": {(2026, 9): 8, (2026, 10): 3},
        "Scrum": {(2026, 9): 5},
    }
    fig = diagramme.anmeldungsverlauf_reihen(reihen, monate)

    namen = {spur.name for spur in fig.data}
    assert namen == {"Alle Schulungen", "Scrum"}

    alle = next(s for s in fig.data if s.name == "Alle Schulungen")
    assert list(alle.x) == ["Sep 2026", "Okt 2026"]
    assert list(alle.y) == [8, 3]
    assert alle.line.color == TINTE

    scrum = next(s for s in fig.data if s.name == "Scrum")
    assert list(scrum.y) == [5, 0]
    assert scrum.line.color == JAHRESFARBEN[0]


def test_anmeldungsverlauf_reihen_ohne_trend_zeigt_keine_trendspuren():
    monate = ((2026, 9),)
    fig = diagramme.anmeldungsverlauf_reihen({"Scrum": {(2026, 9): 5}}, monate)
    assert not any("Trend" in (spur.name or "") for spur in fig.data)


def test_anmeldungsverlauf_reihen_mit_trend_ergaenzt_gestrichelte_spur_je_reihe():
    monate = ((2026, 9), (2026, 10), (2026, 11))
    reihen = {"Scrum": {(2026, 9): 8, (2026, 10): 3, (2026, 11): 4}}
    fig = diagramme.anmeldungsverlauf_reihen(reihen, monate, mit_trend=True)

    trend = next(s for s in fig.data if s.name == "Scrum (Trend)")
    assert trend.line.dash == "dash"
    assert trend.line.color == JAHRESFARBEN[0]
    assert trend.showlegend is False
    assert list(trend.y) == pytest.approx([7.0, 5.0, 3.0])


def test_anmeldungsverlauf_reihen_ohne_auswahl_zeigt_hinweis():
    fig = diagramme.anmeldungsverlauf_reihen({}, ((2026, 9),))
    assert fig.data == ()
    assert "gewählte Auswahl" in fig.layout.annotations[0].text


def _kurzarbeit_ergebnisse() -> dict[tuple[int, int], Kurzarbeitsbewertung]:
    return {
        (2026, 7): Kurzarbeitsbewertung(
            jahr=2026,
            monat=7,
            schwellenwerte=Schwellenwerte(quote_organisation=0.30),
            anzahl_kurzarbeitsfaehig=1,
            anzahl_scheitert_interne_arbeit=9,
        ),
        (2026, 8): Kurzarbeitsbewertung(
            jahr=2026,
            monat=8,
            schwellenwerte=Schwellenwerte(quote_organisation=0.30),
            anzahl_kurzarbeitsfaehig=3,
            anzahl_scheitert_interne_arbeit=1,
        ),
    }


def test_kurzarbeit_grafik_zeigt_gesamtzahl_und_kurzarbeitsfaehig_als_balken():
    fig = diagramme.kurzarbeit_grafik(_kurzarbeit_ergebnisse())

    gesamt = next(s for s in fig.data if s.name == "Gesamtanzahl")
    faehig = next(s for s in fig.data if s.name == "Kurzarbeitsfähig")
    assert list(gesamt.x) == ["Jul 2026", "Aug 2026"]
    assert list(gesamt.y) == [10, 4]
    assert list(faehig.y) == [1, 3]
    assert fig.layout.barmode == "overlay"


def test_kurzarbeit_grafik_zeigt_quote_auf_zweiter_y_achse_farbig_nach_schwelle():
    fig = diagramme.kurzarbeit_grafik(_kurzarbeit_ergebnisse())

    quote = next(s for s in fig.data if s.name == "Quote")
    assert quote.yaxis == "y2"
    assert list(quote.y) == pytest.approx([10.0, 75.0])
    # Juli (10 %) unter der Schwelle (30 %), August (75 %) darueber - unterschiedliche
    # Markerfarben je nachdem.
    assert quote.marker.color[0] != quote.marker.color[1]
    assert fig.layout.yaxis2.range == (0, 100)


def test_kurzarbeit_grafik_ohne_beschriftung_zeigt_keinen_text():
    fig = diagramme.kurzarbeit_grafik(_kurzarbeit_ergebnisse(), mit_beschriftung=False)
    assert all(spur.text is None for spur in fig.data)


def test_kurzarbeit_grafik_mit_beschriftung_zeigt_werte_als_text():
    fig = diagramme.kurzarbeit_grafik(_kurzarbeit_ergebnisse(), mit_beschriftung=True)

    gesamt = next(s for s in fig.data if s.name == "Gesamtanzahl")
    quote = next(s for s in fig.data if s.name == "Quote")
    assert list(gesamt.text) == ["10", "4"]
    assert list(quote.text) == ["10%", "75%"]


def test_kurzarbeit_grafik_ohne_quote_zeigt_n_a_als_text():
    ergebnisse = {
        (2026, 8): Kurzarbeitsbewertung(jahr=2026, monat=8, schwellenwerte=Schwellenwerte())
    }
    fig = diagramme.kurzarbeit_grafik(ergebnisse, mit_beschriftung=True)

    quote = next(s for s in fig.data if s.name == "Quote")
    assert list(quote.y) == [0.0]
    assert list(quote.text) == ["n/a"]


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
    zeitbasiert = Projekt(
        id=1, name="Zeitbasiert", aktiv=True, budget=Gesamtbudget(betrag=Decimal("1000.0"))
    )
    pauschal = Projekt(
        id=2, name="Pauschale", aktiv=True, budget=Gesamtbudget(betrag=Decimal("1000.0"))
    )
    fig = diagramme.kapazitaet_je_projekt([(zeitbasiert, 70.0), (pauschal, 0.0)])
    balken = fig.data[0]

    assert list(balken.x) == [0.0, 10.0]
    assert list(balken.text) == ["0,0 Tage", "10,0 Tage"]


def test_gewinn_verlust_monatlich_faerbt_nach_vorzeichen():
    monate = [Monatsumsatz(2026, 7, Decimal("50000.0")), Monatsumsatz(2026, 8, Decimal("30000.0"))]
    fig = diagramme.gewinn_verlust_monatlich(monate, [Decimal("40000.0"), Decimal("40000.0")])
    balken = fig.data[0]

    assert list(balken.x) == ["Jul 2026", "Aug 2026"]
    assert list(balken.y) == [10000.0, -10000.0]
    assert list(balken.marker.color) == [ERGEBNIS_POSITIV, ERGEBNIS_NEGATIV]


def test_gewinn_verlust_je_jahr_zeigt_monatswerte_nicht_kumuliert():
    monate = [Monatsumsatz(2026, 7, Decimal("50000.0")), Monatsumsatz(2026, 8, Decimal("10000.0"))]
    fig = diagramme.gewinn_verlust_je_jahr(monate, [Decimal("40000.0"), Decimal("40000.0")])
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
        [Decimal("40000.0")],
        prognose=prognose,
        horizont_kosten=[Decimal("15000.0"), Decimal("12000.0")],
        verbrauch_laufender_monat=historie.laufender,
    )
    balken = fig.data[0]
    median = prognose.monatswerte()[0.50]

    assert list(balken.x) == ["Aug 2026", "Sep 2026", "Okt 2026"]
    # September (erster Horizontmonat) traegt zusaetzlich das vor dem Stichtag bereits
    # realisierte historie.laufender.umsatz - dieselbe Rechnung wie im Umsatzverlauf.
    erwartetes_ergebnis = [
        100000.0 - 40000.0,
        (float(historie.laufender.umsatz) + float(median[0])) - 15000.0,
        float(median[1]) - 12000.0,
    ]
    assert list(balken.y) == pytest.approx(erwartetes_ergebnis)
    # September ist der laufende Monat (erster Horizontmonat) - vorlaeufig, nicht rein
    # simuliert wie Oktober.
    assert list(balken.marker.opacity) == [1.0, VORLAEUFIG_DECKKRAFT, PROGNOSE_DECKKRAFT]


def test_gewinn_verlust_monatlich_ohne_prognose_bleibt_wie_zuvor():
    monate = [Monatsumsatz(2026, 7, Decimal("50000.0"))]
    fig = diagramme.gewinn_verlust_monatlich(monate, [Decimal("40000.0")])
    assert list(fig.data[0].marker.opacity) == [1.0]
    # Ohne Prognose gibt es nichts zu unterscheiden - keine Sicherheits-Legende.
    assert not any(spur.name == "Daten" for spur in fig.data)


def test_gewinn_verlust_monatlich_zeigt_datensicherheits_legende_mit_prognose():
    historie, prognose = _historie_und_prognose_mit_horizont()
    monate = historie.abgeschlossene()
    fig = diagramme.gewinn_verlust_monatlich(
        monate,
        [Decimal("40000.0")],
        prognose=prognose,
        horizont_kosten=[Decimal("15000.0"), Decimal("12000.0")],
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
        [Decimal("40000.0")],
        prognose=prognose,
        horizont_kosten=[Decimal("15000.0"), Decimal("12000.0")],
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
        Monatsumsatz(2025, 11, Decimal("10000.0")),
        Monatsumsatz(2025, 12, Decimal("15000.0")),
        Monatsumsatz(2026, 1, Decimal("30000.0")),
        Monatsumsatz(2026, 2, Decimal("10000.0")),
    ]
    fig = diagramme.gewinn_verlust_je_jahr(
        monate, [Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0")]
    )
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
        [Monatsumsatz(2026, 11, Decimal("30000.0")), Monatsumsatz(2026, 12, Decimal("5000.0"))],
        stichtag,
        abgeschlossene=1,
    )
    monate = historie.abgeschlossene()
    projekt = Projekt(
        id=1, name="Projekt", kunde=KUNDE, aktiv=True,
        budget=Gesamtbudget(betrag=Decimal("220000.0")),
        verbrauchtes_volumen=Decimal("20000.0"), verbrauchte_stunden=200.0,
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
        [Decimal("40000.0")],
        prognose=prognose,
        horizont_kosten=[Decimal("15000.0"), Decimal("12000.0")],
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
        [Decimal("40000.0")],
        prognose=prognose,
        horizont_kosten=[Decimal("15000.0"), Decimal("12000.0")],
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
        [Decimal("40000.0")],
        prognose=prognose,
        horizont_kosten=[Decimal("15000.0"), Decimal("12000.0")],
        verbrauch_laufender_monat=historie.laufender,
    )
    legende = {spur.name: spur.marker.opacity for spur in fig.data if spur.name not in {"2026"}}
    assert legende == {
        "Daten": 1.0,
        "Vorläufig": VORLAEUFIG_DECKKRAFT,
        "Prognose": PROGNOSE_DECKKRAFT,
    }


def test_gewinn_verlust_je_jahr_ohne_prognose_zeigt_keine_datensicherheits_legende():
    monate = [Monatsumsatz(2026, 7, Decimal("50000.0"))]
    fig = diagramme.gewinn_verlust_je_jahr(monate, [Decimal("40000.0")])
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
        [
            Monatsumsatz(2026, 8, Decimal("100000.0"), 800.0),
            Monatsumsatz(2026, 9, Decimal("20000.0"), 150.0),
        ],
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
        budget=Gesamtbudget(betrag=Decimal("220000.0")),
        verbrauchtes_volumen=Decimal("20000.0"),
        verbrauchte_stunden=200.0,
        anteile=(Projektanteil(anna, stunden=200.0),),
    )
    # Eine Buchung im zweiten Horizontmonat, damit auch die "Bereits gebucht"-Spur
    # etwas zu zeichnen hat.
    verlauf_projekt = Verbrauchsverlauf.fuer(
        projekt, [Monatsumsatz(jahr=2026, monat=10, umsatz=Decimal("5000.0"), stunden=50.0)]
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
        [
            Monatsumsatz(2026, 8, Decimal("100000.0"), 800.0),
            Monatsumsatz(2026, 9, Decimal("20000.0"), 150.0),
        ],
        stichtag,
        abgeschlossene=1,
    )
    projekt = Projekt(
        id=1, name="Projekt", kunde=KUNDE, aktiv=True,
        budget=Gesamtbudget(betrag=Decimal("220000.0")),
        verbrauchtes_volumen=Decimal("20000.0"), verbrauchte_stunden=200.0,
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
        termine=(
            Schulungstermin(2026, 9, Decimal("3000.0")),
            Schulungstermin(2026, 10, Decimal("1500.0")),
        ),
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
            Kostenposten(2026, 8, Decimal("40000.0")),
            Kostenposten(2026, 9, Decimal("15000.0")),
            Kostenposten(2026, 10, Decimal("12000.0")),
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
        (float(historie.laufender.umsatz) + float(median[0])) - 15000.0,
        float(median[1]) - 12000.0,
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
                2026,
                8,
                pauschale=Decimal("40000.0"),
                allgemeinkosten=Decimal("10000.0"),
                erfassung=Erfasst(Decimal("12000.0")),
            ),
            Kostenposten(2026, 9, Decimal("15000.0")),
            Kostenposten(2026, 10, Decimal("12000.0")),
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
        termine=(
            Schulungstermin(2026, 9, Decimal("3000.0")),
            Schulungstermin(2026, 10, Decimal("1500.0")),
        ),
    )

    tabelle = tabellen.umsatztabelle(historie, prognose, schulungsplan)
    sep, okt = tabelle.iloc[1], tabelle.iloc[2]
    assert sep["Schulungsanmeldungen"] == "3.000,00 EUR"
    assert okt["Schulungsanmeldungen"] == "1.500,00 EUR"

    erwartete_sep_summe = (
        historie.laufender.umsatz + prognose.monatswerte()[0.50][0] + Decimal("3000.0")
    )
    assert sep["Summe"] == euro(erwartete_sep_summe)


def test_umsatztabelle_ohne_schulungsplan_laesst_spalte_leer():
    tabelle = tabellen.umsatztabelle(HISTORIE, BESTAND.simulieren())
    assert (tabelle["Schulungsanmeldungen"] != "").sum() == 0


def test_umsatztabelle_mit_kostenplan_ergaenzt_kosten_und_gewinn_fuer_historie_und_horizont():
    historie, prognose = _historie_und_prognose_mit_horizont()
    kostenplan = Kostenplan(
        posten=(
            Kostenposten(2026, 8, Decimal("40000.0")),
            Kostenposten(2026, 9, Decimal("15000.0")),
            Kostenposten(2026, 10, Decimal("12000.0")),
        )
    )

    tabelle = tabellen.umsatztabelle(historie, prognose, None, kostenplan)
    aug, sep, okt = tabelle.iloc[0], tabelle.iloc[1], tabelle.iloc[2]

    assert aug["Kosten"] == euro(Decimal("40000.0"))
    assert aug["Gewinn"] == euro(Decimal("100000.0") - Decimal("40000.0"))

    erwartete_sep_summe = historie.laufender.umsatz + prognose.monatswerte()[0.50][0]
    assert sep["Kosten"] == euro(Decimal("15000.0"))
    assert sep["Gewinn"] == euro(erwartete_sep_summe - Decimal("15000.0"))

    erwartete_okt_summe = prognose.monatswerte()[0.50][1]
    assert okt["Kosten"] == euro(Decimal("12000.0"))
    assert okt["Gewinn"] == euro(erwartete_okt_summe - Decimal("12000.0"))


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
        budget=Gesamtbudget(betrag=Decimal("220000.0")),
        verbrauchtes_volumen=Decimal("20000.0"),
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
        budget=Gesamtbudget(betrag=Decimal("220000.0")),
        verbrauchtes_volumen=Decimal("20000.0"),
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
        verbrauchtes_volumen=Decimal("20000.0"),
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
        verbrauchtes_volumen=Decimal("20000.0"),
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


def test_dashboard_simuliere_meldet_fortschritt_einmal_nach_abschluss():
    """``fortschritt`` bei ``simuliere()`` feuert genau einmal, nach Abschluss - die
    Simulation ist eine einzige Rechnung ohne sinnvolle Zwischenschritte."""
    dashboard = Dashboard(BESTAND, SCHULUNGSPLAN, KOSTENPLAN)
    zeilen: list[str] = []
    dashboard.simuliere(monate=1, laeufe=100, fortschritt=zeilen.append)
    assert len(zeilen) == 1
    assert "Simulation abgeschlossen" in zeilen[0]
    assert "100 Laeufe" in zeilen[0]
    assert "1 Monat(e)" in zeilen[0]


def test_dashboard_zeigt_horizont_im_umsatzverlauf():
    stichtag = date(2026, 9, 1)
    historie = Umsatzhistorie.zum_stichtag(
        [Monatsumsatz(2026, 9, Decimal("20000.0"), 150.0)], stichtag, abgeschlossene=0
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
        [
            Monatsumsatz(2026, 8, Decimal("100000.0"), 800.0),
            Monatsumsatz(2026, 9, Decimal("20000.0"), 150.0),
        ],
        stichtag,
        abgeschlossene=1,
    )
    projekt = Projekt(
        id=1, name="Projekt", kunde=KUNDE, aktiv=True,
        budget=Gesamtbudget(betrag=Decimal("220000.0")),
        verbrauchtes_volumen=Decimal("20000.0"), verbrauchte_stunden=200.0,
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


def test_anmeldungstabelle_zeigt_teilnehmerzahl_je_kategorie_und_monat_mit_summe_und_gesamtzeile():
    """Eine Kategorie je Zeile, Monate als Spalten (siehe Docstring von
    tabellen.anmeldungstabelle) - transponiert gegenueber einer frueheren Fassung mit
    einem Monat je Zeile, damit die Kategorien in der Webapp aufklappbar werden
    koennen (siehe tabellen.anmeldungsdetailtabellen)."""
    verlauf = Anmeldungsverlauf(
        anmeldungen=(
            Anmeldung(2026, 9, "CSM 2-tägig", 5),
            Anmeldung(2026, 9, "KSD", 2),
            Anmeldung(2026, 9, "Ein ganz neuer Kurs", 1),
            Anmeldung(2026, 10, "CSM 2-tägig", 3),
        )
    )
    kategorien = {"Scrum": ["CSM 2-tägig"], "Kanban": ["KSD"]}

    tabelle = tabellen.anmeldungstabelle(verlauf, kategorien)

    assert list(tabelle.columns) == ["Kategorie", "Sep 2026", "Okt 2026", "Summe"]
    assert tabelle["Kategorie"].tolist() == ["Scrum", "Kanban", "Sonstige", "Gesamt"]
    assert tabelle["Sep 2026"].tolist() == [5, 2, 1, 8]
    assert tabelle["Okt 2026"].tolist() == [3, 0, 0, 3]
    assert tabelle["Summe"].tolist() == [8, 2, 1, 11]


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
        [Monatsumsatz(2026, 7, Decimal("50000.0")), Monatsumsatz(2026, 8, Decimal("30000.0"))],
        STICHTAG,
        abgeschlossene=1,
    )
    bestand = Bestand(stichtag=STICHTAG, umsatzhistorie=historie)
    kostenplan = Kostenplan(posten=(Kostenposten(2026, 7, Decimal("40000.0")),))
    dashboard = Dashboard(bestand, SCHULUNGSPLAN, kostenplan)

    fig = dashboard.gewinn_verlust_monatlich(monate=1)
    # abgeschlossene(1) liefert nur Juli (August ist der laufende Monat).
    assert list(fig.data[0].x) == ["Jul 2026"]
    assert list(fig.data[0].y) == [10000.0]  # 50.000 - 40.000, Kostenplan ohne August-Posten


def test_dashboard_gewinn_verlust_monatlich_ohne_monate_zeigt_mehr_als_zwoelf_monate():
    stichtag = date(2026, 3, 15)
    monate = [Monatsumsatz(2025, m, Decimal("1000.0")) for m in range(2, 13)] + [
        Monatsumsatz(2026, 1, Decimal("1000.0")),
        Monatsumsatz(2026, 2, Decimal("1000.0")),
    ]  # Feb 2025 bis Feb 2026 - 13 abgeschlossene Monate, mehr als STANDARD_HISTORIE_MONATE (12)
    historie = Umsatzhistorie.zum_stichtag(monate, stichtag, abgeschlossene=13)
    bestand = Bestand(stichtag=stichtag, umsatzhistorie=historie)
    dashboard = Dashboard(bestand, SCHULUNGSPLAN, KOSTENPLAN)

    fig = dashboard.gewinn_verlust_monatlich(monate=None)

    assert len(fig.data[0].x) == 13


def test_dashboard_gewinn_verlust_je_jahr_nutzt_kostenplan():
    historie = Umsatzhistorie.zum_stichtag(
        [
            Monatsumsatz(2026, 6, Decimal("50000.0")),
            Monatsumsatz(2026, 7, Decimal("10000.0")),
            Monatsumsatz(2026, 8, Decimal("0.0")),
        ],
        STICHTAG,
        abgeschlossene=2,
    )
    bestand = Bestand(stichtag=STICHTAG, umsatzhistorie=historie)
    kostenplan = Kostenplan(
        posten=(
            Kostenposten(2026, 6, Decimal("40000.0")),
            Kostenposten(2026, 7, Decimal("40000.0")),
        )
    )
    dashboard = Dashboard(bestand, SCHULUNGSPLAN, kostenplan)

    fig = dashboard.gewinn_verlust_je_jahr()
    assert list(fig.data[0].y) == [10000.0, -30000.0]


def test_dashboard_umsatzrendite_kumuliert_nutzt_kostenplan():
    historie = Umsatzhistorie.zum_stichtag(
        [
            Monatsumsatz(2026, 6, Decimal("50000.0")),
            Monatsumsatz(2026, 7, Decimal("50000.0")),
            Monatsumsatz(2026, 8, Decimal("0.0")),
        ],
        STICHTAG,
        abgeschlossene=2,
    )
    bestand = Bestand(stichtag=STICHTAG, umsatzhistorie=historie)
    kostenplan = Kostenplan(
        posten=(
            Kostenposten(2026, 6, Decimal("40000.0")),
            Kostenposten(2026, 7, Decimal("30000.0")),
        )
    )
    dashboard = Dashboard(bestand, SCHULUNGSPLAN, kostenplan)

    fig = dashboard.umsatzrendite_kumuliert()
    # Juni: 10.000 / 50.000 = 20 %. Juli kumuliert: (10.000+20.000) / 100.000 = 30 %.
    assert list(fig.data[0].y) == pytest.approx([20.0, 30.0])


def test_dashboard_gewinn_verlust_je_jahr_laesst_jahr_ganz_ohne_kostenerfassung_weg():
    historie = Umsatzhistorie(
        stichtag=STICHTAG,
        monate=(
            Monatsumsatz(2025, 12, Decimal("50000.0")),
            Monatsumsatz(2026, 7, Decimal("60000.0")),
            Monatsumsatz(2026, 8, Decimal("0.0")),
        ),
    )
    bestand = Bestand(stichtag=STICHTAG, umsatzhistorie=historie)
    # Nur 2026 hat ueberhaupt einen Kostenposten - 2025 bleibt vollstaendig ohne Quelle.
    kostenplan = Kostenplan(posten=(Kostenposten(2026, 7, Decimal("40000.0")),))
    dashboard = Dashboard(bestand, SCHULUNGSPLAN, kostenplan)

    fig = dashboard.gewinn_verlust_je_jahr()
    assert [spur.name for spur in fig.data] == ["2026"]


def test_dashboard_umsatzrendite_kumuliert_laesst_jahr_ganz_ohne_kostenerfassung_weg():
    historie = Umsatzhistorie(
        stichtag=STICHTAG,
        monate=(
            Monatsumsatz(2025, 12, Decimal("50000.0")),
            Monatsumsatz(2026, 7, Decimal("60000.0")),
            Monatsumsatz(2026, 8, Decimal("0.0")),
        ),
    )
    bestand = Bestand(stichtag=STICHTAG, umsatzhistorie=historie)
    kostenplan = Kostenplan(posten=(Kostenposten(2026, 7, Decimal("40000.0")),))
    dashboard = Dashboard(bestand, SCHULUNGSPLAN, kostenplan)

    fig = dashboard.umsatzrendite_kumuliert()
    # Ohne den Filter waere 2025 (0 Kostenposten) als 100 % Rendite gezeigt worden.
    assert [spur.name for spur in fig.data] == ["2026"]


def test_dashboard_gewinn_verlust_je_jahr_ohne_jede_kostenquelle_zeigt_trotzdem_alles():
    historie = Umsatzhistorie(
        stichtag=STICHTAG,
        monate=(Monatsumsatz(2025, 12, Decimal("50000.0")), Monatsumsatz(2026, 8, Decimal("0.0"))),
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
            Kostenposten(2026, 8, Decimal("40000.0")),
            Kostenposten(2026, 9, Decimal("15000.0")),
            Kostenposten(2026, 10, Decimal("12000.0")),
        )
    )
    dashboard = Dashboard(bestand, SCHULUNGSPLAN, kostenplan)
    dashboard.prognose = prognose

    fig = dashboard.gewinn_verlust_monatlich(monate=1)
    assert list(fig.data[0].x) == ["Aug 2026", "Sep 2026", "Okt 2026"]


def test_dashboard_gewinn_verlust_je_jahr_ohne_simulation_bleibt_bei_der_historie():
    historie = Umsatzhistorie.zum_stichtag(
        [Monatsumsatz(2026, 7, Decimal("50000.0")), Monatsumsatz(2026, 8, Decimal("30000.0"))],
        STICHTAG,
        abgeschlossene=1,
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


def test_dashboard_ladebericht_zeigt_nur_stand_ohne_dauer_je_repository():
    """Die Dauer/Umfang-Zeilen je Abruf zeigt im Notebook bereits ``fortschritt`` sukzessive
    waehrend des Ladens (siehe ``test_dashboard_laden_meldet_fortschritt_...``) - ``ladebericht()``
    wiederholt sie deshalb nicht mehr, nur noch Stand der Auswertung."""
    dashboard = Dashboard(BESTAND, SCHULUNGSPLAN, KOSTENPLAN)
    bericht = dashboard.ladebericht()
    assert bericht == "Abrechnungsdaten geladen.\nStand der Auswertung: 24.08.2026"


def test_dashboard_schritt_berichte_rekonstruiert_dieselben_vier_zeilen():
    """``schritt_berichte()`` liefert dieselben Zeilen wie ``fortschritt`` waehrend eines
    Ladevorgangs, aus einem schon fertig geladenen Dashboard - fuer einen Aufrufer, der
    ohne neuen Ladevorgang trotzdem berichten will (siehe ``notebooks/setup.py``)."""
    ladedauern = Ladedauern(
        bestand=timedelta(seconds=95),
        schulungsplan=timedelta(seconds=2),
        kostenplan=timedelta(seconds=1),
        auslastung=timedelta(seconds=3),
    )
    dashboard = Dashboard(BESTAND, SCHULUNGSPLAN, KOSTENPLAN, ladedauern=ladedauern)

    bestand_zeile, schulungsplan_zeile, kostenplan_zeile, auslastung_zeile = (
        dashboard.schritt_berichte()
    )

    assert bestand_zeile == f"{len(PROJEKTE)} Projekt(e) im Bestand geladen (in 2 Minuten)"
    assert schulungsplan_zeile == "0 Schulung(en) geladen (in 2 Sekunden)"
    assert kostenplan_zeile == "0 Monat(e) mit Kostenprognose geladen (in eine Sekunde)"
    assert auslastung_zeile == "0 Auslastungsmonat(e) geladen (in 3 Sekunden)"


def test_dashboard_schritt_berichte_mit_dauer_ueberschreibt_gespeicherte_werte():
    """``dauer`` ersetzt die urspruenglichen, teuren Ladedauern - fuer einen Aufrufer,
    der dasselbe Dashboard nur aus einem eigenen, schnellen Zwischenspeicher zurueckgibt
    und dafuer die tatsaechlich kurze Dauer dieses Zugriffs zeigen will, statt
    faelschlich die alte, teure Original-Ladedauer erneut zu melden."""
    ladedauern = Ladedauern(
        bestand=timedelta(seconds=16),
        schulungsplan=timedelta(seconds=1),
        kostenplan=timedelta(seconds=3),
        auslastung=timedelta(seconds=0),
    )
    dashboard = Dashboard(BESTAND, SCHULUNGSPLAN, KOSTENPLAN, ladedauern=ladedauern)

    berichte = dashboard.schritt_berichte(dauer=timedelta(seconds=0.001))

    assert all("ein Moment" in zeile for zeile in berichte)
    assert "16 Sekunden" not in "".join(berichte)


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
            Projekt(
                id=projekt, name="Projekt", aktiv=True, budget=Gesamtbudget(betrag=Decimal("1.0"))
            ),
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
    projekt = Projekt(
        id=1,
        name="Pauschale",
        kunde=KUNDE,
        aktiv=True,
        budget=Gesamtbudget(betrag=Decimal("50000.0")),
        verbrauchtes_volumen=Decimal("20000.0"),
        verbrauchte_stunden=0.0,
    )
    bestand = Bestand(stichtag=STICHTAG, projekte=(projekt,), umsatzhistorie=HISTORIE)
    dashboard = Dashboard(bestand, SCHULUNGSPLAN, KOSTENPLAN)
    assert dashboard.bestand.projekte[0].effektiver_stundensatz is None

    dashboard.stundensatz_uebersteuern({"Pauschale": Decimal("95.0")})

    assert dashboard.bestand.projekte[0].effektiver_stundensatz == Decimal("95.0")


def test_dashboard_verbrauchsplan_uebersteuern_wirkt_auf_folgende_ansichten():
    projekt = Projekt(
        id=1,
        name="Beispielprojekt",
        kunde=KUNDE,
        aktiv=True,
        budget=Gesamtbudget(betrag=Decimal("50000.0")),
        verbrauchtes_volumen=Decimal("20000.0"),
        verbrauchte_stunden=0.0,
    )
    bestand = Bestand(stichtag=STICHTAG, projekte=(projekt,), umsatzhistorie=HISTORIE)
    dashboard = Dashboard(bestand, SCHULUNGSPLAN, KOSTENPLAN)
    assert dashboard.bestand.projekte[0].verbrauchsplan_zielmonat is None

    dashboard.verbrauchsplan_uebersteuern({"Beispielprojekt": (2026, 12)})

    assert dashboard.bestand.projekte[0].verbrauchsplan_zielmonat == (2026, 12)


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

    monkeypatch.setattr(BestandRepository, "mit_automatischen_zugangsdaten", _StubBestandRepository)
    monkeypatch.setattr(
        SchulungenRepository, "mit_automatischen_zugangsdaten", _StubSchulungenRepository
    )
    monkeypatch.setattr(KostenRepository, "mit_automatischen_zugangsdaten", _StubKostenRepository)
    monkeypatch.setattr(
        AuslastungRepository, "mit_automatischen_zugangsdaten", _StubAuslastungRepository
    )

    dashboard = Dashboard.laden(stichtag=STICHTAG)

    assert dashboard.bestand is BESTAND
    assert dashboard.schulungsplan is SCHULUNGSPLAN
    assert dashboard.kostenplan is KOSTENPLAN
    assert dashboard.auslastung == ()


def test_dashboard_laden_meldet_fortschritt_nach_jedem_der_vier_abrufe(dashboard_repository_stubs):
    """``fortschritt`` feuert sukzessive: eine Zeile direkt nach jedem Abruf, nicht erst am Ende.

    Bestand zuerst und allein, garantiert an erster Stelle. Schulungsplan, Kostenplan und
    Auslastung laufen danach gleichzeitig (siehe ``Dashboard.laden_async``) - ihre drei
    Meldungen kommen deshalb in der Reihenfolge, in der sie tatsaechlich fertig werden,
    nicht in einer festen Reihenfolge.
    """
    zeilen: list[str] = []
    Dashboard.laden(stichtag=STICHTAG, fortschritt=zeilen.append)

    assert len(zeilen) == 4
    assert "Bestand geladen" in zeilen[0]
    uebrige = zeilen[1:]
    assert any("Schulung(en) geladen" in z for z in uebrige)
    assert any("Kostenprognose geladen" in z for z in uebrige)
    assert any("Auslastungsmonat(e) geladen" in z for z in uebrige)


def test_dashboard_laden_meldet_beginn_jedes_schritts_vor_dessen_fortschritt(
    dashboard_repository_stubs,
):
    """``schritt_beginnt`` feuert je Abruf vor dessen ``fortschritt`` - fuer eine Anzeige,
    die schon waehrend des laufenden Abrufs zeigt, was gerade geladen wird.

    Bestand und Schulungsplan laufen gleichzeitig, Kostenplan und Auslastung erst
    danach (siehe ``Dashboard.laden_async``) - geprueft werden deshalb nur die
    tatsaechlich garantierten Invarianten: je Abruf beginnt vor fortschritt, und
    Kostenplan/Auslastung beginnen erst, nachdem Bestand fertig gemeldet hat. Die
    Reihenfolge zwischen echt nebenlaeufigen Abrufen (Bestand/Schulungsplan
    zueinander, Kostenplan/Auslastung zueinander) ist bewusst nicht Teil dieser
    Pruefung.
    """
    ereignisse: list[str] = []
    Dashboard.laden(
        stichtag=STICHTAG,
        fortschritt=lambda text: ereignisse.append(f"fortschritt:{text}"),
        schritt_beginnt=lambda name: ereignisse.append(f"beginnt:{name}"),
    )

    beginnt_namen = {e.split(":", 1)[1] for e in ereignisse if e.startswith("beginnt:")}
    assert beginnt_namen == {"Bestand", "Schulungsplan", "Kostenplan", "Auslastung"}
    assert len(ereignisse) == 8

    def index(vorhersage):
        return next(i for i, e in enumerate(ereignisse) if vorhersage(e))

    idx_bestand_beginnt = index(lambda e: e == "beginnt:Bestand")
    idx_bestand_fortschritt = index(
        lambda e: e.startswith("fortschritt:") and "Bestand geladen" in e
    )
    idx_schulungsplan_beginnt = index(lambda e: e == "beginnt:Schulungsplan")
    idx_schulungsplan_fortschritt = index(
        lambda e: e.startswith("fortschritt:") and "Schulung(en)" in e
    )
    idx_kostenplan_beginnt = index(lambda e: e == "beginnt:Kostenplan")
    idx_kostenplan_fortschritt = index(
        lambda e: e.startswith("fortschritt:") and "Kostenprognose" in e
    )
    idx_auslastung_beginnt = index(lambda e: e == "beginnt:Auslastung")
    idx_auslastung_fortschritt = index(
        lambda e: e.startswith("fortschritt:") and "Auslastungsmonat" in e
    )

    # Je Abruf: sein beginnt kommt vor seinem eigenen fortschritt.
    assert idx_bestand_beginnt < idx_bestand_fortschritt
    assert idx_schulungsplan_beginnt < idx_schulungsplan_fortschritt
    assert idx_kostenplan_beginnt < idx_kostenplan_fortschritt
    assert idx_auslastung_beginnt < idx_auslastung_fortschritt

    # Kostenplan und Auslastung haengen von Bestand ab: ihr beginnt kommt erst, nachdem
    # Bestand fertig gemeldet hat. Schulungsplan haengt an nichts - seine Reihenfolge
    # relativ zu Bestand ist bewusst nicht Teil dieser Pruefung (echte Nebenlaeufigkeit).
    assert idx_kostenplan_beginnt > idx_bestand_fortschritt
    assert idx_auslastung_beginnt > idx_bestand_fortschritt


def test_dashboard_laden_reicht_fortschritt_als_cache_fortschritt_durch(
    dashboard_repository_stubs,
):
    """``fortschritt`` ist der einzige Ladehinweis-Callback - Verlaufscache-Meldungen
    laufen ueber denselben Kanal wie die vier Abrufe (Vereinheitlichung), nicht ueber
    einen eigenen ``cache_fortschritt``-Parameter. Dashboard reicht dafuer intern eine
    Weiterleitung als ``cache_fortschritt`` bis zu ``BestandRepository.laden_async()``
    durch - erst dort (und tiefer, siehe test_client.py/test_cache.py) entstehen die
    eigentlichen Verlaufscache-Meldungen."""
    zeilen: list[str] = []
    Dashboard.laden(stichtag=STICHTAG, fortschritt=zeilen.append)

    # Die an BestandRepository durchgereichte Weiterleitung ruft, aufgerufen, denselben
    # fortschritt-Callback auf, den Dashboard.laden() bekommen hat - eine Verlaufscache-
    # Meldung landet also in derselben Liste wie die vier Abruf-Meldungen.
    weiterleitung = dashboard_repository_stubs[0]["cache_fortschritt"]
    assert weiterleitung is not None
    weiterleitung("Projektanteile: aus dem Cache geladen (3 ms)")
    assert "Projektanteile: aus dem Cache geladen (3 ms)" in zeilen
