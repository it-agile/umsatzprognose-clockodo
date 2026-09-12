"""Kurzarbeitsbereitschaft - rueckblickend je Kalendermonat pruefen, ob die
Organisation die Voraussetzungen fuer Kurzarbeit erfuellt haette.

**Additiv und unabhaengig vom Baustein Bestand**, wie :mod:`.schulung` und
:mod:`.kosten`: kein Monte-Carlo-Lauf, keine Bandbreite - jeder Monat hat ein
eindeutiges, deterministisches Ergebnis auf Basis bereits gebuchter Zeit. Anders als
dort aber **kein Bezug zur Umsatzprognose ueberhaupt** - ein Kapazitaets-/
Personalsignal statt eines Umsatz- oder Kostensignals, deshalb
bewusst nicht an :class:`~umsatzprognose.domaene.bestand.Bestand` angebunden.

Getrennt wie bei :mod:`~umsatzprognose.domaene.simulation`: :class:`Personenmonat` ist
die reine, bewertungsfreie Rohdatenabbildung (liefert
:class:`~umsatzprognose.clockodo.kurzarbeit.KurzarbeitRepository`),
:func:`bewerten` die reine Domänenfunktion, die Rohdaten mit der Rollenzuordnung
(:class:`Rollenzuordnung`) und den Schwellenwerten (:class:`Schwellenwerte`)
verknuepft.

**Fuer einzelne Personen bleibt unsichtbar, an welcher Bedingung sie scheitern**:
:class:`Kurzarbeitsbewertung` traegt ausschliesslich Aggregatzahlen.
Die drei personenbezogenen :class:`~umsatzprognose.domaene.hinweis.Hinweis` (fuer
ausgeschlossene, unklassifizierte und nicht bestimmbare Personen) tragen zwar
IDs in ``betroffene``, aber nur zur Zaehlung (``Hinweis.anzahl``) - keine Ausgabe
zeigt ``betroffene`` selbst.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from umsatzprognose.util import Monat

from collections import defaultdict
from dataclasses import dataclass, field

from .hinweis import Hinweis

# Die sechs sich gegenseitig ausschliessenden Kategorien einer Person in einem Monat -
# Schluessel fuer :func:`_kategorie` und die Sammlung in :func:`bewerten`.
_NICHT_BESTIMMBAR = "nicht_bestimmbar"
_AUSGESCHLOSSEN = "ausgeschlossen"
_KURZARBEITSFAEHIG = "kurzarbeitsfaehig"
_SCHEITERT_BEIDE = "scheitert_beide"
_SCHEITERT_INTERN = "scheitert_intern"
_SCHEITERT_UEBERSTUNDEN = "scheitert_ueberstunden"


@dataclass(frozen=True, slots=True)
class Personenmonat:
    """Die fuer die Regel noetigen Rohdaten einer Person in einem Kalendermonat.

    Reine Clockodo-Abbildung, ohne Kenntnis von Rollen oder
    Schwellenwerten - ``name`` ist trotzdem Teil dieser Rohdaten, weil
    :class:`Rollenzuordnung` ueber den Namen zuordnet und :func:`bewerten`
    ausser den Rohdaten selbst keine weitere Personenzuordnung entgegennimmt.

    Attributes:
        mitarbeiter_id: die ``users_id``.
        name: der Personenname, ``None`` wenn nicht hinterlegt.
        jahr: Kalenderjahr des Monats.
        monat: Kalendermonat (1-12).
        interne_stunden: gebuchte Zeit mit ``billable == 0``.
        externe_stunden: gebuchte Zeit mit ``billable in {1, 2}``.
        gesamt_stunden: gebuchte Zeit ohne Billable-Filter - der ungefilterte
            Konsistenz-Abruf. Kann wegen unabhaengiger
            Abrufe geringfuegig von ``interne_stunden + externe_stunden``
            abweichen; die Differenz ist :attr:`unklassifizierte_stunden`.
        ueberstundenstand: der kumulierte Ueberstundenstand zum Monatsende, ``None``
            wenn dafuer kein Eintrag vorliegt.
    """

    mitarbeiter_id: int
    name: str | None
    jahr: int
    monat: int
    interne_stunden: float
    externe_stunden: float
    gesamt_stunden: float
    ueberstundenstand: float | None

    @property
    def unklassifizierte_stunden(self) -> float:
        """Abweichung zwischen ungefiltertem und intern+extern klassifiziertem Abruf.

        Nie negativ: eine geringfuegig kleinere ungefilterte Summe (Rundung
        unabhaengiger Abrufe) zaehlt hier als 0, nicht als negative Klassifikation.
        """
        return max(0.0, self.gesamt_stunden - self.interne_stunden - self.externe_stunden)

    @property
    def alle_arbeitsstunden(self) -> float:
        """Nenner fuer den Anteil interner Arbeit - intern, extern und
        unklassifiziert zusammen."""
        return self.interne_stunden + self.externe_stunden + self.unklassifizierte_stunden

    @property
    def anteil_interner_arbeit(self) -> float | None:
        """Anteil von :attr:`interne_stunden` an :attr:`alle_arbeitsstunden`, ``None``
        ohne gebuchte Arbeitsstunden in diesem Monat."""
        arbeitsstunden = self.alle_arbeitsstunden
        return self.interne_stunden / arbeitsstunden if arbeitsstunden else None


@dataclass(frozen=True, slots=True)
class Rollenzuordnung:
    """Personen, die nie in den Zaehler kurzarbeitsfaehiger Personen eingehen.

    Zuordnung ueber den Namen statt der ID: die Liste ist eine personenbezogene
    Angabe und wird zur Laufzeit aus einer Umgebungsvariable/einem Colab-Secret
    gelesen (siehe :mod:`umsatzprognose.clockodo.kurzarbeit`), nie im Repository
    geführt.
    """

    namen: frozenset[str] = frozenset()

    def ausgeschlossen(self, name: str | None) -> bool:
        return name is not None and name in self.namen


@dataclass(frozen=True, slots=True)
class Schwellenwerte:
    """Die drei Schwellenwerte der Regel, als Parameter von aussen."""

    anteil_interne_arbeit: float = 0.24
    ueberstunden_stunden: float = 14.0
    quote_organisation: float = 0.30


@dataclass(frozen=True, slots=True)
class Kurzarbeitsbewertung:
    """Das Ergebnis von :func:`bewerten` fuer einen Kalendermonat - ausschliesslich
    Aggregatzahlen, keine personenbezogenen Einzelwerte.

    Die fuenf Zaehler ``anzahl_kurzarbeitsfaehig``, ``anzahl_scheitert_*`` und
    ``anzahl_ausgeschlossen`` sind eine Partition der einbezogenen Personen -
    :attr:`anzahl_einbezogen` (der Nenner der 30-%-Quote) ist ihre Summe.
    ``anzahl_nicht_bestimmbar`` steht ausserhalb dieser Partition, weder
    Zaehler noch Nenner.
    """

    jahr: int
    monat: int
    schwellenwerte: Schwellenwerte
    anzahl_kurzarbeitsfaehig: int = 0
    anzahl_scheitert_interne_arbeit: int = 0
    anzahl_scheitert_ueberstunden: int = 0
    anzahl_scheitert_beide: int = 0
    anzahl_ausgeschlossen: int = 0
    anzahl_nicht_bestimmbar: int = 0
    hinweise: tuple[Hinweis, ...] = field(default_factory=tuple)

    @property
    def schluessel(self) -> Monat:
        return (self.jahr, self.monat)

    @property
    def anzahl_einbezogen(self) -> int:
        """Der Nenner der 30-%-Quote - alle bewertbaren Personen, inklusive
        der laut Rollenzuordnung ausgeschlossenen."""
        return (
            self.anzahl_kurzarbeitsfaehig
            + self.anzahl_scheitert_interne_arbeit
            + self.anzahl_scheitert_ueberstunden
            + self.anzahl_scheitert_beide
            + self.anzahl_ausgeschlossen
        )

    @property
    def quote(self) -> float | None:
        """Anteil kurzarbeitsfaehiger Personen, ``None`` ohne einbezogene Person."""
        nenner = self.anzahl_einbezogen
        return self.anzahl_kurzarbeitsfaehig / nenner if nenner else None

    @property
    def vorbereitet(self) -> bool | None:
        """Ob die Organisation die Voraussetzung erfuellt, ``None`` ohne Quote."""
        quote = self.quote
        return None if quote is None else quote >= self.schwellenwerte.quote_organisation


def _kategorie(
    person: Personenmonat, *, rollenzuordnung: Rollenzuordnung, schwellenwerte: Schwellenwerte
) -> str:
    """Die Kategorie einer Person in einem Monat - eine reine
    Klassifikationsfunktion ohne Zaehlerzustand, siehe :func:`bewerten`."""
    anteil_intern = person.anteil_interner_arbeit
    if person.ueberstundenstand is None or anteil_intern is None:
        return _NICHT_BESTIMMBAR
    if rollenzuordnung.ausgeschlossen(person.name):
        return _AUSGESCHLOSSEN

    erfuellt_intern = anteil_intern >= schwellenwerte.anteil_interne_arbeit
    erfuellt_ueberstunden = person.ueberstundenstand < schwellenwerte.ueberstunden_stunden
    if erfuellt_intern and erfuellt_ueberstunden:
        return _KURZARBEITSFAEHIG
    if not erfuellt_intern and not erfuellt_ueberstunden:
        return _SCHEITERT_BEIDE
    if not erfuellt_intern:
        return _SCHEITERT_INTERN
    return _SCHEITERT_UEBERSTUNDEN


_STANDARD_ROLLENZUORDNUNG = Rollenzuordnung()
_STANDARD_SCHWELLENWERTE = Schwellenwerte()


def bewerten(
    personenmonate: Sequence[Personenmonat],
    *,
    monat: Monat,
    rollenzuordnung: Rollenzuordnung = _STANDARD_ROLLENZUORDNUNG,
    schwellenwerte: Schwellenwerte = _STANDARD_SCHWELLENWERTE,
) -> Kurzarbeitsbewertung:
    """Bewertet die Rohdaten genau eines Kalendermonats.

    Fuer mehrere Monate siehe :func:`bewertungen`.
    """
    jahr, monat_nr = monat

    ids_je_kategorie: dict[str, list[str]] = defaultdict(list)
    unklassifizierte_ids: list[str] = []
    for person in personenmonate:
        kategorie = _kategorie(
            person, rollenzuordnung=rollenzuordnung, schwellenwerte=schwellenwerte
        )
        ids_je_kategorie[kategorie].append(str(person.mitarbeiter_id))
        if kategorie != _NICHT_BESTIMMBAR and person.unklassifizierte_stunden > 0:
            unklassifizierte_ids.append(str(person.mitarbeiter_id))

    ausgeschlossene_ids = ids_je_kategorie[_AUSGESCHLOSSEN]
    nicht_bestimmbare_ids = ids_je_kategorie[_NICHT_BESTIMMBAR]

    hinweise = tuple(
        Hinweis(text, tuple(betroffene))
        for text, betroffene in (
            (
                "Diese Personen sind laut Rollenzuordnung ausgeschlossen (Geschäftsführung/"
                "Vertrieb) und zählen nie in den Zähler kurzarbeitsfähiger Personen",
                ausgeschlossene_ids,
            ),
            (
                "Bei diesen Personen weicht die Summe aus interner und externer Zeit von der "
                "ungefilterten Gesamtzeit ab - die Differenz zählt als unklassifizierte Stunden",
                unklassifizierte_ids,
            ),
            (
                "Für diese Personen ist kein Überstundenstand bestimmbar oder es liegt keine "
                "gebuchte Stunde vor - sie wurden vollständig aus der Auswertung genommen",
                nicht_bestimmbare_ids,
            ),
        )
        if betroffene
    )

    return Kurzarbeitsbewertung(
        jahr=jahr,
        monat=monat_nr,
        schwellenwerte=schwellenwerte,
        anzahl_kurzarbeitsfaehig=len(ids_je_kategorie[_KURZARBEITSFAEHIG]),
        anzahl_scheitert_interne_arbeit=len(ids_je_kategorie[_SCHEITERT_INTERN]),
        anzahl_scheitert_ueberstunden=len(ids_je_kategorie[_SCHEITERT_UEBERSTUNDEN]),
        anzahl_scheitert_beide=len(ids_je_kategorie[_SCHEITERT_BEIDE]),
        anzahl_ausgeschlossen=len(ausgeschlossene_ids),
        anzahl_nicht_bestimmbar=len(nicht_bestimmbare_ids),
        hinweise=hinweise,
    )


def bewertungen(
    daten: Mapping[Monat, Sequence[Personenmonat]],
    *,
    rollenzuordnung: Rollenzuordnung = _STANDARD_ROLLENZUORDNUNG,
    schwellenwerte: Schwellenwerte = _STANDARD_SCHWELLENWERTE,
) -> dict[Monat, Kurzarbeitsbewertung]:
    """Bewertet mehrere Kalendermonate - ruft :func:`bewerten` je Monat auf."""
    return {
        monat: bewerten(
            personenmonate,
            monat=monat,
            rollenzuordnung=rollenzuordnung,
            schwellenwerte=schwellenwerte,
        )
        for monat, personenmonate in daten.items()
    }
