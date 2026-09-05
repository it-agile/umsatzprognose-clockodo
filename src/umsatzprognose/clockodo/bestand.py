"""Der Einstieg in Clockodo.

**Sieben Abrufe, alle gleichzeitig - plus zwei je Jahr im Horizont fuer Abwesenheiten
und Feiertage.** Kunden, Personen, Sollzeiten, Projekte, Verbrauch, Umsatzhistorie und
der monatliche Verbrauch je Projekt sind sieben unabhaengige Antworten, dazu die
geplanten Abwesenheiten und Feiertage: ``/v4/absences`` und
``/v2/usersNonbusinessDays`` filtern beide nur nach einem Jahr, ein Horizont ueber die
Jahresgrenze braucht also je zwei Abrufe statt einem. Keine dieser Antworten baut auf
einer anderen auf. Aufeinander angewiesen ist erst das *Zusammensetzen*: die Projekte
brauchen Kunden und Personen als Beschriftung und fuer die Anteile, die
Verbrauchsverlaeufe brauchen die fertigen Projekte samt Budget. Deshalb ist der Abruf
hier gefaechert und die Abbildung danach der Reihe nach.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .client import EntryGroupV2

from datetime import date

from umsatzprognose.domaene import Bestand

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
        cache_cutoff_monate: int | None = None,
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
                cache_cutoff_monate=cache_cutoff_monate,
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
        cache_cutoff_monate: int | None = None,
    ) -> Bestand:
        """Den vollstaendigen Bestand zum Stichtag.

        Args:
            stichtag: Tag, auf den sich die Prognose bezieht; ohne Angabe heute. Er
                begrenzt auch den Verbrauch - ein Bestand zu einem
                vergangenen Stichtag rechnet damit nicht mit Buchungen, die es damals
                noch nicht gab.
            mit_anteilen: die Anteile je Person.
            mit_verbrauchsverlauf: den monatlichen Verbrauch je Projekt. Er
                traegt die Abrufquote-Verteilung und die bereits gebuchten
                Betraege im Horizont.
            abgeschlossene_monate: Laenge der Umsatzhistorie vor dem laufenden Monat.
            horizont_monate: Laenge des Prognosehorizonts. Sie
                bestimmt, wie weit der monatliche Verbrauch in die Zukunft reicht.
            cache_cutoff_monate: siehe
                :meth:`~.client.ClockodoClient.entrygroups_je_projekt_und_person` - ohne
                aktivierten Verlaufscache (Standardfall, siehe :mod:`.cache`) ohne
                jede Wirkung.
        """
        stichtag = stichtag or date.today()
        personen = MitarbeiterRepository(self._client)
        # Der Horizont beginnt im Stichtagsjahr und kann bis ins naechste reichen;
        # /v4/absences und /v2/usersNonbusinessDays filtern beide nur nach
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
            projekt_rohdaten(
                self._client,
                time_until=verbrauch_bis(stichtag),
                cache_cutoff_monate=cache_cutoff_monate,
            ),
            UmsatzRepository(self._client).laden_async(
                stichtag, abgeschlossene=abgeschlossene_monate
            ),
            self._monatsgruppen(
                stichtag,
                horizont_monate=horizont_monate,
                geladen=mit_verbrauchsverlauf,
                cache_cutoff_monate=cache_cutoff_monate,
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
        self,
        stichtag: date,
        *,
        horizont_monate: int,
        geladen: bool,
        cache_cutoff_monate: int | None = None,
    ) -> list[EntryGroupV2]:
        """Der siebte Abruf - oder nichts, wenn er abgeschaltet ist.

        Als Coroutine und nicht als ``if`` um den ``gleichzeitig``-Aufruf herum: sonst
        stuende die Liste der Abrufe zweimal im Code, und eine der beiden Fassungen
        wuerde eines Tages nicht mitgepflegt.
        """
        if not geladen:
            return []
        return await monatsverbrauch_rohdaten(
            self._client,
            stichtag=stichtag,
            horizont_monate=horizont_monate,
            cache_cutoff_monate=cache_cutoff_monate,
        )
