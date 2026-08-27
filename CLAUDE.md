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
Kapazitätsdeckel wirkt je Person über *alle* ihre Projekte, und ein
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
nach Person, einmal nach Monat.
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
`users_id` je Eintrag – das wären allein für zwölf Monate mehrere Seiten
Einzeleinträge. `/v2/entrygroups` mit `grouping[]=projects_id&grouping[]=users_id` liefert
dieselbe Aufteilung fertig aggregiert, in einem Abruf. Der Begriff bleibt als
`Projektanteil` im Modell.

### Notebooks

Zielwerkzeug ist ein Notebook in **Google Colab**, deshalb
bleibt der Notebook-Layer dünn und beginnt mit einer nur in Colab greifenden
Installationszelle – das lokale venv steht dort nicht zur Verfügung.

- `notebooks/01_dashboard.ipynb` – für Fachexperten. Je Zelle ein Aufruf auf
  `Dashboard`, Fachsprache, keine Endpunkte, keine IDs, keine technischen Marker.
- `notebooks/02_technik_restvolumen.ipynb` – für die Entwicklung. Prüfsummen,
  Aufteilungsschlüssel, Sollarbeitszeiten und die offenen fachlichen Fragen
  (`ENTSCHEIDEN`-Abschnitte).

Rechenlogik gehört ins Paket, nicht ins Notebook.

## Keine gelesenen Werte im Repository

**Werte, die aus der Clockodo-API gelesen wurden, gehören in keine Datei dieses
Repositories** – weder in Code, Tests, Spec, diese Datei noch in Notizen. Gemeint sind
Umsätze, Stundensätze, Budgets, Anzahlen von Projekten, Personen oder Gruppen, IDs sowie
Kunden-, Projekt- und Personennamen. Das Repository ist öffentlich, die Werte sind echte
Geschäfts- und Personendaten, und sie veralten mit jeder Zeitbuchung – als Zahl in einer
versionierten Datei werden sie zum Regressionswert, der nie gestimmt hat.

Erlaubt und erwünscht bleibt die Beschreibung des **Verhaltens**: Envelope, Feldnamen,
Typen, Sonderfälle, Statuscodes, Grenzen der API, Reihenfolge und Rundung der Antwort.
Wo eine Größenordnung nötig ist, steht sie qualitativ („eine Minderheit der Gruppen",
„nah an der Seitengröße von 1000"). Testfixtures bilden die **Struktur** der echten
Antwort nach, mit frei erfundenen IDs, Namen und Beträgen.

Die gemessenen Zahlen gehören in die Notebook-Ausgabe: dort entstehen sie bei jedem Lauf
neu und sind aktuell. Notebooks werden deshalb **ohne Zellausgaben** committet.

## Was das Modul fachlich tut

Rollierende 1–3-Monats-Umsatzprognose für den **Baustein Bestand**: Umsatz aus bereits
in Clockodo angelegten Projekten. Ausgabe ist eine **Bandbreite** (Konfidenzniveaus
95 % / 85 % / 50 % je Monat und als Summe), kein Punktwert.

Zwei Annahmen prägen das ganze Modell:

- Ein in Clockodo angelegtes Projekt gilt als beauftragt. Storno auf Projektebene wird
  daher nicht modelliert.
- Die einzige modellierte Unsicherheit ist die **Abrufquote**: wie viel des beauftragten
  Restvolumens im Prognosezeitraum tatsächlich abgerufen wird.

## Rechenkern (Monte Carlo, 10.000 Läufe)

Die Simulation rechnet **in Euro als Leitgröße** und nutzt **Stunden** nur als
Zwischenschritt für den Kapazitätsdeckel. Stunden und nicht Personentage, weil `/targethours` Stunden je
Wochentag liefert (20–35 h/Woche, meist 7 h/Tag) und keine Taglänge hinterlegt ist; eine
angenommene würde den Deckel still verschieben.

Der Horizont **beginnt mit dem laufenden Monat**, genauer: am Stichtag. Monat 1 ist nur
der Rest des Monats, deshalb werden gezogene Abrufquote und Kapazität mit dem Anteil der
verbleibenden Arbeitstage skaliert. Was **vor** dem Stichtag gebucht wurde, ist Verbrauch
und aus dem Restvolumen abgezogen; es taucht in der Bandbreite nicht wieder auf, wird für
die Darstellung aber daneben ausgewiesen.

**Was nach dem Stichtag datiert ist, ist die Untergrenze**, nicht Verbrauch:

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
| Geplante Abwesenheit | `GET /v4/absences`, `filter[year]` (kein `year` direkt) | geladen in `Mitarbeiter.abwesenheiten`; Typ/Status gedeutet über `Abwesenheit.zaehlt_als_kapazitaetsabzug` (Spec 5.3) |
| Feiertage | `GET /v2/nonbusinessDays` | `nonbusiness_group_id`, `evaluated_date`, `half_day` (bool) – ungenutzt, siehe unten |
| Feiertage je Person | `GET /v2/usersNonbusinessDays`, `year` | `users_id`, `days[]` – geladen in `Mitarbeiter.feiertage`, roh (Spec 5.3) |
| Feiertagsgruppe je Person | `GET /v3/usersNonbusinessGroups` | `users_id`, `nonbusiness_groups_id`, `date_since`/`date_until` – ungenutzt, siehe unten |
| Einzeleinträge | `GET /v2/entries` | **wird nicht benutzt**, siehe unten |

`budget.hard` ist in dieser Installation `false` – Budgets sind also weiche Grenzen und
sind kein technisches Limit: der Verbrauch kann sie übersteigen, das rohe Restvolumen
wird dann negativ. Das ist ein Kalibrierungssignal und kein Fehler.

Für die Prognose gilt trotzdem eine harte Grenze: **eine
Überschreitung kann nur historisch entstehen, die Prognose überschreitet das Budget
nicht.** Projekte mit historisch überschrittenem Budget tragen 0 zur Prognose bei.
Deshalb führt `Projekt` beide Größen getrennt – `restvolumen_roh`
(vorzeichenbehaftet, für die Kalibrierung) und `restvolumen_prognosewirksam` (bei 0
gekappt, für die Simulation).

Basis-URL ist `https://my.clockodo.com/api`. Authentifizierung über drei Header, alle
drei sind Pflicht: `X-ClockodoApiUser` (E-Mail des Benutzers), `X-ClockodoApiKey` und
`X-Clockodo-External-Application` im Format `name;email` mit **maximal 50 Zeichen
Gesamtlänge**. `clockodo.config.ClockodoCredentials` kapselt das und prüft die Längengrenze.

**Die OpenAPI-Beschreibung liegt im Repository**:
`spec/clocodo-api.yaml`, Fassung `2026-08-24`.

**Die Doku ist die erste Anlaufstelle.** An
drei Stellen widersprechen sich beide, und zwar so, dass die Doku die schlechtere Quelle
ist:

- `EntryGroupV2.group` ist als `string` deklariert, kommt aber bei `group == 0` und bei
  `grouping[]=year` als **Zahl**. Deshalb bleibt `str()` vor dem Zerlegen.
- `EntryGroupV2.revenue` ist als `integer/int64` deklariert und ist in Wahrheit ein
  **Float**. Deshalb bleibt `float()`.
- `EntryGroupV2.duration` nennt keine Einheit; **Sekunden** steht nur an den Feldern von
  `/v2/entries` („Duration in seconds").

**Fehler immer im Body diagnostizieren, nicht am Status.** Clockodo begründet 400er in
der Form `{"error": {"message": …, "fields": [...]}}` und benennt dort den beanstandeten
Parameter. `httpx.Response.raise_for_status()` zeigt nur Status und URL und verwirft
genau diese Information – deshalb wirft `get()` im Notebook einen eigenen
`ClockodoError` mit angehängtem Antwortkörper. Bei einem neuen 400er also den Körper
lesen, statt Parametervarianten zu raten.

Eine Entrygroup sieht so aus (Felder gekürzt):

```
{"group": "101", "name": …, "number": …, "duration": 2160000, "revenue": 60000.0,
 "hourly_rate": null, "hourly_rate_is_equal_and_has_no_lumpsums": false,
 "budget_used": false, "grouped_by": "projects_id", "restrictions": {"customers_id": …}}
```

Fallen:
- **Die Projekt-ID kommt als String** (hier `"101"`), nicht als Zahl.
- **`group == 0`** (dort als Zahl) steht für Buchungen auf einen Kunden ohne Projekt.
  Ohne Filter entsteht daraus ein Phantom-Projekt 0.
- **`hourly_rate` ist als effektiver Stundensatz unbrauchbar.** Es ist genau dann
  gesetzt, wenn `hourly_rate_is_equal_and_has_no_lumpsums` `true` ist – nur bei einer
  Minderheit der Gruppen, und dort meist `0`. Für Gruppen mit gemischten Sätzen oder
  Pauschalleistungen ist es `null`. Der effektive Satz muss aus `revenue` und `duration`
  (**Sekunden**) abgeleitet werden. Auch dort, wo beide vorliegen, weicht
  `revenue / (duration/3600)` vom nominalen `hourly_rate` ab – nicht abgerechnete Zeit.
  Einige Gruppen haben Umsatz bei `duration == 0`, das sind reine Pauschalleistungen.

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
  Aufteilungsschlüssel fertig aggregiert.
- Die Projektsummen dieser Antwort sind mit denen der einfachen Gruppierung
  **identisch** (über alle Gruppen verglichen, keine Abweichung), und die
  Untergruppen summieren sich exakt auf sie. Deshalb genügt ein Abruf für Verbrauch und
  Aufteilungsschlüssel – rund 1,9 MB und etwa 20 Sekunden gegen 800 KB und 10 Sekunden
  bei der einfachen Gruppierung.
- Die Monatsgruppierung enthält **alle** Buchungen, auch die auf einen Kunden ohne
  Projekt. Genau das ist im Dashboard gewollt: gefragt ist der Gesamtumsatz.
- `grouping[]=projects_id&grouping[]=month` liefert je Projekt die Monate als
  `sub_groups` 
  - **Die Untergruppen kommen nach `duration` absteigend, nie chronologisch** – bei allen
    Gruppen mit mehr als einem Monat.
  - **Die Monatssummen gehen nur auf den Cent auf.** Bei einer Reihe von Projekten
    weicht die Summe der Monate von der Projektsumme um Cent-Beträge ab – Clockodo
    rundet jede Gruppe einzeln. Die Zeitsummen stimmen
    exakt, und die Projektsummen sind mit der einfachen Gruppierung identisch. Ein
    Vergleich auf Gleichheit wäre also ein Fehlalarm.
  - **`group == 0` kommt mehrfach vor** – zweimal, je Kunde ohne Projekt einmal, und das
    ist der einzige doppelt vergebene Schlüssel.
    `VerbrauchsverlaufRepository.abbilden()` faltet deshalb je Projekt-ID zusammen,
    statt zuzuweisen.

- Der Gruppierungswert **`is_lumpsum`** trennt Pauschalleistungen von Zeitbuchungen –
  Untergruppen `"0"` und `"1"` als String. Damit ist der letzte Grund für `/v2/entries`
  entfallen: die Trennung braucht den Einzeleintrag nicht.
- Weitere gültige Gruppierungswerte laut `clocodo-api.yaml`, bisher unbenutzt:
  `billable`, `services_id`, `subprojects_id`, `lumpsum_services_id`, `texts_id`.
- **Serverseitige Filter gibt es auch**, ebenfalls bisher unbenutzt: `filter[projects_id]`,
  `filter[users_id]`, `filter[customers_id]`, `filter[billable]` und `filter[budget_type]`
  als `deepObject`. Dazu `prepend_customer_to_project_name` (daher das „Kunde / Projekt"
  in `name`), `round_to_minutes` und
  `calc_also_revenues_for_projects_with_hard_budget`.
- Laut Doku sind **`time_since` und `time_until` beide Pflicht**, nicht nur `time_since`.

### Sollarbeitszeit
Die Werte stehen im **unversionierten** `/targethours` (`/v2` und `/v3` geben 404):

```
{"targethours": [{"id": 1, "users_id": 301, "type": "weekly",
                  "date_since": "2023-06-14", "date_until": null,
                  "monday": 7, …, "sunday": 0}]}
```

Die Doku ergänzt vier Dinge dazu:

- **`type` kennt genau zwei Werte**, `weekly` und `monthly`, mit je eigenem Schema. Eine
  monatliche Zeile führt `monthly_target` statt der Wochentage – die Wochentagsfelder
  fehlen dort. In dieser Anlage sind alle Zeilen `weekly`; tritt `monthly` auf, ist
  es kein unbekannter Fall mehr, sondern ein zu bauender.
- **Die Stunden sind `number`, nicht `integer`** – halbe Stunden (8.5) sind vorgesehen.
- **`users.default_target_hours` heißt „Uses the company's default target hours".** Der
  Schalter ist damit nicht nur kein Stundenwert, er hat eine Folge: wer ihn gesetzt hat,
  hat **keine eigene Zeile** in `/targethours`, und `Mitarbeiter.wochenstunden()` liefert
  `None`. Heute geht das auf – je aktiver Person genau eine offene Zeile –, aber es ist eine
  stille Lücke, sobald jemand auf den Firmenstandard umgestellt wird.
- `/targethours` nimmt einen `users_id`-Filter (Array, Zahl oder CSV), bisher unbenutzt.

Für die geplanten Abwesenheiten ist `/v4/absences` der richtige Endpunkt –
`/absences`, `/v2/absences` und `/v3/absences` antworten mit 410 `deprecated`. Der
Jahresfilter ist ein `deepObject`-Parameter (`filter[year]`, nicht `year` direkt),
analog zu `grouping[]` bei `/v2/entrygroups`; die Antwort hat kein `paging`, Envelope-Key
ist `data`. `ClockodoClient.absences(year)` und `MitarbeiterRepository.laden_async(jahre=…)`
holen sie ungefiltert nach Status und Typ – Envelope und Feldnamen stehen fest, aber nicht
jede Abwesenheit soll in den Kapazitätsdeckel eingehen. `Mitarbeiter.abwesenheiten` führt
sie deshalb roh, mit Clockodos `type`- und `status`-Codes.

**`type` als Abwesenheit vom Arbeiten: nur
Urlaub und Krankheit.** `Abwesenheit.gilt_als_abwesend` prüft das gegen
`domaene.mitarbeiter.TYPEN_ABWESEND` – `TYP_URLAUB` (1, `RegularHoliday`, das
Kontingent, nicht `SpecialLeave`/Sonderurlaub) und `TYPEN_KRANKHEIT` (4 `SickSelf`,
5 `SickChild`, 11 `SickSelfUnpaid`, 12 `SickChildUnpaid`, 15
`SickSelfWithCertificate` – alle fünf Krankheitsvarianten, bezahlt wie unbezahlt,
eigene wie die des Kindes). Alle anderen Typen zählen ausdrücklich **nicht**, auch dort,
wo das fachlich diskutabel ist – etwa `Quarantine` (13, „work not possible“) oder
`MaternityProtection` (7). `Home office` (8) und `Work out of office` (9) fielen ohnehin
schon vorher heraus: sie tragen laut Doku die geplanten Stunden („planned hours get
applied“), sind also keine Abwesenheit vom Arbeiten.

**`status`: eine Abwesenheit zählt schon ab
„beantragt", nicht erst ab „genehmigt".** `Enquired` und `Approved` (`STATUS_GEPLANT`)
zählen beide, `Declined`, `ApprovalCancelled` und `Cancelled` nicht – das sind keine
reale Abwesenheit (mehr). `Abwesenheit.zaehlt_als_kapazitaetsabzug` kombiniert Typ und
Status; `Abwesenheit.genehmigt` (nur `Approved`) bleibt separat verfügbar, geht aber
nicht mehr in den Kapazitätsdeckel ein.