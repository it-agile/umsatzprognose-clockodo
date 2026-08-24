"""Verbrauchtes Volumen je Projekt - ``revenue`` aus ``/v2/entrygroups``.

Spec Abschnitt 4 nennt ``/v2/entrygroups`` (Gruppierung nach Projekt) als Quelle des
verbrauchten Volumens; in 5.1 ist das ``revenue_kumuliert``, also der Gesamtverbrauch
eines Projekts und nicht der eines Monats. Das Zeitfenster der Abfrage muss deshalb die
ganze Historie umfassen - siehe :mod:`umsatzprognose.api`.

Reine Abbildung von Antwort-JSON auf ``projects_id -> Betrag``, ohne HTTP. Verifiziert
am 24.08.2026 an den 870 Gruppen dieser Installation: die Projekt-ID steht als
**String** in ``group``, und der Wert ``0`` (dort als Zahl) steht fuer Buchungen auf
einen Kunden ohne Projekt. Ohne Filter entstuende daraus ein Phantom-Projekt 0.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping


def revenue_je_projekt(
    gruppen: Iterable[Mapping[str, object]],
) -> tuple[dict[int, float], list[Mapping[str, object]]]:
    """Bildet ``projects_id -> kumuliertes revenue`` aus ``/v2/entrygroups`` ab.

    Args:
        gruppen: die ``groups``-Liste einer Abfrage mit ``grouping[]=projects_id``.

    Returns:
        Den Verbrauch je Projekt sowie die Gruppen ohne Projektbezug (``group == 0``),
        damit deren Umsatz nicht unbemerkt verschwindet.
    """
    revenue: dict[int, float] = {}
    ohne_projekt: list[Mapping[str, object]] = []

    for gruppe in gruppen:
        pid = int(gruppe["group"])  # type: ignore[arg-type]
        if pid == 0:
            ohne_projekt.append(gruppe)
            continue
        # Summiert statt zugewiesen: eine Gruppierung liefert je Projekt eine Gruppe,
        # ein doppelter Schluessel wuerde sonst still eine Zeile verwerfen.
        revenue[pid] = revenue.get(pid, 0.0) + float(gruppe.get("revenue") or 0.0)

    return revenue, ohne_projekt
