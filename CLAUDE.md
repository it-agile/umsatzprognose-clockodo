# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status des Repositories

Dieses Repository enthält **noch keinen Code** – ausschließlich die Spezifikation
`spec/spec-umsatzprognose-clockodo-modul-v0.4.md`. Es gibt kein Git-Repository, keine
Build-, Test- oder Lint-Konfiguration und keine Abhängigkeitsdeklaration. Entsprechend
existieren keine Build-/Test-Kommandos, die hier dokumentiert werden könnten.

Vor dem Erfinden von Struktur: Zielwerkzeug ist laut Spec (Abschnitt 9) ein
**Jupyter Notebook in Google Colab**, nicht ein Paket oder Service. Neue Artefakte
sollten dieser Entscheidung folgen, solange sie nicht explizit revidiert wird.

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
2. Abrufquote je Monat aus der Verteilung der **Referenzklasse** des Projekts ziehen
   → gewünschter Euro-Verbrauch.
3. Über den effektiven Stundensatz in Personentage umrechnen und auf Personen aufteilen –
   Schlüssel ist der **historische Anteil je Person am jeweiligen Projekt** (`users_id`
   je Entry, Anteil an den Gesamtstunden), unverändert in die Zukunft fortgeschrieben.
4. Je Person Bedarf über **alle** Projekte gegen die verfügbare Kapazität deckeln; bei
   Überschreitung anteilig kürzen. Der Deckel ist projektübergreifend, nicht pro Projekt.
5. Gelieferte Personentage zurück in Euro → Monatsumsatz je Projekt.
6. Restvolumen um den tatsächlichen Euro-Verbrauch reduzieren, in den nächsten Monat
   übertragen.

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
| Verbrauch, effektiver Satz | `GET /v2/entrygroups` (nach Projekt gruppiert) | `revenue`, `hourly_rate` |
| Einzeleinträge | `GET /v2/entries` | `type`, `duration`, `revenue`, `users_id` |
| Sollarbeitszeit | `GET /v3/users` | `default_target_hours` |
| Geplante Abwesenheit | Absence-Endpunkt (Legacy `/api`) | Zeitraum, Art, Person |

`budget.hard` ist in dieser Installation `false` – Budgets sind also weiche Grenzen und
dürfen im Modell nicht als harte Kappung behandelt werden.

## Kalibrierung als Teil des Modells

Zwei Größen sind geschätzt und veralten: die Referenzklassen-Zuordnung der Projekte und
der historische Aufteilungsschlüssel je Person. Wechselt die Teambesetzung eines Projekts
spürbar, wird der Schlüssel falsch. Die Spec ordnet das ausdrücklich der monatlichen
Kalibrierung zu und **nicht** einer Modelländerung – bei Abweichungen also zuerst die
Kalibrierung prüfen, nicht die Simulationslogik umbauen.

## Wichtige Einschränkung der Spec-Datei

v0.4 ist ein Delta-Dokument: viele Abschnitte (Begriffe, Abrufquote-Verteilung,
Referenzklassen, Kalibrierung, Verhältnis zur Gesamtprognose) stehen dort nur als
„Unverändert zu v0.3“. **v0.3 liegt nicht im Repository.** Fehlen für eine Aufgabe
Details – etwa die konkrete Form der Abrufquote-Verteilung oder die Definition der
Referenzklassen – sind sie hier nicht auffindbar; dann beim Nutzer nachfragen statt
plausible Werte zu erfinden.

Offen und bewusst zurückgestellt: Verantwortlichkeit für Referenzklassen-Pflege und
monatliche Kalibrierung. Blockiert den produktiven Rollout, nicht den Prototyp.

## Nächster geplanter Schritt

Laut Spec Abschnitt 10: Prototyp in Colab, der `/v4/projects` und `/v2/entrygroups`
abfragt und das Restvolumen je Projekt berechnet – als Zwischenschritt **vor** der
vollen Monte-Carlo-Logik.
