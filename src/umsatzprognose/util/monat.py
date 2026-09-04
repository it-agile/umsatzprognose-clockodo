"""Monat als Zahlenpaar ``(jahr, monat)`` - Arithmetik ueber Jahresgrenzen hinweg.

Ohne Bibliotheksabhaengigkeit, gemeinsam genutzt von ``domaene``, ``clockodo``,
``schulungen`` und ``kosten`` - die Umrechnung "Monate seit Jahr 0" tauchte vor dieser
Zusammenfuehrung an sieben Stellen unabhaengig voneinander auf.
"""

from __future__ import annotations

Monat = tuple[int, int]  # (jahr, monat)


def ordnung(jahr: int, monat: int) -> int:
    """Monate seit Jahr 0 - macht Vergleich und Fortzaehlung ueber Jahresgrenzen trivial."""
    return jahr * 12 + (monat - 1)


def aus_ordnung(ordnung: int) -> Monat:
    return (ordnung // 12, ordnung % 12 + 1)


def vormonat(jahr: int, monat: int) -> Monat:
    return aus_ordnung(ordnung(jahr, monat) - 1)


def monatsfolge(start: Monat, anzahl: int) -> list[Monat]:
    """``anzahl`` aufeinanderfolgende Monate, beginnend bei ``start``."""
    basis = ordnung(*start)
    return [aus_ordnung(basis + i) for i in range(anzahl)]
