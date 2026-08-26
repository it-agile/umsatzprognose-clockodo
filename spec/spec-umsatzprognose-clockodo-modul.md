# Spec: Umsatzprognose – Baustein Bestand (Clockodo)
--

## 1. Ziel

Eine rollierende 1–3-Monats-Prognose des Umsatzes aus laufenden, in Clockodo
angelegten Projekten – mit Bandbreite statt Punktwert.

Ist ein Projekt in Clockodo angelegt, gilt es als beauftragt. Storno auf Projekteben 
ist damit kein Thema. Die zentrale Unsicherheit: **Wie viel vom beauftragten Volumen
wird im Prognosezeitraum tatsächlich abgerufen?**

## 2. Nicht-Ziele im MVP

- Keine Pipeline-Betrachtung, kein Kurzfristgeschäft, keine Cash-Schicht
  (Rechnungsstellung und Zahlungseingang sind ein eigenes Thema; die Felder
  `billed_money` und `billed_completely` an `/v4/projects` grenzen daran an).
- Keine Prognose für Projekte, die noch nicht in Clockodo angelegt sind.

## 3. Begriffe

- **Projekt:** Clockodo-Objekt `project` mit einem Budget und einem aus den
  Zeiteinträgen ableitbaren effektiven Stundensatz. Das Budget ist in der Regel ein
  Euro-Gesamtbudget, aber nicht immer – siehe 5.0.
- **Auftragsvolumen:** `budget.amount` aus `/v4/projects`, sofern es als
  Euro-Gesamtbudget lesbar ist (5.0).
- **Verbrauchtes Volumen:** kumulierte `revenue` aus `/v2/entrygroups`, gruppiert nach
  Projekt. Diese Kennzahl wendet Clockodos eigene Ratenlogik an und schließt
  Pauschalleistungen ein; eine Rekonstruktion aus Einzeleinträgen ist nicht nötig.
- **Rohes Restvolumen:** Auftragsvolumen minus verbrauchtes Volumen, vorzeichenbehaftet.
- **Prognosewirksames Restvolumen:** `max(0, rohes Restvolumen)`.
- **Abrufquote:** Anteil des zu Monatsbeginn verbleibenden Restvolumens, der im Monat
  tatsächlich verbraucht wird. Zentrale Zielgröße der Schätzung.
- **Effektiver Stundensatz je Projekt:** erzielter Umsatz je geleisteter Stunde,
  abgeleitet als `revenue / (duration / 3600)` aus `/v2/entrygroups`. **Nicht** das Feld
  `hourly_rate` – Begründung in Abschnitt 4.
- **Verfügbare Kapazität:** Netto-Arbeitsstunden je Person und Monat, aus der
  Sollarbeitszeit abzüglich geplanter und eines geschätzten Anteils ungeplanter
  Abwesenheit (5.3).
- **Konfidenzniveau:** Anteil der Simulationsläufe, die mindestens den ausgewiesenen
  Wert erreichen.

## 4. Datenmodell aus Clockodo

**Zur Herkunft dieser Tabelle.** Alle Angaben unten sind gegen die Installation
geprüft. Seit dem 26.08.2026 liegt zusätzlich die OpenAPI-Beschreibung im Repository
(`spec/clocodo-api.yaml`, Fassung 2026-08-24). Beide Quellen widersprechen sich an
einigen Stellen; dann gilt die echte Antwort. Die Doku deklariert `EntryGroupV2.group`
als String (kommt bei `group == 0` und `grouping[]=year` als Zahl) und
`EntryGroupV2.revenue` als Integer (ist ein Float).

**`/api/entrygroups` ist auf 10 GET je Minute begrenzt**, ein endpunkteigenes Limit
zusätzlich zum globalen (900/min, 20.000/Tag); darüber antwortet die API mit 429. Ein
Ladevorgang verbraucht drei davon. Der Rückwärtstest aus 11.4 über 12 Stichtage wären 36
Abrufe und braucht damit eine Drosselung.
| Zweck | Endpunkt | Relevante Felder |
|---|---|---|
| Auftragsvolumen | `GET /v4/projects` | `budget` (`amount`, `hard`, `monetary`, `interval`, `from_subprojects`), `active`, `completed`, `customers_id`, `name` |
| Verbrauchtes Volumen, effektiver Satz | `GET /v2/entrygroups`, `grouping[]=projects_id` | `revenue`, `duration` (Sekunden) |
| Anteil je Person am Projekt | dieselbe Abfrage, zusätzlich `grouping[]=users_id` | `sub_groups` mit `group`, `duration`, `revenue` |
| Umsatz je Monat | `GET /v2/entrygroups`, `grouping[]=month` | `group` (`"JJJJMM"`), `revenue`, `duration` |
| Kundenname | `GET /v3/customers` | `id`, `name` |
| Personen | `GET /v3/users` | `id`, `name`, `active`, `nonbusinessgroups_id` |
| Sollarbeitszeit je Person | `GET /targethours` (unversioniert) | `users_id`, `type`, `date_since`, `date_until`, Stunden je Wochentag |
| Geplante Abwesenheit | `GET /v4/absences?year=…` | Zeitraum, Art, Person |
| Feiertage je Feiertagsgruppe | `GET /nonbusinessdays?year=…` (unversioniert) | `nonbusinessgroups_id`, `date`, `name`, `half_day` |

Basis-URL ist `https://my.clockodo.com/api`. Authentifizierung über drei Pflicht-Header:
`X-ClockodoApiUser` (E-Mail), `X-ClockodoApiKey` und
`X-Clockodo-External-Application` im Format `name;email` mit **maximal 50 Zeichen
Gesamtlänge**.

- **`entrygroups.hourly_rate` ist als effektiver Stundensatz unbrauchbar.** Es ist nur
  gesetzt, wenn `hourly_rate_is_equal_and_has_no_lumpsums` `true` ist – nur bei einer
  Minderheit der Gruppen, und dort meist `0`. Sonst ist es `null`. Auch wo beides
  vorliegt, weicht `revenue / (duration/3600)` davon ab, weil nicht jede erfasste
  Stunde abgerechnet wird. Der effektive Satz wird deshalb abgeleitet.
- **`users.default_target_hours` ist ein Boolean-Schalter, keine Stundenzahl.** Beide
  Werte kommen über alle Personen vor, ohne Zusammenhang zu `active`. Wer es als
  Stunden liest, bekommt 0 oder 1 und einen still falschen Kapazitätsdeckel. Die echten
  Werte stehen im unversionierten `/targethours` (`/v2` und `/v3` davon geben 404):
  je Person mehrere Einträge, alle mit `type: "weekly"`, davon je aktiver Person genau
  einer offen. Ein anderer `type` ist nie aufgetreten; träte er auf, wird er nicht
  gedeutet, sondern gemeldet.
- **Abwesenheiten liegen auf `/v4/absences`.** Die Legacy-Pfade `/absences`,
  `/v2/absences` und `/v3/absences` antworten mit 410 `deprecated`.
- **Feiertage gibt es in zwei Generationen**, und beide funktionieren. Die frühere
  Notiz, `/v2` bis `/v4` gäben 404 und die Feiertagsgruppen seien nicht abrufbar, war ein
  **Schreibweisenfehler**: `/v2/nonbusinessDays` und `/v2/nonbusinessGroups` antworten mit
  200, die kleingeschriebenen Varianten mit 404 bzw. 410 (korrigiert am 26.08.2026).
  Dieselben Feiertage, verschiedene Felder – wer sie verwechselt, liest `null`:

  | | `/nonbusinessdays` (unversioniert) | `/v2/nonbusinessDays` |
  |---|---|---|
  | Envelope | `nonbusinessdays` | `data` |
  | Gruppe | `nonbusinessgroups_id` | `nonbusiness_group_id` |
  | Datum | `date` | `evaluated_date` |
  | Halber Tag | `half_day: 0` / `1` | `half_day: false` / `true` |
  | `year` | Pflicht (400 ohne) | optional |

  Beide ohne `paging`; die unversionierte Fassung liefert alle Einträge über alle
  Feiertagsgruppen der Anlage auf einmal. Die beweglichen Feste sind serverseitig
  gerechnet und nicht kopiert (Karfreitag 2025-04-18, 2026-04-03, 2027-03-26). Der
  Gruppenfilter wirkt in beiden Fassungen als echter Filter – anders als bei
  `/v4/projects`, wo unbekannte Parameter still ignoriert werden.
- **Die Feiertagsgruppen sind abrufbar**: `/v2/nonbusinessGroups` liefert je Gruppe `id`,
  `name` und `company_default`. Die Namen benennen die Bundesländer-Kombination der
  Gruppe und sind damit zur Beschriftung brauchbar.
- **Zwei Endpunkte sind für 5.3 die kürzere Strecke**, beide mit Paginierung (50 je
  Seite): `/v2/usersNonbusinessDays?year=…` liefert die Feiertage **je Person** fertig
  zugeordnet (`{"users_id": …, "days": [...]}`), `/v3/usersNonbusinessGroups` die
  Zuordnung Person → Gruppe **mit Gültigkeitszeitraum** (`date_since`, `date_until`; es
  gibt mehr Einträge als Personen, eine Zuordnung hat also schon gewechselt).
  `users.nonbusinessgroups_id` kennt nur den heutigen Stand und ist für einen vergangenen
  Stichtag der falsche Wert.
- **Was die Doku zu `half_day` nicht sagt: was es bewirkt.** Sie deklariert ein Boolean,
  nicht seine Wirkung auf die Sollstunden. Die Deutung in 5.3 bleibt damit eine Annahme;
  belegt ist nur, dass es ein Schalter ist und keine Stundenzahl.
- **`/v2/entries` wird nicht benutzt.** Bei `items_per_page` von 2500 sind schon zwölf
  Monate mehrere Seiten Einzeleinträge, um dieselbe Summe zu bilden, die
  `/v2/entrygroups` schon gebildet hat. Die Doppelgruppierung nach Projekt und Person
  liefert die Aufteilung fertig aggregiert; ihre Projektsummen sind mit denen der
  einfachen Gruppierung über alle Gruppen identisch. Der einzige Grund, der bisher
  für den Endpunkt sprach – `type` zur Trennung von Pauschalleistungen –, ist mit dem
  Gruppierungswert **`is_lumpsum`** entfallen.
- **`grouping` kennt mehr Werte als benutzt**: neben `projects_id`, `users_id`,
  `customers_id`, `month`, `year`, `week`, `day` auch `is_lumpsum`, `billable`,
  `services_id`, `subprojects_id`, `lumpsum_services_id` und `texts_id`. Dazu gibt es
  serverseitige Filter (`filter[projects_id]`, `filter[users_id]`, `filter[customers_id]`,
  `filter[billable]`, `filter[budget_type]`) und `prepend_customer_to_project_name` –
  letzteres erklärt das „Kunde / Projekt" im Feld `name`. Laut Doku sind `time_since` und
  `time_until` **beide** Pflicht.

Weiter zu beachten, ebenfalls verifiziert:

- `/v2/entrygroups` verlangt `grouping` als **Array-Parameter** (`grouping[]=…`),
  Gruppierungswerte mit `_id`-Suffix bei Objekten (`projects_id`), ohne Suffix und im
  Singular bei Zeiträumen (`month`, `year`, `week`, `day`). Zeitgrenzen brauchen die
  volle ISO-Form mit Uhrzeit. Ein falscher Parameter führt zu 400 mit
  `{"error": {"message": …, "fields": [...]}}` – **Fehler am Antwortkörper diagnostizieren,
  nicht am Status.**
- Bei `/v4/projects` ist es umgekehrt: **unbekannte Query-Parameter werden still
  ignoriert.** Ein 200 belegt einen Parameternamen nicht; dafür ist das `paging`-Objekt
  der Antwort zu prüfen.
- In der Projektgruppierung kommt die Projekt-ID als **String**, und `group == 0` (dort
  als Zahl) steht für Buchungen auf einen Kunden ohne Projekt. Ohne Filter entsteht
  daraus ein Phantom-Projekt.
- `revenue_factor` ist bei allen aktiven Projekten 1, `test_data` überall `false`, und
  kein aktives Projekt hat Teilprojekte. Diese Felder brauchen keine Sonderbehandlung,
  solange das so bleibt. Die Doku nennt die Regel dahinter: `revenue_factor` ist `1` bei
  weichem oder fehlendem Budget, `null` bei einem harten Budget vor Projektende, und
  darunter, wenn ein hartes Budget überzogen wurde (bei 400 % Nutzung `0.25`). Weil
  `budget.hard` hier überall `false` ist, bleibt er 1 – bei einem harten Budget müsste er
  in Umsatz und Stundensatz eingerechnet werden.
- **`deadline` und `automatic_completion` sind ab Projekt-Ebene abgebildet** (Entscheidung
  26.08.2026): ein Projekt mit `automatic_completion: true` und gesetzter `deadline`
  trägt ab diesem Datum keinen Umsatz mehr bei – die Simulation (5.4) muss das je
  Horizontmonat berücksichtigen, sobald sie gebaut wird. `automatic_completion` ist bei
  fast allen aktiven Projekten `true`, eine `deadline` haben nur wenige – mindestens
  eine davon liegt **innerhalb des heutigen Horizonts**. Eine `deadline` **ohne**
  `automatic_completion` ist unverbindlich und bleibt ohne Wirkung, weil Abschnitt 7 nur
  `active`, `completed` und `completed_at` als zuverlässiges Endesignal führt.
  `start_date` bleibt unbenutzt: nur bei einer Handvoll Projekte gesetzt und damit
  ungeeignet, den Beginn des Beobachtungsfensters aus 5.2 zu bestimmen.
- **`budget.interval` ist ein Integer-Enum** (0 wochenweise, 1 monatlich, 2 quartalsweise,
  3 jährlich), kein String. Die 0 ist gültig und falsy – eine Prüfung auf den
  Wahrheitswert würde ein Wochenbudget still als Gesamtbudget lesen. In dieser
  Installation ist `interval` bei jedem Projekt mit Budget `null`.
- **Historientiefe:** `revenue` deckt die ganze Historie ab, sobald die untere
  Zeitgrenze weit genug liegt – `time_since=2010-01-01` liefert dieselben Gruppen
  und dieselbe Summe wie `2020-01-01`. Die Antwort hat kein `paging`.

## 5. Modell

### 5.0 Prognose-Scope

Welche Projekte in die Prognose eingehen, es gilt:

Ein Projekt ist **im Prognose-Scope**, wenn es `active` ist, **nicht** `completed`
trägt und sein Budget als Euro-Gesamtbudget lesbar ist.

**`completed` schließt aus, auch wenn `active` zugleich gesetzt ist.** Abschnitt 7 hält `completed` für ein zuverlässiges
Endesignal, während `active` auch ein nicht nachgezogener Schalter sein kann. Das offene
Restvolumen eines beendeten Projekts wird nicht mehr abgerufen; es prognostisch
mitzunehmen hieße, Umsatz zu erwarten, den niemand mehr leistet. Die betroffenen
Projekte werden als Hinweis ausgewiesen.

`budget.amount` ist nicht immer ein Euro-Gesamtbudget. Drei Felder entscheiden darüber,
und ist eines davon gesetzt, gilt das Budget als **nicht verwertbar**:

- `monetary: false` – der Betrag ist eine **Stundenzahl** (8 Projekte, alle inaktiv, mit
  Werten wie 6, 12, 48). Als Euro gelesen wäre das ein stiller Faktor-Fehler.
- `interval` gesetzt – Budget je Intervall statt Gesamtbudget; die Formel aus 5.1 gilt
  dann nicht.
- `from_subprojects: true` – das Budget stammt aus Teilprojekten
  (`subprojects_budget_total`).

Bei den aktiven Projekten trat keiner der drei Fälle auf, keiner ist also an echten
Zahlen durchgerechnet. Statt eine plausible Umrechnung zu erfinden, fällt ein solches
Projekt aus dem Scope, und der Grund wird als Hinweis bis in die Darstellung geführt.
**Eine sichtbare Untererfassung ist besser als eine still falsche Euro-Zahl.** Dasselbe
gilt Projekte, deren `budget` `null` ist.

### 5.1 Restvolumen je Projekt (in Euro)

```
rohes Restvolumen(Projekt)          = budget.amount − revenue_kumuliert(Projekt)
prognosewirksames Restvolumen       = max(0, rohes Restvolumen)
```

`revenue_kumuliert` kommt aus `/v2/entrygroups` mit `grouping[]=projects_id` über die
gesamte Historie. Ein Abruf deckt alle Projekte ab.

**Das Zeitfenster endet am Stichtag.** Verbrauch ist streng Vergangenheit. Eine Buchung,
die später datiert ist, ist zwar erfasst, gehört aber in den Prognosehorizont: sie wird
dort angerechnet (5.4), statt vorab vom Restvolumen abgezogen zu werden.


**Beide Grenzen müssen zur Laufzeit bestimmt werden, nicht beim Programmstart.** Eine
feste obere Grenze im Code schneidet nach ihrem Ablauf stumm Buchungen ab: die Zahlen
sinken, ohne dass etwas abbricht. Dasselbe gilt für einen Wert, der beim Import einmal
berechnet wird.

Weil das Fenster am Stichtag endet, ist ein Bestand zu einem **vergangenen** Stichtag
konsistent rechenbar: er kennt nur Buchungen, die es damals gab. Das ist die
Voraussetzung für den Rückwärtstest aus 11.4.

**Budgetüberschreitungen.** `budget.hard` ist in dieser Installation `false`, wo es
zählt: Budgets sind weiche Grenzen, der Verbrauch kann sie übersteigen. Eine
Überschreitung kann damit nur **historisch** entstehen. **Die Prognose überschreitet das
Budget eines Projekts nicht.** Ein Projekt mit historisch überschrittenem Budget startet
bei 0 und trägt über den gesamten Horizont keinen Umsatz.

Das rohe Restvolumen wird trotzdem geführt und nicht verworfen: Häufigkeit und Höhe von
Überschreitungen sind ein Kalibrierungssignal (Abschnitt 7) und kein Fehler.

Ein Enddatum je Projekt wird nicht verwendet; ein auslaufendes Projekt erkennt das
Modell am sinkenden Restvolumen. Ein **beendetes** Projekt erkennt es dagegen an
`completed` (5.0); `completed_at` bleibt ungenutzt, weil der Scope nur die Gegenwart
braucht.

**Pauschalleistungen.**
- Der effektive Stundensatz eines Projekts ist `revenue / (duration/3600)` über seine
  gesamte Historie. Pauschalleistungen mit gebuchter Zeit sind darin normalisiert
  enthalten, ohne eigenen Modellzweig.
- **Diese Normalisierung ist am 26.08.2026 gemessen worden** (`grouping[]=is_lumpsum`):
  Pauschalen machen einen erheblichen Teil des Gesamtumsatzes aus, und Pauschaleinträge
  tragen **grundsätzlich keine Dauer** – null Stunden über alle. Auch im Prognose-Scope
  betreffen sie die Mehrzahl der Projekte, viele davon vollständig. Die Annahme hält
  trotzdem: die Arbeit hinter einer Pauschale wird als Zeit **ohne** Umsatz gebucht, und
  die abgeleiteten Sätze im Scope bleiben in einer plausiblen Größenordnung für
  Beratungsleistung, ohne Ausreißer nach oben. Wäre die Arbeit gar nicht erfasst,
  müssten hier Sätze in Tausenderhöhe stehen.
- **Umsatz ohne jede erfasste Zeit** (`duration == 0`) liefert keinen Satz. Solche
  Projekte gehen mit ihrem Restvolumen in die Simulation ein, verbrauchen aber
  **keine Kapazität**
- **Ein Stundensatz von genau 0 ist derselbe Fall wie kein Satz.** Es gibt Projekte im
  Scope mit gebuchter Zeit und noch keinem Umsatz; ihr abgeleiteter Satz ist `0.0`. In
  Schritt 3 von 5.4 wäre das eine Division durch Null, sie dürfen also keinen
  Stundenbedarf erzeugen. Der Hinweis aus 5.5 nennt bisher nur die Projekte ohne
  erfasste Zeit, nicht diesen Fall.

### 5.2 Abrufquote-Verteilung

Die Abrufquote wird als **empirische Verteilung** aus der eigenen Historie geschätzt.

- **Beobachtungseinheit** ist ein Projekt-Monat.
- **Quote** = Verbrauch im Monat geteilt durch das Restvolumen zu Monatsbeginn.
- **Datenquelle** ist `/v2/entrygroups` mit `grouping[]=projects_id&grouping[]=month`.
- **Einbezogen** werden Projekt-Monate mit einem Restvolumen > 0 zu Monatsbeginn; sonst
  ist die Quote undefiniert.
- **Welche Monate zum Beobachtungsfenster gehören** (entschieden am 26.08.2026, weil die
  API Monate ohne Buchung gar nicht liefert und die Frage damit nicht offen bleiben
  kann): je Projekt von seinem **ersten Monat mit Buchung** bis zum **Vormonat des
  Stichtags**, wenn das Projekt im Prognose-Scope ist (5.0) – sonst bis zu seinem
  **letzten Monat mit Buchung**. Lücken innerhalb dieses Fensters zählen als Quote 0: ein
  laufendes Projekt, das einen Monat nichts abruft, ist eine Beobachtung und kein
  fehlender Datensatz. Der Stichtagsmonat selbst bleibt außen vor, weil er angebrochen
  ist (5.4) und seine Quote damit systematisch zu niedrig wäre. Ein beendetes Projekt
  bekommt keine Nullen für die Zeit nach seinem Ende angerechnet.
  Die Richtung des verbleibenden Fehlers ist benennbar: ruhige Monate **vor** der ersten
  Buchung fehlen der Verteilung, ihre Quoten liegen damit eher zu hoch. Das Anlagedatum
  eines Projekts wird nicht mitgelesen; ohne es ist der Beginn der Laufzeit unbekannt.
- Beobachtete Quoten **über 1 werden nicht gekappt** – bei weichen Budgets kommen sie
  vor. Schritt 2 der Simulation begrenzt ohnehin auf das verbleibende Restvolumen.
- **Ziehung** je Lauf, Projekt und Monat unabhängig mit Zurücklegen aus den beobachteten
  Quoten.

Zwei Einschränkungen, die zur Schätzung gehören und nicht wegdefiniert werden:

- **Das Budget ist nur in seinem heutigen Stand bekannt.** Das Restvolumen zu einem
  vergangenen Monatsbeginn wird rückwärts als `budget_heute − revenue_kumuliert(bis
  Monatsbeginn)` rekonstruiert. Wurde ein Budget im Verlauf erhöht, fallen die älteren
  Quoten dieses Projekts zu niedrig aus. Das Ausmaß ist unbekannt; es begrenzt die
  Genauigkeit der Kalibrierung.
- **Die unabhängige Ziehung ignoriert Korrelation zwischen Projekten.** Ein
  portfolioweiter Nachfrageeinbruch träfe alle Projekte gleichzeitig; unabhängige
  Ziehungen mitteln ihn weg und liefern damit eine **zu enge** Bandbreite. Die Richtung
  des Fehlers ist bekannt, seine Größe nicht (siehe 9.2).

### 5.3 Kapazitätsdeckel

**Gerechnet wird in Stunden**, nicht in Personentagen. Die Länge eines Arbeitstags ist in
`/targethours`hinterlegt und liefert Stunden je Wochentag (20–35 h/Woche, meist 7 h/Tag).
```
verfügbare Kapazität(Person, Monat) = Sollstunden(Person, Monat)
                                     − geplante Abwesenheit
                                     − Abschlag für ungeplante Abwesenheit
```

- **Sollstunden** aus `/targethours`: die zum Monat gültige Wochenarbeitszeit, über die
  Wochentage des Monats aufsummiert. Der Gültigkeitszeitraum (`date_since`,
  `date_until`) ist zu beachten – es gibt je Person mehrere, historisch abgeschlossene
  Einträge.
- **Geplante Abwesenheit** aus `/v4/absences?year=…`, in Stunden gegen dieselbe
  Sollarbeitszeit gerechnet.
- **Feiertage** am besten aus `/v2/usersNonbusinessDays?year=…`, das sie je Person
  fertig zugeordnet liefert; die eigene Zuordnung über `users.nonbusinessgroups_id`
  erspart sich damit – und mit ihr der Fehler, für einen vergangenen Stichtag die heutige
  Zuordnung zu benutzen (die historische steht in `/v3/usersNonbusinessGroups` mit
  `date_since`/`date_until`). Sie stehen weder in `/targethours` noch in den Abwesenheiten
  und sind deshalb eigens abzuziehen: ein Feiertag ohne `half_day` setzt die Sollstunden
  seines Wochentags auf 0, mit `half_day` halbiert er sie. Fällt er auf einen Wochentag
  ohne Sollstunden, wirkt er von selbst nicht – ein Sonderfall für Wochenenden ist nicht
  nötig.
- **Sollstunden können fehlen.** `users.default_target_hours` heißt laut Doku „Uses the
  company's default target hours": wer den Schalter trägt, hat keine eigene Zeile in
  `/targethours`. Heute geht die Rechnung auf – je aktiver Person genau eine offene
  Zeile –, aber der Fall ist vorgesehen und braucht dann eine Quelle für den
  Firmenstandard.
- **Abschlag für ungeplante Abwesenheit**: ein aus der Abwesenheitshistorie geschätzter
  Prozentsatz. Noch nicht geschätzt (11.2).

**Die Feiertagsgruppe ist Teil des Deckels, kein Detail.** Die Gruppen dieser Anlage
führen unterschiedlich viele Feiertage im Jahr, und die Unterschiede fallen in einzelne
Monate: Fronleichnam, Allerheiligen, Reformationstag, Buß- und Bettag, Mariä Himmelfahrt
sind je nach Gruppe gesetzt oder nicht. Ein pauschaler Abschlag über alle Personen würde
diese Spreizung innerhalb eines Horizontmonats verwischen. Die aktiven Personen
verteilen sich sehr ungleich auf die Gruppen, mit einer klar dominierenden.

**Derselbe Kalender gilt für die Skalierung von Monat 1** (5.4). Der dort verlangte
„Anteil der verbleibenden Arbeitstage am Monat" ist ohne Feiertage ein anderer als
der Deckel, den er skaliert.

Offen bleibt die Deutung von `half_day`: dass ein halber Feiertag die Sollstunden des
Tages halbiert, passt zum Feldnamen und zu den betroffenen Tagen (Heiligabend und
Silvester, in einer Gruppe gar nicht geführt). Die OpenAPI-Beschreibung deklariert das
Feld nur als Boolean und sagt nichts über seine Wirkung – die Annahme bleibt damit eine
Annahme, belegt ist nur, dass es ein Schalter und keine Stundenzahl ist. Es geht um zwei
Tage im Dezember.

### 5.4 Simulationslogik

10.000 Läufe. Der Horizont umfasst 1 bis 3 Monate und **beginnt mit dem laufenden
Monat** – gefragt ist, was ab dem Stichtag noch hereinkommt.

**Der laufende Monat ist angebrochen.** Monat 1 umfasst nur den Rest des Monats ab dem
Stichtag; gezogene Abrufquote und verfügbare Kapazität werden dafür mit dem **Anteil der
verbleibenden Arbeitstage am Monat** skaliert. Was vor dem Stichtag gebucht wurde, ist
Verbrauch (5.1) und aus dem Restvolumen bereits abgezogen – es taucht hier nicht wieder
auf.

**Bereits gebuchte Beträge im Horizont sind die Untergrenze der Bandbreite.** Eine
Buchung, die nach dem Stichtag datiert und in einen Horizontmonat fällt, ist sicherer
Umsatz. Die Simulation zieht für ihr Projekt trotzdem eine Abrufquote und weiß nichts
davon; ohne Untergrenze könnte das 95-%-Niveau eines Monats **unter** dem liegen, was
schon feststeht. Deshalb gilt je Projekt und Horizontmonat:

```
Monatsumsatz = max(simulierter Umsatz, bereits gebuchter Umsatz dieses Monats)
```

Der gebuchte Betrag zählt gegen dasselbe Restvolumen wie der simulierte, wird also nicht
zusätzlich abgerufen. Datenquelle ist `/v2/entrygroups` mit
`grouping[]=projects_id&grouping[]=month` über den Horizont – dieselbe
Gruppierungskombination, die 11.1 für die Schätzung der Verteilung braucht.

Je Lauf und Monat:

1. Restvolumen (Euro) je Projekt aus dem Vormonat übernehmen bzw. mit dem
   **prognosewirksamen** Restvolumen aus 5.1 initialisieren. Projekte mit historisch
   überschrittenem Budget starten bei 0 und liefern über den gesamten Horizont keinen
   Umsatz. Ebenso Projekte mit `automatic_completion` und einer `deadline` **ab** dem
   Datum der `deadline`: sie werden automatisch abgeschlossen und liefern ab da keinen
   Umsatz mehr, unabhängig vom verbleibenden Restvolumen (Abschnitt 4).
2. Abrufquote aus der Verteilung (5.2) ziehen, für Monat 1 skalieren → gewünschter
   Euro-Verbrauch. **Auf das verbleibende Restvolumen begrenzt** – das Budget wird in der
   Prognose nicht überschritten, unabhängig davon, wie hoch die gezogene Quote liegt.
3. Über den effektiven Stundensatz (5.1) in **Stunden** umrechnen und auf die
   beteiligten Personen aufteilen. Schlüssel ist der **historische Stundenanteil je
   Person am jeweiligen Projekt**, aus der Doppelgruppierung von `/v2/entrygroups`, und
   unverändert in die Zukunft fortgeschrieben. Projekte ohne ableitbaren Stundensatz
   (5.1) erzeugen keinen Stundenbedarf.
4. Je Person: Bedarf über **alle** ihre Projekte gegen die verfügbare Kapazität (5.3)
   deckeln, bei Überschreitung anteilig kürzen. Der Deckel ist projektübergreifend.
5. Tatsächlich gelieferte Stunden über denselben Satz zurück in Euro → Monatsumsatz je
   Projekt, summiert.
6. Restvolumen um den tatsächlichen Euro-Verbrauch reduzieren, in den nächsten Monat
   übertragen. Durch die Begrenzung in Schritt 2 bleibt es ≥ 0.

Der Aufteilungsschlüssel aus Schritt 3 veraltet, wenn die Teambesetzung eines Projekts
wechselt. Das ist ein Kalibrierungsthema (Abschnitt 7), keine Modelländerung.

### 5.5 Ausgabe

- Umsatz auf den Konfidenzniveaus **95 % / 85 % / 50 %**, je Monat des Horizonts und als
  Summe über den Horizont.
- **Anteil der Läufe, in denen die Kapazität der limitierende Faktor war** – die Größe
  unterscheidet einen Nachfrage- von einem Kapazitätsengpass und ist ein geforderter
  Output, kein Nebenprodukt.
- Je Horizontmonat der **bereits gebuchte Betrag**, getrennt ausgewiesen. Er ist laut
  5.4 die Untergrenze der Bandbreite; sichtbar gemacht wird er trotzdem, weil der
  Unterschied zwischen „steht fest" und „ist erwartet" für die Steuerung der wichtigere
  ist als die Bandbreite selbst.
- Für den laufenden Monat zusätzlich der **Verbrauch vor dem Stichtag**. Er steckt nicht
  in der Bandbreite, weil er aus dem Restvolumen schon abgezogen ist – erst zusammen mit
  ihr ist der Monat mit den Werten der Historie vergleichbar.
- Die Hinweise aus 5.0, 5.1 und 5.3 zu allem, was nicht oder nur genähert erfasst ist.

**Solange die Simulation nicht gebaut ist, wird keine Bandbreite ausgewiesen**, sondern
die Begründung, was ihr fehlt. Eine erfundene Kurve wäre der schlechtere Platzhalter.

## 6. entfallen

## 7. Kalibrierung

Monatlich zu prüfen:

- **Die Abrufquote-Verteilung** gegen den zuletzt beobachteten Monat.
- **Der Aufteilungsschlüssel je Person** (5.4 Schritt 3) auf veraltete
  Team-Zusammensetzungen. Wechselt die Besetzung eines Projekts spürbar, wird der
  Schlüssel falsch.
- **Budgetüberschreitungen** (5.1): Häufigkeit und Höhe. Sie sind das Signal dafür, ob
  Budgets in der Praxis als Grenze wirken.
- **Der Abschlag für ungeplante Abwesenheit** (5.3).

`active`, `completed` und `completed_at` aus `/v4/projects` markieren rückwirkend
zuverlässig, wann ein Projekt real endete, und sind damit die Grundlage jedes
Rückwärtstests.

Bei Abweichungen zwischen Prognose und Ist gilt: **zuerst die Kalibrierung prüfen, nicht
die Simulationslogik umbauen.**

## 8. Verhältnis zur Gesamt-Umsatzprognose

Dieser Baustein deckt ausschließlich den Umsatz aus bereits in Clockodo angelegten
Projekten ab. Pipeline, Kurzfristgeschäft und Cash-Schicht sind eigene Bausteine; ihre
Zusammenführung ist nicht Teil dieser Spec.

## 9. Offene Punkte

**Fachlich offen:**

1. **Aktive Projekte ohne Budget** – die Mehrzahl der aktiven Projekte. Die Deutung als Katalogpositionen ohne
   beauftragtes Volumen stützt sich auf die Projekt- und Kundennamen. Zu prüfen, ob
   darunter echte Bestandsprojekte mit bloß fehlendem Budget sind.
2. **Korrelation zwischen Projekten** (5.2). Die unabhängige Ziehung liefert eine zu
   enge Bandbreite. Ob das für eine 1–3-Monats-Prognose vertretbar ist, ist eine
   fachliche Entscheidung.

## 10. Stand der Umsetzung

Umgesetzt als Python-Paket `umsatzprognose` mit Notebook-Oberfläche in Google Colab:

- **Vollständig:** Abschnitte 4, 5.0, 5.1 (ohne die Näherung für Umsatz ohne Zeit, die
  als Hinweis ausgewiesen wird), **5.2**, der Aufteilungsschlüssel aus 5.4 Schritt 3, die
  Sollarbeitszeit aus 5.3 sowie die Umsatzhistorie der letzten zwölf Monate.
- **Nicht gebaut:** die Simulation (5.4) sowie geplante Abwesenheiten, Feiertage und der
  Abschlag für ungeplante Abwesenheit (5.3). An der Stelle der Bandbreite steht die
  Begründung.

Die Abrufquote-Verteilung ist am 26.08.2026 geschätzt. Ihre Kennzahlen stehen bewusst
nicht hier: sie stammen aus der Installation, bewegen sich mit jeder Zeitbuchung und
gehören in die Notebook-Ausgabe, nicht in eine versionierte Datei. Ihre Form ist stark
rechtsschief – ein niedriger Median, ein deutlich höherer Mittelwert, ein erheblicher
Anteil Monate ganz ohne Abruf und einzelne Quoten weit über 1. Diese Ausreißer sind
keine Fehlmessung, sondern genau die in 5.2 benannte Einschränkung: ein Projekt-Monat
mit kleinem rekonstruiertem Restvolumen und einer großen Buchung. Für die Simulation
sind sie unschädlich, weil Schritt 2 auf das verbleibende Restvolumen begrenzt – eine
sehr hohe Quote heißt dort „alles Offene abrufen". Nur ein kleiner Teil der
Beobachtungen stammt aus Projekten, die heute im Prognose-Scope sind; die übrigen aus
der Historie beendeter Projekte. Das ist die Folge der portfolioweiten Schätzung und
keine Verzerrung, die sich beheben ließe, ohne Referenzklassen einzuführen.

## 11. Nächste Schritte

1. ~~**Abrufquote-Verteilung schätzen** (5.2)~~ – gebaut am 26.08.2026. Der Abruf mit
   `grouping[]=projects_id&grouping[]=month` liefert wie vorgesehen beide Zwecke: die
   Historie für die Verteilung und die bereits gebuchten Beträge im Horizont für die
   Untergrenze aus 5.4. Drei Eigenheiten der Antwort waren dabei nicht vorhergesehen: die
   Monate kommen **nach Dauer absteigend** und nie chronologisch, die Monatssummen gehen
   nur auf den Cent auf (Clockodo rundet jede Gruppe einzeln), und `group == 0` kommt
   mehrfach vor – je Kunde ohne Projekt einmal.
2. **Abwesenheiten und Feiertage auswerten** (5.3): `/v4/absences` anbinden und aus der
   Historie den Abschlag für ungeplante Abwesenheit schätzen; für die Feiertage
   `/v2/usersNonbusinessDays?year=…` statt der Feiertagsgruppen von Hand zuzuordnen. Der
   Horizont reicht über eine Jahresgrenze, also zwei Abrufe je Endpunkt.
3. **Simulation bauen** (5.4) und die Ausgabe aus 5.5 vollständig liefern.
4. **Rückwärtstest über 12 Stichtage.** Er entscheidet auch, ob Referenzklassen nötig
   sind (Abschnitt 6). Zu beachten: ein Ladevorgang verbraucht drei der 10 zulässigen
   `entrygroups`-Abrufe je Minute – 12 Stichtage brauchen also eine Drosselung oder eine
   Wiederverwendung der Antworten über die Stichtage hinweg. Letzteres ist möglich, weil
   sich zwischen zwei Stichtagen nur die Zeitgrenzen ändern, nicht die Gruppierung.