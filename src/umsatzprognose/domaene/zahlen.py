"""Zahlen in der Form, in der ein Fachexperte sie liest - und zurueck.

Deutsche Schreibweise mit Punkt als Tausender- und Komma als Dezimaltrennzeichen, ohne
``locale``:.
"""

from __future__ import annotations

import re

_PLATZHALTER = "\x00"
_UNERLAUBTE_ZEICHEN = re.compile(r"[^\d,.]")


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


def euro_parsen(text: str) -> float:
    """``"12.345,67 €"`` -> ``12345.67``; leer oder ohne Ziffern -> ``0.0``."""
    bereinigt = _UNERLAUBTE_ZEICHEN.sub("", text).replace(".", "").replace(",", ".")
    return float(bereinigt) if bereinigt else 0.0
