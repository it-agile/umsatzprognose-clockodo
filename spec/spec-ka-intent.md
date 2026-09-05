---
type: Feature Intent
title: Kurzarbeitsbereitschaft aus Arbeitszeitdaten bewerten
description: Rückblickende Bewertung, ob die Organisation in einem abgeschlossenen Monat die Voraussetzungen für Kurzarbeit erfüllt hätte.
tags: [kurzarbeit, kapazitaet, auslastung, clockodo, mvp]
status: draft
created: 2026-09-04
---

# Intent: Kurzarbeitsbereitschaft bewerten

## Problem

Wir können heute nicht aus den vorhandenen Arbeitszeitdaten ablesen, ob genügend
Mitarbeitende für Kurzarbeit infrage gekommen wären. Dadurch fehlt ein belastbares,
rückblickendes Signal dafür, wie vorbereitet die Organisation auf Kurzarbeit gewesen
wäre.

## Gewünschtes Ergebnis

Das Dashboard zeigt für mindestens den zuletzt vollständig abgeschlossenen
Kalendermonat, ob die Kurzarbeitsbereitschaft nach den unten definierten Regeln
erfüllt gewesen wäre. Es macht nachvollziehbar, welche Bedingung erfüllt oder
verfehlt wurde, ohne eine arbeitsrechtliche Zusage oder Beratung zu ersetzen.

## MVP: Rückblickende Bewertung

### Bezugszeitraum

- Standardmäßig wird der letzte vollständig abgeschlossene Kalendermonat bewertet.
- Die Auswertung soll auch für weitere vergangene, vollständig abgeschlossene Monate
  abrufbar sein.
- Der laufende Monat wird nicht bewertet, weil seine Arbeitszeit noch unvollständig
  ist.

### Personenkreis

- Mini-Jobber zählen mit.
- **Alle Mitarbeitenden**, einschließlich Geschäftsführung und Vertrieb, zählen in den
  Nenner der 30-%-Quote.
- Geschäftsführung und Vertrieb können nicht als kurzarbeitsfähig in den Zähler
  eingehen.
- Die Auswertung verwendet nur Personen, deren Beschäftigungsstatus im jeweiligen
  historischen Monat nachvollziehbar ist.

### Regel für eine als kurzarbeitsfähig geltende Person

Eine Person gilt im betrachteten Monat als **kurzarbeitsfähig**, wenn beide Bedingungen
erfüllt sind:

1. Ihr Anteil interner Arbeit beträgt mindestens 24 % ihrer erfassten Arbeitszeit im
   Monat.
2. Ihr kumulierter Überstundenstand zum Ende des Monats liegt unter 14 Stunden.

Die 24-%-Schwelle ist bewusst doppelt so hoch wie die angestrebten 12 % Kurzarbeit:
Mindestens die Hälfte der internen Arbeit soll realistisch durch Kurzarbeit ersetzbar
sein. Die relevante Rechnung lautet damit:

```text
Anteil interne Arbeit = interne gebuchte Stunden / alle gebuchten Arbeitsstunden
kurzarbeitsfähig wegen interner Arbeit = Anteil interne Arbeit >= 24 %
```

Für einzelne Personen soll es nicht erkennbar sein, ob sie an der Schwelle für interne Arbeit oder am
Überstundenstand scheitert. Die Darstellung von Namen oder Einzelwerten folgt den im
Projekt geltenden Zugriffs- und Datenschutzregeln.

### Regel für die Organisation

Die Organisation gilt für den Monat als **vorbereitet**, wenn die kurzarbeitsfähigen
Personen mindestens 30 % aller Mitarbeitenden ausmachen. Geschäftsführung und Vertrieb
sind damit Teil des Nenners, aber nie Teil des Zählers:

```text
Quote kurzarbeitsfähiger Personen =
  Anzahl kurzarbeitsfähiger Personen /
  Anzahl aller Mitarbeitenden einschließlich Geschäftsführung und Vertrieb

vorbereitet = Quote kurzarbeitsfähiger Personen >= 30 %
```

Das Ergebnis enthält mindestens:

- Status: „Voraussetzung erfüllt“ oder „Voraussetzung nicht erfüllt“;
- Anteil und Anzahl kurzarbeitsfähiger Personen;
- Vergleich mit der 30-%-Schwelle;
- Anzahl der Personen, die jeweils an der internen Arbeit, den Überstunden oder an
  beiden Bedingungen scheitern;
- verständliche Hinweise bei unvollständigen oder nicht zuordenbaren Daten.

## Betroffene Nutzer und Systeme

- Führung und Geschäftsleitung erhalten ein steuerndes Rückblick-Signal.
- Clockodo ist die Quelle für Zeitbuchungen, Personen und – sofern fachlich
  ausreichend ableitbar – Sollarbeitszeit und Überstunden.
- Die bestehende Domänen-, Clockodo- und Darstellungsschicht dieses Repositories sind
  betroffen.

## Daten- und Qualitätsanforderungen

- Nicht abrechenbare Clockodo-Zeit gilt als interne Arbeit; abrechenbare Zeit gilt als
  externe Arbeit. Eine nicht klassifizierbare Buchung wird sichtbar als Hinweis
  behandelt und nicht stillschweigend intern oder extern gezählt.
- Der Überstundenwert ist der kumulierte Saldo zum Monatsende, nicht nur die Differenz
  des betrachteten Monats. Die Berechnung muss daher die Zeiterfassung und
  Sollarbeitszeit bis zu diesem Stichtag berücksichtigen.
- Es werden keine aus Clockodo gelesenen Personen-, Stunden- oder Geschäftsdaten in
  Repository-Dateien gespeichert oder committet.
- Die Berechnung ist je Monat reproduzierbar: Zeitraum, Grundgesamtheit, Zähler,
  Nenner und verwendete Schwellen sind in der Ausgabe oder ihren Details ersichtlich.
- Tests decken mindestens die Schwellenwerte 24 %, 30 % und 14 Stunden sowie fehlende
  oder unklassifizierte Daten ab.

## Nicht-Ziele des MVP

- Keine arbeitsrechtliche Bewertung oder Entscheidung über die tatsächliche Einführung
  von Kurzarbeit.
- Keine Prognose für zukünftige Monate.
- Keine automatische Kommunikation oder individuelle Maßnahme für Mitarbeitende.
- Keine dauerhafte Speicherung von aus der Auswertung gewonnenen Personaldaten.
- Bekannte, noch nicht vollzogene Abgänge werden im MVP nicht gesondert berücksichtigt.
  Die Auswertung kann dadurch die tatsächliche Kurzarbeitsbereitschaft überschätzen.

## Spätere Ausbaustufe: Blick nach vorn

Nach dem MVP kann eine **Vorbereitungsprognose** untersucht werden. Sie soll nicht
behaupten, Kurzarbeit rechtssicher vorherzusagen, sondern ein Frühwarnsignal liefern.
Mögliche Eingaben sind der aktuelle Überstundenstand, der Trend interner Arbeit und
die vorhandene Umsatz-/Auslastungsprognose. Die Methodik und ihre Unsicherheit müssen
vor Umsetzung separat fachlich abgestimmt werden.

Ein naheliegender erster Verbesserungsschritt ist, bekannte Abgänge als separaten,
nicht kurzarbeitsfähigen Personenkreis auszuweisen. Falls die Kostenplanung die
Abgänge mit einem wirksamen Datum ausreichend verlässlich enthält, kann sie dafür eine
Quelle sein. Vor einer solchen Anbindung müssen Datenqualität, Zugriff und die fachlich
gültige Bedeutung eines Abgangs geklärt werden.

## Offene Fragen 

1. Wie werden Minusstunden bei der Regel „Überstundenstand unter 14 Stunden“ behandelt?
2. Sollen Urlaub, Krankheit und sonstige Abwesenheiten beim Nenner der 24-%-Quote
   unberücksichtigt bleiben, indem nur tatsächlich gebuchte Arbeitszeit zählt?
3. Wie werden Neueintritte, Austritte und Personen ohne vollständige Buchungen im
   betrachteten Monat behandelt: ausschließen, als nicht kurzarbeitsfähig werten oder
   separat ausweisen?

Für ein MVP könne hier erstmal vereinfachte Annahmen getroffen werden.

## Erfolgskriterien

- Für jeden vollständig abgeschlossenen Monat ist ohne manuelle Tabellenrechnung
  erkennbar, ob die 30-%-Regel erfüllt gewesen wäre.
- Die Herleitung jeder Kennzahl ist fachlich nachvollziehbar.
- Unvollständige Daten führen zu einem sichtbaren Hinweis statt zu einem scheinbar
  verlässlichen Ergebnis.
