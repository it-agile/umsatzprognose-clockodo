# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Kommandos

Abhängigkeits- und Python-Verwaltung läuft ausschließlich über **uv**; die Version ist
in `.python-version` auf 3.13 gepinnt. Kein `pip install` im Projekt-venv, kein manuell
angelegtes venv. Colab läuft auf Python 3.13.

```bash
uv sync --extra notebook       # Umgebung herstellen
uv run pytest                  # alle Tests
uv run pytest tests/test_projekt.py::test_restvolumen_ist_budget_minus_verbrauch  # ein Test
uv run ruff check .            # Lint
uv run ruff format .           # Formatierung
uv run jupyter lab             # Notebooks lokal
```

## Aufbau und wo was hingehört

Das Paket bildet ab: Kunde, Projekt,
Mitarbeiter, Projektanteil, Umsatzhistorie. Drei Schichten mit genau einer erlaubten
Abhängigkeitsrichtung:

```
darstellung  ──►  domaene  ◄──  clockodo
```

- `src/umsatzprognose/domaene/` – die Fachobjekte, unveränderlich (`frozen=True`) und
  ohne jede Bibliotheksabhängigkeit. `projekt.py` (`Projekt`, `Budget` – Restvolumen
  roh und prognosewirksam nach Spec 5.1, effektiver Stundensatz, Prognose-Scope),
  `kunde.py`, `mitarbeiter.py` (`Mitarbeiter`, `Wochenarbeitszeit`), `projektanteil.py`
  (der Aufteilungsschlüssel aus 5.4 Schritt 3), `umsatzhistorie.py` (`Monatsumsatz`,
  `Umsatzhistorie`), `verbrauchsverlauf.py` (`Verbrauchsverlauf` – der Monatsverbrauch je
  Projekt, die Rückrechnung des Restvolumens und das Beobachtungsfenster aus 5.2),
  `abrufquote.py` (`Abrufquote`, `Abrufquotenverteilung` – die empirische Verteilung nach
  5.2 samt Ziehung mit Zurücklegen), `bestand.py` (das Aggregat), `prognose.py` (ABC plus
  `NochKeinePrognose`), `hinweis.py`, `zahlen.py` (deutsche Zahlformate ohne `locale`).
- `src/umsatzprognose/clockodo/` – **alles, was Clockodo weiß, weiß nur dieses Paket.**
  `config.py` (Zugangsdaten mit den benannten Konstruktoren `automatisch`,
  `aus_umgebung`, `aus_colab_secrets`), `client.py` (`ClockodoClient`: HTTP,
  Paginierung, die verifizierte Parameterform je Endpunkt, `ClockodoError` mit
  Antwortkörper), `nebenlaeufig.py` (`synchron`, `gleichzeitig` – siehe unten), dazu je
  Endpunkt ein Repository: `kunden.py`, `mitarbeiter.py`, `projekte.py`, `umsatz.py`,
  `verbrauchsverlauf.py` und `bestand.py` (`BestandRepository`, der eine Einstieg).
- `src/umsatzprognose/darstellung/` – der einzige Ort mit plotly (`diagramme.py`,
  `gestaltung.py`) und pandas (`tabellen.py`), dazu `dashboard.py` mit der Fassade
  `Dashboard`, die die Notebooks benutzen.
- `tests/` – pytest. Die Antwortausschnitte in `conftest.py` sind gekürzte, aber echte
  Antworten samt ihrer Fallen.
- `notebooks/` – zwei Notebooks mit verschiedenen Zielgruppen, siehe unten.
- `spec/spec-umsatzprognose-clockodo-modul.md` – die Spezifikation.

**Die Domäne kennt kein JSON und keinen HTTP-Client.** Das ist die tragende Regel:
das Wissen über Clockodos Eigenheiten steht in `clockodo/`, je Endpunkt
dort, wo seine Abbildung liegt.

**Die Simulation gehört an den `Bestand`, nicht an das `Projekt`.** Der
Kapazitätsdeckel aus 5.4 Schritt 4 wirkt je Person über *alle* ihre Projekte, und ein
Lauf ist eine Ziehung über das gesamte Portfolio – die Summe unabhängig gerechneter
Projektverteilungen ist nicht die Portfolio-Bandbreite, und der geforderte „Anteil der
Läufe mit Kapazität als limitierendem Faktor" entsteht erst auf dieser Ebene. Projekt
und Mitarbeiter liefern Regeln und Zustand, keine fertigen Prognosen.

**Die Fachobjekte bleiben unveränderlich.** Bei 10.000 Läufen existieren 10.000
Restvolumen-Verläufe gleichzeitig; ein `projekt.restvolumen -= verbrauch` im
Simulationsschritt würde die Stammdaten zum Lauf-Zustand machen und beim zweiten Lauf
falsche Zahlen liefern. Der Lauf-Zustand gehört neben die Objekte.

**Die Abrufe laufen gleichzeitig, die Abbildung nacheinander.** Die sieben Antworten
einer Prognose – Kunden, Personen, Sollzeiten, Projekte, Verbrauch, Umsatzhistorie und
der Monatsverbrauch je Projekt – hängen nicht voneinander ab; aufeinander angewiesen ist
erst das Zusammensetzen, weil die Projekte Kunde und Person als Objekt tragen und die
Verbrauchsverläufe das fertige Projekt samt Budget brauchen. Deshalb sind die Methoden
von `ClockodoClient` **Coroutinen**, `BestandRepository.laden_async()` fächert sie mit
`gleichzeitig()` auf, und erst danach bildet `ProjektRepository.abbilden()` ab. Abruf
und Abbildung sind in den Repositories dafür getrennt (`laden_async` / `abbilden`,
bei den Projekten zusätzlich die freie Funktion `projekte.rohdaten`).

Zwei der sieben Abrufe sind dieselbe Doppelgruppierung von `/v2/entrygroups` – einmal
nach Person, einmal nach Monat, je rund 20 Sekunden. Nebeneinander kosten sie zusammen
kaum mehr als einer: ein vollständiger Ladevorgang dauerte am 26.08.2026 18 Sekunden.
Wer den Monatsverbrauch nicht braucht, schaltet ihn mit `mit_verbrauchsverlauf=False` ab
– dann gibt es allerdings keine geschätzte Abrufquote-Verteilung.

Die öffentlichen Einstiege bleiben gewöhnliche Funktionen: `Dashboard.laden()` und
`BestandRepository.laden()` legen `synchron()` um die Coroutine. **Das ist mehr als ein
`asyncio.run`** – in Colab und Jupyter läuft bereits ein Event-Loop, dort bricht
`asyncio.run` mit `RuntimeError: asyncio.run() cannot be called from a running event
loop` ab und `loop.run_until_complete` mit `This event loop is already running`.
`synchron()` erkennt den Fall und führt die Coroutine in einem eigenen Thread mit
eigenem Loop aus; `nest_asyncio` wäre eine Abhängigkeit, die nur an dieser Stelle
gebraucht würde. Wer selbst in einem Loop steht, ruft `laden_async()` direkt auf.

Nebenläufigkeitsprimitive gehören **nicht** an ein langlebiges Objekt: ein
`asyncio.Semaphore` bindet sich an den Loop, in dem es zuerst benutzt wird, und jeder
synchrone Ladevorgang bringt einen neuen Loop mit. `gleichzeitig()` erzeugt seine Sperre
deshalb je Aufruf – und bricht bei einem Fehler die übrigen Abrufe ab, damit ein 400
nicht erst nach den fünf anderen Antworten auffällt.

Dass die Abrufe wirklich überlappen, prüft `tests/test_nebenlaeufig.py` mit einer
`asyncio.Barrier`: laufen sie wieder nacheinander, wartet der erste Handler vergeblich.
Ein Test auf die Zahlen allein würde die Umstellung nicht bemerken – sequenziell kommt
dasselbe heraus, nur langsamer.

**Zeitbuchungen werden nicht einzeln geladen.** Die Spec nennt dafür `/v2/entries` mit
`users_id` je Eintrag – das wären allein für zwölf Monate 16.461 Einträge über sieben
Seiten. `/v2/entrygroups` mit `grouping[]=projects_id&grouping[]=users_id` liefert
dieselbe Aufteilung fertig aggregiert, in einem Abruf. Der Begriff bleibt als
`Projektanteil` im Modell.

### Notebooks

Zielwerkzeug ist laut Spec (Abschnitt 9) ein Notebook in **Google Colab**, deshalb
bleibt der Notebook-Layer dünn und beginnt mit einer nur in Colab greifenden
Installationszelle – das lokale venv steht dort nicht zur Verfügung.

- `notebooks/01_dashboard.ipynb` – für Fachexperten. Je Zelle ein Aufruf auf
  `Dashboard`, Fachsprache, keine Endpunkte, keine IDs, keine technischen Marker.
- `notebooks/02_technik_restvolumen.ipynb` – für die Entwicklung. Prüfsummen,
  Aufteilungsschlüssel, Sollarbeitszeiten und die offenen fachlichen Fragen
  (`ENTSCHEIDEN`-Abschnitte).

Rechenlogik gehört ins Paket, nicht ins Notebook.

## Stand der Implementierung

Umgesetzt sind die Schritte 1 und 2 aus Spec Abschnitt 11: Restvolumen je Projekt (5.1)
und die **geschätzte Abrufquote-Verteilung** (5.2), dazu das vollständige Domänenmodell
außer der Simulation – inklusive Aufteilungsschlüssel je Person (5.4 Schritt 3) und
Sollarbeitszeit (Teil von 5.3).

Die Verteilung liegt an `Bestand.abrufquotenverteilung()` und stammt aus den
`Verbrauchsverlauf`-Objekten. Am 26.08.2026 gegen die Installation: **2.640
Projekt-Monate**, Median 0,117, Mittelwert 0,396, **32 % ohne Abruf**, 3,1 % über 1,
Maximum 175,7. Die Zahlen bewegen sich mit jeder Zeitbuchung und taugen als
Größenordnung, nicht als Regressionswert.

Zwei Punkte dazu, die man wissen muss:

- **Das Beobachtungsfenster ist eine Entscheidung, keine Vorgabe.** Spec 5.2 nennt nur
  „Restvolumen > 0 zu Monatsbeginn"; welche Monate überhaupt dazugehören, legt
  `Verbrauchsverlauf.beobachtungsmonate()` fest: von der ersten Buchung bis zum Vormonat
  des Stichtags, wenn das Projekt heute im Prognose-Scope ist – sonst bis zur letzten
  Buchung. Lücken darin zählen als Quote 0, der angebrochene Stichtagsmonat zählt nie
  mit. Ruhige Monate **vor** der ersten Buchung fehlen der Verteilung; ihre Quoten liegen
  damit eher zu hoch.
- **Quoten über 1 sind echt und bleiben stehen.** Das Maximum von 175,7 (ein Projekt-Monat
  mit 400 EUR offenem Restvolumen und einer großen Buchung) ist genau der Fall, den 5.2
  benennt: das Budget ist nur in seinem heutigen Stand bekannt. In der Simulation ist der
  Schaden begrenzt, weil Schritt 2 auf das verbleibende Restvolumen kappt – eine Quote von
  175 heißt dort „ruf alles ab, was offen ist".

Es fehlen: die Monte-Carlo-Simulation (5.4) und die verfügbare Kapazität (5.3, es fehlen
Abwesenheiten, Feiertage und der Abschlag für ungeplante Abwesenheit).
`Bestand.simulieren()` liefert deshalb `NochKeinePrognose` mit Begründung, und das
Dashboard zeigt an der Stelle der Bandbreite genau diese Begründung an – eine erfundene
Kurve wäre der schlechtere Platzhalter.

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

Die Simulation rechnet **in Euro als Leitgröße** und nutzt **Stunden** nur als
Zwischenschritt für den Kapazitätsdeckel. Diese Richtung ist zentral – wer sie umdreht,
baut ein anderes Modell. Stunden und nicht Personentage, weil `/targethours` Stunden je
Wochentag liefert (20–35 h/Woche, meist 7 h/Tag) und keine Taglänge hinterlegt ist; eine
angenommene würde den Deckel still verschieben (Spec 5.3).

Der Horizont **beginnt mit dem laufenden Monat**, genauer: am Stichtag. Monat 1 ist nur
der Rest des Monats, deshalb werden gezogene Abrufquote und Kapazität mit dem Anteil der
verbleibenden Arbeitstage skaliert. Was **vor** dem Stichtag gebucht wurde, ist Verbrauch
und aus dem Restvolumen abgezogen; es taucht in der Bandbreite nicht wieder auf, wird für
die Darstellung aber daneben ausgewiesen (5.5).

**Was nach dem Stichtag datiert ist, ist die Untergrenze**, nicht Verbrauch (5.4):

    Monatsumsatz = max(simulierter Umsatz, bereits gebuchter Umsatz dieses Monats)

Ohne diese Grenze könnte das 95-%-Niveau eines Monats unter dem liegen, was schon
feststeht – die Simulation zieht eine Abrufquote und weiß nichts von der Buchung. Der
gebuchte Betrag zählt gegen dasselbe Restvolumen, wird also nicht zusätzlich abgerufen.

1. Restvolumen je Projekt: `budget.amount − revenue_kumuliert` (aus `entrygroups`).
   Pauschalleistungen werden über einen abgeleiteten effektiven Stundensatz normalisiert.
   Initialisiert wird mit dem **prognosewirksamen** Restvolumen, also `max(0, …)`.
2. Abrufquote je Monat aus der **portfolioweiten** empirischen Verteilung ziehen
   → gewünschter Euro-Verbrauch, **begrenzt auf das verbleibende Restvolumen**.
3. Über den effektiven Stundensatz in Stunden umrechnen und auf Personen aufteilen –
   Schlüssel ist der **historische Anteil je Person am jeweiligen Projekt** (Anteil an
   den Gesamtstunden), unverändert in die Zukunft fortgeschrieben. Er liegt als
   `Projekt.anteil_je_mitarbeiter()` vor und stammt aus der Doppelgruppierung von
   `/v2/entrygroups`, nicht aus den Einzeleinträgen.
4. Je Person Bedarf über **alle** Projekte gegen die verfügbare Kapazität deckeln; bei
   Überschreitung anteilig kürzen. Der Deckel ist projektübergreifend, nicht pro Projekt.
5. Gelieferte Stunden zurück in Euro → Monatsumsatz je Projekt.
6. Restvolumen um den tatsächlichen Euro-Verbrauch reduzieren, in den nächsten Monat
   übertragen. Durch die Begrenzung in Schritt 2 bleibt es ≥ 0.

Neben den Konfidenzniveaus ist der **Anteil der Läufe, in denen Kapazität der limitierende
Faktor war**, ein geforderter Output – er unterscheidet Nachfrage- von Kapazitätsengpass.

Verfügbare Kapazität = Sollarbeitszeit − geplante Abwesenheit − geschätzter Abschlag für
ungeplante Abwesenheit.

## Clockodo-API: gemischte Versionen

Die benötigten Daten liegen über vier verschiedene API-Generationen verteilt; das ist
Stand der Clockodo-API:

| Zweck | Endpunkt | Felder |
|---|---|---|
| Auftragsvolumen | `GET /v4/projects`, `/v4/projects/{id}` | `budget.amount`, `budget.hard` |
| Verbrauch, effektiver Satz | `GET /v2/entrygroups`, `grouping[]=projects_id` | `revenue`, `duration` (nicht `hourly_rate`, siehe unten) |
| Anteil je Person | `GET /v2/entrygroups`, zusätzlich `grouping[]=users_id` | `sub_groups` mit `duration`, `revenue` |
| Umsatz je Monat | `GET /v2/entrygroups`, `grouping[]=month` | `group` (`"JJJJMM"`), `revenue`, `duration` |
| Abrufquote, gebuchter Horizont | `GET /v2/entrygroups`, `grouping[]=projects_id&grouping[]=month` | `sub_groups` mit `group` (`"JJJJMM"`), `revenue` |
| Kundenname (Beschriftung) | `GET /v3/customers` | `id`, `name` |
| Personen | `GET /v3/users` | `id`, `name`, `active` – **nicht** `default_target_hours` |
| Sollarbeitszeit | `GET /targethours` (unversioniert) | `users_id`, `date_since`/`date_until`, Stunden je Wochentag |
| Geplante Abwesenheit | `GET /v4/absences?year=…` | noch nicht ausgewertet (Spec 5.3) |
| Feiertage | `GET /nonbusinessdays?year=…` (unversioniert) | `nonbusinessgroups_id`, `date`, `half_day` – noch nicht ausgewertet (Spec 5.3) |
| Einzeleinträge | `GET /v2/entries` | **wird nicht benutzt**, siehe unten |

`budget.hard` ist in dieser Installation `false` – Budgets sind also weiche Grenzen und
sind kein technisches Limit: der Verbrauch kann sie übersteigen, das rohe Restvolumen
wird dann negativ. Das ist ein Kalibrierungssignal und kein Fehler.

Für die Prognose gilt trotzdem eine harte Grenze (Spec 5.1): **eine
Überschreitung kann nur historisch entstehen, die Prognose überschreitet das Budget
nicht.** Projekte mit historisch überschrittenem Budget tragen 0 zur Prognose bei.
Deshalb führt `Projekt` beide Größen getrennt – `restvolumen_roh`
(vorzeichenbehaftet, für die Kalibrierung) und `restvolumen_prognosewirksam` (bei 0
gekappt, für die Simulation).

Basis-URL ist `https://my.clockodo.com/api`. Authentifizierung über drei Header, alle
drei sind Pflicht: `X-ClockodoApiUser` (E-Mail des Benutzers), `X-ClockodoApiKey` und
`X-Clockodo-External-Application` im Format `name;email` mit **maximal 50 Zeichen
Gesamtlänge**. `clockodo.config.ClockodoCredentials` kapselt das und prüft die Längengrenze.

`docs.clockodo.com` wird als JavaScript-Anwendung ausgeliefert und war nicht auslesbar;
die Response-Strukturen stammen daher aus echten Läufen, nicht aus der Doku.

`/v4/projects` liefert

```
{"paging": {"items_per_page": 1000, "current_page": 1, "count_pages": 1, "count_items": 895},
 "data": [{"id": …, "customers_id": …, "name": …, "number": …, "active": …, …}]}
```

Also: Envelope-Key ist `data` (nicht `projects`), die Projekt-ID heißt `id`, und es gibt
ein `paging`-Objekt. `items_per_page` ist 1000 bei aktuell 895 Projekten – die Grenze ist
nah, deshalb läuft `ClockodoClient.get_paged` über alle Seiten statt nur über die erste.

Die Paginierung ist inzwischen ausgeführt und nicht mehr geraten: `items_per_page` setzt
die Seitengröße, `page` wählt die Seite. Mit `items_per_page=3` antwortet die API mit
`count_pages: 299`, und `page=2` liefert `current_page: 2` samt anderer IDs.

**Unbekannte Query-Parameter werden still ignoriert, nicht abgelehnt.** `count=3` und
`limit=3` antworten mit 200 und den vollen 895 Projekten. Ein 200 belegt einen
Parameternamen also nicht – dafür muss das `paging`-Objekt der Antwort geprüft werden.
Bei `/v2/entrygroups` ist es umgekehrt: dort führt ein falscher Parameter zu 400.

`/v2/entrygroups` verlangt genau diese Form:

```
GET /v2/entrygroups?time_since=2020-01-01T00:00:00Z&time_until=2026-08-31T23:59:59Z&grouping[]=projects_id
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

**Fehler immer im Body diagnostizieren, nicht am Status.** Clockodo begründet 400er in
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

Fallen:

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

### Gruppierungen von `/v2/entrygroups`

`/v2/entrygroups` kann mehr als nach Projekt gruppieren, und das ersetzt eine Menge
eigener Rechnerei:

- Gültige **Zeit**gruppierungen sind `month`, `year`, `week` und `day` – im **Singular
  und ohne `_id`-Suffix**, anders als bei Objekten. `months`, `years` und `date`
  antworten mit 400.
- **`group` wechselt den Typ**: bei `month` kommt der String `"202509"`, bei `year` die
  Zahl `2026`. Vor dem Zerlegen also `str()`, nicht auf den Typ verlassen.
- **Mehrfachgruppierung** ist erlaubt. `grouping[]=projects_id&grouping[]=users_id`
  hängt die Personen als `sub_groups` unter das Projekt, jede mit `group` (die
  `users_id` als String), `name`, `duration` und `revenue`. Das ist der historische
  Aufteilungsschlüssel aus Spec 5.4 Schritt 3, fertig aggregiert.
- Die Projektsummen dieser Antwort sind mit denen der einfachen Gruppierung
  **identisch** (über alle 870 Gruppen verglichen, keine Abweichung), und die
  Untergruppen summieren sich exakt auf sie. Deshalb genügt ein Abruf für Verbrauch und
  Aufteilungsschlüssel – rund 1,9 MB und etwa 20 Sekunden gegen 800 KB und 10 Sekunden
  bei der einfachen Gruppierung.
- Die Monatsgruppierung enthält **alle** Buchungen, auch die auf einen Kunden ohne
  Projekt. Genau das ist im Dashboard gewollt: gefragt ist der Gesamtumsatz.
- `grouping[]=projects_id&grouping[]=month` liefert je Projekt die Monate als
  `sub_groups` – die Kombination aus Spec 11.1, am 26.08.2026 verifiziert: 870 Gruppen mit
  zusammen 5.467 Projekt-Monaten von 01/2021 bis 11/2026, rund 23 Sekunden. **Die äußere
  Ebene ist die zuerst genannte.** Drei Fallen darin:
  - **Die Untergruppen kommen nach `duration` absteigend, nie chronologisch** – bei allen
    667 Gruppen mit mehr als einem Monat. Die Rückrechnung des Restvolumens aus 5.2 lebt
    von der Reihenfolge; wer sie übernimmt, rechnet still falsch. Bei der
    Personengruppierung fiel das nie auf, weil Personen keine Reihenfolge haben.
  - **Die Monatssummen gehen nur auf den Cent auf.** Bei 31 Projekten weicht die Summe
    der Monate von der Projektsumme ab, höchstens um 0,06 EUR und in der Gesamtsumme um
    0,63 EUR auf 30,6 Mio. – Clockodo rundet jede Gruppe einzeln. Die Zeitsummen stimmen
    exakt, und die Projektsummen sind mit der einfachen Gruppierung identisch. Ein
    Vergleich auf Gleichheit wäre also ein Fehlalarm.
  - **`group == 0` kommt mehrfach vor** – zweimal, je Kunde ohne Projekt einmal, und das
    ist der einzige doppelt vergebene Schlüssel (869 verschiedene auf 870 Gruppen).
    `VerbrauchsverlaufRepository.abbilden()` faltet deshalb je Projekt-ID zusammen,
    statt zuzuweisen.

**`/v2/entries` wird bewusst nicht benutzt.** Erst wenn eine
Auswertung wirklich den einzelnen Eintrag braucht (etwa `type` zur Trennung von
Pauschalleistungen), lohnt er sich.

### Sollarbeitszeit
Die Werte stehen im **unversionierten** `/targethours` (`/v2` und `/v3` geben 404):

```
{"targethours": [{"id": 336993, "users_id": 143323, "type": "weekly",
                  "date_since": "2023-06-14", "date_until": null,
                  "monday": 7, …, "sunday": 0}]}
```

Für die geplanten Abwesenheiten (5.3) ist `/v4/absences?year=…` der richtige Endpunkt:
`/absences`, `/v2/absences` und `/v3/absences` antworten mit 410 `deprecated`.

**Kundennamen nur über `/v3/customers`**: `/v4/customers`
antwortet mit 404 `RouteNotFound`, `/v2/customers` mit 410 `deprecated`. Die Antwortform
gleicht `/v4/projects` – `{"paging": {...}, "data": [{"id": …, "name": …, …}]}`. `/v4/projects` selbst führt nur `customers_id`, keinen
Kundennamen. Alle Projekte tragen einen `name` und eine auflösbare `customers_id`;
`clockodo/projekte.py` lässt eine Lücke trotzdem als `None` durch, statt einen Abruf mit
einem `KeyError` zu beenden – eine fehlende Beschriftung darf keine Zahl kosten. Für
Personen gilt dasselbe: eine `users_id` ohne Stammdatensatz bekommt ein
Platzhalterobjekt, ihre Stunden gehen nicht verloren.

`revenue` deckt die ganze Historie ab, sobald die untere Zeitgrenze weit genug liegt:
`time_since=2010-01-01` liefert dieselben Gruppen und dieselbe Umsatzsumme wie
`2020-01-01`. Die Antwort hat **kein `paging`** – alle Gruppen kommen in einem Rutsch.

**Drei obere Zeitgrenzen, und keine ist die andere.** Alle in `client.py`, alle
Funktionen:

- `verbrauch_bis(stichtag)` – **der Stichtag selbst**, Grenze des Verbrauchs (Spec 5.1).
  Verbrauch ist streng Vergangenheit. `BestandRepository.laden()` bindet sie an den
  Stichtag des Bestands, nicht an heute; erst damit ist ein Bestand zu einem vergangenen
  Stichtag konsistent – Voraussetzung für den Rückwärtstest (Spec 11.4).
- `monatsende(tag)` – der letzte Tag des Kalendermonats, Fenster der **Umsatzhistorie**.
  Dort ist der laufende Monat ein Balken, und eine später im Monat datierte Buchung
  gehört hinein.
- `horizontende(stichtag, monate)` – der letzte Tag des letzten **Horizontmonats**.
  Weil der Horizont mit dem laufenden Monat beginnt (5.4), enden drei Monate ab dem
  26.08.2026 am 31.10.2026. Diese Grenze zieht den Monatsverbrauch je Projekt: derselbe
  Abruf trägt die Historie für 5.2 und die gebuchten Beträge im Horizont für 5.4.

Wer zwei davon zusammenlegt, bricht eines von beidem. Bis zum 24.08.2026 lag die
Verbrauchsgrenze am Monatsende: das schlug 600 EUR aus dem Restaugust stumm dem Verbrauch
zu, statt sie der Prognose anzurechnen.

**Funktionen und nicht Konstanten**.

## Nächster geplanter Schritt

Laut Spec Abschnitt 11, Schritt 2: **Abwesenheiten und Feiertage auswerten** (5.3).
`/v4/absences?year=…` anbinden und daraus den Abschlag für ungeplante Abwesenheit
schätzen; `/nonbusinessdays?year=…` je Feiertagsgruppe anbinden und die
`nonbusinessgroups_id` der Person mitlesen, die heute noch verworfen wird. Der Horizont
reicht über eine Jahresgrenze, also zwei Abrufe je Endpunkt. Danach die Simulation (5.4)
samt vollständiger Ausgabe (5.5), dann der Rückwärtstest über 12 Stichtage.
