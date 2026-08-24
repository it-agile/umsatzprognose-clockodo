# Umsatzprognose – Baustein Bestand (Clockodo)

Rollierende 1–3-Monats-Prognose des Umsatzes aus laufenden, in Clockodo angelegten
Projekten – als Bandbreite (95 % / 85 % / 50 %), nicht als Punktwert.

Maßgeblich ist die Spezifikation: [`spec/spec-umsatzprognose-clockodo-modul-v0.5.md`](spec/spec-umsatzprognose-clockodo-modul-v0.5.md).

## Stand

Prototyp-Phase. Umgesetzt ist Schritt 1 aus Spec Abschnitt 10: das Restvolumen je
Projekt (Abschnitt 5.1). Die Monte-Carlo-Simulation (5.4) ist noch nicht gebaut.

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

- `src/umsatzprognose/` – testbare Logik. `config.py` (Zugangsdaten, Header),
  `restvolumen.py` (Spec 5.1).
- `tests/` – pytest.
- `notebooks/` – Prototyp-Notebooks. Sie rufen die API auf und nutzen das Paket;
  Rechenlogik gehört ins Paket, nicht ins Notebook.
- `spec/` – Spezifikation.

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
`notebooks/01_restvolumen.ipynb` öffnen. Da das Repository öffentlich ist, braucht Colab
dafür keine GitHub-Autorisierung.

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

Die Installationszelle zieht das Paket anhand von `PAKET_REF`. Statt `main` eine
Version zu pinnen ist der Unterschied zwischen „die Prognose von letztem Monat“ und
„die Prognose mit dem Code von letztem Monat“.

### 4. Zugangsdaten in Colab

Die vier Clockodo-Variablen aus `.env.sample` als Colab-Secrets anlegen –
`CLOCKODO_API_USER`, `CLOCKODO_API_KEY`, `CLOCKODO_APP_NAME`, `CLOCKODO_APP_EMAIL`.
Keine `.env` in Colab. Das Notebook hebt die Secrets in die Umgebung und ruft
`load_credentials(use_dotenv=False)` auf.

### Bekannte Einschränkungen

- **Abhängigkeitsversionen weichen ab.** `uv.lock` gilt nur lokal; `pip` in Colab
  ignoriert die Lockfile und löst gegen die dort vorinstallierten Pakete auf. Ein
  lokal grüner Testlauf garantiert daher kein identisches Verhalten in Colab.
- **Der API-Teil ist gegen die echte Installation geprüft, aber nicht in Colab.**
  Envelope, Query-Parameter und Feldnamen von `/v4/projects` und `/v2/entrygroups` sind
  am 24.08.2026 per `curl` verifiziert, und das Notebook läuft lokal durch. Offen sind
  keine Strukturfragen mehr, sondern zwei fachliche Abgrenzungen, im Notebook mit
  `ENTSCHEIDEN` markiert.
- **Kein automatisierter Lauf.** Ob die monatliche Prognose dauerhaft manuell in Colab
  ausgeführt wird, ist nicht entschieden. Sobald sie regelmäßig und unbeaufsichtigt
  laufen soll, ist Colab das falsche Werkzeug – dann braucht es einen Scheduler und
  einen Ort für die Zugangsdaten, der nicht an ein persönliches Google-Konto hängt.
  Das hängt an der offenen Verantwortlichkeitsfrage aus Spec Abschnitt 9.
