# Umsatzprognose – Baustein Bestand (Clockodo) + Schulungsanmeldungen

Rollierende 1–3-Monats-Prognose des Umsatzes aus laufenden, in Clockodo angelegten
Projekten – als Bandbreite (Konfidenzniveaus 95 % / 85 % / 50 % je Monat und als
Summe), nicht als Punktwert. Modelliert wird dabei nur eine Unsicherheit: wie viel des
beauftragten Restvolumens im Prognosezeitraum tatsächlich abgerufen wird. Additiv dazu
kommt der Umsatz bereits geplanter öffentlicher Schulungstermine aus einer externen
Google-Sheets-Tabelle – deterministisch, ohne eigene Bandbreite.

Maßgeblich sind die Spezifikationen:
[`spec/spec-umsatzprognose-clockodo-modul.md`](spec/spec-umsatzprognose-clockodo-modul.md)
(Baustein Bestand) und
[`spec/spec-schulungsanmeldungen.md`](spec/spec-schulungsanmeldungen.md)
(Baustein Schulungsanmeldungen).

## Stand

Prototyp-Phase. Umgesetzt sind das Restvolumen je Projekt (Spec 5.1) und die geschätzte
Abrufquote-Verteilung (5.2), dazu das vollständige Domänenmodell außer der Simulation –
inklusive Aufteilungsschlüssel je Person und Sollarbeitszeit. Es fehlen die verfügbare
Kapazität (5.3: Abwesenheiten, Feiertage) und die Monte-Carlo-Simulation (5.4). Das
Dashboard zeigt an der Stelle der Bandbreite eine Begründung an, statt eine Zahl zu
erfinden. Der Baustein Schulungsanmeldungen ist umgesetzt.

## Setup

Voraussetzung ist [uv](https://docs.astral.sh/uv/); die Python-Version ist über
`.python-version` auf 3.13 festgelegt.

```bash
uv sync --extra notebook
git config core.hooksPath .githooks
```

Der zweite Befehl aktiviert einmalig pro Klon den Pre-Commit-Hook (`.githooks/`), der
Zellausgaben aus Notebooks entfernt, bevor sie committet werden – das Repository ist
öffentlich, Notebook-Ausgaben könnten reale Geschäftsdaten enthalten.

Zugangsdaten aus `.env.sample` nach `.env` kopieren und ausfüllen. Den API-Key findet
jede Person in Clockodo unter „Persönliche Daten“. Für den Baustein Schulungsanmeldungen
zusätzlich eine OAuth-Client-ID (kein Service-Account, siehe `.env.sample`) sowie die
Jahr-zu-Spreadsheet-Zuordnung eintragen; der erste Aufruf öffnet dafür lokal einmalig
einen Browser-Tab zum Anmelden.

## Nutzung

```python
from umsatzprognose import Dashboard

dashboard = Dashboard.laden()
dashboard.umsatzverlauf()
```

Zielwerkzeug ist laut Spezifikation ein Notebook in Google Colab:

- `notebooks/01_dashboard.ipynb` – für Fachexperten, ein Aufruf je Zelle.
- `notebooks/02_technik_pruefung.ipynb` – für die Entwicklung.

Beide beginnen mit einer nur in Colab wirksamen Installationszelle, die das Paket direkt
aus GitHub installiert. Die Zugangsdaten liegen dort als Colab-Secrets, lokal in `.env`.

## Kommandos

```bash
uv run pytest                  # Tests
uv run ruff check .            # Lint
uv run ruff format .           # Formatierung
uv run jupyter lab             # Notebooks lokal
uvx tox                        # Tests unter Python 3.12-3.14 + Coverage + Lint, ein Kommando
uvx tox -e jupyter             # Notebooks starten (wie uv run jupyter lab, mit --autoreload)
uvx tox -r -e jupyter -- execute notebooks/01_dashboard.ipynb --output tmp.ipynb # Notebook ausführen und Output in tmp.ipynb schreiben
```

## Automatisierung: wöchentlicher Slack-Bericht

`.github/workflows/wochenbericht.yml` postet montags die Dashboard-Diagramme
(`scripts/wochenbericht.py`, Bilder gerendert über `kaleido`) in einen Slack-Kanal,
über einen Slack-Bot (`chat:write`, `files:write`). Die Zeit im Workflow steht in UTC.

Als Repository-Secrets (Settings → Secrets and variables → Actions) hinterlegen:

- `CLOCKODO_API_USER`, `CLOCKODO_API_KEY`, `CLOCKODO_APP_NAME`, `CLOCKODO_APP_EMAIL` –
  wie in `.env`.
- `GOOGLE_OAUTH_CLIENT_JSON`, `KOSTEN_SHEET_IDS` – wie in `.env`.
- `GOOGLE_OAUTH_TOKEN_JSON` – der Inhalt der lokal einmalig erzeugten
  `.google_oauth_token.json` (siehe Setup). Ohne sie versucht der Runner einen
  interaktiven Browser-Login, der dort nicht funktioniert; mit ihr erneuert der
  bestehende Code das Token automatisch. Voraussetzung: Der OAuth-Consent-Screen in
  der Google-Cloud-Konsole steht auf „In production“, nicht „Testing“ – sonst läuft
  das Refresh-Token nach 7 Tagen ab.
- `SLACK_BOT_TOKEN`, `SLACK_CHANNEL_ID` – Token eines Slack-Bots mit `chat:write` und
  `files:write` in dem Kanal, ID über „Kanalname → Details → Kanal-ID“.

Manuell auslösen: Actions → „Wochenbericht nach Slack“ → „Run workflow“.

## Aufbau

Vier Pakete, `clockodo/` und `schulungen/` als zwei gleichrangige Quellschichten:

```
darstellung  ──►  domaene  ◄──  clockodo
                      ▲
                      └──  schulungen
```

- `src/umsatzprognose/domaene/` – die Fachobjekte (Kunde, Projekt, Mitarbeiter,
  Projektanteil, Umsatzhistorie, Verbrauchsverlauf, Abrufquote, Bestand, Prognose,
  Schulungsplan), unveränderlich und ohne Bibliotheksabhängigkeit.
- `src/umsatzprognose/clockodo/` – Zugriff auf die Clockodo-API (Client, Konfiguration,
  Nebenläufigkeit) und je Endpunkt ein Repository, das die Antworten in Fachobjekte
  abbildet.
- `src/umsatzprognose/schulungen/` – Zugriff auf die Schulungs-Sheets (Google Sheets API,
  OAuth-Client-ID statt Service-Account) und das Repository, das ein Tabellenblatt je
  Jahr in einen `Schulungsplan` abbildet.
- `src/umsatzprognose/darstellung/` – Diagramme (plotly), Tabellen (pandas) und die
  Fassade `Dashboard`, die die Notebooks benutzen.
- `tests/` – pytest.
- `spec/` – Spezifikationen und die Clockodo-OpenAPI-Beschreibung.
