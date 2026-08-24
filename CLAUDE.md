# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Kommandos

Abhängigkeits- und Python-Verwaltung läuft ausschließlich über **uv**; die Version ist
in `.python-version` auf 3.12 gepinnt (Colab-Nähe, siehe unten). Kein `pip install` im
Projekt-venv, kein manuell angelegtes venv.

```bash
uv sync --extra notebook       # Umgebung herstellen
uv run pytest                  # alle Tests
uv run pytest tests/test_restvolumen.py::test_summe_ignoriert_ueberschreitungen   # ein Test
uv run ruff check .            # Lint
uv run ruff format .           # Formatierung
uv run jupyter lab             # Notebooks lokal
```

## Aufbau und wo was hingehört

- `src/umsatzprognose/` – testbare Logik. `config.py` (Zugangsdaten, Header),
  `restvolumen.py` (Spec 5.1).
- `tests/` – pytest.
- `notebooks/` – Prototyp-Notebooks: API-Abrufe, Exploration, Darstellung.
- `spec/` – Spezifikation, maßgeblich für alle Modellfragen.

Rechenlogik gehört ins Paket, nicht ins Notebook. Zielwerkzeug ist laut Spec
(Abschnitt 9) ein Notebook in **Google Colab**, deshalb bleibt der Notebook-Layer dünn
und beginnt mit einer nur in Colab greifenden Installationszelle – das lokale venv
steht dort nicht zur Verfügung. Zugangsdaten in Colab über die Secrets-Verwaltung,
lokal über `.env` (`load_credentials(use_dotenv=False)` in Colab).

## Stand der Implementierung

Umgesetzt ist Schritt 1 aus Spec Abschnitt 10: Restvolumen je Projekt (5.1), plus
`notebooks/01_restvolumen.ipynb`, das die beiden Endpunkte abfragt. Die Monte-Carlo-
Simulation (5.4), Abrufquote-Verteilungen, Referenzklassen und der Kapazitätsdeckel
existieren noch nicht.

## Was das Modul fachlich tut

Rollierende 1–3-Monats-Umsatzprognose für den **Baustein Bestand**: Umsatz aus bereits
in Clockodo angelegten Projekten. Ausgabe ist eine **Bandbreite** (Konfidenzniveaus
95 % / 85 % / 50 % je Monat und als Summe), kein Punktwert.

Zwei Annahmen prägen das ganze Modell:

- Ein in Clockodo angelegtes Projekt gilt als beauftragt. Storno auf Projektebene wird
  daher nicht modelliert.
- Die einzige modellierte Unsicherheit ist die **Abrufquote**: wie viel des beauftragten
  Restvolumens im Prognosezeitraum tatsächlich abgerufen wird.

Nicht im MVP: Pipeline, Kurzfristgeschäft, Cash-Schicht, Projekte ohne Clockodo-Eintrag.

## Rechenkern (Monte Carlo, 10.000 Läufe)

Die Simulation rechnet **in Euro als Leitgröße** und nutzt Personentage nur als
Zwischenschritt für den Kapazitätsdeckel. Diese Richtung ist zentral – wer sie umdreht,
baut ein anderes Modell:

1. Restvolumen je Projekt: `budget.amount − revenue_kumuliert` (aus `entrygroups`).
   Pauschalleistungen werden über einen abgeleiteten effektiven Stundensatz normalisiert.
2. Abrufquote je Monat aus der Verteilung der **Referenzklasse** des Projekts ziehen
   → gewünschter Euro-Verbrauch.
3. Über den effektiven Stundensatz in Personentage umrechnen und auf Personen aufteilen –
   Schlüssel ist der **historische Anteil je Person am jeweiligen Projekt** (`users_id`
   je Entry, Anteil an den Gesamtstunden), unverändert in die Zukunft fortgeschrieben.
4. Je Person Bedarf über **alle** Projekte gegen die verfügbare Kapazität deckeln; bei
   Überschreitung anteilig kürzen. Der Deckel ist projektübergreifend, nicht pro Projekt.
5. Gelieferte Personentage zurück in Euro → Monatsumsatz je Projekt.
6. Restvolumen um den tatsächlichen Euro-Verbrauch reduzieren, in den nächsten Monat
   übertragen.

Neben den Konfidenzniveaus ist der **Anteil der Läufe, in denen Kapazität der limitierende
Faktor war**, ein geforderter Output – er unterscheidet Nachfrage- von Kapazitätsengpass.

Verfügbare Kapazität = Sollarbeitszeit − geplante Abwesenheit − geschätzter Abschlag für
ungeplante Abwesenheit.

## Clockodo-API: gemischte Versionen

Die benötigten Daten liegen über vier verschiedene API-Generationen verteilt; das ist
kein Versehen, sondern Stand der Clockodo-API:

| Zweck | Endpunkt | Felder |
|---|---|---|
| Auftragsvolumen | `GET /v4/projects`, `/v4/projects/{id}` | `budget.amount`, `budget.hard` |
| Verbrauch, effektiver Satz | `GET /v2/entrygroups` (nach Projekt gruppiert) | `revenue`, `hourly_rate` |
| Einzeleinträge | `GET /v2/entries` | `type`, `duration`, `revenue`, `users_id` |
| Sollarbeitszeit | `GET /v3/users` | `default_target_hours` |
| Geplante Abwesenheit | Absence-Endpunkt (Legacy `/api`) | Zeitraum, Art, Person |

`budget.hard` ist in dieser Installation `false` – Budgets sind also weiche Grenzen und
dürfen im Modell nicht als harte Kappung behandelt werden. Konkret: das rohe Restvolumen
kann negativ werden, und dass es das wird, ist ein Kalibrierungssignal und kein Fehler.

Basis-URL ist `https://my.clockodo.com/api`. Authentifizierung über drei Header, alle
drei sind Pflicht: `X-ClockodoApiUser` (E-Mail des Benutzers), `X-ClockodoApiKey` und
`X-Clockodo-External-Application` im Format `name;email` mit **maximal 50 Zeichen
Gesamtlänge**. `config.ClockodoCredentials` kapselt das und prüft die Längengrenze.

**Nicht verifiziert:** JSON-Envelope, Feldnamen jenseits der in der Spec genannten und
Query-Parameter der Endpunkte. `docs.clockodo.com` wird als JavaScript-Anwendung
ausgeliefert und war nicht auslesbar. Die betroffenen Stellen in
`notebooks/01_restvolumen.ipynb` sind mit `PRÜFEN` markiert und geben die Roh-Keys aus.
Diese Annahmen beim ersten echten API-Lauf korrigieren, statt sie fortzuschreiben.

## Kalibrierung als Teil des Modells

Zwei Größen sind geschätzt und veralten: die Referenzklassen-Zuordnung der Projekte und
der historische Aufteilungsschlüssel je Person. Wechselt die Teambesetzung eines Projekts
spürbar, wird der Schlüssel falsch. Die Spec ordnet das ausdrücklich der monatlichen
Kalibrierung zu und **nicht** einer Modelländerung – bei Abweichungen also zuerst die
Kalibrierung prüfen, nicht die Simulationslogik umbauen.

## Wichtige Einschränkung der Spec-Datei

v0.4 ist ein Delta-Dokument: viele Abschnitte (Begriffe, Abrufquote-Verteilung,
Referenzklassen, Kalibrierung, Verhältnis zur Gesamtprognose) stehen dort nur als
„Unverändert zu v0.3“. **v0.3 liegt nicht im Repository.** Fehlen für eine Aufgabe
Details – etwa die konkrete Form der Abrufquote-Verteilung oder die Definition der
Referenzklassen – sind sie hier nicht auffindbar; dann beim Nutzer nachfragen statt
plausible Werte zu erfinden.

Offen und bewusst zurückgestellt: Verantwortlichkeit für Referenzklassen-Pflege und
monatliche Kalibrierung. Blockiert den produktiven Rollout, nicht den Prototyp.

## Nächster geplanter Schritt

Laut Spec Abschnitt 10: Prototyp in Colab, der `/v4/projects` und `/v2/entrygroups`
abfragt und das Restvolumen je Projekt berechnet – als Zwischenschritt **vor** der
vollen Monte-Carlo-Logik.
