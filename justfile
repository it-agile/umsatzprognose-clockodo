# Dünne Hülle um tox: alle Rezepte rufen `uvx tox` auf, Konfiguration steht in
# pyproject.toml ([tool.tox]). Zusätzliche Argumente werden an tox durchgereicht.

# Rezepte auflisten
default:
    @just --list

# Lokaler Gesamtlauf mit nur einer Python-Version (Projektstandard 3.13): Tests, ruff,
# mypy, ty. Die Python-Matrix 3.12-3.14 läuft nur in GitHub Actions (siehe `matrix`).
check:
    uvx tox -e py313,ruff,mypy,mypy-notebooks,ty

# Tests unter einer Python-Version (Standard py313): just test py312
test env="py313":
    uvx tox -e {{ env }}

# Komplette Python-Matrix und alles weitere wie in der CI (`uvx tox` ohne Angabe)
matrix *args:
    uvx tox {{ args }}

# Tests mit Coverage-Bericht
coverage *args:
    uvx tox -e coverage -- {{ args }}

# Lint (ruff check)
lint *args:
    uvx tox -e ruff -- {{ args }}

# Typprüfung: mypy (Paket + Tests + Skripte) und mypy für die Notebooks
types:
    uvx tox -e mypy,mypy-notebooks

# ty (Beobachtung, Fehlschlag bricht nicht ab)
ty *args:
    uvx tox -e ty -- {{ args }}

# Jupyter Lab mit --autoreload; Argumente ersetzen die Standardargumente
jupyter *args:
    uvx tox -e jupyter {{ if args == "" { "" } else { "-- " + args } }}

# Web-Frontend lokal starten; Argumente ersetzen die Standardargumente
web *args:
    uvx tox -e web {{ if args == "" { "" } else { "-- " + args } }}
