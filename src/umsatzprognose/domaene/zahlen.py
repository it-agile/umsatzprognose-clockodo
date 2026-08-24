"""Zahlen in der Form, in der ein Fachexperte sie liest.

Deutsche Schreibweise mit Punkt als Tausender- und Komma als Dezimaltrennzeichen, ohne
``locale``: in Colab ist keine deutsche Locale gesetzt, und ein
``locale.setlocale``-Aufruf wirkt prozessweit - ein zu hoher Preis fuer ein
Tausendertrennzeichen.

Steht in der Domaene, weil bereits die Hinweise und die Monatsbeschriftungen fertige
Saetze fuer Menschen sind. Die Darstellungsschicht benutzt dieselben Funktionen, damit
Tabelle, Diagramm und Hinweis dieselbe Schreibweise zeigen.
"""

from __future__ import annotations

_PLATZHALTER = "\x00"


def _deutsch(wert: float, nachkommastellen: int) -> str:
    englisch = f"{wert:,.{nachkommastellen}f}"
    return englisch.replace(",", _PLATZHALTER).replace(".", ",").replace(_PLATZHALTER, ".")


def euro(betrag: float, *, nachkommastellen: int = 2) -> str:
    """Etwa ``729.212,45 EUR``."""
    return f"{_deutsch(betrag, nachkommastellen)} EUR"


def tausend_euro(betrag: float) -> str:
    """Etwa ``729 Tsd. EUR`` - fuer Kennzahlen, in denen Cent nur stoeren."""
    return f"{_deutsch(betrag / 1000, 0)} Tsd. EUR"


def stunden(wert: float) -> str:
    """Etwa ``3.699,5 h``."""
    return f"{_deutsch(wert, 1)} h"
