# Spec: Umsatzprognose – Baustein Bestand (Clockodo)

**Version:** 0.3
**Stand:** 24.08.2026
**Änderung zu v0.2:** Alle vier offenen Punkte aus Abschnitt 9 (v0.2) sind
geklärt, teils direkt anhand der Clockodo-OpenAPI-Spezifikation
(`docs.clockodo.com/openapi.yaml`). Damit ist der Datenzugriff für dieses
Modul vollständig spezifiziert. Verbleibende offene Punkte sind organisatorisch,
nicht mehr datentechnisch.

---

## 1. Ziel

Eine rollierende 1–3-Monats-Prognose des Umsatzes aus laufenden, in Clockodo
angelegten Projekten – mit Bandbreite statt Punktwert, ausschließlich aus
Clockodo-Daten.

Ist ein Projekt in Clockodo angelegt, gilt es als beauftragt. Storno auf
Projektebene ist damit kein Thema. Die zentrale Unsicherheit: **Wie viel vom
beauftragten Volumen wird im Prognosezeitraum tatsächlich abgerufen?**

## 2. Nicht-Ziele im MVP

- Keine Pipeline-Betrachtung, kein Kurzfristgeschäft, keine Cash-Schicht
  (Rechnungsstellung/Zahlungseingang – das ist ein separates Thema, siehe
  Hinweis zu `billed_money` in Abschnitt 4).
- Keine Prognose für Projekte, die noch nicht in Clockodo angelegt sind.

## 3. Begriffe

- **Projekt:** Clockodo-Objekt `project`, mit Budget in Euro (weich, laut
  Prüfung dem beauftragten Volumen entsprechend) und einem aus den
  Zeiteinträgen ableitbaren effektiven Stundensatz.
- **Auftragsvolumen:** `budget.amount` aus `GET /v4/projects/{id}`.
- **Verbrauchtes Volumen:** kumulierte `revenue` aus `GET /v2/entrygroups`
  (gruppiert nach Projekt, Zeitraum = Projektstart bis heute). Diese Kennzahl
  wendet Clockodos eigene Ratenlogik an und schließt Pauschalleistungen ein –
  keine eigene Rekonstruktion aus Einzeleinträgen nötig.
- **Restvolumen:** Auftragsvolumen minus verbrauchtes Volumen, in Euro.
- **Abrufquote:** Anteil des Restvolumens, der im Prognosezeitraum tatsächlich
  verbraucht wird. Zentrale Zielgröße.
- **Effektiver Stundensatz je Projekt:** `hourly_rate` aus
  `GET /v2/entrygroups`, inklusive Pauschalleistungen normalisiert (siehe
  Abschnitt 5.1). Ein Wert je Projekt genügt.
- **Verfügbare Kapazität:** Nettoarbeitstage je Person und Monat, aus
  Sollarbeitszeit abzüglich geplanter und eines geschätzten Anteils
  ungeplanter Abwesenheit (Abschnitt 5.3).
- **Referenzklasse:** Gruppe von Projekten mit vergleichbarem Abrufverhalten.
- **Konfidenzniveau:** Anteil der Simulationsläufe, die mindestens den
  ausgewiesenen Wert erreichen.

## 4. Datenmodell aus Clockodo (mit konkreten Endpunkten)

| Zweck | Endpunkt | Relevante Felder |
|---|---|---|
| Auftragsvolumen | `GET /v4/projects` bzw. `/v4/projects/{id}` | `budget.amount`, `budget.hard` (bei euch `false`), `budget.interval` |
| Verbrauchtes Volumen, effektiver Satz | `GET /v2/entrygroups` (Gruppierung nach Projekt) | `revenue`, `hourly_rate`, `hourly_rate_is_equal_and_has_no_lumpsums` |
| Einzelne Zeit-/Pauschaleinträge | `GET /v2/entries` | `type` (1 Zeit / 2 Pauschalbetrag / 3 Pauschalleistung), `duration`, `revenue`, `hourly_rate`, `billable` |
| Sollarbeitszeit je Person | `GET /v3/users` bzw. `/v4/users/me` | `default_target_hours`, `work_time_regulations_id` |
| Geplante Abwesenheit | Absence-Endpunkt (Legacy `/api`, laut Recherche noch nicht auf v3/v4 migriert) | Zeitraum, Art, Person |
| Rechnungsstatus (nicht Teil dieses Bausteins, aber angrenzend) | `GET /v4/projects` | `billed_money`, `billed_completely` |

**Wichtiger Klarstellungspunkt:** `revenue_factor` (Feld am Projekt) ist nur
bei harten Budgets ungleich 1 und bildet eine rückwirkende Kappung ab. Da
eure Budgets weich sind, ist dieser Faktor bei euch immer `1` – er darf nicht
mit dem Restvolumen verwechselt werden und ist für dieses Modul irrelevant.

**Historientiefe:** Ist-Zeiten seit 2021 vorhanden – ausreichend für die
Kalibrierung (Abschnitt 7).

## 5. Modell

### 5.1 Restvolumen je Projekt (in Euro)

```
Restvolumen(Projekt, t) = budget.amount(Projekt)
                         − revenue_kumuliert(Projekt, Projektstart bis t)
```

`revenue_kumuliert` wird über `GET /v2/entrygroups` mit `time_since` =
Projektstart und `time_until` = t abgefragt. Das Feld deckt sowohl
zeitbasierte als auch Pauschal-Einträge ab.

**Pauschalleistungen:** Einträge mit `type = 2` (Pauschalbetrag) oder
`type = 3` (Pauschalleistung) werden über `GET /v2/entries` identifiziert.
Für jede Pauschalleistung wird ein effektiver Stundensatz aus gebuchter Zeit
und Pauschalbetrag berechnet (`Pauschalbetrag / gebuchte Stunden`); für die
Simulation wird angenommen, dass künftig vergleichbare Pauschalleistungen im
selben Stundenumfang anfallen wie historisch beobachtet. Damit fließen
Pauschalleistungen ohne separaten Modellzweig in dieselbe Euro/Personentage-
Logik ein wie zeitbasierte Leistungen.

Da kein Enddatum existiert, erkennt das Modell ein auslaufendes Projekt
weiterhin ausschließlich am sinkenden Restvolumen.

### 5.2 Abrufquote-Verteilung

Unverändert: je Referenzklasse eine empirische Verteilung, wie viel Prozent
des zu Monatsbeginn verbleibenden Restvolumens historisch im Monat verbraucht
wurde.

### 5.3 Kapazitätsdeckel (mit Unsicherheitsabschlag)

Nettoarbeitstage = Sollarbeitszeit − eingetragene geplante Abwesenheiten −
ein aus historischen Daten geschätzter Abschlag für ungeplante Abwesenheit.
Historische Daten für diese Schätzung sind vorhanden (siehe Abschnitt 10,
nächste Schritte, für das konkrete Vorgehen).

### 5.4 Simulationslogik

Pro Durchlauf (10.000 Läufe), je Monat des Horizonts:

1. Restvolumen (Euro) je Projekt aus Vormonat übernehmen bzw. via 5.1
   initialisieren.
2. Abrufquote aus Referenzklassen-Verteilung ziehen → gewünschter
   Euro-Verbrauch im Monat.
3. Über den projektspezifischen effektiven Stundensatz (`hourly_rate` aus
   `entrygroups`) in Personentage umrechnen, auf beteiligte Personen
   aufteilen (Aufteilungsschlüssel: weiterhin offen, Abschnitt 9).
4. Je Person: Bedarf über alle Projekte gegen verfügbare Kapazität (5.3)
   deckeln, bei Überschreitung anteilig kürzen.
5. Tatsächlich gelieferte Personentage zurück in Euro umrechnen →
   Monatsumsatz je Projekt, summiert.
6. Restvolumen um tatsächlichen Euro-Verbrauch reduzieren.

### 5.5 Ausgabe

Unverändert: 95 % / 85 % / 50 % Konfidenzniveaus je Monat und Summe, plus
Anteil der Fälle mit Kapazität als limitierendem Faktor.

## 6. Referenzklassen

Unverändert:

- Laufendes Coaching-/Beratungsmandat (Bestandskund:in)
- Neues Projekt bei Bestandskund:in
- Neukund:in
- Abruf aus Rahmenvertrag

## 7. Kalibrierung

Unverändert. Aktiv/Archiviert-Status (`active`, `completed`, `completed_at`
aus `/v4/projects`) markiert rückwirkend zuverlässig, wann ein Projekt real
endete.

## 8. Verhältnis zur Gesamt-Umsatzprognose

Unverändert: Dieser Baustein deckt nur den Umsatz aus bereits in Clockodo
angelegten Projekten ab.

## 9. Offene Punkte

Alle vier datentechnischen Punkte aus v0.2 sind geklärt. Verbleibend, rein
organisatorisch:

1. **Aufteilungsschlüssel bei Teamprojekten:** Nach welcher Logik wird der
   gezogene Monatsbedarf auf mehrere beteiligte Personen verteilt?
2. **Zielwerkzeug:** Python/Notebook, Excel, oder direkt auf Basis der
   API/des offiziellen Clockodo-MCP-Servers (`mcp.clockodo.com`)?
3. **Verantwortlichkeit:** Wer pflegt die Referenzklassen-Zuordnung und führt
   die monatliche Kalibrierung durch?

## 10. Nächste Schritte

1. Aufteilungsschlüssel (9.1) und Zielwerkzeug (9.2) entscheiden.
2. Aus den vorhandenen historischen Abwesenheitsdaten eine Verteilung für den
   Kapazitätsabschlag (Abschnitt 5.3) schätzen.
3. Referenzklassen gegen die tatsächliche Projektlandschaft validieren.
4. Abrufquoten-Verteilungen je Referenzklasse aus `entrygroups`-Historie
   schätzen, Rückwärtstest über 12 Stichtage.
5. Prototyp bauen: `/v4/projects` + `/v2/entrygroups` liefern bereits die
   beiden zentralen Größen (Budget, kumulierter Verbrauch) in vergleichsweise
   wenigen API-Aufrufen – ein erster Restvolumen-Report ist ohne Simulation
   schnell umsetzbar und eignet sich als Zwischenschritt vor der vollen
   Monte-Carlo-Logik.
