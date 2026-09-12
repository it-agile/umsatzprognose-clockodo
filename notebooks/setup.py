"""Gemeinsame Ladelogik der drei Notebooks, siehe deren erste Zelle.

Kein Teil des installierten Pakets: das Colab-`pip install` in den Notebooks muss
zuerst laufen, sonst waere `umsatzprognose` beim Import dieses Moduls noch nicht da.
"""

import html
import threading
import time
from collections.abc import Sequence
from datetime import date, timedelta

import humanize
from IPython.display import HTML, display, update_display

from umsatzprognose import Dashboard
from umsatzprognose.clockodo import KurzarbeitRepository, anzahl_ladeschritte
from umsatzprognose.domaene import Anmeldungsverlauf, Personenmonat
from umsatzprognose.schulungen import SchulungenRepository
from umsatzprognose.util import Monat

humanize.i18n.activate("de_DE")

_dashboard: Dashboard | None = None
_anmeldungsverlauf: Anmeldungsverlauf | None = None
_anmeldungsverlauf_dauer: timedelta | None = None
_kurzarbeit_rohdaten: dict[Monat, tuple[Personenmonat, ...]] | None = None
_kurzarbeit_rohdaten_dauer: timedelta | None = None


class _Mehrzeilenanzeige:
    """Eine feste Anzahl Zeilen (eine je Datenquelle), die bei jeder Aenderung
    gemeinsam neu ausgegeben werden - je eine eigene Zeile zeigt, was gerade laedt und
    wie weit es ist (als grafischer Fortschrittsbalken, siehe :meth:`balken`/
    :meth:`spinner`), am Ende ersetzt durch die fertige Statuszeile. Das Gegenstueck zu
    ``scripts/wochenbericht.py``/``scripts/diagramme_exportieren.py``, dieselbe Idee,
    nur fuer eine Jupyter/Colab-Ausgabezelle statt ein Terminal - dort grafisch statt
    als Text-Balken aus Unicode-Blockzeichen, weil ein HTML-faehiger Ausgabebereich
    echte Balken darstellen kann.

    Frueher (siehe Git-Historie) liefen die einzelnen Zeilen ueber tqdms
    ``position=``-Parameter als unabhaengige Balken. Das teilt sich mit der
    Terminal-Variante denselben Fehler: ``tqdm.notebook.tqdm_notebook.close()`` ruft
    ueber ``super().close()`` dieselbe Positionsverwaltung aus ``tqdm.std`` auf, die
    beim Schliessen eines Balkens die Positionen aller noch offenen Balken mit
    hoeherer Positionsnummer verschiebt - bei mehreren gleichzeitig laufenden,
    mehrfach aktualisierten Quellen (Bestand, Schulungsplan, Kostenplan, Auslastung)
    fuehrt das zu Zeilen, die mitten im Update in der falschen Zelle landen, genau wie
    im Terminal. Diese Klasse zeichnet stattdessen bei jeder Aenderung alle Zeilen
    gemeinsam neu, ohne jede Annahme ueber die Fertigstellungsreihenfolge - und ohne
    tqdm ueberhaupt zu benutzen.

    ``display(..., display_id=...)``/``update_display()`` ersetzen den einmal
    angelegten Block in place - dasselbe Prinzip wie in den Scripts, nur ueber das
    Display-Update-Protokoll von IPython statt ueber Terminal-Cursor-Bewegungen. Immer
    explizit als ``IPython.display.HTML``, nie als roher mehrzeiliger Text: IPython
    zeigt einen reinen ``str`` beim Anzeigen ueber dessen ``repr()`` an (mit
    Anfuehrungszeichen und sichtbaren ``\\n`` statt echter Zeilenumbrueche), was sich
    erst durch den expliziten HTML-Umweg vermeiden laesst - das ergibt nebenbei auch
    den Rahmen fuer echte ``<progress>``-Balken statt blosser Textbalken.

    Threadsicher wie das Gegenstueck in den Scripts: ``fortschritt()``-Meldungen
    koennen aus dem Kernel-Thread selbst ankommen oder aus dem eigenen Thread, den
    ``synchron()`` aufmacht, weil in Jupyter/Colab immer schon ein Event-Loop laeuft
    (siehe ``clockodo.nebenlaeufig``) - die Sperre serialisiert die Aktualisierung
    unabhaengig davon, aus welchem Thread sie kommt.
    """

    def __init__(self, namen: Sequence[str], *, vorlage: str = "{name} laden ...") -> None:
        self._namen = list(namen)
        self._zeilen = {name: self._zeile(vorlage.format(name=name)) for name in self._namen}
        self._sperre = threading.Lock()
        self._anzeige_id = f"anzeige-{id(self)}"
        display(HTML(self._html()), display_id=self._anzeige_id)

    @staticmethod
    def _zeile(inhalt: str) -> str:
        return f"<div>{inhalt}</div>"

    def _html(self) -> str:
        return "".join(self._zeilen[name] for name in self._namen)

    def _setzen(self, name: str, inhalt: str) -> None:
        with self._sperre:
            self._zeilen[name] = self._zeile(inhalt)
            update_display(HTML(self._html()), display_id=self._anzeige_id)

    def aktualisieren(self, name: str, text: str) -> None:
        """Ersetzt die Zeile zu ``name`` durch reinen (HTML-escapten) Text - fuer
        Platzhalter ohne Zwischenstand genauso wie fuer die fertige Statuszeile
        (letzter Aufruf zu diesem ``name``)."""
        self._setzen(name, html.escape(text))

    def balken(self, name: str, *, beschriftung: str, erledigt: int, gesamt: int) -> None:
        """Ein grafischer Fortschrittsbalken (HTML ``<progress>``) mit bekanntem
        Gesamtwert, z. B. fuer Bestands fuenf gleichzeitige Zweige."""
        self._setzen(
            name,
            f"{html.escape(beschriftung)} "
            f'<progress value="{erledigt}" max="{gesamt}" '
            f'style="vertical-align:middle"></progress> {erledigt}/{gesamt}',
        )

    def spinner(self, name: str, *, beschriftung: str) -> None:
        """Ein unbestimmter Fortschrittsbalken (HTML ``<progress>`` ohne ``value``) fuer
        Zwischenschritte ohne bekanntes Gesamt, z. B. Kostenplans verarbeitete Jahre."""
        self._setzen(
            name,
            f'{html.escape(beschriftung)} <progress style="vertical-align:middle"></progress>',
        )


# Ein je Schritt eindeutiger Textbaustein aus dessen fertiger Statuszeile (siehe
# Dashboard.laden_async), der Name entspricht der Zeile in _Mehrzeilenanzeige.
# Verlaufscache-Meldungen o.Ae. passen auf keinen dieser Bausteine und werden
# stattdessen einfach verworfen (wie in den Scripts, siehe dort).
_ABSCHLUSS_MUSTER = {
    "Bestand": "Bestand geladen",
    "Schulungsplan": "Schulung(en) geladen",
    "Kostenplan": "Kostenprognose geladen",
    "Auslastung": "Auslastungsmonat(e) geladen",
}
# Bestand meldet sich zusaetzlich zwischendurch, je einem seiner fuenf gleichzeitigen
# Zweige (siehe BestandRepository.laden_async) - diese Texte sind fest und bekannt,
# anders als bei Kostenplan (dort variiert die Jahreszahl).
_BESTAND_ZWISCHENSCHRITTE = (
    "Kunden geladen",
    "Personen geladen",
    "Projekt-Rohdaten geladen",
    "Umsatzhistorie geladen",
    "Verbrauchsverlauf geladen",
)
# Kostenplan meldet sich ebenfalls zwischendurch, je verarbeitetem Jahr (siehe
# KostenRepository.laden) - die Jahresanzahl ist vorher nicht bekannt, deshalb ein
# unbestimmter Balken (siehe :meth:`_Mehrzeilenanzeige.spinner`) statt eines Anteils
# von einem Gesamtwert.
_KOSTENPLAN_ZWISCHENSCHRITT_MUSTER = "Kostenposten bis"


def dashboard(
    *,
    stichtag: date | None = None,
    horizont_monate: int = 3,
    auslastung_monate: int = 12,
) -> Dashboard:
    """Laedt das Dashboard beim ersten Aufruf je Kernel, danach nur noch zurueckgegeben.

    Zeigt sofort alle vier Schritte (Bestand, Schulungsplan, Kostenplan, Auslastung),
    jeden in einer eigenen Zeile (siehe :class:`_Mehrzeilenanzeige`) - Bestand und
    Schulungsplan laufen gleichzeitig, Kostenplan und Auslastung danach ebenfalls
    gleichzeitig (siehe ``Dashboard.laden_async``). Jede Zeile wird durch ihre fertige
    Statuszeile (Umfang und Dauer) ersetzt, sobald der jeweilige Abruf tatsaechlich
    fertig ist - in der Reihenfolge, in der die vier tatsaechlich fertig werden, nicht
    in der oben genannten. Bestands Zeile fuellt sich zusaetzlich sichtbar ueber dessen
    fuenf gleichzeitige Zweige (Kunden, Personen, Projekt-Rohdaten, Umsatzhistorie,
    Verbrauchsverlauf) als Balken, Kostenplans Zeile zeigt waehrenddessen die
    verarbeiteten Jahre als Spinner - beides ohne eine eigene Zeile je Zwischenschritt
    zu hinterlassen (siehe :data:`_BESTAND_ZWISCHENSCHRITTE`/
    :data:`_KOSTENPLAN_ZWISCHENSCHRITT_MUSTER`).

    Beim zweiten Aufruf im selben Kernel wird nicht neu geladen, die vier Zeilen
    erscheinen aber trotzdem - mit derselben Anzahl Eintraege wie beim ersten Laden,
    aber mit der tatsaechlich gemessenen (nur sehr kurzen) Dauer *dieses* Zugriffs auf
    das schon geladene Dashboard, statt faelschlich die alte, teure Original-Ladedauer
    erneut zu zeigen (siehe ``dauer`` bei
    :meth:`~umsatzprognose.darstellung.dashboard.Dashboard.schritt_berichte`).
    """
    global _dashboard
    start = time.perf_counter()
    namen = ["Bestand", "Schulungsplan", "Kostenplan", "Auslastung"]
    anzeige = _Mehrzeilenanzeige(namen)

    if _dashboard is None:
        bestand_erledigt = 0
        kostenplan_jahre = 0

        def _melden(text: str) -> None:
            nonlocal bestand_erledigt, kostenplan_jahre
            for name, muster in _ABSCHLUSS_MUSTER.items():
                if muster in text:
                    anzeige.aktualisieren(name, text)
                    return
            if text in _BESTAND_ZWISCHENSCHRITTE:
                bestand_erledigt += 1
                anzeige.balken(
                    "Bestand",
                    beschriftung="Bestand laden",
                    erledigt=bestand_erledigt,
                    gesamt=len(_BESTAND_ZWISCHENSCHRITTE),
                )
                return
            if _KOSTENPLAN_ZWISCHENSCHRITT_MUSTER in text:
                kostenplan_jahre += 1
                anzeige.spinner(
                    "Kostenplan", beschriftung=f"Kostenplan laden ({kostenplan_jahre} Jahr(e))"
                )
                return
            # Verlaufscache-Meldungen o.Ae. passen auf keines der bekannten Muster -
            # ohne eigene Zeile bewusst verworfen, siehe scripts/wochenbericht.py.

        _dashboard = Dashboard.laden(
            stichtag=date.today() if stichtag is None else stichtag,
            horizont_monate=horizont_monate,
            auslastung_monate=auslastung_monate,
            fortschritt=_melden,
        )
    else:
        zugriffsdauer = timedelta(seconds=time.perf_counter() - start)
        berichte = _dashboard.schritt_berichte(dauer=zugriffsdauer)
        for name, text in zip(namen, berichte, strict=True):
            anzeige.aktualisieren(name, text)
    return _dashboard


def simulieren(
    dashboard: Dashboard,
    *,
    monate: int = 3,
    laeufe: int = 10_000,
    interne_arbeit_abschlag: float = 0.0,
) -> None:
    """Fuehrt die Monte-Carlo-Simulation aus (siehe ``Dashboard.simuliere``) und zeigt
    dabei einen unbestimmten grafischen Fortschrittsbalken, ersetzt durch das Ergebnis,
    sobald es da ist.

    ``interne_arbeit_abschlag`` siehe ``Dashboard.simuliere`` - Standard 0.0 laesst die
    Simulation unveraendert, wie bisher.

    Anders als beim Laden nur eine einzelne Zeile statt einer Mehrzeilen-Anzeige: die
    Simulation ist eine einzige vektorisierte Rechnung ohne sinnvolle Zwischenschritte
    (siehe Docstring von ``Dashboard.simuliere``) - ein Vorher/Nachher-Bericht genuegt,
    ``fortschritt`` meldet sich entsprechend nur einmal nach Abschluss. Der Balken kann
    deshalb keinen echten Anteil zeigen (siehe :meth:`_Mehrzeilenanzeige.spinner`) -
    ohne ihn stuende waehrend der rechenintensiven Simulation nur ein statischer Text
    da, ohne jedes sichtbare Lebenszeichen.
    """
    anzeige = _Mehrzeilenanzeige(["Simulation"])
    anzeige.spinner("Simulation", beschriftung="Simulation läuft")

    def _melden(text: str) -> None:
        anzeige.aktualisieren("Simulation", text)

    dashboard.simuliere(
        monate=monate,
        laeufe=laeufe,
        interne_arbeit_abschlag=interne_arbeit_abschlag,
        fortschritt=_melden,
    )


def anmeldungsverlauf(*, ab_jahr: int = 2022) -> Anmeldungsverlauf:
    """Laedt den Anmeldungsverlauf beim ersten Aufruf je Kernel, danach nur noch zurueckgegeben.

    Anders als :func:`dashboard` unabhaengig vom Baustein Bestand - liest ueber
    :meth:`~umsatzprognose.schulungen.schulungen.SchulungenRepository.anmeldungsverlauf_laden`
    direkt aus der Schulungsanmeldungen-Quelle, ab dem angegebenen Jahr bis zum
    aktuellen. Die Zeile fuellt sich dabei sichtbar ueber echte Zwischenschritte, ein
    Jahr nach dem anderen (siehe Docstring von ``anmeldungsverlauf_laden``), als
    Balken - ersetzt am Ende durch die eine Statuszeile aus
    :func:`anmeldungsverlauf_bericht`. Beim zweiten Aufruf im selben Kernel wird nicht
    neu geladen, die Statuszeile erscheint aber trotzdem - mit der tatsaechlich
    gemessenen (nur sehr kurzen) Dauer *dieses* Zugriffs, statt faelschlich die alte,
    teure Original-Ladedauer erneut zu zeigen.
    """
    global _anmeldungsverlauf, _anmeldungsverlauf_dauer
    start = time.perf_counter()
    jahre = list(range(ab_jahr, date.today().year + 1))
    anzeige = _Mehrzeilenanzeige(["Anmeldungsverlauf"])
    neu_geladen = _anmeldungsverlauf is None

    if neu_geladen:
        erledigt = 0
        gesamt = len(jahre)

        def _melden(text: str) -> None:
            nonlocal erledigt
            erledigt += 1
            anzeige.balken(
                "Anmeldungsverlauf",
                beschriftung="Anmeldungsverlauf laden",
                erledigt=erledigt,
                gesamt=gesamt,
            )

        _anmeldungsverlauf = (
            SchulungenRepository.mit_automatischen_zugangsdaten().anmeldungsverlauf_laden(
                jahre, fortschritt=_melden
            )
        )
    zugriffsdauer = timedelta(seconds=time.perf_counter() - start)
    if neu_geladen:
        _anmeldungsverlauf_dauer = zugriffsdauer
        anzeige.aktualisieren("Anmeldungsverlauf", anmeldungsverlauf_bericht())
    else:
        anzeige.aktualisieren("Anmeldungsverlauf", anmeldungsverlauf_bericht(dauer=zugriffsdauer))
    return _anmeldungsverlauf


def kurzarbeit_rohdaten(
    *, stichtag: date | None = None, anzahl_monate: int = 6
) -> dict[Monat, tuple[Personenmonat, ...]]:
    """Laedt die Personenmonat-Rohdaten fuer den Baustein Kurzarbeitsbereitschaft beim
    ersten Aufruf je Kernel, danach nur noch zurueckgegeben.

    Komplett unabhaengig von :func:`dashboard` - eigener Baustein, kein Bezug zur
    Umsatzprognose. Liefert bewusst nur die Rohdaten, nicht schon eine
    :class:`~umsatzprognose.domaene.kurzarbeit.Kurzarbeitsbewertung` - die Bewertung
    mit Rollenzuordnung und Schwellenwerten ist eine reine, sofortige Rechnung
    (:func:`~umsatzprognose.domaene.kurzarbeit.bewertungen`) und braucht deshalb keinen
    eigenen Ladevorgang; sie steht im Notebook selbst, damit Schwellenwerte dort ohne
    Neuabruf geaendert werden koennen.

    Die Zeile fuellt sich dabei sichtbar ueber echte Zwischenschritte (fuenf
    gleichzeitige Zweige plus ein ``/userreports``-Abruf je Jahr, siehe Docstring von
    ``KurzarbeitRepository.laden_async``) als Balken. ``total`` steht dabei vorab fest
    (:func:`anzahl_ladeschritte`) - ein "X von Y Monaten" waere hier irrefuehrend, weil
    die Monate selbst nie einzeln, sondern immer als ganzes Zeitfenster je Endpunkt
    abgerufen werden; die tatsaechlich abgesetzten Meldungen zaehlen stattdessen die
    Zweige/Jahres-Abrufe.
    """
    global _kurzarbeit_rohdaten, _kurzarbeit_rohdaten_dauer
    stichtag_aufgeloest = date.today() if stichtag is None else stichtag
    start = time.perf_counter()
    gesamt = anzahl_ladeschritte(stichtag_aufgeloest, anzahl_monate)
    anzeige = _Mehrzeilenanzeige(["Kurzarbeit-Rohdaten"])
    neu_geladen = _kurzarbeit_rohdaten is None

    if neu_geladen:
        erledigt = 0

        def _melden(text: str) -> None:
            nonlocal erledigt
            erledigt += 1
            anzeige.balken(
                "Kurzarbeit-Rohdaten",
                beschriftung="Kurzarbeit-Rohdaten laden",
                erledigt=erledigt,
                gesamt=gesamt,
            )

        _kurzarbeit_rohdaten = KurzarbeitRepository.mit_automatischen_zugangsdaten().laden(
            stichtag=stichtag_aufgeloest,
            anzahl_monate=anzahl_monate,
            fortschritt=_melden,
        )
    zugriffsdauer = timedelta(seconds=time.perf_counter() - start)
    if neu_geladen:
        _kurzarbeit_rohdaten_dauer = zugriffsdauer
        anzeige.aktualisieren("Kurzarbeit-Rohdaten", kurzarbeit_rohdaten_bericht())
    else:
        anzeige.aktualisieren(
            "Kurzarbeit-Rohdaten", kurzarbeit_rohdaten_bericht(dauer=zugriffsdauer)
        )
    return _kurzarbeit_rohdaten


def kurzarbeit_rohdaten_bericht(*, dauer: timedelta | None = None) -> str:
    """Kurzer Ladehinweis, analog zu :func:`anmeldungsverlauf_bericht`.

    Setzt voraus, dass :func:`kurzarbeit_rohdaten` bereits im selben Kernel gelaufen ist.
    """
    if _kurzarbeit_rohdaten is None or _kurzarbeit_rohdaten_dauer is None:
        raise ValueError("Die Kurzarbeit-Rohdaten wurden noch nicht geladen.")
    tatsaechliche_dauer = dauer if dauer is not None else _kurzarbeit_rohdaten_dauer
    anzahl_personen = len({p.mitarbeiter_id for pm in _kurzarbeit_rohdaten.values() for p in pm})
    return (
        f"Kurzarbeits-Rohdaten aus {len(_kurzarbeit_rohdaten)} Monate(n) von {anzahl_personen} "
        f"Person(en) geladen (in {humanize.naturaldelta(tatsaechliche_dauer)})"
    )


def anmeldungsverlauf_bericht(*, dauer: timedelta | None = None) -> str:
    """Kurzer Ladehinweis wie ``Dashboard.ladebericht()`` - Umfang und Dauer des Abrufs.

    Setzt voraus, dass :func:`anmeldungsverlauf` bereits im selben Kernel gelaufen ist.
    ``dauer``, sofern angegeben, ersetzt die gespeicherte Original-Ladedauer - fuer den
    Wiederholungsfall in :func:`anmeldungsverlauf`, siehe dort.
    """
    if _anmeldungsverlauf is None or _anmeldungsverlauf_dauer is None:
        raise ValueError("Der Anmeldungsverlauf wurde noch nicht geladen.")
    tatsaechliche_dauer = dauer if dauer is not None else _anmeldungsverlauf_dauer
    return (
        f"{len(_anmeldungsverlauf.anmeldungen)} Anmeldungen aus "
        f"{len(_anmeldungsverlauf.monate)} Monaten geladen"
        f" (in {humanize.naturaldelta(tatsaechliche_dauer)})"
    )
