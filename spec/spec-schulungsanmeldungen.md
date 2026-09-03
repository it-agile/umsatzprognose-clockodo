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
(6).
