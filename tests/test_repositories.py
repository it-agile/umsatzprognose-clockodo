"""Tests zur Abbildung der Clockodo-Antworten auf Fachobjekte.

Hier wird geprueft, was beim Lesen der Antworten schiefgehen kann - Typen, die nicht
sind, wonach sie aussehen, Sonderwerte, fehlende Verknuepfungen. Die Rechenregeln
stehen in den Domaenentests.
"""

from __future__ import annotations

from datetime import date

from conftest import client_mit_routen
from umsatzprognose.clockodo.bestand import BestandRepository
from umsatzprognose.clockodo.kunden import KundenRepository
from umsatzprognose.clockodo.mitarbeiter import MitarbeiterRepository
from umsatzprognose.clockodo.projekte import ProjektRepository, budget, projekt_id
from umsatzprognose.clockodo.umsatz import UmsatzRepository
from umsatzprognose.clockodo.verbrauchsverlauf import VerbrauchsverlaufRepository

STICHTAG = date(2026, 8, 24)


def routen(
    projekt_antwort,
    kunden_antwort,
    benutzer_antwort,
    sollzeit_antwort,
    entrygroup_antwort,
    monats_antwort,
) -> dict:
    return {
        "/v4/projects": projekt_antwort,
        "/v3/customers": kunden_antwort,
        "/v3/users": benutzer_antwort,
        "/targethours": sollzeit_antwort,
        "/v2/entrygroups": entrygroup_antwort,
    }  # fmt: skip


def test_kunden_werden_nach_id_abgelegt(kunden_antwort):
    client, _ = client_mit_routen({"/v3/customers": kunden_antwort})
    kunden = KundenRepository(client).laden()

    assert kunden[201].name == "Musterkunde GmbH"
    assert str(kunden[202]) == "Beispiel AG"


def test_sollarbeitszeit_kommt_nicht_aus_default_target_hours(benutzer_antwort, sollzeit_antwort):
    # default_target_hours ist ein Schalter (hier False bei der aktiven Person). Die
    # Stunden stehen in /targethours, mit Gueltigkeitszeitraum.
    client, _ = client_mit_routen({"/v3/users": benutzer_antwort, "/targethours": sollzeit_antwort})
    personen = MitarbeiterRepository(client).laden()

    person = personen[301]
    assert person.aktiv
    assert person.wochenstunden(STICHTAG) == 35.0
    assert person.wochenstunden(date(2021, 1, 1)) == 40.0
    assert personen[302].wochenstunden(STICHTAG) is None


def test_projekt_id_und_budgetformen(projekt_antwort):
    daten = projekt_antwort["data"]
    assert projekt_id(daten[0]) == 101
    assert budget(daten[0]).auftragsvolumen == 160000.0
    # budget ist null - der Schluessel ist da, ein Betrag nicht.
    assert budget(daten[1]).auftragsvolumen is None
    # monetary=false: der Betrag sind Stunden, kein Euro-Wert.
    assert budget(daten[2]).auftragsvolumen is None
    assert "Stunden" in budget(daten[2]).sonderfall


def test_projekte_bekommen_kunde_verbrauch_und_anteile(
    projekt_antwort, kunden_antwort, benutzer_antwort, sollzeit_antwort, entrygroup_antwort
):
    client, _ = client_mit_routen(
        {
            "/v4/projects": projekt_antwort,
            "/v3/customers": kunden_antwort,
            "/v3/users": benutzer_antwort,
            "/targethours": sollzeit_antwort,
            "/v2/entrygroups": entrygroup_antwort,
        }
    )
    kunden = KundenRepository(client).laden()
    personen = MitarbeiterRepository(client).laden()
    projekte = ProjektRepository(client, kunden, personen).laden()

    gefunden = {p.id: p for p in projekte}
    assert len(gefunden) == 3  # auch inaktive Projekte werden geladen
    coaching = gefunden[101]
    assert str(coaching.kunde) == "Musterkunde GmbH"
    assert coaching.verbrauchtes_volumen == 60000.0
    assert coaching.verbrauchte_stunden == 2160000 / 3600
    assert len(coaching.anteile) == 2
    assert coaching.deadline == date(2026, 9, 30)
    assert coaching.automatischer_abschluss == date(2026, 9, 30)
    # Kein deadline-Schluessel in der Antwort - nicht None am Zugriff verwechseln.
    assert gefunden[102].deadline is None
    assert gefunden[102].automatischer_abschluss is None


def test_person_ohne_stammdatensatz_verliert_ihre_stunden_nicht(
    projekt_antwort, kunden_antwort, benutzer_antwort, sollzeit_antwort, entrygroup_antwort
):
    client, _ = client_mit_routen(
        {
            "/v4/projects": projekt_antwort,
            "/v3/customers": kunden_antwort,
            "/v3/users": benutzer_antwort,
            "/targethours": sollzeit_antwort,
            "/v2/entrygroups": entrygroup_antwort,
        }
    )
    personen = MitarbeiterRepository(client).laden()
    projekte = ProjektRepository(client, {}, personen).laden()

    coaching = next(p for p in projekte if p.id == 101)
    unbekannt = next(a for a in coaching.anteile if a.mitarbeiter.id == 399)
    assert unbekannt.mitarbeiter.name is None
    assert unbekannt.stunden > 0
    assert sum(a.stunden for a in coaching.anteile) == coaching.verbrauchte_stunden


def test_buchungen_ohne_projekt_werden_nicht_zu_projekt_null(projekt_antwort, entrygroup_antwort):
    # group == 0 steht fuer Buchungen auf einen Kunden ohne Projekt. Ohne Filter
    # entstuende daraus ein Phantom-Projekt mit der ID 0.
    client, _ = client_mit_routen(
        {"/v4/projects": projekt_antwort, "/v2/entrygroups": entrygroup_antwort}
    )
    repository = ProjektRepository(client)
    projekte = repository.laden()

    assert 0 not in {p.id for p in projekte}
    assert any("ohne Projekt" in h.text for h in repository.hinweise)
    assert any("6,0 h" in h.text for h in repository.hinweise)


def test_verbrauch_auf_unbekanntes_projekt_wird_gemeldet(entrygroup_antwort):
    client, _ = client_mit_routen(
        {"/v4/projects": {"data": []}, "/v2/entrygroups": entrygroup_antwort}
    )
    repository = ProjektRepository(client)
    repository.laden()

    assert any("Stammdaten" in h.text for h in repository.hinweise)


def test_ohne_anteile_wird_der_verbrauch_trotzdem_gelesen(projekt_antwort, entrygroup_antwort):
    client, _ = client_mit_routen(
        {"/v4/projects": projekt_antwort, "/v2/entrygroups": entrygroup_antwort}
    )
    projekte = ProjektRepository(client).laden(mit_anteilen=False)

    coaching = next(p for p in projekte if p.id == 101)
    assert coaching.anteile == ()
    assert coaching.verbrauchtes_volumen == 60000.0


def test_monatsumsaetze_werden_gelesen_und_luecken_gefuellt(monats_antwort):
    client, requests = client_mit_routen({"/v2/entrygroups": monats_antwort})
    historie = UmsatzRepository(client).laden(STICHTAG)

    assert len(historie.monate) == 13
    assert historie.monate[-1].schluessel == (2026, 8)
    assert next(m for m in historie.monate if m.schluessel == (2026, 7)).umsatz == 0.0
    assert next(m for m in historie.monate if m.schluessel == (2026, 6)).umsatz == 300000.0
    # Das Fenster beginnt zwoelf Monate vor dem laufenden und endet am Monatsende.
    params = requests[0].url.params
    assert params["time_since"] == "2025-08-01T00:00:00Z"
    assert params["time_until"] == "2026-08-31T23:59:59Z"


def test_monatsverbrauch_wird_je_projekt_und_chronologisch_abgebildet(
    projekt_antwort, projekt_monats_antwort
):
    client, requests = client_mit_routen({"/v2/entrygroups": projekt_monats_antwort})
    projekte = ProjektRepository(client).abbilden(projekt_antwort["data"], [])
    verlaeufe = VerbrauchsverlaufRepository(client).laden(
        projekte, stichtag=STICHTAG, horizont_monate=3
    )

    # Die beiden Gruppen mit group == 0 fallen heraus, uebrig bleibt das eine Projekt,
    # dessen Monate in der Antwort nach Dauer absteigend stehen.
    assert [v.projekt.id for v in verlaeufe] == [101]
    assert [m.schluessel for m in verlaeufe[0].monate] == [
        (2026, 4),
        (2026, 5),
        (2026, 7),
        (2026, 8),
        (2026, 9),
    ]
    # Die Monatssummen gehen nur auf den Cent auf - ein Vergleich auf Gleichheit mit der
    # Gruppensumme (64.999,99) waere ein Fehlalarm.
    assert round(verlaeufe[0].verbrauch, 2) == 65000.0
    # Das Fenster reicht bis zum Ende des Horizonts, nicht bis zum Stichtag: derselbe
    # Abruf traegt die gebuchten Betraege im Horizont (Spec 11.1).
    assert requests[0].url.params["time_until"] == "2026-10-31T23:59:59Z"


def test_monatsverbrauch_ohne_projekt_in_den_stammdaten_wird_ausgelassen(projekt_monats_antwort):
    # Ein Verlauf ohne Projekt haette kein Budget und damit kein Restvolumen. Gemeldet
    # wird der Fall bereits vom ProjektRepository.
    client, _ = client_mit_routen({"/v2/entrygroups": projekt_monats_antwort})

    assert VerbrauchsverlaufRepository(client).laden([], stichtag=STICHTAG) == ()


def test_bestand_setzt_alles_zusammen(
    projekt_antwort,
    kunden_antwort,
    benutzer_antwort,
    sollzeit_antwort,
    entrygroup_antwort,
    monats_antwort,
    projekt_monats_antwort,
):
    def entrygroups(request):
        # Derselbe Pfad, drei voellig verschiedene Antworten - je nach Gruppierung.
        gruppierung = tuple(request.url.params.get_list("grouping[]"))
        return {
            ("projects_id", "users_id"): entrygroup_antwort,
            ("month",): monats_antwort,
            ("projects_id", "month"): projekt_monats_antwort,
        }[gruppierung]

    client, requests = client_mit_routen(
        {
            "/v4/projects": projekt_antwort,
            "/v3/customers": kunden_antwort,
            "/v3/users": benutzer_antwort,
            "/targethours": sollzeit_antwort,
            "/v2/entrygroups": entrygroups,
        }
    )
    bestand = BestandRepository(client).laden(stichtag=STICHTAG)

    assert bestand.stichtag == STICHTAG
    assert len(bestand.projekte) == 3
    assert len(bestand.mitarbeiter) == 2
    assert [p.id for p in bestand.im_prognose_scope] == [101]
    assert bestand.restvolumen_prognosewirksam == 160000.0 - 60000.0
    assert bestand.umsatzhistorie.summe() == 300000.0
    # Sieben Abrufe: Kunden, Personen, Sollzeiten, Projekte, Verbrauch, Monatsumsatz,
    # Monatsverbrauch je Projekt.
    assert len(requests) == 7
    assert any("ohne Projekt" in h.text for h in bestand.hinweise())
    # Der siebte Abruf traegt die Verteilung aus Spec 5.2 bis in den Bestand.
    assert [v.projekt.id for v in bestand.verbrauchsverlaeufe] == [101]
    assert bestand.abrufquotenverteilung().anzahl == 4
