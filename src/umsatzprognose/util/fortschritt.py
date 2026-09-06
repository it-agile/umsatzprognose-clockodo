"""Der gemeinsame Callback-Typ fuer eine sukzessive Ladeanzeige.

Dieselbe Form (ein Text hinein, nichts heraus) fuer alle Sorten von Ladehinweisen im
Projekt - Schritt-Start, Schritt-Ende, Verlaufscache-Zugriff
(:mod:`umsatzprognose.clockodo.cache`) und der einmalige Abschlussbericht der
Monte-Carlo-Simulation (:meth:`~umsatzprognose.darstellung.dashboard.Dashboard.simuliere`)
unterscheiden sich nur durch Zeitpunkt und Wortlaut der Aufrufe, nicht durch die
Signatur. Ein einzelner benannter Typ statt ``Callable[[str], None] | None`` an jeder
Stelle, durch die ein solcher Callback gereicht wird (``Dashboard.laden_async`` bis
hinunter zu ``cache.gecacht_oder_neu``).

In ``util/`` statt in ``clockodo/``, weil sowohl ``clockodo`` als auch ``darstellung``
(und potenziell ``domaene``) ihn brauchen koennen - ``domaene`` darf ``clockodo`` nicht
importieren (siehe Abschnitt "Aufbau" in ``CLAUDE.md``), ``util/`` ist das einzige
Paket, das beide importieren duerfen. ``umsatzprognose.clockodo.Fortschritt`` bleibt
unveraendert importierbar (siehe ``clockodo/fortschritt.py``), damit bestehender Code
nicht angepasst werden muss.

Kein eigenes Wissen ueber ``tqdm`` oder eine sonstige Darstellung - das entscheidet
ausschliesslich der Aufrufer (siehe ``notebooks/setup.py``,
``scripts/diagramme_exportieren.py``).
"""

from __future__ import annotations

from typing import Protocol


class Fortschritt(Protocol):
    """Eine einzelne Statuszeile melden - Wortlaut und Zeitpunkt bestimmt der Aufrufer.

    ``text`` positional-only (``/``): sonst lehnt mypy einen einfachen
    ``Callable[[str], None]`` wie ``liste.append`` als Wert ab, weil dessen Parameter
    ebenfalls keinen (fuer die Struktur-Pruefung passenden) Namen traegt.
    """

    def __call__(self, text: str, /) -> None: ...
