# Spec: Umsatzprognose – Baustein Schulungsanmeldungen

## 1. Ziel

Den erwarteten Umsatz zukünftiger, öffentlicher Schulungstermine zusätzlich zur
Bestand-Prognose ausweisen. Anders als beim Baustein Bestand ist hier keine Abrufquote
zu schätzen: der erwartete Umsatz je Termin steht in der externen Planungstabelle
bereits fest. Die Unsicherheit liegt nicht im Modell dieses Bausteins, sondern in der
Pflegequalität der Quelle selbst.

## 2. Nicht-Ziele

- Keine Monte-Carlo-Simulation, keine Bandbreite/Konfidenzniveaus für
  Schulungsumsatz – der Wert wird deterministisch aus der Quelle übernommen.
- Keine Auswertung von Teilnehmerzahlen, Rabattstufen, Trainer- oder
  Präsenz/Online-Angaben – nur die Spalte `Umsatz gesamt`.
- Keine automatische Storno-Erkennung. Abgesagte Termine stehen nur als Freitext in
  `Bemerkungen`; das Feld wird nicht geparst. Ein abgesagter Termin mit `Umsatz gesamt
  = 0 €` wirkt sich von selbst nicht aus.
- Keine Verrechnung mit oder Rückwirkung auf den Baustein Bestand (Restvolumen,
  Abrufquote, Kapazitätsdeckel bleiben unberührt).

## 3. Begriffe

- **Schulungstermin:** eine Zeile der Quelltabelle – ein konkreter Termin einer
  Schulung mit erwartetem Gesamtumsatz.
- **Schulungsumsatz (Monat):** Summe von `Umsatz gesamt` aller Schulungstermine eines
  Kalendermonats.
- **Quelle:** eine Google-Sheets-Datei mit dem Tabellenblatt `Öffentliche Schulungen`.
  Es gibt **eine Datei je Jahr** – die Datei-ID ist damit kein feststehender Wert,
  sondern wird je Aufruf angegeben (siehe 5.3).

## 4. Datenmodell aus dem Google Sheet

| Zweck | Zugriff | Relevante Spalten |
|---|---|---|
| Schulungsumsatz je Termin | Google Sheets API (OAuth-Client-ID, kein Service-Account - siehe Abschnitt 5.3), Tabellenblatt `Öffentliche Schulungen` | `Jahr`, `Monat`, `Umsatz gesamt` |

Weitere vorhandene, hier ungenutzte Spalten: `Schulung`, `Trainer`, `Datum`, `TN Zahl`,
diverse Rabattstufen-Spalten (`TN`/`Umsatz` je Rabattart), `Kostenfreie TN`,
`Präsenz/Online`, `Bemerkungen`, sowie eine zweite Spaltengruppe `TN Zahl`, `Max Zahl`,
`Restplätze`, `Auslastung`.

- **Die Kopfzeile steht nicht zuverlässig in Zeile 1.** Der eigentlichen Tabelle kann im
  selben Tabellenblatt noch etwas anderes vorausgehen, das nicht alle Pflichtspalten
  trägt. Die Spaltenzuordnung wird deshalb wie beim Baustein Kosten **inhaltsbasiert**
  ermittelt (erste Zeile, die alle Pflichtspalten enthält), nicht positionsbasiert als
  erste Zeile angenommen.
- **Die Kopfzeile der `Jahr`-Spalte ist nicht verlässlich.** Verifiziert am Jahrgang
  2024: dort steht statt `"Jahr"` ein Vertipper (`"x^"`) in der Kopfzeile. `Jahr` zählt
  deshalb nicht zu den bei der Kopfzeilensuche verlangten Pflichtspalten; ohne eine
  Spalte namens `Jahr` gilt stattdessen **positionsbasiert die erste Spalte des
  Blatts** - dort steht das Jahr unabhängig von ihrer Beschriftung.
- `Jahr` und `Monat` sind getrennte Spalten, nicht kombiniert.
- `Umsatz gesamt` steht im deutschen Zahlenformat mit Euro-Zeichen, uneinheitlich
  formatiert (z. B. `12.345,67 €` oder `1.234,56€`, mit/ohne Leerzeichen vorm
  Eurozeichen). Muss beim Einlesen robust geparst werden (Tausenderpunkt entfernen,
  Komma als Dezimaltrennzeichen, Eurozeichen/Leerzeichen abtrennen).
- `Monat` steht als reine Zahl (1–12, ohne führende Null), nicht als Monatsname
- Zeilen mit `Umsatz gesamt = 0 €` kommen vor (u. a. abgesagte Termine, laut
  Stichprobe rund ein Viertel der Zeilen) und werden wie jede andere Zeile behandelt
  (tragen 0 zur Monatssumme bei).
- Pro Kalenderjahr liegen rund 80 Zeilen vor, 3–13 je Monat.

## 5. Modell

### 5.1 Aggregation je Monat

```
Schulungsumsatz(Jahr, Monat) = Summe(Umsatz gesamt) über alle Zeilen mit
                                passendem Jahr und Monat
```

Keine Sonderbehandlung für Stornos oder Nullzeilen (siehe Nicht-Ziele). Keine automatische Erkennung stornierter Termine

### 5.2 Zeitfenster

Nur Monate **ab dem aktuellen Monat** (Stichtagsmonat, wie der des
Bestand-Bausteins) fließen ein. Vergangene Monate sind bereits über Clockodo als
Ist-Umsatz erfasst; sie hier zusätzlich einzubeziehen, würde Umsatz doppelt ausweisen.

### 5.3 Mehrere Quelldateien

Die Spreadsheet-ID ist **kein fester Wert im Code**, sondern wird aus Colab Secrets bzw. .env (KOSTEN_SHEET_IDS als dict zum Beispie: {2026: %SHEET_ID%, 2027: %SHEET_ID%}) gelesen
 – weil jedes Jahr eine neue Datei angelegt wird. Reicht der Prognosehorizont
über einen Jahreswechsel (z. B. 6-Monats-Prognose im November), werden die entsprechenden Dateien
mehrerer Jahrgänge übergeben; ihre Schulungstermine werden vor der Aggregation
(5.1) zusammengeführt.

**Authentifizierung: kein Service-Account, sondern OAuth-Client-ID.** Google gibt für
diese Anlage keine Service-Account-Keys aus, sondern eine OAuth-Client-ID (Anwendungstyp
"Desktopanwendung"). Deshalb meldet sich in Colab die aufrufende Person über ihr eigenes
Google-Konto an (`google.colab.auth.authenticate_user`, kein JSON nötig - sie braucht
selbst Lesezugriff auf die Trainings-Sheets); lokal startet ein einmaliger interaktiver
Login im Browser auf Basis des Client-JSON aus `GOOGLE_OAUTH_CLIENT_JSON`, dessen Token
danach lokal zwischengespeichert wird.

### 5.4 Verhältnis zur Bestand-Simulation

Der Schulungsumsatz ist **additiv und unabhängig** von der Monte-Carlo-Simulation des
Bestand-Bausteins (`umsatzprognose.domaene.simulation.simulieren()`). Er fließt nicht
in Restvolumen, Abrufquote-Verteilung oder Kapazitätsdeckel ein und verändert keinen
bestehenden Rechenschritt dieses Bausteins.

## 6. Ausgabe

Je Horizontmonat wird der Schulungsumsatz zusätzlich zur Bestand-Bandbreite
ausgewiesen – **sichtbar als eigene Kategorie**, nicht in `Prognose.gebucht()` oder die
Bandbreite eingerechnet:

- Im Diagramm (`diagramme.umsatzverlauf()`): ein eigener, additiver
  Balkenabschnitt „Schulungsanmeldungen" mit eigenem Legendeneintrag und eigener
  Farbe, unten im bestehenden Stapel (gebucht + prognostiziert) gesetzt.
- In der Tabelle (`tabellen.umsatztabelle()`): dieselbe Ergänzung, damit Diagramm und
  Tabelle konsistent bleiben.
- Fehlt eine Quelle für einen Horizontmonat (Datei nicht geladen, kein Termin in dem
  Monat), wird 0 angenommen – kein Fehler, keine Ersatzannahme, aber ein Hinweis für den Leser.

## 7. Verhältnis zur Gesamt-Umsatzprognose

Dieser Baustein ergänzt den Baustein Bestand um eine weitere, von Clockodo unabhängige
Umsatzquelle. Er bleibt getrennt von Pipeline, Kurzfristgeschäft und Cash-Schicht
(siehe Abschnitt 8 der Bestand-Spec) – öffentliche Schulungen sind kein Ersatz für
diese, sondern eine eigene, bereits konkret geplante Größe.

## 8. Stand der Umsetzung

Umgesetzt: `domaene.schulung.Schulungstermin`/`Schulungsplan` (5.1, 5.2, 6), das Paket
`schulungen/` mit `SchulungenRepository` auf Basis der gemeinsamen
Google-Sheets-Infrastruktur in `google_sheets/` (`GoogleSheetsConfig`,
`GoogleSheetsClient`, seit dem Baustein Kosten geteilt mit `kosten/`, siehe
`spec-kosten.md`) (4, 5.3), sowie die additive Darstellung in
`diagramme.umsatzverlauf()`, `tabellen.umsatztabelle()` und `Dashboard.schulungen_laden()`
(6). Die inhaltsbasierte Kopfzeilensuche `schulungen._kopfzeile_finden()` und der
positionsbasierte Rückfall `schulungen._jahr_spalte_ermitteln()` für die `Jahr`-Spalte
(4) decken sowohl `_zeilen_zu_terminen()` als auch `_zeilen_zu_anmeldungen()` (Abschnitt
9) ab.

## 9. Zusatzauswertung: Anmeldungsverlauf (Teilnehmerzahl)

Eine zweite, von der Umsatzprognose unabhängige Auswertung derselben Quelle (Abschnitt
3): nicht der Umsatz, sondern die **Teilnehmerzahl je Schulungstyp und Monat** - Grundlage
für den intern bekannten Verlauf "Anmeldungen bleiben auf niedrigem Niveau". Diese
Auswertung hebt die Nicht-Ziele aus Abschnitt 2 nicht auf; sie ergänzt sie um einen
eigenständigen, rein diagnostischen Blick auf dieselbe Tabelle, ohne dass Umsatz,
Restvolumen, Abrufquote oder Kapazitätsdeckel davon berührt werden.

- **Spalten:** `Jahr` (positionsbasiert, siehe Abschnitt 4), `Monat`, `Schulung`
  (Schulungstyp) und `TN Zahl`. Die Kopfzeile trägt `TN Zahl` laut Abschnitt 4 zweimal -
  einmal als Gesamtsumme direkt vor `Umsatz gesamt`, einmal in der Gruppe mit `Max
  Zahl`/`Restplätze`/`Auslastung`; verifiziert am Jahrgang 2024 tragen beide denselben
  Wert. Gelesen wird die **zuletzt (am weitesten rechts) stehende** Spalte dieses Namens.
- **Zeitfenster:** anders als Abschnitt 5.2 **nicht auf den Prognosehorizont
  beschränkt**, sondern über mehrere zurückliegende Kalenderjahre (Aufruf mit einer
  Jahresliste). Eine Teilnehmerzahl ist kein Umsatz und dupliziert daher nichts aus
  Clockodo - das Doppelzählungsrisiko aus Abschnitt 5.2 entfällt hier.
- **Aggregation:** Summe der Teilnehmerzahl je Monat, wahlweise gesamt, je einzelnem
  Schulungstyp oder je Kategorie (siehe unten).
- **Kategorisierung:** frei konfigurierbar, keine Konstante im Paket - eine
  `dict[str, list[str]]` (Kategoriename -> zugehörige Schulungstypen), die im Notebook
  gepflegt wird (`notebooks/03_schulungsanmeldungen.ipynb`, Zelle "Kategorien
  konfigurieren"; Standardbelegung dort wie in der internen ZDF-Präsentation:
  **Scrum** und **Kanban**). Eine von Hand gepflegte Liste einzelner Schulungstypen,
  keine Stichwortsuche: Zertifizierungen laufen überwiegend über Kürzel (`CSM`, `KSD`,
  `SBK` = "Scrum better with Kanban", ...), nicht über die ausgeschriebenen Wörter
  "Scrum"/"Kanban". Ein Schulungstyp, der in keiner konfigurierten Kategorie auftaucht,
  fällt auf `Sonstige` zurück (`domaene.anmeldung.KATEGORIE_SONSTIGE`).
- **Betrachtungszeitraum:** konfigurierbar, standardmäßig die letzten 13 Kalendermonate
  bis einschließlich des Stichtagsmonats (`Anmeldungsverlauf.letzte(monate=...,
  stichtag=...)` - `monate` keyword-only, damit an der Aufrufstelle lesbar bleibt, was
  die Zahl bedeutet) - unabhängig von der vollständig geladenen, mehrjährigen Historie.
- **Ausgabe:** eine Linie mit Datenpunkten je Kategorie, zusätzlich eine "Gesamt"-Linie
  (Summe aller Kategorien je Monat) und eine lineare Trendlinie (Ausgleichsgerade)
  derselben Gesamtsumme - in derselben dunkelroten Farbe wie die Trendlinie beim
  Kontostand-Chart der Präsentation (dort exponentiell geglättet, hier linear). In
  einem eigenen Notebook, unabhängig vom `Dashboard` der Umsatzprognose.

Umgesetzt: `domaene.anmeldung.Anmeldung`/`Anmeldungsverlauf` (inkl. `letzte()`,
`je_monat_und_kategorie()`, `_kategorie_zuordnung()`), `SchulungenRepository.anmeldungsverlauf_laden()`,
`diagramme.anmeldungsverlauf()` (inkl. `_linearer_trend()`),
`notebooks/setup.anmeldungsverlauf()` und `notebooks/03_schulungsanmeldungen.ipynb`.
