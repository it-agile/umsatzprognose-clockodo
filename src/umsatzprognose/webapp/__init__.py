"""Web-Frontend neben den Notebooks - dieselben Daten, ohne Jupyter/Colab.

Kein eigener Baustein und keine eigene Fachlogik: dieses Paket ist, wie
``notebooks/``, nur ein weiterer Konsument von
:class:`umsatzprognose.darstellung.dashboard.Dashboard`. Siehe CLAUDE.md, Abschnitt
"Web-Frontend", fuer die Beweggruende und die Abgrenzung zu den Notebooks.

Es gibt keine eigene Benutzerverwaltung. Alle Besucher sehen denselben, periodisch
aktualisierten Stand aus genau einer Clockodo-/Google-Sheets-Anbindung (siehe
:mod:`.cache`) - wie beim Dashboard-Notebook auch, nur serverseitig gerendert statt
zellenweise in Jupyter.

Gehoert zum optionalen ``web``-Extra (siehe ``pyproject.toml``): ``fastapi``/
``uvicorn`` sind keine Basisabhaengigkeit, weil nur dieses Paket sie braucht.
"""
