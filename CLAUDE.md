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
uv run pytest tests/test_projekt.py::test_restvolumen_ist_budget_minus_verbrauch  # ein Test
uv run ruff check .            # Lint
uv run ruff format .           # Formatierung
uv run jupyter lab             # Notebooks lokal
```

## Aufbau und wo was hingehört

Das Paket bildet den **Gegenstand** ab, nicht den Rechenweg: Kunde, Projekt,
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
  `Umsatzhistorie`), `bestand.py` (das Aggregat), `prognose.py` (ABC plus
  `NochKeinePrognose`), `hinweis.py`, `zahlen.py` (deutsche Zahlformate ohne `locale`).
- `src/umsatzprognose/clockodo/` – **alles, was Clockodo weiß, weiß nur dieses Paket.**
  `config.py` (Zugangsdaten mit den benannten Konstruktoren `automatisch`,
  `aus_umgebung`, `aus_colab_secrets`), `client.py` (`ClockodoClient`: HTTP,
  Paginierung, die verifizierte Parameterform je Endpunkt, `ClockodoError` mit
  Antwortkörper), dazu je Endpunkt ein Repository: `kunden.py`, `mitarbeiter.py`,
  `projekte.py`, `umsatz.py` und `bestand.py` (`BestandRepository`, der eine Einstieg).
- `src/umsatzprognose/darstellung/` – der einzige Ort mit plotly (`diagramme.py`,
  `gestaltung.py`) und pandas (`tabellen.py`), dazu `dashboard.py` mit der Fassade
  `Dashboard`, die die Notebooks benutzen.
- `tests/` – pytest. Die Antwortausschnitte in `conftest.py` sind gekürzte, aber echte
  Antworten samt ihrer Fallen.
- `notebooks/` – zwei Notebooks mit verschiedenen Zielgruppen, siehe unten.
- `spec/` – Spezifikation, maßgeblich für alle Modellfragen.

**Die Domäne kennt kein JSON und keinen HTTP-Client.** Das ist die tragende Regel: das
teuer erarbeitete Wissen über Clockodos Eigenheiten steht in `clockodo/`, je Endpunkt
dort, wo seine Abbildung liegt. Sickert es in die Fachobjekte, ist beides nicht mehr
getrennt prüfbar.

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
  (`ENTSCHEIDEN`-Abschnitte). Ersetzt das frühere `01_restvolumen.ipynb`.

Rechenlogik gehört ins Paket, nicht ins Notebook.

Diese Zelle installiert mit **`--force-reinstall`**, und das ist kein Ritual: die
Versionsnummer bleibt über Commits hinweg 0.1.0, weshalb `pip install git+…@main` einen
bereits installierten Stand stehen lässt – ohne Fehlermeldung, aber auch ohne Wirkung.
`--upgrade` hilft nicht. Am 24.08.2026 in frischen venvs nachgestellt: nach `@5b672de`
und anschließendem `@main` fehlten die neuen Module weiterhin, in Colab endete das in
`ModuleNotFoundError: No module named 'umsatzprognose.api'`. Wirksam sind
`--force-reinstall`, `uninstall` + `install` oder ein **Versionssprung** – letzterer ist
ebenfalls belegt, taugt aber nicht als Verlass, weil ein vergessener Sprung lautlos
scheitert und Colab dann alte Rechenlogik ausführt.

Der Reinstall läuft mit **`--no-deps`**, und davor ein gewöhnliches `pip install` für
die Abhängigkeiten. Ohne `--no-deps` zieht `--force-reinstall` pandas und numpy neu und
bricht Colabs Pins (`google-colab` verlangt `pandas==2.2.3`, `numba` `numpy<2.3`; am
24.08.2026 real gesehen mit pandas 3.0.5 und numpy 2.5.2). Aus demselben Grund steht
**numpy nicht in den Abhängigkeiten**, obwohl die Simulation es später braucht: ein
unbenutzter Pin, der in Colab eine Aktualisierung erzwingt, ist reiner Schaden. **plotly
ist mit `>=5` ohne Obergrenze eingetragen** – Colab bringt es mit, die Anforderung ist
damit erfüllt und der erste `pip install` lässt die vorhandene Version stehen.

Ein Runtime-Neustart allein genügt nicht, ist nach einem Push aber zusätzlich nötig:
Python liefert für bereits geladene Module das Objekt aus `sys.modules`, auch wenn die
Datei auf der Platte ersetzt wurde. Das erzeugt einen gemischten Zustand – neue Module
werden frisch geladen, alte bleiben alt – und endet als `ImportError: cannot import
name …` auf eine Funktion, die in der installierten Datei durchaus steht.

**Die Installationszelle erneuert das Paket, nie das Notebook.** Die `.ipynb` liegt in
der Colab-Sitzung (oder als Kopie in Drive); `pip install git+…@main` fasst sie nicht
an, ein Runtime-Neustart auch nicht. Nach einer Notebook-Änderung im Repository muss
das Notebook selbst neu geladen werden: *File → Open notebook → GitHub*. Der Fehler ist
tückisch, weil nichts abbricht – neues Paket plus alte Zelle läuft durch und liefert
still ein altes Ergebnis. Am 24.08.2026 genau so aufgetreten: die Tabelle hatte die
neuen Spalten `kunde` und `projekt`, aber die alte Zelle übergab keine Bezeichnungen,
also standen dort durchgehend `None`. Deshalb endet die Installationszelle mit einem
Print, der ihren Stand nennt – fehlt diese Ausgabe, ist nicht das Paket alt, sondern
das Notebook.

**Die Paket-API wurde beim Umbau gebrochen.** Die früheren Module `api.py`, `config.py`,
`auftragsvolumen.py`, `verbrauchtes_volumen.py`, `restvolumen.py`, `stammdaten.py` und
`tabellen.py` gibt es nicht mehr; ihre Funktionen sind Methoden der Fachobjekte
geworden. Ein altes Notebook gegen den neuen Stand scheitert mit `ImportError` – das
ist hier der freundliche Fall, weil er auffällt.

## Stand der Implementierung

Umgesetzt ist Schritt 1 aus Spec Abschnitt 10: Restvolumen je Projekt (5.1), dazu das
vollständige Domänenmodell außer der Simulation – inklusive Aufteilungsschlüssel je
Person (5.4 Schritt 3) und Sollarbeitszeit (Teil von 5.3).

Beide Notebooks laufen am 24.08.2026 gegen die echte Installation durch: 895 Projekte,
davon 122 aktiv und 44 im Prognose-Scope, 59 Personen (26 aktiv, zusammen 801
Wochenstunden), rund **729.000 EUR** prognosewirksames Restvolumen bei 2,38 Mio. EUR
Auftragsvolumen, Umsatz der zwölf abgeschlossenen Monate 09/2025–08/2026 rund
**3,48 Mio. EUR**. Die Zahlen bewegen sich mit jeder Zeitbuchung – sie taugen als
Größenordnung, nicht als Regressionswert. Ein vollständiger Ladevorgang dauert rund
15 Sekunden.

Es fehlen: die Monte-Carlo-Simulation (5.4), die Abrufquote-Verteilungen (5.2), die
Referenzklassen (6), die verfügbare Kapazität (5.3, es fehlen Abwesenheiten und der
Abschlag für ungeplante Abwesenheit) und die Normalisierung von Pauschalleistungen
(5.1). `Bestand.simulieren()` liefert deshalb `NochKeinePrognose` mit Begründung, und
das Dashboard zeigt an der Stelle der Bandbreite genau diese Begründung an – eine
erfundene Kurve wäre der schlechtere Platzhalter.

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
   Schlüssel ist der **historische Anteil je Person am jeweiligen Projekt** (Anteil an
   den Gesamtstunden), unverändert in die Zukunft fortgeschrieben. Er liegt als
   `Projekt.anteil_je_mitarbeiter()` vor und stammt aus der Doppelgruppierung von
   `/v2/entrygroups`, nicht aus den Einzeleinträgen.
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
| Verbrauch, effektiver Satz | `GET /v2/entrygroups`, `grouping[]=projects_id` | `revenue`, `duration` (nicht `hourly_rate`, siehe unten) |
| Anteil je Person | `GET /v2/entrygroups`, zusätzlich `grouping[]=users_id` | `sub_groups` mit `duration`, `revenue` |
| Umsatz je Monat | `GET /v2/entrygroups`, `grouping[]=month` | `group` (`"JJJJMM"`), `revenue`, `duration` |
| Kundenname (Beschriftung) | `GET /v3/customers` | `id`, `name` |
| Personen | `GET /v3/users` | `id`, `name`, `active` – **nicht** `default_target_hours` |
| Sollarbeitszeit | `GET /targethours` (unversioniert) | `users_id`, `date_since`/`date_until`, Stunden je Wochentag |
| Geplante Abwesenheit | `GET /v4/absences?year=…` | noch nicht ausgewertet (Spec 5.3) |
| Einzeleinträge | `GET /v2/entries` | **wird nicht benutzt**, siehe unten |

`budget.hard` ist in dieser Installation `false` – Budgets sind also weiche Grenzen und
sind kein technisches Limit: der Verbrauch kann sie übersteigen, das rohe Restvolumen
wird dann negativ. Das ist ein Kalibrierungssignal und kein Fehler.

Für die Prognose gilt trotzdem eine harte Grenze (Spec 5.1, seit v0.5): **eine
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

**Verifiziert am 24.08.2026 an einer echten Antwort** – `/v4/projects` liefert

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

### Gruppierungen von `/v2/entrygroups` (verifiziert am 24.08.2026)

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

**`/v2/entries` wird bewusst nicht benutzt.** Der Endpunkt antwortet mit
`{"paging": …, "filter": …, "entries": [...]}`; `count_items` steht bei **16.461** für
die letzten zwölf Monate, `items_per_page` bei 2500 – sieben Abrufe je Jahr Historie,
um daraus dieselbe Summe zu bilden, die der Server schon gebildet hat. Erst wenn eine
Auswertung wirklich den einzelnen Eintrag braucht (etwa `type` zur Trennung von
Pauschalleistungen), lohnt er sich.

### Sollarbeitszeit: die Spec liegt falsch (verifiziert am 24.08.2026)

Spec Abschnitt 4 nennt `default_target_hours` aus `/v3/users` als Sollarbeitszeit.
**Das Feld ist ein Boolean-Schalter**, keine Stundenzahl: 56 mal `false`, 3 mal `true`
über alle 59 Personen, ohne Zusammenhang zu `active`. Wer es als Stunden liest, bekommt
0 oder 1 und einen still falschen Kapazitätsdeckel.

Die echten Werte stehen im **unversionierten** `/targethours` (`/v2` und `/v3` geben 404):

```
{"targethours": [{"id": 336993, "users_id": 143323, "type": "weekly",
                  "date_since": "2023-06-14", "date_until": null,
                  "monday": 7, …, "sunday": 0}]}
```

186 Einträge, alle mit `type: "weekly"`; 160 sind mit `date_until` abgeschlossen, die 26
offenen entsprechen genau den 26 aktiven Personen – je einer, mit 20 bis 35
Wochenstunden. Ein anderer `type` ist nie aufgetreten und wird deshalb nicht gedeutet,
sondern übersprungen und gemeldet.

Für die geplanten Abwesenheiten (5.3) ist `/v4/absences?year=…` der richtige Endpunkt:
`/absences`, `/v2/absences` und `/v3/absences` antworten mit 410 `deprecated`.

**Kundennamen nur über `/v3/customers`** (geprüft am 24.08.2026): `/v4/customers`
antwortet mit 404 `RouteNotFound`, `/v2/customers` mit 410 `deprecated`. Die Antwortform
gleicht `/v4/projects` – `{"paging": {...}, "data": [{"id": …, "name": …, …}]}`, bei 324
Kunden auf einer Seite. `/v4/projects` selbst führt nur `customers_id`, keinen
Kundennamen. Alle 895 Projekte tragen einen `name` und eine auflösbare `customers_id`;
`clockodo/projekte.py` lässt eine Lücke trotzdem als `None` durch, statt einen Abruf mit
einem `KeyError` zu beenden – eine fehlende Beschriftung darf keine Zahl kosten. Für
Personen gilt dasselbe: eine `users_id` ohne Stammdatensatz bekommt ein
Platzhalterobjekt, ihre Stunden gehen nicht verloren.

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
Fälle auf, keiner ist also durchgerechnet. `Budget.verwertbar` ist deshalb bei ihnen
`false`, und `Budget.sonderfall` nennt den Grund, der als Hinweis bis ins Dashboard
durchschlägt: eine sichtbare Untererfassung ist besser als eine still falsche Euro-Zahl. Von den 3 Projekten mit `hard: true` ist
ebenfalls keines aktiv.

**Offene fachliche Abgrenzungen** (Zahlen vom 24.08.2026):

- Von 895 Projekten sind **122 aktiv**; nur sie gehen in die Prognose ein
  (`Projekt.im_prognose_scope`). Die Spec deckt diese Abgrenzung nicht ab.
- **78 dieser 122 aktiven Projekte haben kein Budget** und fallen damit aus der Prognose;
  es bleiben 44 mit zusammen 2,38 Mio. EUR Budget und rund 729.000 EUR
  prognosewirksamem Restvolumen. Die Namen der 78 sind überwiegend Schulungs- und Ausbildungsprodukte
  (`A-CSM`, `A-CSPO`, `ACC`) beim Kunden **„Öffentliche Schulung“** – der Kundenname ist
  seit der Beschriftung sichtbar und stützt die Deutung als Katalogposition ohne
  beauftragtes Volumen. Das rechnet die Spec dem Kurzfristgeschäft zu und schließt es aus dem MVP aus. Ob darunter
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

Laut Spec Abschnitt 10: Abrufquoten-Verteilungen je Referenzklasse aus der
`entrygroups`-Historie schätzen, Rückwärtstest über 12 Stichtage. Beides setzt voraus,
dass die Definition der Referenzklassen und die Form der Verteilung geklärt sind – sie
stehen in Spec v0.3, die nicht vorliegt. Vorher also nachfragen, nicht schätzen.
