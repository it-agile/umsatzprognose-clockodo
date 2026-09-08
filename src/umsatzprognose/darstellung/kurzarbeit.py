"""Textuelle Berichte zum Baustein Kurzarbeitsbereitschaft.

Eigenstaendig neben :mod:`~umsatzprognose.darstellung.diagramme` (dort
``kurzarbeit_grafik``) - unabhaengig von
:class:`~umsatzprognose.darstellung.dashboard.Dashboard`, wie der ganze Baustein
Kurzarbeitsbereitschaft (siehe CLAUDE.md, ``spec/spec-kurzarbeit.md`` Abschnitt 2/7).
Fasst den Notebook-Code aus ``notebooks/04_kurzarbeit.ipynb`` (Tabellen- und
Hinweisausgabe) in zwei aufrufbare Funktionen zusammen, statt ihn im Notebook zu
wiederholen.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from umsatzprognose.domaene import Kurzarbeitsbewertung
    from umsatzprognose.util import Monat

from .gestaltung import KURZARBEIT_SCHWELLE_ERREICHT, KURZARBEIT_SCHWELLE_NICHT_ERREICHT

# Ausgeschriebene Monatsnamen, nicht die abgekuerzten aus domaene.umsatzhistorie.
# MONATSNAMEN (dort fuer Diagramm-Achsenbeschriftungen gedacht) - deckt sich mit
# _KURZARBEIT_MONATSNAMEN in webapp/app.py, aus demselben Grund bewusst dupliziert statt
# importiert: der Baustein Kurzarbeit bleibt eigenstaendig (Spec Abschnitt 5.8).
_MONATSNAMEN = (
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
)  # fmt: skip

_ANSI_RESET = "\033[0m"


def _ansi_vordergrund(hex_farbe: str) -> str:
    """ANSI-Truecolor-Code fuer eine Vordergrundfarbe aus einem ``#rrggbb``-Hexwert -
    dieselbe Farbquelle wie Grafik (:func:`~.diagramme.kurzarbeit_grafik`) und Webapp
    (``.status-erfuellt``/``.status-nicht-erfuellt`` in ``basis.html``)."""
    rot, gruen, blau = (int(hex_farbe[i : i + 2], 16) for i in (1, 3, 5))
    return f"\033[38;2;{rot};{gruen};{blau}m"


def _status_text(bewertung: Kurzarbeitsbewertung) -> str:
    if bewertung.vorbereitet is None:
        return "keine Auswertung möglich (keine einbezogene Person)"
    return "Voraussetzung erfüllt" if bewertung.vorbereitet else "Voraussetzung nicht erfüllt"


def _status_farbe(bewertung: Kurzarbeitsbewertung, *, mit_farbe: bool) -> str:
    if not mit_farbe or bewertung.vorbereitet is None:
        return ""
    schluessel = (
        KURZARBEIT_SCHWELLE_ERREICHT
        if bewertung.vorbereitet
        else (KURZARBEIT_SCHWELLE_NICHT_ERREICHT)
    )
    return _ansi_vordergrund(schluessel)


def _quote_text(bewertung: Kurzarbeitsbewertung) -> str:
    return f"{bewertung.quote:.1%}" if bewertung.quote is not None else "n/a"


def _reset(*, mit_farbe: bool) -> str:
    return _ANSI_RESET if mit_farbe else ""


def kurzarbeit_bericht(
    ergebnisse: Mapping[Monat, Kurzarbeitsbewertung], *, mit_farbe: bool = True
) -> str:
    """Kurzarbeitsbereitschaft als Text: Detail zum jüngsten Monat, danach eine
    Tabelle über alle übergebenen Monate.

    Dieselbe (nicht wertende) Farbfamilie wie die Grafik
    (:func:`~.diagramme.kurzarbeit_grafik`) und die Webapp-Seite
    (``.status-erfuellt``/``.status-nicht-erfuellt`` in ``basis.html``), hier als
    ANSI-Truecolor-Code für Terminal-/Notebook-Ausgabe. ``mit_farbe=False`` liefert
    reinen Text ohne ANSI-Codes, etwa für ein Ziel ohne Terminalfarben.
    """
    monate = sorted(ergebnisse)
    letzter_monat = monate[-1]
    letzte_bewertung = ergebnisse[letzter_monat]
    jahr, monat_nr = letzter_monat
    schwellenwerte = letzte_bewertung.schwellenwerte
    reset = _reset(mit_farbe=mit_farbe)

    zeilen = [
        f"{_MONATSNAMEN[monat_nr - 1]} {jahr}: "
        f"{_status_farbe(letzte_bewertung, mit_farbe=mit_farbe)}"
        f"{_status_text(letzte_bewertung)}{reset}",
        f"  Quote kurzarbeitsfähiger Personen: {_quote_text(letzte_bewertung)}"
        f" (Schwelle {schwellenwerte.quote_organisation:.0%}),"
        f" {letzte_bewertung.anzahl_kurzarbeitsfaehig} von {letzte_bewertung.anzahl_einbezogen}",
        f"  Scheitert an interner Arbeit: {letzte_bewertung.anzahl_scheitert_interne_arbeit}",
        f"  Scheitert an Überstunden:    {letzte_bewertung.anzahl_scheitert_ueberstunden}",
        f"  Scheitert an beidem:         {letzte_bewertung.anzahl_scheitert_beide}",
        f"  Ausgeschlossen (Rollenzuordnung): {letzte_bewertung.anzahl_ausgeschlossen}",
        f"  Nicht bestimmbar:                 {letzte_bewertung.anzahl_nicht_bestimmbar}",
        f"  Schwellenwerte: Anteil interne Arbeit >= {schwellenwerte.anteil_interne_arbeit:.0%},"
        f" Überstundenstand < {schwellenwerte.ueberstunden_stunden:.0f}h,"
        f" Quote >= {schwellenwerte.quote_organisation:.0%}",
        "",
        f"{'Monat':<16} {'Status':<26} {'Quote':>7} {'KA':>4} {'Ausgeschl.':>11} {'N.best.':>8}",
    ]
    for monat in monate:
        bewertung = ergebnisse[monat]
        jahr, monat_nr = monat
        bezeichnung = f"{_MONATSNAMEN[monat_nr - 1]} {jahr}"
        # status_text() wird zuerst auf die Zielbreite gepolstert, erst danach mit den
        # ANSI-Codes umschlossen - sonst zaehlten deren unsichtbare Zeichen mit und die
        # Spalten dahinter wuerden verrutschen.
        status_gepolstert = f"{_status_text(bewertung):<26}"
        zeilen.append(
            f"{bezeichnung:<16} {_status_farbe(bewertung, mit_farbe=mit_farbe)}"
            f"{status_gepolstert}{reset} "
            f"{_quote_text(bewertung):>7}"
            f" {bewertung.anzahl_kurzarbeitsfaehig:>4} {bewertung.anzahl_ausgeschlossen:>11}"
            f" {bewertung.anzahl_nicht_bestimmbar:>8}"
        )
    return "\n".join(zeilen)


def kurzarbeit_hinweise_bericht(ergebnisse: Mapping[Monat, Kurzarbeitsbewertung]) -> str:
    """Alle Hinweise je Monat als Text, oder ``"Keine Hinweise."``, wenn keiner vorliegt."""
    zeilen: list[str] = []
    for monat in sorted(ergebnisse):
        hinweise = ergebnisse[monat].hinweise
        if not hinweise:
            continue
        jahr, monat_nr = monat
        zeilen.append(f"{_MONATSNAMEN[monat_nr - 1]} {jahr}:")
        zeilen.extend(f"  - {hinweis.text}" for hinweis in hinweise)
    return "\n".join(zeilen) if zeilen else "Keine Hinweise."
