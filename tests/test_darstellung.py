"""Tests zu Diagrammen, Tabellen und Dashboard - alle ohne Netzzugriff.

Geprueft wird nicht das Aussehen, sondern was ueberhaupt dargestellt wird: dass die
Zahlen aus der Domaene unveraendert ankommen, dass der laufende Monat abgesetzt bleibt
und dass gleichnamige Projekte nicht zu einem Balken verschmelzen.
"""

from __future__ import annotations

from datetime import date

from umsatzprognose.darstellung import diagramme, tabellen
from umsatzprognose.darstellung.dashboard import Dashboard
from umsatzprognose.domaene.bestand import Bestand
from umsatzprognose.domaene.hinweis import Hinweis
from umsatzprognose.domaene.kunde import Kunde
from umsatzprognose.domaene.projekt import Budget, Projekt
from umsatzprognose.domaene.umsatzhistorie import Monatsumsatz, Umsatzhistorie

STICHTAG = date(2026, 8, 24)
KUNDE = Kunde(id=7, name="Union Asset Management Holding AG")

HISTORIE = Umsatzhistorie.zum_stichtag(
    [Monatsumsatz(2026, 7, 300000.0, 2000.0), Monatsumsatz(2026, 8, 50000.0, 400.0)],
    STICHTAG,
)
PROJEKTE = (
    Projekt(id=1, name="Trainings 2026 Agilität erleben 4600000422", kunde=KUNDE, aktiv=True,
            budget=Budget(betrag=50000.0), verbrauchtes_volumen=16000.0, verbrauchte_stunden=100.0),
    Projekt(id=2, name="Trainings 2026 Scrum/Kanban 4600000438", kunde=KUNDE, aktiv=True,
            budget=Budget(betrag=20000.0), verbrauchtes_volumen=7000.0, verbrauchte_stunden=50.0),
)  # fmt: skip
BESTAND = Bestand(stichtag=STICHTAG, projekte=PROJEKTE, umsatzhistorie=HISTORIE)


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


def test_prognoseflaeche_nennt_den_grund():
    fig = diagramme.prognose(BESTAND.simulieren())
    text = fig.layout.annotations[0].text
    assert "5.4" in text
    assert "Abrufquote" in text


def test_kennzahlen_zeigen_eine_kachel_je_eintrag():
    fig = diagramme.kennzahlen([("Umsatz", 1000.0, "EUR"), ("Projekte", 3, "")])
    assert len(fig.data) == 2
    assert fig.data[0].value == 1000.0


def test_umsatztabelle_kennzeichnet_den_laufenden_monat():
    tabelle = tabellen.umsatztabelle(HISTORIE)
    assert len(tabelle) == 13
    assert tabelle.iloc[-1]["Status"] == "läuft noch"
    assert tabelle.iloc[-2]["Status"] == "abgeschlossen"
    assert tabelle.iloc[-2]["Umsatz"] == "300.000,00 EUR"


def test_projekttabelle_zeigt_leere_zellen_statt_erfundener_nullen():
    ohne_budget = Projekt(id=3, name="A-CSM", aktiv=True)
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
    assert dashboard.prognose().layout.annotations
    assert len(dashboard.projekttabelle()) == 2
    assert len(dashboard.umsatztabelle()) == 13
