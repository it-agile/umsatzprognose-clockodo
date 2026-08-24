"""Der eine Einstieg, der aus Clockodo einen fertigen Bestand macht.

Fuenf Abrufe in fester Reihenfolge, weil sie aufeinander aufbauen: Kunden und Personen
zuerst, weil die Projekte sie als Beschriftung und fuer die Anteile brauchen; die
Projekte selbst mit Verbrauch und Anteilen; zuletzt die Umsatzhistorie. Wer die Reihen-
folge aendert, muss die Uebergaben mitziehen.

Rund 30 Sekunden gegen die echte Installation, der groesste Teil davon der Abruf der
Entrygroups mit Personen-Untergruppen (1,9 MB). Fuer eine manuell ausgeloeste Prognose
ist das vertretbar; wer nur die Zahlen des Dashboards braucht, kann die Anteile ueber
``mit_anteilen=False`` weglassen und spart die Haelfte.
"""

from __future__ import annotations

from datetime import date

from umsatzprognose.clockodo.client import ClockodoClient
from umsatzprognose.clockodo.config import ClockodoCredentials
from umsatzprognose.clockodo.kunden import KundenRepository
from umsatzprognose.clockodo.mitarbeiter import MitarbeiterRepository
from umsatzprognose.clockodo.projekte import ProjektRepository
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
        """Den vollstaendigen Bestand zum Stichtag.

        Args:
            stichtag: Tag, auf den sich die Prognose bezieht; ohne Angabe heute.
            mit_anteilen: die Anteile je Person mitladen (Spec 5.4, Schritt 3).
            abgeschlossene_monate: Laenge der Umsatzhistorie vor dem laufenden Monat.
        """
        stichtag = stichtag or date.today()

        kunden = KundenRepository(self._client).laden()
        personen = MitarbeiterRepository(self._client)
        mitarbeiter = personen.laden()

        projekte = ProjektRepository(self._client, kunden, mitarbeiter)
        geladene_projekte = projekte.laden(mit_anteilen=mit_anteilen)

        umsatzhistorie = UmsatzRepository(self._client).laden(
            stichtag, abgeschlossene=abgeschlossene_monate
        )

        return Bestand(
            stichtag=stichtag,
            projekte=geladene_projekte,
            mitarbeiter=tuple(mitarbeiter.values()),
            umsatzhistorie=umsatzhistorie,
            abbildungshinweise=personen.hinweise + projekte.hinweise,
        )
