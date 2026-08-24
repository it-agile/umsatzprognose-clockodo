# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Kommandos

Abhängigkeits- und Python-Verwaltung läuft ausschließlich über **uv**; die Version ist
in `.python-version` auf 3.13 gepinnt. Kein `pip install` im Projekt-venv, kein manuell
angelegtes venv.

Die 3.13 ist kein Zufall: **Colab läuft auf Python 3.13** (verifiziert am 24.08.2026 an
einem Traceback aus einer echten Colab-Sitzung). Ein früherer Pin auf 3.12 mit
`requires-python = ">=3.12,<3.13"` ließ die Installation in Colab fehlschlagen. Deshalb
ist `requires-python` auf `>=3.13` gesetzt, ohne Obergrenze – ein Colab-Upgrade darf die
Installation nicht brechen. Wer die Version anfasst, prüft sie gegen Colab, nicht gegen
lokale Bequemlichkeit.

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
  `extraktion.py` (Antwort-JSON → `projects_id -> Wert`, samt der geprüften Randfälle),
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
`notebooks/01_restvolumen.ipynb`, das die beiden Endpunkte abfragt. Das Notebook läuft
am 24.08.2026 gegen die echte Installation durch und liefert 729.678 EUR
prognosewirksames Restvolumen über 44 aktive Projekte mit Budget. Die Monte-Carlo-
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
   Initialisiert wird mit dem **prognosewirksamen** Restvolumen, also `max(0, …)`.
2. Abrufquote je Monat aus der Verteilung der **Referenzklasse** des Projekts ziehen
   → gewünschter Euro-Verbrauch, **begrenzt auf das verbleibende Restvolumen**.
3. Über den effektiven Stundensatz in Personentage umrechnen und auf Personen aufteilen –
   Schlüssel ist der **historische Anteil je Person am jeweiligen Projekt** (`users_id`
   je Entry, Anteil an den Gesamtstunden), unverändert in die Zukunft fortgeschrieben.
4. Je Person Bedarf über **alle** Projekte gegen die verfügbare Kapazität deckeln; bei
   Überschreitung anteilig kürzen. Der Deckel ist projektübergreifend, nicht pro Projekt.
5. Gelieferte Personentage zurück in Euro → Monatsumsatz je Projekt.
6. Restvolumen um den tatsächlichen Euro-Verbrauch reduzieren, in den nächsten Monat
   übertragen. Durch die Begrenzung in Schritt 2 bleibt es ≥ 0.

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
| Verbrauch, effektiver Satz | `GET /v2/entrygroups` (nach Projekt gruppiert) | `revenue`, `duration` (nicht `hourly_rate`, siehe unten) |
| Einzeleinträge | `GET /v2/entries` | `type`, `duration`, `revenue`, `users_id` |
| Sollarbeitszeit | `GET /v3/users` | `default_target_hours` |
| Geplante Abwesenheit | Absence-Endpunkt (Legacy `/api`) | Zeitraum, Art, Person |

`budget.hard` ist in dieser Installation `false` – Budgets sind also weiche Grenzen und
sind kein technisches Limit: der Verbrauch kann sie übersteigen, das rohe Restvolumen
wird dann negativ. Das ist ein Kalibrierungssignal und kein Fehler.

Für die Prognose gilt trotzdem eine harte Grenze (Spec 5.1, seit v0.5): **eine
Überschreitung kann nur historisch entstehen, die Prognose überschreitet das Budget
nicht.** Projekte mit historisch überschrittenem Budget tragen 0 zur Prognose bei.
Deshalb führt `restvolumen.py` beide Größen getrennt – `roh` (vorzeichenbehaftet, für
die Kalibrierung) und `prognosewirksam` (bei 0 gekappt, für die Simulation).

Basis-URL ist `https://my.clockodo.com/api`. Authentifizierung über drei Header, alle
drei sind Pflicht: `X-ClockodoApiUser` (E-Mail des Benutzers), `X-ClockodoApiKey` und
`X-Clockodo-External-Application` im Format `name;email` mit **maximal 50 Zeichen
Gesamtlänge**. `config.ClockodoCredentials` kapselt das und prüft die Längengrenze.

`docs.clockodo.com` wird als JavaScript-Anwendung ausgeliefert und war nicht auslesbar;
die Response-Strukturen stammen daher aus echten Läufen, nicht aus der Doku.

**Verifiziert am 24.08.2026 an einer echten Antwort** – `/v4/projects` liefert

```
{"paging": {"items_per_page": 1000, "current_page": 1, "count_pages": 1, "count_items": 895},
 "data": [{"id": …, "customers_id": …, "name": …, "number": …, "active": …, …}]}
```

Also: Envelope-Key ist `data` (nicht `projects`), die Projekt-ID heißt `id`, und es gibt
ein `paging`-Objekt. `items_per_page` ist 1000 bei aktuell 895 Projekten – die Grenze ist
nah, deshalb läuft das Notebook über alle Seiten statt nur über die erste.

Die Paginierung ist inzwischen ausgeführt und nicht mehr geraten: `items_per_page` setzt
die Seitengröße, `page` wählt die Seite. Mit `items_per_page=3` antwortet die API mit
`count_pages: 299`, und `page=2` liefert `current_page: 2` samt anderer IDs.

**Unbekannte Query-Parameter werden still ignoriert, nicht abgelehnt.** `count=3` und
`limit=3` antworten mit 200 und den vollen 895 Projekten. Ein 200 belegt einen
Parameternamen also nicht – dafür muss das `paging`-Objekt der Antwort geprüft werden.
Bei `/v2/entrygroups` ist es umgekehrt: dort führt ein falscher Parameter zu 400.

**Ebenfalls verifiziert am 24.08.2026** – `/v2/entrygroups` verlangt genau diese Form:

```
GET /v2/entrygroups?time_since=2020-01-01T00:00:00Z&time_until=2026-12-31T23:59:59Z&grouping[]=projects_id
→ {"groups": [...]}
```

Vier Punkte, jeder an einer 400er-Antwort belegt:

- `grouping` ist ein **Array-Parameter**. `grouping=projects_id` antwortet mit
  `{"error":{"message":"Array expected.","fields":["grouping"]}}`; erst `grouping[]=…`
  wird akzeptiert. In httpx heißt das ein Dict mit dem Schlüssel `"grouping[]"` – als
  Python-Schlüsselwort ist der Name nicht schreibbar, deshalb nimmt `get()` im Notebook
  ein Params-Dict.
- Gültiger Gruppierungswert ist `projects_id`, nicht `projects` (`Unknown group option`).
  `customers_id` funktioniert ebenfalls, die Werte tragen also durchgehend das Suffix.
- `grouping` und `time_since` sind Pflicht (`Missing data: …`).
- Zeitgrenzen brauchen die volle ISO-Form mit Uhrzeit; ein reines Datum gibt
  `{"error":{"message":"Wrong format","fields":["time_since"]}}`.

**Fehler immer am Körper diagnostizieren, nicht am Status.** Clockodo begründet 400er in
der Form `{"error": {"message": …, "fields": [...]}}` und benennt dort den beanstandeten
Parameter. `httpx.Response.raise_for_status()` zeigt nur Status und URL und verwirft
genau diese Information – deshalb wirft `get()` im Notebook einen eigenen
`ClockodoError` mit angehängtem Antwortkörper. Bei einem neuen 400er also den Körper
lesen, statt Parametervarianten zu raten.

Eine Entrygroup sieht so aus (Felder gekürzt):

```
{"group": "1375839", "name": …, "number": …, "duration": 27314640, "revenue": 1132440.7,
 "hourly_rate": null, "hourly_rate_is_equal_and_has_no_lumpsums": false,
 "budget_used": false, "grouped_by": "projects_id", "restrictions": {"customers_id": …}}
```

Drei Fallen darin, alle an den 870 Gruppen dieser Installation belegt:

- **Die Projekt-ID kommt als String** (`"1375839"`), nicht als Zahl.
- **`group == 0`** (dort als Zahl) steht für Buchungen auf einen Kunden ohne Projekt.
  Ohne Filter entsteht daraus ein Phantom-Projekt 0.
- **`hourly_rate` ist als effektiver Stundensatz unbrauchbar.** Es ist genau dann
  gesetzt, wenn `hourly_rate_is_equal_and_has_no_lumpsums` `true` ist – bei 92 von 870
  Gruppen, und dort meist `0`. Für die 778 Gruppen mit gemischten Sätzen oder
  Pauschalleistungen ist es `null`. Der effektive Satz muss aus `revenue` und `duration`
  (**Sekunden**) abgeleitet werden. Auch dort, wo beide vorliegen, weicht
  `revenue / (duration/3600)` vom nominalen `hourly_rate` ab – nicht abgerechnete Zeit.
  8 Gruppen haben Umsatz bei `duration == 0`, das sind reine Pauschalleistungen.

`revenue` deckt die ganze Historie ab, sobald die untere Zeitgrenze weit genug liegt:
`time_since=2010-01-01` liefert dieselben 870 Gruppen und dieselbe Umsatzsumme wie
`2020-01-01`. Die Antwort hat **kein `paging`** – alle Gruppen kommen in einem Rutsch
(870 Gruppen ≈ 800 KB).

`budget` in `/v4/projects` ist immer als Schlüssel vorhanden, aber bei 236 von 895
Projekten `null`. Ist es gesetzt, hat es mehr Felder als die Spec nennt:

```
{"monetary": true, "hard": false, "from_subprojects": false, "interval": null,
 "amount": 11300, "subprojects_budget_total": 0}
```

Drei davon entscheiden, ob `amount` überhaupt ein Euro-Gesamtbudget ist – `monetary`
(bei `false` steht dort eine **Stundenzahl**: 8 Projekte, alle inaktiv, mit Werten wie
6, 12, 48), `interval` (Budget je Intervall statt Gesamtbudget) und `from_subprojects`
(Summe in `subprojects_budget_total`). Bei den aktiven Projekten trat keiner der drei
Fälle auf, keiner ist also durchgerechnet. `extraktion.budgets_je_projekt` benutzt
solche Budgets deshalb nicht und meldet sie einzeln: eine sichtbare Untererfassung ist
besser als eine still falsche Euro-Zahl. Von den 3 Projekten mit `hard: true` ist
ebenfalls keines aktiv.

**Offene fachliche Abgrenzungen** (Zahlen vom 24.08.2026):

- Von 895 Projekten sind **122 aktiv**; das Notebook filtert über `NUR_AKTIVE = True`.
  Die Spec deckt diese Abgrenzung nicht ab.
- **78 dieser 122 aktiven Projekte haben kein Budget** und fallen damit aus der Prognose;
  es bleiben 44 mit zusammen 2,38 Mio. EUR Budget und 729.678 EUR prognosewirksamem
  Restvolumen. Die Namen der 78 sind überwiegend Schulungs- und Ausbildungsprodukte
  (`A-CSM`, `A-CSPO`, `ACC`), also Katalogpositionen ohne beauftragtes Volumen – das
  rechnet die Spec dem Kurzfristgeschäft zu und schließt es aus dem MVP aus. Ob darunter
  echte Bestandsprojekte mit fehlendem Budget stecken, ist ein Pflegethema.
- **Zwei aktive Projekte tragen `completed: true`**, eines mit 12.424 EUR offenem Budget.
  Sie gehen derzeit in die Prognose ein; das Feld kennt die Spec nicht.
- `revenue_factor` ist bei allen aktiven Projekten 1, `test_data` überall `false`, und
  kein aktives Projekt hat Teilprojekte. Diese drei Felder brauchen also keine
  Sonderbehandlung, solange das so bleibt.

## Kalibrierung als Teil des Modells

Zwei Größen sind geschätzt und veralten: die Referenzklassen-Zuordnung der Projekte und
der historische Aufteilungsschlüssel je Person. Wechselt die Teambesetzung eines Projekts
spürbar, wird der Schlüssel falsch. Die Spec ordnet das ausdrücklich der monatlichen
Kalibrierung zu und **nicht** einer Modelländerung – bei Abweichungen also zuerst die
Kalibrierung prüfen, nicht die Simulationslogik umbauen.

## Wichtige Einschränkung der Spec-Datei

v0.5 ist wie schon v0.4 ein Delta-Dokument: viele Abschnitte (Begriffe, Abrufquote-Verteilung,
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
