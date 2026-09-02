# Spec: Umsatzprognose – Baustein Kosten

## 1. Ziel

Der Umsatzprognose (Baustein Bestand, additiv Baustein Schulungsanmeldungen) eine
Kostenprognose gegenüberstellen, um daraus den **Gewinn** je Monat abzuleiten. Wie bei
den Schulungsanmeldungen ist keine Simulation nötig: die Gesamtkosten je Monat stehen
in einer externen Planungstabelle bereits fest.

## 2. Nicht-Ziele

- Keine Monte-Carlo-Simulation, keine Bandbreite/Konfidenzniveaus für Kosten – der
  Wert wird deterministisch aus der Quelle übernommen.
- Keine Aufschlüsselung nach Kostenart (Reisekosten, Personalkosten, Sonstiges, …) –
  nur die Spalte `Gesamtkosten`.
- Kein eigenes Domänenobjekt, das Umsatz und Kosten gegeneinander verrechnet. Der
  Gewinn wird ausschließlich in der Darstellungsschicht gebildet
  (`tabellen.umsatztabelle()`, `diagramme.umsatzverlauf()`).
- Keine Verrechnung mit oder Rückwirkung auf den Baustein Bestand (Restvolumen,
  Abrufquote, Kapazitätsdeckel bleiben unberührt).

## 3. Begriffe

- **Kostenposten:** eine Zeile der Quelltabelle – die Gesamtkosten eines
  Kalendermonats.
- **Quelle:** dieselbe jährliche Google-Sheets-Datei wie beim Baustein
  Schulungsanmeldungen (`TRAINING_SHEET_ID`), aber ein anderes Tabellenblatt:
  `Kosten {jahr}`.

## 4. Datenmodell aus dem Google Sheet

| Zweck | Zugriff | Relevanter Bereich |
|---|---|---|
| Gesamtkosten je Monat | Google Sheets API (dieselben Zugangsdaten wie Schulungsanmeldungen, siehe `spec-schulungsanmeldungen.md` Abschnitt 5.3), Tabellenblatt `Kosten {jahr}` | Zellbereich `L3:R15`, Spalten `Monat` und `Gesamtkosten` |

- Zeile 3 des Bereichs ist die Kopfzeile, Zeile 4–15 sind die zwölf Monate des Jahres.
  Spalten werden wie bei den Schulungsanmeldungen **über die Kopfzeile namentlich**
  zugeordnet, nicht über die Position – robust gegenüber der Reihenfolge der Spalten
  innerhalb L:R (weitere, hier ungenutzte Spalten wie Reisekosten oder
  Personalkosten liegen dazwischen).
- `Monat` steht als ausgeschriebener deutscher Monatsname (`Januar`…`Dezember`),
  anders als bei den Schulungsanmeldungen, wo `Monat` eine Zahl ist.
- `Gesamtkosten` steht im selben deutschen Zahlenformat mit Euro-Zeichen wie `Umsatz
  gesamt` bei den Schulungsanmeldungen und wird mit derselben Logik geparst
  (`domaene.zahlen.euro_parsen()`).

## 5. Modell

### 5.1 Aggregation je Monat

```
Kosten(Jahr, Monat) = Gesamtkosten der Zeile mit passendem Monat im Tabellenblatt
                       Kosten {Jahr}
```

### 5.2 Zeitfenster – Unterschied zu den Schulungsanmeldungen

**Anders als beim Baustein Schulungsanmeldungen gilt die Kostenprognose auch für
bereits vergangene und den laufenden Monat**, nicht nur für den Prognosehorizont:
Clockodo liefert keine Ist-Kosten, nur Umsätze aus Einsätzen – es gibt also keine
andere Quelle für die Vergangenheit. `Kostenplan` filtert deshalb, anders als
`Schulungsplan`, nicht nach einem Stichtag; welche Monate gebraucht werden,
bestimmt allein der Aufrufer über die an `Kostenplan.kosten_je_monat()` übergebenen
Monate.

`KostenRepository.laden()` deckt entsprechend sowohl die Monate der bereits geladenen
Umsatzhistorie als auch den Prognosehorizont ab (Parameter `historie_monate` bzw.
`stichtag`/`horizont_monate`).

### 5.3 Mehrere Quelldateien

Wie bei den Schulungsanmeldungen (`spec-schulungsanmeldungen.md` Abschnitt 5.3): die
Spreadsheet-ID kommt aus `TRAINING_SHEET_ID`, eine Datei je Jahr. Reichen die
benötigten Monate (Historie und/oder Prognosehorizont) über einen Jahreswechsel,
werden die Dateien mehrerer Jahrgänge gelesen und ihre Kostenposten vor der
Aggregation zusammengeführt.

### 5.4 Verhältnis zur Bestand-Simulation und zu den Schulungsanmeldungen

Die Kostenprognose ist **additiv und unabhängig** von der Monte-Carlo-Simulation des
Bestand-Bausteins und vom Baustein Schulungsanmeldungen. Sie fließt nicht in
Restvolumen, Abrufquote-Verteilung oder Kapazitätsdeckel ein und verändert keinen
bestehenden Rechenschritt dieser Bausteine.

## 6. Ausgabe

Je Monat (Historie **und** Prognosehorizont) werden Kosten und Gewinn zusätzlich zur
bestehenden Umsatzdarstellung ausgewiesen:

- Im Diagramm (`diagramme.umsatzverlauf()`): eine eigenfarbige Linie „Kosten" über die
  volle Breite (Historie und Prognosehorizont), mit eigenem Legendeneintrag. Anders als
  die additiven Balkenabschnitte hat die Kostenlinie keine eigene Bandbreite – der Wert
  steht fest. Der Gewinn wird nicht separat gezeichnet; er ist visuell die Lücke
  zwischen Umsatzbalken und Kostenlinie.
- In der Tabelle (`tabellen.umsatztabelle()`): zwei zusätzliche Spalten „Kosten" und
  „Gewinn" (Summe aus Umsatz, Schulungsanmeldungen und Kosten). Gewinn wird gegen den
  **Gesamtumsatz** gerechnet (Bestand-Prognose plus Schulungsanmeldungen).
- Fehlt eine Quelle für einen benötigten Monat (Datei nicht geladen, kein Kostenposten
  in dem Monat), wird 0 angenommen – kein Fehler, keine Ersatzannahme, aber ein
  Hinweis für den Leser.

## 7. Verhältnis zur Gesamt-Umsatzprognose

Dieser Baustein stellt den bestehenden Umsatzbausteinen (Bestand, Schulungsanmeldungen)
eine Kostenseite gegenüber. Er bleibt getrennt von Pipeline, Kurzfristgeschäft und
Cash-Schicht (siehe Abschnitt 8 der Bestand-Spec) – die Kostenprognose ist kein Ersatz
für diese, sondern eine eigene, bereits extern geplante Größe.

## 8. Stand der Umsetzung

Umgesetzt: `domaene.kosten.Kostenposten`/`Kostenplan` (5.1, 5.2, 6), das Paket
`kosten/` mit `KostenRepository` (4, 5.3) auf Basis der gemeinsamen
Google-Sheets-Infrastruktur in `google_sheets/`, sowie die additive Darstellung in
`diagramme.umsatzverlauf()` und `tabellen.umsatztabelle()` (6). Der `Kostenplan` wird,
wie der `Schulungsplan`, in `Dashboard.laden()`/`laden_async()` mitgeladen.
