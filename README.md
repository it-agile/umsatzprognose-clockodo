# Umsatzprognose – Baustein Bestand (Clockodo)

Rollierende 1–3-Monats-Prognose des Umsatzes aus laufenden, in Clockodo angelegten
Projekten – als Bandbreite (Konfidenzniveaus 95 % / 85 % / 50 % je Monat und als
Summe), nicht als Punktwert. Modelliert wird dabei nur eine Unsicherheit: wie viel des
beauftragten Restvolumens im Prognosezeitraum tatsächlich abgerufen wird.

Maßgeblich ist die Spezifikation:
[`spec/spec-umsatzprognose-clockodo-modul.md`](spec/spec-umsatzprognose-clockodo-modul.md).

## Stand

Prototyp-Phase. Umgesetzt sind das Restvolumen je Projekt (Spec 5.1) und die geschätzte
Abrufquote-Verteilung (5.2), dazu das vollständige Domänenmodell außer der Simulation –
inklusive Aufteilungsschlüssel je Person und Sollarbeitszeit. Es fehlen die verfügbare
Kapazität (5.3: Abwesenheiten, Feiertage) und die Monte-Carlo-Simulation (5.4). Das
Dashboard zeigt an der Stelle der Bandbreite eine Begründung an, statt eine Zahl zu
erfinden.

## Setup

Voraussetzung ist [uv](https://docs.astral.sh/uv/); die Python-Version ist über
`.python-version` auf 3.13 festgelegt.

```bash
uv sync --extra notebook
```

Zugangsdaten aus `.env.sample` nach `.env` kopieren und ausfüllen. Den API-Key findet
jede Person in Clockodo unter „Persönliche Daten“.

## Nutzung

```python
from umsatzprognose import Dashboard

dashboard = Dashboard.laden()
dashboard.umsatzverlauf()
```

Zielwerkzeug ist laut Spezifikation ein Notebook in Google Colab:

- `notebooks/01_dashboard.ipynb` – für Fachexperten, ein Aufruf je Zelle.
- `notebooks/02_technik_restvolumen.ipynb` – für die Entwicklung.

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
```

## Aufbau

Drei Schichten mit genau einer erlaubten Abhängigkeitsrichtung:

```
darstellung  ──►  domaene  ◄──  clockodo
```

- `src/umsatzprognose/domaene/` – die Fachobjekte (Kunde, Projekt, Mitarbeiter,
  Projektanteil, Umsatzhistorie, Verbrauchsverlauf, Abrufquote, Bestand, Prognose),
  unveränderlich und ohne Bibliotheksabhängigkeit.
- `src/umsatzprognose/clockodo/` – Zugriff auf die Clockodo-API (Client, Konfiguration,
  Nebenläufigkeit) und je Endpunkt ein Repository, das die Antworten in Fachobjekte
  abbildet.
- `src/umsatzprognose/darstellung/` – Diagramme (plotly), Tabellen (pandas) und die
  Fassade `Dashboard`, die die Notebooks benutzen.
- `tests/` – pytest.
- `spec/` – Spezifikation und die Clockodo-OpenAPI-Beschreibung.
