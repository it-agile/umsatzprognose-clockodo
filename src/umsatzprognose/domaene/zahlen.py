"""Zahlen in der Form, in der ein Fachexperte sie liest - und zurueck.

Deutsche Schreibweise mit Punkt als Tausender- und Komma als Dezimaltrennzeichen, ohne
``locale``:.

Euro-Betraege laufen als :class:`~decimal.Decimal`, nicht als ``float`` - ein
Rundungsfehler in einer Geldgroesse waere in einem oeffentlichen Repository nur schwer
zu rechtfertigen. Reine Verhaeltnis- und Stundengroessen (``stunden``, ``tage``,
``prozent``) bleiben ``float``, weil sie keine Geldbetraege sind.
"""

from __future__ import annotations

import re
from decimal import Decimal

_PLATZHALTER = "\x00"
_UNERLAUBTE_ZEICHEN = re.compile(r"[^\d,.]")

STUNDEN_JE_TAG = 7.0


def _deutsch(wert: float | Decimal, nachkommastellen: int) -> str:
    englisch = f"{wert:,.{nachkommastellen}f}"
    return englisch.replace(",", _PLATZHALTER).replace(".", ",").replace(_PLATZHALTER, ".")


def euro(betrag: Decimal, *, nachkommastellen: int = 2) -> str:
    """Etwa ``729.212,45 EUR``."""
    return f"{_deutsch(betrag, nachkommastellen)} EUR"


def tausend_euro(betrag: Decimal) -> str:
    """Etwa ``729 Tsd. EUR`` - fuer Kennzahlen, in denen Cent nur stoeren."""
    return f"{_deutsch(betrag / 1000, 0)} Tsd. EUR"


def stunden(wert: float) -> str:
    """Etwa ``3.699,5 h``."""
    return f"{_deutsch(wert, 1)} h"


def tage(stunden: float) -> str:
    """Etwa ``12,5 Tage`` - Kapazitaet als Personentage a :data:`STUNDEN_JE_TAG` Stunden."""
    return f"{_deutsch(stunden / STUNDEN_JE_TAG, 1)} Tage"


def prozent(anteil: float, *, nachkommastellen: int = 0) -> str:
    """Etwa ``82 %`` - ``anteil`` als Bruch (0,82), nicht bereits mit 100 multipliziert."""
    return f"{_deutsch(anteil * 100, nachkommastellen)} %"


def euro_parsen(text: str) -> Decimal:
    """``"12.345,67 €"`` -> ``Decimal("12345.67")``; leer oder ohne Ziffern -> ``Decimal("0")``.

    Parst direkt in ``Decimal``, ohne den Umweg ueber ``float`` - der wuerde die
    Nachkommastellen schon vor der Umwandlung mit einem Binaerrundungsfehler behaften.
    """
    bereinigt = _UNERLAUBTE_ZEICHEN.sub("", text).replace(".", "").replace(",", ".")
    return Decimal(bereinigt) if bereinigt else Decimal("0")
