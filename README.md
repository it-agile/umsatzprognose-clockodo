# Umsatzprognose – Baustein Bestand (Clockodo)

Rollierende 1–3-Monats-Prognose des Umsatzes aus laufenden, in Clockodo angelegten
Projekten – als Bandbreite (95 % / 85 % / 50 %), nicht als Punktwert.

Maßgeblich ist die Spezifikation: [`spec/spec-umsatzprognose-clockodo-modul-v0.4.md`](spec/spec-umsatzprognose-clockodo-modul-v0.4.md).

## Stand

Prototyp-Phase. Umgesetzt ist Schritt 1 aus Spec Abschnitt 10: das Restvolumen je
Projekt (Abschnitt 5.1). Die Monte-Carlo-Simulation (5.4) ist noch nicht gebaut.

## Setup

Voraussetzung ist [uv](https://docs.astral.sh/uv/). Die Python-Version ist über
`.python-version` auf 3.12 festgelegt – uv lädt sie bei Bedarf selbst.

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

## Google Colab

Zielwerkzeug laut Spec ist ein Notebook in Google Colab. Das lokale venv steht dort
nicht zur Verfügung, deshalb beginnt jedes Notebook mit einer Installationszelle, die
nur in Colab ausgeführt wird. Zugangsdaten in Colab über die Secrets-Verwaltung
bereitstellen, nicht über eine `.env`.
