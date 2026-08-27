"""Tests zu Diagrammen, Tabellen und Dashboard - alle ohne Netzzugriff.

Geprueft wird nicht das Aussehen, sondern was ueberhaupt dargestellt wird: dass die
Zahlen aus der Domaene unveraendert ankommen, dass der laufende Monat abgesetzt bleibt
und dass gleichnamige Projekte nicht zu einem Balken verschmelzen.
"""

from __future__ import annotations

from datetime import date

import numpy as np

from umsatzprognose.darstellung import Dashboard, diagramme, tabellen
from umsatzprognose.darstellung.gestaltung import PROGNOSE_DECKKRAFT, SCHULUNG, SERIE_HELL
from umsatzprognose.domaene import (
    Bestand,
    Budget,
    Hinweis,
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
from umsatzprognose.domaene.zahlen import euro

STICHTAG = date(2026, 8, 24)
KUNDE = Kunde(id=7, name="Union Asset Management Holding AG")

HISTORIE = Umsatzhistorie.zum_stichtag(
    [Monatsumsatz(2026, 7, 300000.0, 2000.0), Monatsumsatz(2026, 8, 50000.0, 400.0)],
    STICHTAG,
)
PROJEKTE = (
    Projekt(id=1, name="Beispielprojekt Eins", kunde=KUNDE, aktiv=True,
            budget=Budget(betrag=50000.0), verbrauchtes_volumen=16000.0, verbrauchte_stunden=100.0),
    Projekt(id=2, name="Beispielprojekt Zwei", kunde=KUNDE, aktiv=True,
            budget=Budget(betrag=20000.0), verbrauchtes_volumen=7000.0, verbrauchte_stunden=50.0),
)  # fmt: skip
BESTAND = Bestand(stichtag=STICHTAG, projekte=PROJEKTE, umsatzhistorie=HISTORIE)


def _historie_fuer_abrufquote(quote: float) -> Verbrauchsverlauf:
    """Ein einzelner Beobachtungsmonat, der die Abrufquote-Verteilung auf ``quote`` setzt.

    Dasselbe Muster wie in ``tests/test_simulation.py``: das Projekt liegt ausserhalb
    des Prognose-Scope und traegt selbst keinen Umsatz bei, nur die eine Beobachtung.
    """
    projekt = Projekt(id=900, name="Historie", aktiv=False, budget=Budget(betrag=1000.0))
    return Verbrauchsverlauf.fuer(
        projekt, [Monatsumsatz(jahr=2026, monat=6, umsatz=quote * 1000.0, stunden=1.0)]
    )


def test_umsatzverlauf_zeigt_alle_monate_und_hebt_den_laufenden_hervor():
    fig = diagramme.umsatzverlauf(HISTORIE)
    balken = fig.data[0]

    assert len(balken.x) == 13
    assert balken.x[-1] == "Aug 2026"
    # Der laufende Monat bekommt die hellere Stufe derselben Farbe.
    assert balken.marker.color[-1] != balken.marker.color[-2]
    assert any(a.text == "läuft noch" for a in fig.layout.annotations)


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
        budget=Budget(betrag=220000.0),
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
        budget=Budget(betrag=220000.0), verbrauchtes_volumen=20000.0, verbrauchte_stunden=200.0,
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


def test_dashboard_hinweise_enthaelt_luecken_des_schulungsplans():
    historie, _prognose = _historie_und_prognose_mit_horizont()
    projekt = Projekt(
        id=1,
        name="Projekt",
        kunde=KUNDE,
        aktiv=True,
        budget=Budget(betrag=220000.0),
        verbrauchtes_volumen=20000.0,
        verbrauchte_stunden=200.0,
    )
    bestand = Bestand(
        stichtag=historie.stichtag,
        projekte=(projekt,),
        umsatzhistorie=historie,
        verbrauchsverlaeufe=(_historie_fuer_abrufquote(0.2),),
    )
    dashboard = Dashboard(bestand)
    dashboard.prognose = bestand.simulieren(monate=2, laeufe=5, zufall=np.random.default_rng(1))
    dashboard.schulungsplan = Schulungsplan(stichtag=historie.stichtag, termine=())

    hinweise = dashboard.hinweise()
    assert any("Schulungsanmeldung" in text for text in hinweise["Hinweis"])


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
    dashboard = Dashboard(bestand)
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
        budget=Budget(betrag=220000.0), verbrauchtes_volumen=20000.0, verbrauchte_stunden=200.0,
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
    hinweis = Hinweis("Viele Projekte", tuple(range(20)))
    zeile = tabellen.hinweistabelle([hinweis]).iloc[0]
    assert zeile["Betroffen"] == 20
    assert zeile["Projekte"].endswith("…")


def test_dashboard_rechnet_kennzahlen_ohne_den_laufenden_monat():
    dashboard = Dashboard(BESTAND)
    kacheln = {k.title.text: k.value for k in dashboard.kennzahlen().data}

    assert kacheln["Umsatz letzte 12 Monate"] == 300000.0
    assert kacheln["Durchschnitt je Monat"] == 25000.0
    assert kacheln["Offenes Auftragsvolumen"] == 47000.0
    assert kacheln["Projekte in der Prognose"] == 2


def test_dashboard_liefert_alle_ansichten_zum_selben_stand():
    dashboard = Dashboard(BESTAND)
    assert dashboard.stichtag == STICHTAG
    assert dashboard.umsatzverlauf().data
    assert dashboard.restvolumen_je_projekt(top=1).data[0].x == (34000.0,)
    assert len(dashboard.projekttabelle()) == 2
    assert len(dashboard.umsatztabelle()) == 13
