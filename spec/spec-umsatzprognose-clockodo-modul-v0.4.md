# Spec: Umsatzprognose – Baustein Bestand (Clockodo)

**Version:** 0.4
**Stand:** 24.08.2026
**Änderung zu v0.3:** Aufteilungsschlüssel und Zielwerkzeug entschieden.
Verantwortlichkeit bewusst noch offen (siehe Abschnitt 9) – muss vor
produktivem Rollout geklärt sein, nicht vor dem Prototyp.

---

## 1. Ziel

Eine rollierende 1–3-Monats-Prognose des Umsatzes aus laufenden, in Clockodo
angelegten Projekten – mit Bandbreite statt Punktwert, ausschließlich aus
Clockodo-Daten.

Ist ein Projekt in Clockodo angelegt, gilt es als beauftragt. Storno auf
Projektebene ist damit kein Thema. Die zentrale Unsicherheit: **Wie viel vom
beauftragten Volumen wird im Prognosezeitraum tatsächlich abgerufen?**

## 2. Nicht-Ziele im MVP

- Keine Pipeline-Betrachtung, kein Kurzfristgeschäft, keine Cash-Schicht.
- Keine Prognose für Projekte, die noch nicht in Clockodo angelegt sind.

## 3. Begriffe

Unverändert zu v0.3 – siehe dort für Auftragsvolumen, Restvolumen,
Abrufquote, effektiven Stundensatz, verfügbare Kapazität, Referenzklasse,
Konfidenzniveau.

## 4. Datenmodell aus Clockodo

Unverändert zu v0.3:

| Zweck | Endpunkt | Relevante Felder |
|---|---|---|
| Auftragsvolumen | `GET /v4/projects` bzw. `/v4/projects/{id}` | `budget.amount`, `budget.hard` (bei euch `false`) |
| Verbrauchtes Volumen, effektiver Satz | `GET /v2/entrygroups` (Gruppierung nach Projekt) | `revenue`, `hourly_rate` |
| Einzelne Zeit-/Pauschaleinträge | `GET /v2/entries` | `type`, `duration`, `revenue`, `users_id` |
| Sollarbeitszeit je Person | `GET /v3/users` | `default_target_hours` |
| Geplante Abwesenheit | Absence-Endpunkt (Legacy `/api`) | Zeitraum, Art, Person |

## 5. Modell

### 5.1 Restvolumen je Projekt (in Euro)

Unverändert zu v0.3: `budget.amount − revenue_kumuliert` (aus
`entrygroups`), Pauschalleistungen über abgeleiteten effektiven Stundensatz
normalisiert.

### 5.2 Abrufquote-Verteilung

Unverändert.

### 5.3 Kapazitätsdeckel

Unverändert: Sollarbeitszeit minus geplante Abwesenheit minus geschätzter
Abschlag für ungeplante Abwesenheit.

### 5.4 Simulationslogik

Pro Durchlauf (10.000 Läufe), je Monat des Horizonts:

1. Restvolumen (Euro) je Projekt aus Vormonat übernehmen bzw. initialisieren.
2. Abrufquote aus Referenzklassen-Verteilung ziehen → gewünschter
   Euro-Verbrauch im Monat.
3. Über den effektiven Stundensatz in Personentage umrechnen. **Aufteilung
   auf beteiligte Personen: historischer Anteil je Person am jeweiligen
   Projekt** – ermittelt aus den vergangenen Zeiteinträgen (`users_id` je
   Entry, Anteil an Gesamtstunden des Projekts) und unverändert in die
   Zukunft fortgeschrieben. Wechselt die Teambesetzung eines Projekts
   spürbar, veraltet dieser Schlüssel entsprechend – das ist ein
   Kalibrierungsthema (Abschnitt 7), keine Modelländerung.
4. Je Person: Bedarf über alle Projekte gegen verfügbare Kapazität (5.3)
   deckeln, bei Überschreitung anteilig kürzen.
5. Tatsächlich gelieferte Personentage zurück in Euro umrechnen →
   Monatsumsatz je Projekt, summiert.
6. Restvolumen um tatsächlichen Euro-Verbrauch reduzieren.

### 5.5 Ausgabe

Unverändert: 95 % / 85 % / 50 % Konfidenzniveaus je Monat und Summe, plus
Anteil der Fälle mit Kapazität als limitierendem Faktor.

## 6. Referenzklassen

Unverändert.

## 7. Kalibrierung

Unverändert. **Ergänzung:** Da der Aufteilungsschlüssel (5.4, Schritt 3) auf
historischen Anteilen beruht, gehört eine Prüfung auf veraltete
Team-Zusammensetzungen explizit in den monatlichen Kalibrierungs-Check.

## 8. Verhältnis zur Gesamt-Umsatzprognose

Unverändert.

## 9. Offene Punkte

**Geklärt seit v0.3:**

- ~~Aufteilungsschlüssel bei Teamprojekten~~ → historischer Anteil je Person,
  fortgeschrieben (siehe 5.4).
- ~~Zielwerkzeug~~ → Jupyter Notebook in Google Colab.

**Weiterhin offen, bewusst zurückgestellt:**

1. **Verantwortlichkeit:** Wer pflegt die Referenzklassen-Zuordnung und führt
   die monatliche Kalibrierung durch? Muss vor dem produktiven Rollout
   geklärt sein – nicht vor dem Prototyp, da sonst das Risiko besteht, dass
   das Modell nach der ersten Version unbemerkt veraltet (siehe Abschnitt 7).

## 10. Nächste Schritte

1. Prototyp in Google Colab: `/v4/projects` + `/v2/entrygroups` abfragen,
   Restvolumen je Projekt berechnen – als Zwischenschritt vor der vollen
   Monte-Carlo-Logik.
2. Aus vorhandenen historischen Abwesenheitsdaten eine Verteilung für den
   Kapazitätsabschlag (5.3) schätzen.
3. Referenzklassen gegen die tatsächliche Projektlandschaft validieren.
4. Abrufquoten-Verteilungen je Referenzklasse aus `entrygroups`-Historie
   schätzen, Rückwärtstest über 12 Stichtage.
5. Vor produktivem Einsatz: Verantwortlichkeit (9.1) klären.
