"""Der eine Einstieg, der aus Clockodo einen fertigen Bestand macht.

**Sieben Abrufe, alle gleichzeitig - plus zwei je Jahr im Horizont fuer Abwesenheiten
und Feiertage.** Kunden, Personen, Sollzeiten, Projekte, Verbrauch, Umsatzhistorie und
der monatliche Verbrauch je Projekt sind sieben unabhaengige Antworten, dazu die
geplanten Abwesenheiten und Feiertage (Spec 5.3): ``/v4/absences`` und
``/v2/usersNonbusinessDays`` filtern beide nur nach einem Jahr, ein Horizont ueber die
Jahresgrenze braucht also je zwei Abrufe statt einem. Keine dieser Antworten baut auf
einer anderen auf. Aufeinander angewiesen ist erst das *Zusammensetzen*: die Projekte
brauchen Kunden und Personen als Beschriftung und fuer die Anteile, die
Verbrauchsverlaeufe brauchen die fertigen Projekte samt Budget. Deshalb ist der Abruf
hier gefaechert und die Abbildung danach der Reihe nach.

Nacheinander abgerufen addierten sich die Wartezeiten auf rund 30 Sekunden gegen die
echte Installation; gleichzeitig zaehlt im Wesentlichen der langsamste Abruf - die
Entrygroups mit Personen-Untergruppen (1,9 MB, etwa 20 Sekunden). Die Wartezeit ist
hier fast alles: gerechnet wird beim Abbilden wenig, gewartet wird auf das Netz.

Die beiden teuren Abrufe sind zweimal dieselbe Doppelgruppierung von
``/v2/entrygroups`` - einmal nach Person, einmal nach Monat, je rund 20 Sekunden. Sie
laufen nebeneinander, kosten zusammen also kaum mehr als einer. Wer den monatlichen
Verlauf nicht braucht, schaltet ihn mit ``mit_verbrauchsverlauf=False`` ab; ohne ihn gibt
es allerdings keine geschaetzte Abrufquote-Verteilung (Spec 5.2).

Wer den Bestand in eigenem async-Code laedt, ruft :meth:`BestandRepository.laden_async`
auf; :meth:`BestandRepository.laden` ist derselbe Vorgang fuer Notebook und Skript.
"""

from __future__ import annotations

from datetime import date

from umsatzprognose.domaene.bestand import Bestand

from .client import ClockodoClient, horizontende, verbrauch_bis
from .config import ClockodoCredentials
from .kunden import KundenRepository
from .mitarbeiter import MitarbeiterRepository
from .nebenlaeufig import gleichzeitig, synchron
from .projekte import ProjektRepository
from .projekte import rohdaten as projekt_rohdaten
from .umsatz import UmsatzRepository
from .verbrauchsverlauf import VerbrauchsverlaufRepository
from .verbrauchsverlauf import rohdaten as monatsverbrauch_rohdaten


class BestandRepository:
    """Laedt alle Fachobjekte und setzt sie zum :class:`Bestand` zusammen."""

    def __init__(self, client: ClockodoClient) -> None:
        self._client = client

    @classmethod
    def mit_automatischen_zugangsdaten(cls) -> BestandRepository:
        """Zugangsdaten aus Colab-Secrets oder ``.env``, je nach Umgebung."""
        return cls(ClockodoClient(ClockodoCredentials.automatisch()))

    def laden(
        self,
        *,
        stichtag: date | None = None,
        mit_anteilen: bool = True,
        mit_verbrauchsverlauf: bool = True,
        abgeschlossene_monate: int = 12,
        horizont_monate: int = 3,
    ) -> Bestand:
        """Der Ladevorgang, synchron - der Einstieg fuer Notebook und Skript.

        Auch in Colab und Jupyter, wo bereits ein Event-Loop laeuft; darum kuemmert
        sich :func:`~umsatzprognose.clockodo.nebenlaeufig.synchron`.
        """
        return synchron(
            self.laden_async(
                stichtag=stichtag,
                mit_anteilen=mit_anteilen,
                mit_verbrauchsverlauf=mit_verbrauchsverlauf,
                abgeschlossene_monate=abgeschlossene_monate,
                horizont_monate=horizont_monate,
            )
        )

    async def laden_async(
        self,
        *,
        stichtag: date | None = None,
        mit_anteilen: bool = True,
        mit_verbrauchsverlauf: bool = True,
        abgeschlossene_monate: int = 12,
        horizont_monate: int = 3,
    ) -> Bestand:
        """Den vollstaendigen Bestand zum Stichtag.

        Args:
            stichtag: Tag, auf den sich die Prognose bezieht; ohne Angabe heute. Er
                begrenzt auch den Verbrauch (Spec 5.1) - ein Bestand zu einem
                vergangenen Stichtag rechnet damit nicht mit Buchungen, die es damals
                noch nicht gab. Das ist die Voraussetzung fuer den Rueckwaertstest aus
                Spec 11.4.
            mit_anteilen: die Anteile je Person mitladen (Spec 5.4, Schritt 3).
            mit_verbrauchsverlauf: den monatlichen Verbrauch je Projekt mitladen. Er
                traegt die Abrufquote-Verteilung (Spec 5.2) und die bereits gebuchten
                Betraege im Horizont (5.4); ohne ihn bleibt beides leer.
            abgeschlossene_monate: Laenge der Umsatzhistorie vor dem laufenden Monat.
            horizont_monate: Laenge des Prognosehorizonts (Spec 5.4: 1 bis 3). Sie
                bestimmt, wie weit der monatliche Verbrauch in die Zukunft reicht.
        """
        stichtag = stichtag or date.today()
        personen = MitarbeiterRepository(self._client)
        # Der Horizont beginnt im Stichtagsjahr und kann bis ins naechste reichen
        # (Spec 5.4); /v4/absences und /v2/usersNonbusinessDays filtern beide nur nach
        # einem Jahr, also eines oder zwei je Endpunkt.
        jahre = sorted({stichtag.year, int(horizontende(stichtag, horizont_monate)[:4])})

        # Fuenf Faecher, sieben plus bis zu vier Requests - Personen und Projekte
        # bringen je zwei mit, dazu Abwesenheiten und Feiertage je Jahr im Horizont.
        # Der Stichtag wird hier festgelegt und nicht in den Abrufen aufgeloest: sonst
        # koennten die gleichzeitigen Abrufe ueber einen Tageswechsel hinweg
        # verschiedene Fenster erwischen.
        kunden, mitarbeiter, rohe_projekte, umsatzhistorie, monatsgruppen = await gleichzeitig(
            KundenRepository(self._client).laden_async(),
            personen.laden_async(jahre=jahre),
            projekt_rohdaten(self._client, time_until=verbrauch_bis(stichtag)),
            UmsatzRepository(self._client).laden_async(
                stichtag, abgeschlossene=abgeschlossene_monate
            ),
            self._monatsgruppen(
                stichtag, horizont_monate=horizont_monate, geladen=mit_verbrauchsverlauf
            ),
        )

        # Erst hier treffen sie sich: die Projekte tragen Kunde und Person als Objekt.
        projekte = ProjektRepository(self._client, kunden, mitarbeiter)
        geladene_projekte = projekte.abbilden(*rohe_projekte, mit_anteilen=mit_anteilen)

        return Bestand(
            stichtag=stichtag,
            projekte=geladene_projekte,
            mitarbeiter=tuple(mitarbeiter.values()),
            umsatzhistorie=umsatzhistorie,
            verbrauchsverlaeufe=VerbrauchsverlaufRepository.abbilden(
                monatsgruppen, geladene_projekte
            ),
            abbildungshinweise=personen.hinweise + projekte.hinweise,
        )

    async def _monatsgruppen(
        self, stichtag: date, *, horizont_monate: int, geladen: bool
    ) -> list[dict]:
        """Der siebte Abruf - oder nichts, wenn er abgeschaltet ist.

        Als Coroutine und nicht als ``if`` um den ``gleichzeitig``-Aufruf herum: sonst
        stuende die Liste der Abrufe zweimal im Code, und eine der beiden Fassungen
        wuerde eines Tages nicht mitgepflegt.
        """
        if not geladen:
            return []
        return await monatsverbrauch_rohdaten(
            self._client, stichtag=stichtag, horizont_monate=horizont_monate
        )
