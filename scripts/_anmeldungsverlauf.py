"""Anmeldungsverlauf-Diagramm (Ansicht/Zeitraum-oder-ab_jahr-Fenster, Schulungen-/
Format-/Dauer-Filter, Trendlinien) - gemeinsame Logik fuer
``scripts/diagramme_exportieren.py`` und ``scripts/wochenbericht.py``.

Bewusst ein eigenes Modul statt zweier unabhaengiger Kopien - Vorbild
``scripts/_fortschritt.py``: laeuft dieselbe Logik in mehr als einem Skript
auseinander, gehoert sie hierher extrahiert statt (erneut) dupliziert zu werden
(siehe CLAUDE.md, Abschnitt "Code-Qualitaet"). Deckt sich inhaltlich mit den
gleichnamigen Stellen in ``webapp/app.py`` (Route ``/schulungen``, siehe dortige
Docstrings) - dort bewusst nicht importiert, weil ``scripts/`` kein Teil des
installierten Pakets ist und nicht von ``webapp/`` abhaengt.
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from datetime import date

    import plotly.graph_objects as go

    from umsatzprognose.domaene.anmeldung import Anmeldungsverlauf
    from umsatzprognose.util import Monat

from umsatzprognose.darstellung import diagramme
from umsatzprognose.util import aus_ordnung, ordnung

# Umschalter/Regler, deckt sich mit AnsichtWert/SchulungenZeitraum in webapp/app.py.
ANSICHT_OPTIONEN = ("zeitverlauf", "jahresvergleich")
STANDARD_ANSICHT = "zeitverlauf"
ZEITRAUM_OPTIONEN = ("12", "24", "36", "alle")
STANDARD_MONATE_RUECKBLICK = 12
STANDARD_MONATE_VORAUS = 3
STANDARD_AB_JAHR = 2022
STANDARD_ANZEIGE_MINDESTMONAT = 6
STANDARD_TRENDLINIEN_MAX_LINIEN = 5
ALLE_SCHULUNGEN = "Alle Schulungen"
ALLE = "Alle"


def standard_anzeige_ab_jahr(*, heute: date) -> int:
    """Ohne explizit gewaehltes Jahr fuer die Ansicht "jahresvergleich" gezeigtes
    Jahr - deckt sich mit ``_standard_anzeige_ab_jahr()`` in webapp/app.py (siehe
    Moduldocstring)."""
    jahr = heute.year if heute.month >= STANDARD_ANZEIGE_MINDESTMONAT else heute.year - 1
    return max(jahr, STANDARD_AB_JAHR)


def anmeldungsverlauf_jahre(
    *,
    stichtag: date,
    ansicht: str,
    zeitraum_alle: bool,
    monate_rueckblick: int,
    monate_voraus: int,
    ab_jahr: int | None,
) -> list[int]:
    """Die zu ladenden Jahre fuer den Anmeldungsverlauf - ab ``ab_jahr`` (bzw. dessen
    dynamischem Standard) bei ``ansicht="jahresvergleich"``, sonst ueber das
    rollierende Fenster aus ``monate_rueckblick``/``monate_voraus`` (oder ab
    :data:`STANDARD_AB_JAHR`, wenn ``zeitraum_alle``)."""
    ende = ordnung(stichtag.year, stichtag.month) + monate_voraus
    bis_jahr = aus_ordnung(ende)[0]
    if ansicht == "jahresvergleich":
        start_jahr = ab_jahr if ab_jahr is not None else standard_anzeige_ab_jahr(heute=stichtag)
    elif zeitraum_alle:
        start_jahr = STANDARD_AB_JAHR
    else:
        # Deckt sich mit Anmeldungsverlauf.letzte(): monate_rueckblick abgeschlossene
        # Monate plus der Stichtagsmonat selbst, ohne "- 1".
        start_jahr = aus_ordnung(ende - monate_voraus - monate_rueckblick)[0]
    return list(range(start_jahr, bis_jahr + 1))


def anmeldungsverlauf_fenster(
    verlauf: Anmeldungsverlauf,
    *,
    stichtag: date,
    ansicht: str,
    zeitraum_alle: bool,
    monate_rueckblick: int,
    monate_voraus: int,
    ab_jahr: int | None,
) -> Anmeldungsverlauf:
    """Der geladene Verlauf, zugeschnitten auf den gewaehlten Betrachtungszeitraum -
    das Gegenstueck zu :func:`anmeldungsverlauf_jahre` nach dem Laden."""
    if ansicht == "jahresvergleich":
        jahr = ab_jahr if ab_jahr is not None else standard_anzeige_ab_jahr(heute=stichtag)
        return verlauf.ab_jahr(jahr)
    if zeitraum_alle:
        return verlauf
    return verlauf.letzte(monate=monate_rueckblick, monate_voraus=monate_voraus, stichtag=stichtag)


def identitaeten(
    verlauf: Anmeldungsverlauf,
    schulung_filter: Sequence[str],
) -> list[tuple[str, Callable[..., dict[Monat, int]]]]:
    """Deckt sich mit ``_identitaeten()`` in webapp/app.py (siehe Moduldocstring)."""
    ergebnis: list[tuple[str, Callable[..., dict[Monat, int]]]] = []
    alle_gesehen = False
    for basisname in schulung_filter:
        if basisname == ALLE_SCHULUNGEN:
            if not alle_gesehen:
                ergebnis.append((ALLE_SCHULUNGEN, verlauf.je_monat_gefiltert))
                alle_gesehen = True
            continue
        ergebnis.append((basisname, partial(verlauf.je_monat_gefiltert, basisname=basisname)))
    return ergebnis


def slice_werte(filter_werte: Sequence[str]) -> list[tuple[str, str | None]]:
    """Deckt sich mit ``_slice_werte()`` in webapp/app.py (siehe Moduldocstring)."""
    ergebnis: list[tuple[str, str | None]] = []
    alle_gesehen = False
    for wert in filter_werte:
        if wert == ALLE:
            if not alle_gesehen:
                ergebnis.append(("", None))
                alle_gesehen = True
            continue
        ergebnis.append((wert, wert))
    return ergebnis


def anmeldungsreihen(
    verlauf: Anmeldungsverlauf,
    *,
    schulung_filter: Sequence[str],
    format_filter: Sequence[str],
    dauer_filter: Sequence[str],
) -> dict[str, dict[Monat, int]]:
    """Deckt sich mit ``_anmeldungsreihen()`` in webapp/app.py (siehe Moduldocstring) -
    eine Reihe je Kombination aus Schulungen-Auswahl (siehe :func:`identitaeten`) und
    den gewaehlten Format-/Dauer-Auswahlen (siehe :func:`slice_werte`)."""
    identitaeten_ = identitaeten(verlauf, schulung_filter)
    formate = slice_werte(format_filter)
    dauern = slice_werte(dauer_filter)
    if not identitaeten_ and not formate and not dauern:
        return {}

    reihen: dict[str, dict[Monat, int]] = {}
    for identitaet_name, identitaet_je_monat in identitaeten_ or [("", verlauf.je_monat_gefiltert)]:
        for format_label, format_wert in formate or [("", None)]:
            for dauer_label, dauer_wert in dauern or [("", None)]:
                teile = [teil for teil in (identitaet_name, format_label, dauer_label) if teil]
                name = " ".join(teile) if teile else ALLE_SCHULUNGEN
                reihen.setdefault(
                    name,
                    identitaet_je_monat(format_wert=format_wert, dauer_wert=dauer_wert),
                )
    return reihen


def anmeldungsverlauf_figur(
    verlauf: Anmeldungsverlauf,
    *,
    stichtag: date,
    ansicht: str = STANDARD_ANSICHT,
    schulung_filter: Sequence[str] = (ALLE_SCHULUNGEN,),
    format_filter: Sequence[str] = (ALLE,),
    dauer_filter: Sequence[str] = (ALLE,),
    trendlinien_werte: str | None = None,
) -> go.Figure:
    """Das Anmeldungsverlauf-Diagramm - ``ansicht="jahresvergleich"`` liefert
    :func:`diagramme.anmeldungsverlauf_jahresvergleich`, sonst
    :func:`diagramme.anmeldungsverlauf_reihen`, wie der gleichnamige Umschalter auf
    /schulungen. ``trendlinien_werte=None`` faellt wie dort auf den anhand der
    Linienanzahl dynamisch bestimmten Standard zurueck (siehe
    :data:`STANDARD_TRENDLINIEN_MAX_LINIEN`) - alle Parameter tragen Standardwerte,
    die dem unveraenderten Aufruf ("ohne weitere Parameter") entsprechen.
    """
    laufender_monat = (stichtag.year, stichtag.month)
    reihen = anmeldungsreihen(
        verlauf,
        schulung_filter=schulung_filter,
        format_filter=format_filter,
        dauer_filter=dauer_filter,
    )
    if ansicht == "jahresvergleich":
        jahre = sorted({jahr for jahr, _monat in verlauf.monate})
        linien_anzahl = len(reihen) * len(jahre)
    else:
        linien_anzahl = len(reihen)
    trendlinien = (
        trendlinien_werte == "an"
        if trendlinien_werte is not None
        else linien_anzahl <= STANDARD_TRENDLINIEN_MAX_LINIEN
    )
    if ansicht == "jahresvergleich":
        return diagramme.anmeldungsverlauf_jahresvergleich(
            reihen, jahre, mit_trend=trendlinien, laufender_monat=laufender_monat
        )
    return diagramme.anmeldungsverlauf_reihen(
        reihen, verlauf.monate, mit_trend=trendlinien, laufender_monat=laufender_monat
    )
