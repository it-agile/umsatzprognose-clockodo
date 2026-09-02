# Analyse: Verbrauchsverlauf und Projekt

Ergänzt die vorherige Analyse des Rechenkerns (`simulation.py`) um die beiden
Bausteine, aus denen die Simulation ihre Eingangsgrößen zieht: das Restvolumen samt
Rückrechnung (`domaene/verbrauchsverlauf.py`) und das Projekt als Fachobjekt
(`domaene/projekt.py`).

## `Verbrauchsverlauf` – Rückrechnung und Abrufquoten

### Warum überhaupt zurückgerechnet wird

Clockodo liefert kein historisches Restvolumen, nur den heutigen Budgetstand und den
Verbrauch je Monat. Damit die Abrufquote-Verteilung trotzdem weiß, wie viel Restvolumen
zu einem *vergangenen* Monatsbeginn offen war, rechnet `Verbrauchsverlauf` rückwärts:

    Restvolumen(Monatsbeginn) = heutiges Auftragsvolumen − Verbrauch aller Monate davor

(`restvolumen_zu_monatsbeginn()`, Zeile 111; intern über `verbrauch_vor()`, Zeile 104,
das nur Monate mit `_ordnung(...) < grenze` aufsummiert). Das setzt voraus, dass sich
das Auftragsvolumen seit damals nicht verändert hat – genau das benennt
`Bestand._hinweise_zur_abrufquote()` als Grenze ("nachträglich erhöhte Budgets lassen
ältere Quoten zu niedrig ausfallen").

### Beobachtungsfenster (`beobachtungsmonate()`, Zeile 124)

Das Fenster reicht vom ersten gebuchten Monat bis zu einer Obergrenze, die sich aus
zwei Regeln ergibt:

- Der **Stichtagsmonat zählt nie** – er ist angebrochen (`letzter_vollstaendiger =
  _ordnung(stichtag) - 1`).
- Ein Projekt, das **nicht mehr im Prognose-Scope** ist (inaktiv, abgeschlossen oder
  ohne verwertbares Budget), endet zusätzlich mit seiner letzten Buchung – ein
  beendetes Projekt liefert keine Beobachtungen aus einer Zeit, in der schon länger
  nichts mehr passiert.

Buchungen *nach* dem Stichtag gehören bewusst nicht zur Historie, sondern zum
Horizont (dort tauchen sie über `gebucht()` als Untergrenze wieder auf, siehe unten).

### Von Monaten zu Abrufquoten (`abrufquoten()`, Zeile 144)

Pro Monat im Fenster wird das Restvolumen zu Monatsbeginn und der dortige Verbrauch zu
einer `Abrufquote` (Verbrauch / Restvolumen) verdichtet. Zwei Filterregeln, beide mit
fachlicher Begründung, keine Rundungsdetails:

- **Restvolumen ≤ 0 wird ausgelassen**, nicht als Quote 0 gewertet – eine Quote wäre
  hier undefiniert (Division durch etwas, das schon aufgebraucht oder überschritten
  war), nicht "nichts abgerufen".
- **Quoten > 1 bleiben stehen.** Weiche Budgets (`budget.hard == false`) heißt: in
  einem Monat kann mehr abgerufen werden, als zu Monatsbeginn "offiziell" offen war.
  Gekappt wird das erst in der Simulation, nicht schon in der Beobachtung – sonst
  würde die Verteilung eine reale Überschreitung verschweigen.

Die laufende Summe (`verbraucht`, Zeile 161ff.) läuft einmal linear durchs Fenster statt
je Monat neu zu summieren – bei mehreren tausend Projekt-Monaten und einer Verteilung,
die bei jeder Ansicht neu gebildet wird, ist das kein Selbstzweck.

### Zweitverwendung: `gebucht()` als Untergrenze

Derselbe Verlauf beantwortet in `gebucht(jahr, monat)` (Zeile 92) auch die Frage "was
wurde in diesem Monat real gebucht" – für Monate *nach* dem Stichtag ist das exakt der
Wert, den `simulation.py` als Untergrenze gegen den simulierten Betrag maximiert
(`tatsaechlich = np.maximum(geliefert, gebucht[index])`). Ein Monat ohne Eintrag liefert
hier bewusst `0.0`, nicht `None` – ein Monat ohne Buchung ist eine gültige, aussagekräftige
Beobachtung.

## `Projekt` – Budget, Restvolumen, Stundensatz, Aufteilung

### `Budget` und seine Sonderfälle

`budget.betrag` ist nur dann ein Euro-Gesamtbudget, wenn drei Sonderfälle *nicht*
zutreffen (`Budget.sonderfall`, Zeile 49):

1. `monetaer == False` – der Betrag ist eine Stundenzahl, kein Euro-Betrag (laut
   Docstring nur bei inaktiven Projekten beobachtet).
2. `intervall is not None` – Budget je Intervall (wöchentlich/monatlich/quartalsweise/
   jährlich als Integer-Enum) statt Gesamtbudget.
3. `aus_teilprojekten == True` – das Budget setzt sich aus Teilprojekten zusammen, der
   Top-Level-Betrag ist nicht verwertbar.

Nur wenn keiner dieser Fälle greift, gilt `verwertbar == True` und `auftragsvolumen`
liefert einen Wert statt `None`. Diese Unterscheidung ist die Wurzel dafür, warum
`Bestand.ohne_budget()` und der Hinweis "Aktive Projekte ohne bezifferbares
Auftragsvolumen" existieren – ein gesetzter `betrag` ist nicht automatisch ein
brauchbares Budget.

### Restvolumen: roh vs. prognosewirksam

- `restvolumen_roh` (Zeile 107): `Auftragsvolumen − verbrauchtes_volumen`,
  **vorzeichenbehaftet**. Negativ bedeutet historische Budgetüberschreitung – wird
  nicht verworfen, sondern als Kalibrierungssignal behandelt (siehe
  `anteil_ueber_budget` in `Abrufquotenverteilung`).
- `restvolumen_prognosewirksam` (Zeile 121): dasselbe, aber bei 0 gekappt
  (`max(0.0, roh)`). Die Simulation überschreitet das Budget nie – ein bereits
  überschrittenes Projekt trägt schlicht 0 zur Prognose bei.

Beide sind `None`, wenn kein Auftragsvolumen bezifferbar ist – eine `0` wäre hier eine
andere (falsche) Aussage: "kein Restvolumen" statt "kein Budget bekannt".

### `im_prognose_scope` (Zeile 137)

Drei Bedingungen, **alle** nötig: `aktiv`, **nicht** `abgeschlossen`, und
`budget.verwertbar`. Ein Projekt kann aktiv und mit Budget sein und trotzdem draußen
bleiben, wenn Clockodo es zusätzlich als abgeschlossen markiert (der Hinweis "Projekte,
die als abgeschlossen markiert und trotzdem aktiv sind" in `Bestand` deckt genau diese
Inkonsistenz auf).

### `automatischer_abschluss` (Zeile 146)

Nur gesetzt, wenn `automatic_completion` aktiv ist. Eine reine `deadline` ohne diesen
Schalter ist laut Docstring "unverbindlich" – nur `active`/`completed`/`completed_at`
gelten als zuverlässiges Endesignal. Das ist die Größe, die `simulation._traegt_noch_bei()`
gegen den Horizontmonat prüft (Cutoff monatsweise, nicht taggenau, siehe vorherige
Analyse).

### `effektiver_stundensatz` (Zeile 158)

`verbrauchtes_volumen / verbrauchte_stunden`, mit zwei Besonderheiten:

- Eine manuelle **Übersteuerung** (`stundensatz_uebersteuerung`, gesetzt über
  `Bestand.mit_stundensatz_uebersteuerungen()`) hat immer Vorrang – der Weg, mit dem
  Pauschalprojekte ohne erfasste Zeit oder mit Stundensatz 0 von Hand korrigiert werden
  (siehe Hinweis "Stundensatz 0" in `Bestand`).
  ​- Ohne erfasste Stunden (`verbrauchte_stunden == 0`) liefert die Property `None`,
  nicht `0` oder eine Division durch Null – konsistent mit der Behandlung von `None` als
  "kein Stundenbedarf ableitbar" in der Simulation.

### `anteil_je_mitarbeiter()` (Zeile 170)

Der historische Stundenanteil je Person, aus `anteile` (den `Projektanteil`-Objekten)
berechnet. Ohne erfasste Gesamtstunden liefert die Methode ein **leeres Dict**, nicht
eine Gleichverteilung über die Beteiligten – ein Projekt ohne Zeithistorie bekommt in
der Simulation dadurch auch keine Aufteilungsmatrix-Zeile und trägt (wegen
`hat_satz`/fehlendem Stundensatz meist ohnehin schon) keinen personengebundenen
Kapazitätsbedarf bei.

## Zusammenspiel mit dem Rechenkern

Die drei Analysen ergeben zusammen die vollständige Kette:

`Projekt.budget` → `restvolumen_roh`/`restvolumen_prognosewirksam` (Startvolumen der
Simulation) → `Verbrauchsverlauf.restvolumen_zu_monatsbeginn()` (Rückrechnung für die
Historie) → `Verbrauchsverlauf.abrufquoten()` (Beobachtungen) →
`Abrufquotenverteilung` (portfolioweite empirische Verteilung, aus der die Simulation
zieht) → `simulieren()` (Monte-Carlo-Lauf) → `Verbrauchsverlauf.gebucht()` (Untergrenze
je Horizontmonat, dieselbe Klasse, zweiter Zweck).

Auffällig: **dieselbe Klasse** (`Verbrauchsverlauf`) bedient zwei fachlich getrennte
Fragen – "was ist historisch passiert" (Beobachtungsfenster, Rückrechnung) und "was
steht für den Horizont schon fest" (`gebucht()`). Das ist kein Zufall, sondern folgt
demselben Rohdatensatz (`/v2/entrygroups` mit `grouping[]=projects_id&grouping[]=month`,
siehe CLAUDE.md) – beide Fragen lassen sich aus derselben Monatsreihe beantworten, ohne
zweiten Abruf.

## `Abrufquotenverteilung` – zwei getrennte Berechnungen, leicht zu verwechseln

Die Klasse enthält zwei unterschiedliche "Quantil"-Berechnungen, die auf den ersten
Blick dasselbe zu tun scheinen, aber unterschiedliche Zwecke haben:

### 1. `quantil()` (`abrufquote.py:126`) – beschreibende Kennzahl, nicht Teil der Ziehung

```
stelle = anteil * (len(werte) - 1)
unten = int(stelle)
oben = min(unten + 1, len(werte) - 1)
rest = stelle - unten
return werte[unten] * (1.0 - rest) + werte[oben] * rest
```

Lineare Interpolation zwischen den beiden benachbarten Ordnungsstatistiken der
sortierten Beobachtungen (`_werte`). Liefert `None` bei einer leeren Verteilung (eine
`0` wäre hier "nichts wird abgerufen" und damit eine andere Aussage). Wird für
`median`, `mittelwert`, `anteil_ohne_abruf`, `anteil_ueber_budget` sowie für die
Hinweistexte in `Bestand._hinweise_zur_abrufquote()` gebraucht – **beschreibt** die
Verteilung, **erzeugt aber keine Ziehung** für die Simulation.

### 2. `ziehen()` / `ziehungen()` / `ziehen_array()` (Zeile 175 ff.) – die tatsächliche Ziehung

```
zufall.choice(self._werte_array, size=form)
```

Ein einfaches **Bootstrap mit Zurücklegen**: es wird ein tatsächlich beobachteter Wert
zufällig herausgegriffen, nichts interpoliert, keine Verteilungsannahme (weder Normal-
noch sonst eine parametrische Form). Genau das ist im Modulkopf als Absicht benannt:
"sie kann nichts liefern, was nicht schon einmal vorkam". `ziehen_array()` ist die in
`simulation.py` genutzte Variante – ein Aufruf zieht die Quoten aller Läufe und
Projekte eines Horizontmonats gleichzeitig (Form `(laeufe, len(scope))`), der
Performance-Gewinn kommt vom Vektorisieren über die Läufe, nicht vom Zufallsgenerator
selbst.

**Wichtig für das Verständnis:** Die 95 %/85 %/50 %-Bandbreite am Ende der Simulation
entsteht *nicht* über `Abrufquotenverteilung.quantil()`, sondern über `np.quantile()`
auf die 10.000 simulierten Monats-/Summenwerte (`simulation.py:278`,
`np.quantile(monatssummen[index], 1.0 - niveau)`). Das ist wieder eine lineare
Interpolation (numpys Standardmethode), aber auf einer ganz anderen Zahlenreihe: nicht
auf den rohen Abrufquote-Beobachtungen, sondern auf den Ergebnissen der 10.000 Läufe,
nachdem Kapazitätsdeckel und Restvolumen-Begrenzung bereits eingerechnet sind. Ein
Konfidenzniveau von 0,95 fragt dabei nach dem Wert am 5.-Perzentil (`1.0 - 0.95 =
0.05`) – dem Betrag, den 95 % der Läufe mindestens erreichen.

Kurz: **Eingangsseite** (Abrufquote je Projekt-Monat) wird gezogen, nicht interpoliert;
**Ausgangsseite** (Prognosebandbreite über alle Läufe) wird interpoliert, nicht
gezogen. `quantil()` auf der `Abrufquotenverteilung` selbst dient nur der Beschreibung
der Eingangsverteilung (Median, Hinweistexte), nicht der Berechnung von irgendetwas,
das in die Simulation zurückfließt.
