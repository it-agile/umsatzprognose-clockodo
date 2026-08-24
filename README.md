# Umsatzprognose – Baustein Bestand (Clockodo)

Rollierende 1–3-Monats-Prognose des Umsatzes aus laufenden, in Clockodo angelegten
Projekten – als Bandbreite (95 % / 85 % / 50 %), nicht als Punktwert.

Maßgeblich ist die Spezifikation: [`spec/spec-umsatzprognose-clockodo-modul.md`](spec/spec-umsatzprognose-clockodo-modul.md).
Sie trägt keine Versionsnummer im Namen – die Fassung ist der Git-Tag, der auf den
Commit zeigt (`git describe`). Frühere Fassungen liegen nicht im Verzeichnis, sondern in
der Historie.

## Stand

Prototyp-Phase. Umgesetzt ist der Datenzugriff nach Spec Abschnitt 4, der Prognose-Scope
(5.0), das Restvolumen je Projekt (5.1) und das vollständige Domänenmodell außer der
Simulation – inklusive Aufteilungsschlüssel je Person (5.4 Schritt 3) und
Sollarbeitszeit (Teil von 5.3). Das Dashboard zeigt den Umsatz der letzten zwölf Monate
und das offene Auftragsvolumen.

Die Monte-Carlo-Simulation (5.4) ist noch nicht gebaut. Offen sind dafür die Schätzung
der Abrufquote-Verteilung (5.2 legt ihre Form fest, die Zahlen fehlen), die verfügbare
Kapazität (5.3, es fehlen die Abwesenheiten) und die Untergrenze aus bereits gebuchten
Beträgen im Horizont (5.4). Referenzklassen sind zurückgestellt und blockieren nichts. Das Dashboard zeigt an der Stelle der Bandbreite
diese Begründung an, statt eine Zahl zu erfinden.

## Setup

Voraussetzung ist [uv](https://docs.astral.sh/uv/). Die Python-Version ist über
`.python-version` auf 3.13 festgelegt – uv lädt sie bei Bedarf selbst. 3.13, weil
Google Colab darauf läuft (am 24.08.2026 in einem Colab-Traceback verifiziert) und das
Notebook dort ausgeführt wird. `requires-python` ist `>=3.13` ohne Obergrenze, damit ein
Colab-Upgrade die Installation nicht bricht.

```bash
uv sync --extra notebook
```

Zugangsdaten aus `.env.sample` nach `.env` kopieren und ausfüllen. Die Clockodo-API
verlangt drei Header, entsprechend braucht es vier Werte: API-Benutzer (E-Mail),
API-Key sowie Name und Kontakt-E-Mail der aufrufenden Anwendung. Den API-Key findet
jede Person in Clockodo unter „Persönliche Daten“.

## Kommandos

```bash
uv run pytest                  # Tests
uv run ruff check .            # Lint
uv run ruff format .           # Formatierung
uv run jupyter lab             # Notebooks lokal
```

## Aufbau

Das Paket bildet den Gegenstand ab – Kunde, Projekt, Mitarbeiter, Umsatz – und ist in
drei Schichten geschnitten, mit genau einer erlaubten Abhängigkeitsrichtung:

```
darstellung  ──►  domaene  ◄──  clockodo
```

- `src/umsatzprognose/domaene/` – die Fachobjekte, unveränderlich und ohne
  Bibliotheksabhängigkeit: `Projekt` und `Budget` (Restvolumen nach Spec 5.1, effektiver
  Stundensatz), `Kunde`, `Mitarbeiter`, `Projektanteil` (der Aufteilungsschlüssel aus
  5.4), `Umsatzhistorie` und `Bestand` als Aggregat. Kennt weder JSON noch HTTP.
- `src/umsatzprognose/clockodo/` – Zugriff auf die API und Übersetzung ihrer Antworten
  in Fachobjekte. Hier steht alles, was über die Eigenheiten dieser API bekannt ist.
- `src/umsatzprognose/darstellung/` – Diagramme (plotly), Tabellen (pandas) und die
  Fassade `Dashboard`, die die Notebooks benutzen.
- `tests/` – pytest.
- `notebooks/` – `01_dashboard.ipynb` für Fachexperten (je Zelle ein Aufruf,
  Fachsprache, keine technischen Details) und `02_technik_restvolumen.ipynb` für die
  Entwicklung (Prüfsummen, Datenlage, offene fachliche Fragen). Rechenlogik gehört ins
  Paket, nicht ins Notebook.
- `spec/` – Spezifikation.

Der übliche Einstieg ist eine Zeile:

```python
from umsatzprognose import Dashboard

dashboard = Dashboard.laden()
dashboard.umsatzverlauf()
```

## Deployment (Google Colab)

Es gibt keinen Server und keinen Build-Artefakt-Upload. Zielwerkzeug laut Spec
(Abschnitt 9) ist ein Notebook in **Google Colab**; „deployen“ heißt hier: den Stand
nach GitHub pushen und das Notebook in Colab gegen diesen Stand laufen lassen. Die
Prognose wird manuell ausgeführt, es gibt keinen Scheduler.

Das Repository `it-agile/umsatzprognose-clockodo` ist **öffentlich**. Damit brauchen
weder Colab noch `pip` ein GitHub-Token. Umgekehrt gilt: alles, was hier committet wird,
ist weltweit lesbar – Zugangsdaten gehören ausschließlich in `.env` (gitignored) bzw. in
die Colab-Secrets, niemals in eine Notebook-Zelle oder eine Zellausgabe.

### 1. Stand veröffentlichen

Colab installiert aus GitHub, nicht aus dem lokalen Arbeitsverzeichnis. Was nicht
gepusht ist, existiert für Colab nicht:

```bash
uv run pytest && uv run ruff check .
git push origin main
```

Für nachvollziehbare Läufe einen Tag setzen – dann ist später belegbar, welche
Modellversion eine Prognose erzeugt hat:

```bash
git tag -a v0.1.0 -m "Restvolumen je Projekt (Spec 5.1)"
git push origin v0.1.0
```

### 2. Notebook in Colab öffnen

In Colab unter *Notebook öffnen → GitHub* das Repository angeben und
`notebooks/01_dashboard.ipynb` öffnen (für die Entwicklung:
`notebooks/02_technik_restvolumen.ipynb`). Da das Repository öffentlich ist, braucht
Colab dafür keine GitHub-Autorisierung.

**Nach einer Notebook-Änderung im Repository muss das Notebook hier neu geladen
werden.** Die Installationszelle erneuert das Paket, nie die `.ipynb`. Erkennbar ist der
Fall an der ersten Ausgabe: sie nennt den Stand der Zelle. Fehlt sie, ist das Notebook
alt.

Alternativ Notebook-Datei herunterladen und in Colab hochladen, oder über Google Drive
einbinden. Funktional gleichwertig, nur ohne Verknüpfung zum Repository – Änderungen
müssen dann manuell zurückgeführt werden.

### 3. Paket in Colab installieren

Das lokale venv steht in Colab nicht zur Verfügung, deshalb beginnt jedes Notebook mit
einer Installationszelle, die nur dort greift. Sie installiert das Paket direkt aus
GitHub; die Abhängigkeiten kommen als Requirements mit. Ein Token ist nicht nötig.

Wichtig nach einem Push: in Colab die **Runtime neu starten** und die Zelle erneut
ausführen. Ohne Neustart bleibt das zuvor installierte Paket im Runtime aktiv, und
Korrekturen wirken nicht.

Der Neustart allein genügt aber nicht. Die Versionsnummer des Pakets ändert sich mit
einem Commit nicht, und **`pip install git+…@main` lässt einen bereits installierten
Stand deshalb unangetastet** – es meldet keinen Fehler, installiert aber auch nichts;
`--upgrade` ändert daran nichts (am 24.08.2026 nachgestellt: erst der alte Commit,
dann `@main`, danach fehlten die neuen Module weiterhin und der Import scheiterte mit
`ModuleNotFoundError`). Die Installationszelle installiert deshalb mit
`--force-reinstall`:

```python
!pip install --quiet "$PAKET_URL"
!pip install --quiet --force-reinstall --no-deps "$PAKET_URL"
```

Der erste Aufruf beschafft die Abhängigkeiten, der zweite erneuert nur unseren Code.
**Das `--no-deps` im zweiten ist wichtig:** ohne es zieht `--force-reinstall` auch
pandas und numpy in der neuesten Version nach und bricht damit Colabs eigene Pins –
beobachtet am 24.08.2026:

```
google-colab 1.0.0 requires pandas==2.2.3, but you have pandas 3.0.5
numba 0.61.2 requires numpy<2.3,>=1.24, but you have numpy 2.5.2
```

Mit beiden Aufrufen bleiben pandas 2.2.3 und numpy 2.2.6 unverändert stehen
(nachgestellt in einem venv mit denselben Pins), und der neue Code kommt trotzdem an.
Aus demselben Grund deklariert `pyproject.toml` **kein numpy**: es wird noch nicht
benutzt, und `numpy>=2.1` würde in Colab eine Aktualisierung erzwingen. plotly steht
mit `>=5` und ohne Obergrenze darin – Colab bringt es mit, die Anforderung ist damit
erfüllt, und der erste `pip install` lässt die vorhandene Version stehen.

Ein Versionssprung in `pyproject.toml` würde den Reinstall ebenfalls erübrigen –
nachgestellt: bei gleicher Version installiert pip nichts, bei `0.3.0` installiert es.
Darauf ist aber kein Verlass, denn ein vergessener Sprung scheitert lautlos: Colab
importiert den alten Code und liefert eine plausible Zahl aus veralteter Logik.

Die Installationszelle zieht das Paket anhand von `PAKET_REF`. Statt `main` eine
Version zu pinnen ist der Unterschied zwischen „die Prognose von letztem Monat“ und
„die Prognose mit dem Code von letztem Monat“.

### 4. Zugangsdaten in Colab

Die vier Clockodo-Variablen aus `.env.sample` als Colab-Secrets anlegen –
`CLOCKODO_API_USER`, `CLOCKODO_API_KEY`, `CLOCKODO_APP_NAME`, `CLOCKODO_APP_EMAIL`.
Keine `.env` in Colab. `Dashboard.laden()` erkennt Colab und liest dort die Secrets,
lokal die `.env`.

### Bekannte Einschränkungen

- **Abhängigkeitsversionen weichen ab.** `uv.lock` gilt nur lokal; `pip` in Colab
  ignoriert die Lockfile und löst gegen die dort vorinstallierten Pakete auf. Ein
  lokal grüner Testlauf garantiert daher kein identisches Verhalten in Colab.
- **Der API-Teil ist gegen die echte Installation geprüft, aber nicht in Colab.**
  Envelope, Query-Parameter und Feldnamen aller benutzten Endpunkte sind am 24.08.2026
  gegen die Installation verifiziert, und beide Notebooks laufen lokal durch. Offen sind
  keine Strukturfragen mehr, sondern zwei fachliche Abgrenzungen, im Technik-Notebook
  mit `ENTSCHEIDEN` markiert.
- **Ob die plotly-Diagramme in Colab rendern, ist noch nicht geprüft.** Lokal tun sie
  es. In Colab ist beim ersten Lauf zu kontrollieren, dass der `pip`-Aufruf plotly,
  pandas und numpy unangetastet lässt; tut er es nicht, ist die Versionsangabe zu eng.
- **Kein automatisierter Lauf.** Ob die monatliche Prognose dauerhaft manuell in Colab
  ausgeführt wird, ist nicht entschieden. Sobald sie regelmäßig und unbeaufsichtigt
  laufen soll, ist Colab das falsche Werkzeug – dann braucht es einen Scheduler und
  einen Ort für die Zugangsdaten, der nicht an ein persönliches Google-Konto hängt.
  Das hängt an der offenen Verantwortlichkeitsfrage aus Spec Abschnitt 9.
