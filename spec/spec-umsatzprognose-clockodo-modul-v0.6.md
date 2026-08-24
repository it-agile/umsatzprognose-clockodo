# Spec: Umsatzprognose – Baustein Bestand (Clockodo)

**Version:** 0.6
**Stand:** 24.08.2026

**Dies ist ein vollständiges Dokument.** v0.4 und v0.5 waren Delta-Dokumente, die
tragende Abschnitte nur als „unverändert zu v0.3“ führten; damit war die Spec ohne v0.3
nicht lesbar und als maßgebliche Quelle unbrauchbar. Ab dieser Version steht das Modell
geschlossen an einer Stelle. v0.3 und v0.5 bleiben als Historie liegen.

**Änderungen zu v0.5:**

1. Abschnitt 4 gegen die echte API korrigiert – vier von sechs Zeilen waren falsch
   (siehe den Provenienz-Hinweis dort).
2. Referenzklassen zurückgestellt: die Abrufquote-Verteilung wird zunächst
   portfolioweit geschätzt (Abschnitte 5.2 und 6).
3. Kapazität und Bedarf rechnen durchgehend in **Stunden** statt in Personentagen
   (5.3, 5.4).
4. Pauschalleistungen werden ohne `/v2/entries` behandelt; der Sonderfall wird
   ausgewiesen statt geschätzt (5.1).
5. Der Prognosehorizont beginnt mit dem **laufenden** Monat (5.4).
6. Neuer Abschnitt 5.0: der Prognose-Scope – welche Projekte überhaupt eingehen.
7. Neuer Abschnitt 10: Stand der Umsetzung.

---

## 1. Ziel

Eine rollierende 1–3-Monats-Prognose des Umsatzes aus laufenden, in Clockodo
angelegten Projekten – mit Bandbreite statt Punktwert, ausschließlich aus
Clockodo-Daten.

Ist ein Projekt in Clockodo angelegt, gilt es als beauftragt. Storno auf Projektebene
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

**Zur Herkunft dieser Tabelle.** In v0.3 stammten die Feldangaben aus
`docs.clockodo.com/openapi.yaml`, also aus der Dokumentation. Der Prototyp hat drei
davon an echten Antworten widerlegt – die Dokumentation ist hier keine verlässliche
Quelle. `docs.clockodo.com` wird inzwischen als JavaScript-Anwendung ausgeliefert und
war nicht auslesbar. Alle Angaben unten sind am 24.08.2026 gegen die Installation
geprüft. **Wer die Tabelle ändert, prüft gegen eine echte Antwort, nicht gegen die
Doku.**

| Zweck | Endpunkt | Relevante Felder |
|---|---|---|
| Auftragsvolumen | `GET /v4/projects` | `budget` (`amount`, `hard`, `monetary`, `interval`, `from_subprojects`), `active`, `completed`, `customers_id`, `name` |
| Verbrauchtes Volumen, effektiver Satz | `GET /v2/entrygroups`, `grouping[]=projects_id` | `revenue`, `duration` (Sekunden) |
| Anteil je Person am Projekt | dieselbe Abfrage, zusätzlich `grouping[]=users_id` | `sub_groups` mit `group`, `duration`, `revenue` |
| Umsatz je Monat | `GET /v2/entrygroups`, `grouping[]=month` | `group` (`"JJJJMM"`), `revenue`, `duration` |
| Kundenname | `GET /v3/customers` | `id`, `name` |
| Personen | `GET /v3/users` | `id`, `name`, `active` |
| Sollarbeitszeit je Person | `GET /targethours` (unversioniert) | `users_id`, `type`, `date_since`, `date_until`, Stunden je Wochentag |
| Geplante Abwesenheit | `GET /v4/absences?year=…` | Zeitraum, Art, Person |

Basis-URL ist `https://my.clockodo.com/api`. Authentifizierung über drei Pflicht-Header:
`X-ClockodoApiUser` (E-Mail), `X-ClockodoApiKey` und
`X-Clockodo-External-Application` im Format `name;email` mit **maximal 50 Zeichen
Gesamtlänge**.

Vier Korrekturen gegenüber v0.3 und v0.5, jede an einer echten Antwort belegt:

- **`entrygroups.hourly_rate` ist als effektiver Stundensatz unbrauchbar.** Es ist nur
  gesetzt, wenn `hourly_rate_is_equal_and_has_no_lumpsums` `true` ist – bei 92 von 870
  Gruppen, und dort meist `0`. Für die übrigen 778 ist es `null`. Auch wo beides
  vorliegt, weicht `revenue / (duration/3600)` davon ab, weil nicht jede erfasste
  Stunde abgerechnet wird. Der effektive Satz wird deshalb abgeleitet.
- **`users.default_target_hours` ist ein Boolean-Schalter, keine Stundenzahl.** 56 mal
  `false`, 3 mal `true` über alle 59 Personen, ohne Zusammenhang zu `active`. Wer es als
  Stunden liest, bekommt 0 oder 1 und einen still falschen Kapazitätsdeckel. Die echten
  Werte stehen im unversionierten `/targethours` (`/v2` und `/v3` davon geben 404):
  186 Einträge, alle mit `type: "weekly"`, davon 26 offene – genau die 26 aktiven
  Personen, je einer, mit 20 bis 35 Wochenstunden. Ein anderer `type` ist nie
  aufgetreten; träte er auf, wird er nicht gedeutet, sondern gemeldet.
- **Abwesenheiten liegen auf `/v4/absences`.** Die Legacy-Pfade `/absences`,
  `/v2/absences` und `/v3/absences` antworten mit 410 `deprecated`.
- **`/v2/entries` wird nicht benutzt.** `count_items` steht bei 16.461 für zwölf Monate,
  `items_per_page` bei 2500 – sieben Abrufe je Jahr Historie, um dieselbe Summe zu
  bilden, die `/v2/entrygroups` schon gebildet hat. Die Doppelgruppierung nach Projekt
  und Person liefert die Aufteilung fertig aggregiert; ihre Projektsummen sind mit denen
  der einfachen Gruppierung über alle 870 Gruppen identisch. Erst wenn eine Auswertung
  wirklich den einzelnen Eintrag braucht, lohnt der Endpunkt.

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
  solange das so bleibt.
- **Historientiefe:** `revenue` deckt die ganze Historie ab, sobald die untere
  Zeitgrenze weit genug liegt – `time_since=2010-01-01` liefert dieselben 870 Gruppen
  und dieselbe Summe wie `2020-01-01`. Die Antwort hat kein `paging`.

## 5. Modell

### 5.0 Prognose-Scope

Welche Projekte in die Prognose eingehen, hat v0.3 nicht festgelegt. Es gilt:

Ein Projekt ist **im Prognose-Scope**, wenn es `active` ist und sein Budget als
Euro-Gesamtbudget lesbar ist.

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
gilt für die 236 von 895 Projekten, deren `budget` `null` ist.

Größenordnung am 24.08.2026: 895 Projekte, davon 122 aktiv, davon 44 im Prognose-Scope
mit zusammen 2,38 Mio. EUR Auftragsvolumen und rund 729.000 EUR prognosewirksamem
Restvolumen. Die 78 aktiven Projekte ohne Budget sind überwiegend Schulungs- und
Ausbildungsprodukte beim Kunden „Öffentliche Schulung“, also Katalogpositionen ohne
beauftragtes Volumen – das rechnet Abschnitt 2 dem Kurzfristgeschäft zu. Ob darunter
echte Bestandsprojekte mit bloß fehlendem Budget stecken, ist ein Pflegethema und kein
Modellthema (siehe 9.2).

### 5.1 Restvolumen je Projekt (in Euro)

```
rohes Restvolumen(Projekt)          = budget.amount − revenue_kumuliert(Projekt)
prognosewirksames Restvolumen       = max(0, rohes Restvolumen)
```

`revenue_kumuliert` kommt aus `/v2/entrygroups` mit `grouping[]=projects_id` über die
gesamte Historie. Ein Abruf deckt alle Projekte ab; eine Abfrage je Projekt – wie v0.3
sie formulierte – wäre 895 Abrufe für dieselbe Zahl.

**Budgetüberschreitungen.** `budget.hard` ist in dieser Installation `false`, wo es
zählt: Budgets sind weiche Grenzen, der Verbrauch kann sie übersteigen. Eine
Überschreitung kann damit nur **historisch** entstehen. **Die Prognose überschreitet das
Budget eines Projekts nicht.** Ein Projekt mit historisch überschrittenem Budget startet
bei 0 und trägt über den gesamten Horizont keinen Umsatz.

Das rohe Restvolumen wird trotzdem geführt und nicht verworfen: Häufigkeit und Höhe von
Überschreitungen sind ein Kalibrierungssignal (Abschnitt 7) und kein Fehler.

Ein Enddatum je Projekt wird nicht verwendet; ein auslaufendes Projekt erkennt das
Modell am sinkenden Restvolumen. (`completed_at` existiert und wäre auswertbar – siehe
9.1.)

**Pauschalleistungen.** v0.3 wollte sie über `/v2/entries` (`type` 2 und 3)
identifizieren und je Leistung einen Satz aus Pauschalbetrag und gebuchter Zeit
ableiten. Das ist verworfen: `entrygroups.revenue` schließt Pauschalleistungen bereits
ein, der Zusatzabruf kostet sieben Seiten je Jahr Historie und löst den entscheidenden
Fall nicht. Stattdessen gilt:

- Der effektive Stundensatz eines Projekts ist `revenue / (duration/3600)` über seine
  gesamte Historie. Pauschalleistungen mit gebuchter Zeit sind darin normalisiert
  enthalten, ohne eigenen Modellzweig.
- **Umsatz ohne jede erfasste Zeit** (8 Gruppen; `duration == 0`) liefert keinen Satz.
  Solche Projekte gehen mit ihrem Restvolumen in die Simulation ein, verbrauchen aber
  **keine Kapazität** – sie umgehen den Deckel aus 5.4 Schritt 3. Das ist eine
  benannte Näherung, nicht eine stille: die betroffenen Projekte werden als Hinweis
  ausgewiesen.

### 5.2 Abrufquote-Verteilung

Die Abrufquote wird als **empirische Verteilung** aus der eigenen Historie geschätzt,
nicht als parametrische Verteilungsfamilie – für eine Familie gibt es keine Begründung.

- **Beobachtungseinheit** ist ein Projekt-Monat.
- **Quote** = Verbrauch im Monat geteilt durch das Restvolumen zu Monatsbeginn.
- **Datenquelle** ist `/v2/entrygroups` mit `grouping[]=projects_id&grouping[]=month`.
- **Einbezogen** werden Projekt-Monate mit einem Restvolumen > 0 zu Monatsbeginn; sonst
  ist die Quote undefiniert.
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
  des Fehlers ist bekannt, seine Größe nicht (siehe 9.3).

### 5.3 Kapazitätsdeckel

**Gerechnet wird in Stunden**, nicht in Personentagen. v0.3 sprach von
Nettoarbeitstagen; die Länge eines Arbeitstags ist aber nirgends hinterlegt, und
`/targethours` liefert Stunden je Wochentag (20–35 h/Woche, meist 7 h/Tag). Eine
angenommene Taglänge würde den Deckel still verschieben. Arbeitstage bleiben eine
Darstellungsgröße.

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
- **Abschlag für ungeplante Abwesenheit**: ein aus der Abwesenheitshistorie geschätzter
  Prozentsatz. Noch nicht geschätzt (11.2).

Feiertage sind in `/targethours` nicht enthalten und in den Abwesenheiten
voraussichtlich auch nicht; ob und wie Clockodo sie führt, ist ungeprüft (9.4).

### 5.4 Simulationslogik

10.000 Läufe. Der Horizont umfasst 1 bis 3 Monate und **beginnt mit dem laufenden
Monat** – gefragt ist, was ab dem Stichtag noch hereinkommt.

**Der laufende Monat ist angebrochen**, und das an zwei Stellen:

- Das Ausgangs-Restvolumen aus 5.1 enthält den bereits gebuchten Verbrauch dieses
  Monats. Er wird also nicht doppelt gezählt.
- Gezogene Abrufquote und verfügbare Kapazität werden für Monat 1 mit dem **Anteil der
  verbleibenden Arbeitstage am Monat** skaliert.

Je Lauf und Monat:

1. Restvolumen (Euro) je Projekt aus dem Vormonat übernehmen bzw. mit dem
   **prognosewirksamen** Restvolumen aus 5.1 initialisieren. Projekte mit historisch
   überschrittenem Budget starten bei 0 und liefern über den gesamten Horizont keinen
   Umsatz.
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
- Für den laufenden Monat zusätzlich das **bereits gebuchte Ist**, getrennt von der
  Bandbreite. Erst beides zusammen ist mit den Monatswerten der Historie vergleichbar.
- Die Hinweise aus 5.0, 5.1 und 5.3 zu allem, was nicht oder nur genähert erfasst ist.

**Solange die Simulation nicht gebaut ist, wird keine Bandbreite ausgewiesen**, sondern
die Begründung, was ihr fehlt. Eine erfundene Kurve wäre der schlechtere Platzhalter.

## 6. Referenzklassen – zurückgestellt

v0.3 nannte vier Referenzklassen: laufendes Coaching-/Beratungsmandat bei
Bestandskund:in, neues Projekt bei Bestandskund:in, Neukund:in, Abruf aus
Rahmenvertrag.

**Sie sind zurückgestellt.** Grund: Clockodo führt kein Feld, aus dem die Klasse eines
Projekts hervorgeht. „Abruf aus Rahmenvertrag“ und „laufendes Mandat“ lassen sich aus
Budget, Buchungsverlauf und Kundennummer nicht ableiten, und eine geratene
Zuordnungsregel wäre eine zweite unkalibrierte Größe neben der Verteilung selbst.

Die Abrufquote-Verteilung wird deshalb zunächst **portfolioweit** über alle Projekte im
Scope geschätzt (5.2). Das unterschätzt die Streuung zwischen Projekttypen – ein
Rahmenvertrag ruft anders ab als ein laufendes Mandat –, ist aber eine Näherung mit
bekannter Richtung statt einer erfundenen Zuordnung.

Eingeführt werden Klassen, wenn der Rückwärtstest (11.4) zeigt, dass eine
portfolioweite Verteilung die beobachteten Monatsumsätze nicht trägt. Dann braucht es
zuerst eine Zuordnungsquelle: eine gepflegte Liste im Repository oder ein Feld in
Clockodo.

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

**Fachlich:**

1. **Aktive Projekte mit `completed: true`.** Zwei Fälle, einer mit 12.424 EUR offenem
   Budget. Sie gehen derzeit in die Prognose ein. Abschnitt 7 hält `completed` für ein
   zuverlässiges Endesignal – dann gehören sie aus dem Scope. Ändert die Zahlen, deshalb
   nicht einseitig entschieden.
2. **Aktive Projekte ohne Budget** (78 von 122). Die Deutung als Katalogpositionen ohne
   beauftragtes Volumen stützt sich auf die Projekt- und Kundennamen. Zu prüfen, ob
   darunter echte Bestandsprojekte mit bloß fehlendem Budget sind.
3. **Korrelation zwischen Projekten** (5.2). Die unabhängige Ziehung liefert eine zu
   enge Bandbreite. Ob das für eine 1–3-Monats-Prognose vertretbar ist, ist eine
   fachliche Entscheidung.
4. **Feiertage** (5.3). Ungeprüft, ob und wo Clockodo sie führt. Ohne sie ist die
   Sollzeit im Monat zu hoch angesetzt.

**Organisatorisch:**

5. **Verantwortlichkeit:** Wer führt die monatliche Kalibrierung durch (Abschnitt 7)?
   Muss vor dem produktiven Rollout geklärt sein – nicht vor dem Prototyp, sonst
   veraltet das Modell nach der ersten Version unbemerkt.

## 10. Stand der Umsetzung (24.08.2026)

Umgesetzt als Python-Paket `umsatzprognose` mit Notebook-Oberfläche in Google Colab
(Zielwerkzeug, entschieden in v0.4):

- **Vollständig:** Abschnitte 4, 5.0, 5.1 (ohne die Näherung für Umsatz ohne Zeit, die
  als Hinweis ausgewiesen wird), der Aufteilungsschlüssel aus 5.4 Schritt 3, die
  Sollarbeitszeit aus 5.3 sowie die Umsatzhistorie der letzten zwölf Monate.
- **Nicht gebaut:** die Simulation (5.4), die Schätzung der Abrufquote-Verteilung (5.2),
  geplante Abwesenheiten und der Abschlag für ungeplante (5.3). An der Stelle der
  Bandbreite steht die Begründung.

Kennzahlen des Prototyps: 895 Projekte, 122 aktiv, 44 im Prognose-Scope; 59 Personen,
26 aktiv mit zusammen 801 Wochenstunden; 2,38 Mio. EUR Auftragsvolumen, rund
729.000 EUR prognosewirksames Restvolumen; Umsatz der zwölf abgeschlossenen Monate
09/2025–08/2026 rund 3,48 Mio. EUR. Die Zahlen bewegen sich mit jeder Zeitbuchung – sie
taugen als Größenordnung, nicht als Regressionswert.

## 11. Nächste Schritte

1. **Abrufquote-Verteilung schätzen** (5.2): `/v2/entrygroups` mit
   `grouping[]=projects_id&grouping[]=month`, Restvolumen je Monatsbeginn rückwärts
   rekonstruieren, empirische Verteilung bilden.
2. **Abwesenheiten auswerten** (5.3): `/v4/absences` anbinden und aus der Historie den
   Abschlag für ungeplante Abwesenheit schätzen.
3. **Simulation bauen** (5.4) und die Ausgabe aus 5.5 vollständig liefern.
4. **Rückwärtstest über 12 Stichtage.** Er entscheidet auch, ob Referenzklassen nötig
   sind (Abschnitt 6).
5. **Vor produktivem Einsatz:** Verantwortlichkeit (9.5) klären.
