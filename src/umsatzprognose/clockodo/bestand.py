"""Der eine Einstieg, der aus Clockodo einen fertigen Bestand macht.

**Sechs Abrufe, alle gleichzeitig.** Sie bauen nicht aufeinander auf - Kunden, Personen,
Sollzeiten, Projekte, Verbrauch und Umsatzhistorie sind sechs unabhaengige Antworten.
Aufeinander angewiesen ist erst das *Zusammensetzen*: die Projekte brauchen Kunden und
Personen als Beschriftung und fuer die Anteile. Deshalb ist der Abruf hier gefaechert
und die Abbildung danach der Reihe nach.

Nacheinander abgerufen addierten sich die Wartezeiten auf rund 30 Sekunden gegen die
echte Installation; gleichzeitig zaehlt im Wesentlichen der langsamste Abruf - die
Entrygroups mit Personen-Untergruppen (1,9 MB, etwa 20 Sekunden). Die Wartezeit ist
hier fast alles: gerechnet wird beim Abbilden wenig, gewartet wird auf das Netz.

Wer den Bestand in eigenem async-Code laedt, ruft :meth:`BestandRepository.laden_async`
auf; :meth:`BestandRepository.laden` ist derselbe Vorgang fuer Notebook und Skript.
"""

from __future__ import annotations

from datetime import date

from umsatzprognose.clockodo.client import ClockodoClient, verbrauch_bis
from umsatzprognose.clockodo.config import ClockodoCredentials
from umsatzprognose.clockodo.kunden import KundenRepository
from umsatzprognose.clockodo.mitarbeiter import MitarbeiterRepository
from umsatzprognose.clockodo.nebenlaeufig import gleichzeitig, synchron
from umsatzprognose.clockodo.projekte import ProjektRepository
from umsatzprognose.clockodo.projekte import rohdaten as projekt_rohdaten
from umsatzprognose.clockodo.umsatz import UmsatzRepository
from umsatzprognose.domaene.bestand import Bestand


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
        abgeschlossene_monate: int = 12,
    ) -> Bestand:
        """Der Ladevorgang, synchron - der Einstieg fuer Notebook und Skript.

        Auch in Colab und Jupyter, wo bereits ein Event-Loop laeuft; darum kuemmert
        sich :func:`~umsatzprognose.clockodo.nebenlaeufig.synchron`.
        """
        return synchron(
            self.laden_async(
                stichtag=stichtag,
                mit_anteilen=mit_anteilen,
                abgeschlossene_monate=abgeschlossene_monate,
            )
        )

    async def laden_async(
        self,
        *,
        stichtag: date | None = None,
        mit_anteilen: bool = True,
        abgeschlossene_monate: int = 12,
    ) -> Bestand:
        """Den vollstaendigen Bestand zum Stichtag.

        Args:
            stichtag: Tag, auf den sich die Prognose bezieht; ohne Angabe heute. Er
                begrenzt auch den Verbrauch (Spec 5.1) - ein Bestand zu einem
                vergangenen Stichtag rechnet damit nicht mit Buchungen, die es damals
                noch nicht gab. Das ist die Voraussetzung fuer den Rueckwaertstest aus
                Spec 11.4.
            mit_anteilen: die Anteile je Person mitladen (Spec 5.4, Schritt 3).
            abgeschlossene_monate: Laenge der Umsatzhistorie vor dem laufenden Monat.
        """
        stichtag = stichtag or date.today()
        personen = MitarbeiterRepository(self._client)

        # Vier Faecher, sechs Requests - Personen und Projekte bringen je zwei mit.
        # Der Stichtag wird hier festgelegt und nicht in den Abrufen aufgeloest: sonst
        # koennten die gleichzeitigen Abrufe ueber einen Tageswechsel hinweg
        # verschiedene Fenster erwischen.
        kunden, mitarbeiter, rohe_projekte, umsatzhistorie = await gleichzeitig(
            KundenRepository(self._client).laden_async(),
            personen.laden_async(),
            projekt_rohdaten(self._client, time_until=verbrauch_bis(stichtag)),
            UmsatzRepository(self._client).laden_async(
                stichtag, abgeschlossene=abgeschlossene_monate
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
            abbildungshinweise=personen.hinweise + projekte.hinweise,
        )
