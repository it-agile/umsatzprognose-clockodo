# Spec: Umsatzprognose – Baustein Kurzarbeitsbereitschaft

## 1. Ziel

Rückblickend für einen abgeschlossenen Kalendermonat ausweisen, ob die Organisation die
Voraussetzungen für Kurzarbeit erfüllt hätte: mindestens 30 % aller Mitarbeitenden
gelten als kurzarbeitsfähig, wenn ihr Anteil interner Arbeit mindestens 24 % beträgt und
ihr kumulierter Überstundenstand zum Monatsende unter 14 Stunden liegt. Ausgangspunkt
ist `spec/spec-ka-intent.md`. Wie bei den Bausteinen Schulungsanmeldungen und Kosten
keine Simulation, keine Bandbreite – jeder Monat hat ein eindeutiges, deterministisches
Ergebnis auf Basis bereits gebuchter Zeit.

## 2. Nicht-Ziele

- Keine arbeitsrechtliche Bewertung oder Entscheidung über die tatsächliche Einführung
  von Kurzarbeit – nur ein rückblickendes Signal.
- Keine Prognose für zukünftige Monate (siehe Abschnitt 8 des Intents für eine mögliche
  spätere Ausbaustufe).
- Keine Verrechnung mit oder Rückwirkung auf den Baustein Bestand (Restvolumen,
  Abrufquote, Kapazitätsdeckel bleiben unberührt) oder auf die Bausteine
  Schulungsanmeldungen/Kosten. Kein Anschluss an `Dashboard` – ein eigenständiges
  Notebook wie beim Anmeldungsverlauf (`spec-schulungsanmeldungen.md` Abschnitt 9).
- Keine Anzeige, welche der beiden Bedingungen eine einzelne Person nicht erfüllt, und
  keine Anzeige von Einzelwerten (Stunden, Überstundenstand) je Person in der Ausgabe.
- Keine dauerhafte Speicherung von aus der Auswertung gewonnenen Personaldaten, keine
  dauerhafte Ablage der Rollenzuordnung (Abschnitt 5.2) im Repository.

## 3. Begriffe

- **Personenmonat:** die für die Regel nötigen Rohdaten einer Person in einem
  Kalendermonat – interne und externe gebuchte Stunden sowie der kumulierte
  Überstundenstand zum Monatsende. Reine Clockodo-Abbildung, ohne Kenntnis von Rollen
  oder Schwellenwerten (siehe 5.1).
- **Kurzarbeitsfähig:** eine Person, die im betrachteten Monat beide Bedingungen aus
  Abschnitt 5.3 erfüllt und nicht laut Rollenzuordnung (5.2) ausgeschlossen ist.
- **Vorbereitet:** die Organisation, wenn die Quote kurzarbeitsfähiger Personen die
  30-%-Schwelle erreicht (5.4).

## 4. Datenmodell aus Clockodo

Der Clockodo-Zugriff bleibt **fachlich blind** – er liefert Rohdaten je Person und
Monat, ohne zu wissen, was Geschäftsführung, Vertrieb oder eine Schwelle ist. Diese
Kenntnis liegt ausschließlich in der Domäne (Abschnitt 5).

| Zweck | Endpunkt | Felder |
|---|---|---|
| Personen | `GET /v3/users` | `id`, `name` |
| Interne/externe Arbeitszeit je Person und Monat | `GET /v2/entrygroups`, `grouping[]=users_id&grouping[]=month`, je einmal `filter[billable]=0` (intern), `=1` und `=2` (extern), sowie ungefiltert zur Konsistenzprüfung | `sub_groups[].duration` |
| Kumulierter Überstundenstand zum Monatsende | `GET /userreports?year=…&type=1` | `userreports[].overtime_carryover` (Jahresbeginn-Saldo) + kumulierte Summe von `userreports[].month_details[].diff` bis einschließlich des Zielmonats (siehe Abschnitt 8 – `month_details[].diff` selbst ist **nicht** kumuliert) |

Die Billable-Klassifizierung folgt derselben Regel wie beim Baustein Auslastung
(`clockodo/auslastung.py`): abrechenbar heißt Status 1 und 2 zusammen, nicht
abrechenbar ist Status 0. Weicht die Summe aus intern und extern von der ungefilterten
Gesamtstundenzahl einer Person und eines Monats ab, gilt die Differenz als
**unklassifizierte Stunden** (Abschnitt 5.5) statt stillschweigend einer Seite
zugerechnet zu werden.

## 5. Modell

### 5.1 Rohdaten vs. Domänen-Konfiguration

Die Zuordnung von Personen zu Geschäftsführung/Vertrieb sowie die drei Schwellenwerte
sind **keine Clockodo-Eigenschaft**, sondern Konfiguration der Anwendungsdomäne:

- `KurzarbeitRepository` (Paket `clockodo/`) liefert ausschließlich
  `Personenmonat`-Rohdaten (Abschnitt 3) – jede Person, für die im betreffenden Monat
  Daten vorliegen, ohne Filterung oder Bewertung.
- Eine reine Domänenfunktion (`domaene.kurzarbeit.bewerten()`) verknüpft diese Rohdaten
  mit der Rollenzuordnung (5.2) und den Schwellenwerten (5.3) zu einer
  `Kurzarbeitsbewertung`. Dieselbe Trennung wie zwischen geladenem Zustand und
  `domaene.simulation.simulieren()` beim Baustein Bestand.

### 5.2 Rollenzuordnung (Geschäftsführung/Vertrieb)

Die Zuordnung erfolgt **über den Personennamen**, als eigenes, unveränderliches
Konfigurationsobjekt der Domäne (`domaene.kurzarbeit.Rollenzuordnung`, eine Menge
ausgeschlossener Namen). Eine so zugeordnete Person zählt weiterhin zum Nenner der
30-%-Quote (5.4), geht aber nie in den Zähler kurzarbeitsfähiger Personen ein – unabhängig
davon, ob sie die beiden Bedingungen aus 5.3 rechnerisch erfüllen würde.

Die tatsächliche Namensliste ist eine personenbezogene Angabe und wird deshalb **nicht
im Repository** geführt – weder als Code noch als Notebook-Zelle. Sie wird zur Laufzeit
aus einer Umgebungsvariable bzw. einem Colab-Secret gelesen (analog zu
`ClockodoCredentials`/`GoogleSheetsConfig`) und als `Rollenzuordnung` an
`bewerten()` übergeben. Name der Variable und Ladeort (`notebooks/setup.py` oder ein
schmales `clockodo/config.py`-Pendant) sind Teil der Umsetzung, nicht dieser Spec.

### 5.3 Regel für eine als kurzarbeitsfähig geltende Person

```
Anteil interne Arbeit = interne gebuchte Stunden / alle gebuchten Arbeitsstunden
kurzarbeitsfähig wegen interner Arbeit = Anteil interne Arbeit >= Schwellenwert (Standard 24 %)

kurzarbeitsfähig wegen Überstunden = Überstundenstand zum Monatsende < Schwellenwert (Standard 14 Std.)

kurzarbeitsfähig = kurzarbeitsfähig wegen interner Arbeit
                    UND kurzarbeitsfähig wegen Überstunden
                    UND nicht laut Rollenzuordnung ausgeschlossen (5.2)
```

„Alle gebuchten Arbeitsstunden" umfasst intern, extern und unklassifizierte Stunden
(5.5) – unklassifizierte Stunden zählen nur in diesen Nenner, nie in den Zähler.

Ein negativer Überstundenstand (Minusstunden) gilt als unter der Schwelle erfüllt –
keine Sonderbehandlung.

### 5.4 Regel für die Organisation

```
Quote kurzarbeitsfähiger Personen =
  Anzahl kurzarbeitsfähiger Personen /
  Anzahl aller in die Auswertung einbezogenen Mitarbeitenden (5.5)

vorbereitet = Quote kurzarbeitsfähiger Personen >= Schwellenwert (Standard 30 %)
```

Geschäftsführung und Vertrieb zählen im Nenner mit, nie im Zähler (5.2).

### 5.5 Schwellenwerte als Parameter

Alle drei Schwellenwerte (24 %, 30 %, 14 Std.) sind **Parameter von außen**, kein fest
codierter Wert – wie `stichtag`/`horizont_monate` bei `Dashboard.laden()`. Eine
`domaene.kurzarbeit.Schwellenwerte`-Konfiguration (mit den drei Werten als Standard)
wird an `bewerten()` übergeben und im Notebook als eigene, editierbare Zelle
freigelegt, damit sich Was-wäre-wenn-Szenarien (z. B. „ab welcher Schwelle wäre die
Organisation vorbereitet gewesen") ohne Codeänderung durchspielen lassen.

### 5.6 Unvollständige und unklassifizierbare Daten

- **Unklassifizierte Stunden** (4): fließen in den Nenner von 5.3, nie in den Zähler;
  eine Person/ein Monat mit unklassifizierten Stunden erzeugt einen Hinweis.
- **Kein bestimmbarer Überstundenstand** (kein Eintrag in `/userreports` für die
  Person im betreffenden Monat) oder **keine gebuchte Stunde im Monat** (Anteil interne
  Arbeit rechnerisch nicht bestimmbar, 0/0): die Person wird für diesen Monat
  vollständig aus der Auswertung genommen – weder Zähler noch Nenner – statt eine
  Annahme zu treffen. Anzahl und Hinweis dazu gehören zur Ausgabe (Abschnitt 6). Das
  ist die für das MVP gewählte, bewusst einfache Antwort auf die im Intent offene
  Frage nach Neueintritten, Austritten und unvollständigen Buchungen.

### 5.7 Bezugszeitraum

Die Bewertung arbeitet je Kalendermonat; `bewerten()` bekommt die
`Personenmonat`-Rohdaten genau eines Monats und liefert eine `Kurzarbeitsbewertung`.
Für mehrere Monate (Standard: der letzte vollständig abgeschlossene Monat, zusätzlich
abrufbar für weitere zurückliegende Monate) ruft die aufrufende Schicht
(`KurzarbeitRepository`/Notebook) `bewerten()` je Monat auf. Der laufende Monat wird nie
bewertet, weil seine Zeiterfassung unvollständig ist.

### 5.8 Verhältnis zu Bestand, Schulungsanmeldungen und Kosten

Vollständig unabhängig und ohne Rückwirkung – wie in Abschnitt 2 festgehalten. Dieser
Baustein liest zusätzliche Clockodo-Daten (Billable-Aufschlüsselung, Userreports), die
in keinem der bestehenden Bausteine verwendet werden, und schreibt in kein bestehendes
Fachobjekt zurück.

## 6. Ausgabe

Je bewertetem Monat mindestens:

- Status („Voraussetzung erfüllt" / „Voraussetzung nicht erfüllt").
- Anzahl und Anteil kurzarbeitsfähiger Personen, verglichen mit der 30-%-Schwelle.
- Anzahl der Personen, die an der internen Arbeit, an den Überstunden oder an beiden
  Bedingungen scheitern – nur als Zähler, ohne Namen oder Einzelwerte.
- Anzahl ausgeschlossener Personen (Geschäftsführung/Vertrieb) und Anzahl nicht
  bestimmbarer Personen (5.6), beide mit erläuterndem Hinweis.
- Die verwendeten Schwellenwerte (5.5), damit das Ergebnis nachvollziehbar bleibt, wenn
  mit ihnen experimentiert wurde.

**Für einzelne Personen bleibt unsichtbar, an welcher der beiden Bedingungen sie
scheitern** – das gilt für jede Ausgabeform (Notebook-Text, Tabelle, Diagramm). Ein
eigenständiges Notebook (siehe 2) zeigt den Standardmonat als Text sowie optional eine
Tabelle über mehrere zurückliegende Monate; beides ausschließlich mit den
Aggregatzahlen dieses Abschnitts.

## 7. Verhältnis zur Gesamt-Umsatzprognose

Kein Bezug – anders als Bestand, Schulungsanmeldungen und Kosten ist dieser Baustein
kein Umsatz- oder Kostensignal, sondern ein Kapazitäts-/Personalsignal. Er wird deshalb
bewusst nicht in `Dashboard` integriert (siehe Abschnitt 2).

## 8. Offene technische Klärung vor Umsetzung

**Verifiziert (live gegen die echte Clockodo-API, September 2026):**
`userreports[].month_details[].diff` liefert **nicht** den kumulierten
Überstundenstand, sondern nur die Abweichung des einzelnen Monats. Test: der
`diff`-Wert des letzten verfügbaren Monats eines Jahres stimmte bei 29 von 30
geprüften Personen **nicht** mit dem Top-Level-`diff` des `UserReportV1` überein (der
laut OpenAPI-Beschreibung explizit der kumulierte Jahresstand ist) – bei einem
kumulierten Monatsfeld müsste er exakt übereinstimmen.

**Konsequenz für Abschnitt 4:** Der kumulierte Überstundenstand zum Monatsende eines
Zielmonats wird deshalb selbst gebildet: `overtime_carryover` des Jahres (der
Saldo-Übertrag zum Jahresbeginn) plus die Summe aller `month_details[].diff`-Werte
vom ersten Monat des Jahres bis einschließlich des Zielmonats. Das setzt voraus, dass
sich ein Zielmonat und seine Vormonate innerhalb desselben Kalenderjahres befinden,
das über `year` abgefragt wurde – zutreffend, weil `KurzarbeitRepository` je
vorkommendem Jahr der angefragten Monate einen eigenen `/userreports`-Abruf macht.
Fehlt `month_details` für die Person ganz, oder fehlt der Zielmonat darin, bleibt der
Überstundenstand `None` (5.6 – nicht bestimmbar).

## 9. Stand der Umsetzung

Umgesetzt: `domaene.kurzarbeit` (Personenmonat, Rollenzuordnung, Schwellenwerte,
Kurzarbeitsbewertung, `bewerten()`/`bewertungen()`), `clockodo.kurzarbeit`
(`KurzarbeitRepository`, `rollenzuordnung_automatisch()`), das eigenständige
`notebooks/04_kurzarbeit.ipynb` sowie die eigenständige Webapp-Seite `/kurzarbeit` –
beide ohne Bezug zu `Dashboard` (Abschnitt 2/7). Diese Spec ersetzt für die Umsetzung
`spec/spec-ka-intent.md`.
