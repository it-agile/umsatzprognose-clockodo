# CLAUDE.md

Kompakte Orientierung für Claude Code in diesem Repository. Details stehen in
`spec/*.md`, den Docstrings der jeweiligen Module und im Code selbst – bei Unsicherheit
dort nachsehen statt zu raten.

## Kommandos

Abhängigkeits-/Python-Verwaltung ausschließlich über **uv** (Python 3.13, siehe
`.python-version`). Kein `pip install`, kein manuelles venv. Colab läuft auf 3.13.

```bash
uv sync --extra notebook              # Umgebung herstellen
git config core.hooksPath .githooks   # einmalig: Pre-Commit-Hook aktivieren (siehe unten)
uv run pytest                         # alle Tests
uv run pytest <pfad>::<test>          # ein Test
uv run ruff check .                   # Lint
uv run ruff format .                  # Formatierung
uv run jupyter lab                    # Notebooks lokal
uvx tox                               # Tests Py 3.12-3.14 + Coverage + Lint in einem Kommando
uvx tox -e jupyter                    # Notebooks mit --autoreload
uvx tox -e web                        # Web-Frontend lokal (siehe „Web-Frontend")
uv sync --extra bericht && uv run python scripts/diagramme_exportieren.py   # Diagramme als PNG
```

`tox` läuft über `uvx`, ist keine Projektabhängigkeit (`[tool.tox]` in `pyproject.toml`).
`env_list` (`py312`, `py313`, `py314`, `coverage`, `ruff`, `mypy`, `mypy-notebooks`) läuft
bei `uvx tox` ohne weitere Angabe; `jupyter`, `web`, `ty` nur mit `-e <name>`.

Werkzeugkonfiguration (ruff, mypy, ty, pytest, coverage, tox) steht zentral in
`pyproject.toml` (`[tool.*]`), nicht in eigenen Dateien – außer ein Werkzeug unterstützt
das gar nicht.

## Code-Qualität

Gemessen an den eigenen Ansprüchen des Projekts (Architektur unten), nicht an einem
generischen Idealbild – ein Muster, das eine bereits dokumentierte, bewusste
Entscheidung umsetzt (z. B. `frozen=True`-Dataclasses, das `Prognose`-Protocol), ist
keine Verletzung.

- Funktionale Ansätze: reine Funktionen statt unnötigem Klassenzustand, Comprehensions/
  Generatorausdrücke statt imperativer Schleifen, wo klarer.
- `typing.Protocol` statt ABCs/konkreter Kopplung, abgesichert durch `mypy`.
- Composition over inheritance; Vererbung nur mit echtem Mehrwert.
- SOLID (SRP/OCP/LSP/ISP/DIP).
- Packaging-Prinzipien (REP/CCP/CRP/ADP/SDP/SAP) für den Zuschnitt der sechs Pakete +
  `util/` (siehe „Aufbau").
- Echte Vereinfachungen ohne Verhaltensänderung, keine kosmetischen Vorlieben. Bewusst
  akzeptierte Duplizierung (z. B. zwischen `scripts/wochenbericht.py` und
  `scripts/diagramme_exportieren.py`, weil beides nicht Teil des installierten Pakets
  ist) bleibt nur legitim, solange sie synchron gehalten wird – läuft sie wiederholt
  auseinander, in ein gemeinsames Modul extrahieren (Vorbild: `scripts/_fortschritt.py`).
- `@dataclass(frozen=True, slots=True)` für die unveränderlichen Fachobjekte in
  `domaene/`. Ausnahme: `Abrufquotenverteilung` (ihre `cached_property`-Felder brauchen
  ein beschreibbares Instanz-`__dict__`, unvereinbar mit `slots=True`).
- Web-Standards in `webapp/`: semantisches HTML5, `lang="de"`, Skip-Link mit sichtbarem
  Fokusstil; `<label>` umschließt sein Formularelement, nie nur Nähe im Markup; ARIA nur
  wo HTML den Zustand nicht selbst trägt; WCAG-AA-Kontrast (≥4,5:1); `scope="col"` auf
  jedem Tabellen-Header, auch bei aus `pandas.DataFrame` erzeugten Tabellen; responsiv
  über `rem`/`em` und horizontal scrollende Container statt Media-Queries; Jinja2-
  Autoescaping bleibt an (Ausnahme nur für selbst injiziertes, kontrolliertes Markup wie
  die Gewinn-Einfärbung); nur `GET`-Routen (keine Benutzerverwaltung); kein Drittanbieter-
  CDN (`plotly.js` wird aus dem installierten Paket lokal ausgeliefert).
- `try`/`except` nur wo eine Vorab-Prüfung nicht möglich oder unverhältnismäßig
  aufwendig ist (E/A-Fehler externer Systeme, z. B. Retry-Logik in `clockodo/client.py`;
  Parsen von Fremdformaten) – sonst Look-Before-You-Leap oder `contextlib.suppress()`.

## Aufbau

Sechs Pakete, eine erlaubte Abhängigkeitsrichtung. `clockodo/`, `schulungen/`, `kosten/`
sind gleichrangige, unabhängige Quellschichten für die Domäne; `schulungen/` und
`kosten/` hängen beide von `google_sheets/` ab (dieselbe Infrastruktur, unterschiedliche
Tabellenblätter derselben jährlichen Datei):

```
darstellung  ──►  domaene  ◄──  clockodo
                      ▲
          ┌───────────┼───────────┐
      schulungen                kosten
          │                       │
          └──────►  google_sheets  ◄──────┘
```

`util/` (siebtes, unsichtbares Paket, keine Abhängigkeit zu den sechs Bausteinen, jeder
darf es importieren): Umgebungserkennung (`in_colab()`), Env-Variablen/Colab-Secrets
(`umgebungsvariable()`, `colab_secret()`), `Monat`-Arithmetik (`ordnung()`,
`aus_ordnung()`, `monatsfolge()`).

- `domaene/` – Fachobjekte, unveränderlich, nur `numpy` + `util/` als Abhängigkeit.
  `projekt.py` (`Projekt`, `Budget`), `kunde.py`, `mitarbeiter.py`
  (`verfuegbare_kapazitaet()`), `projektanteil.py`, `umsatzhistorie.py`
  (`Monatsumsatz`), `verbrauchsverlauf.py`, `abrufquote.py` (`Abrufquotenverteilung`),
  `bestand.py` (`Bestand`, das Aggregat), `simulation.py` (Rechenkern, siehe unten),
  `prognose.py` (`Prognose`-Protocol, `NochKeinePrognose`), `hinweis.py`, `zahlen.py`
  (deutsche Zahlformate ohne `locale`), `kurzarbeit.py`, `auslastung.py` – die drei
  letzten additiv, siehe „Was das Modul fachlich tut".
- `clockodo/` – alles, was Clockodo weiß, weiß nur dieses Paket. `config.py`,
  `client.py` (`ClockodoClient`, `ClockodoError`), `nebenlaeufig.py` (`synchron`,
  `gleichzeitig`), `cache.py` (Verlaufscache, opt-in, siehe Kernregeln), je Endpunkt ein
  Repository (`kunden.py`, `mitarbeiter.py`, `projekte.py`, `umsatz.py`,
  `verbrauchsverlauf.py`, `bestand.py` – `BestandRepository` ist der eine Einstieg),
  additiv `kurzarbeit.py`, `auslastung.py`.
- `google_sheets/` – gemeinsamer Sheets-Zugriff für `schulungen/`+`kosten/`.
  `config.py`, `client.py` (OAuth-Client-ID statt Service-Account, kennt keinen
  bestimmten Reiter).
- `schulungen/` – nur dieses Paket weiß vom Tabellenblatt der Schulungsanmeldungen.
  `schulungen.py` (`SchulungenRepository`).
- `kosten/` – nur dieses Paket weiß vom Tabellenblatt der Kostenprognose. `kosten.py`
  (`KostenRepository`).
- `darstellung/` – einziger Ort mit plotly (`diagramme.py`, `gestaltung.py`) und pandas
  (`tabellen.py`); `dashboard.py` mit Fassade `Dashboard` (von Notebooks/Webapp genutzt);
  `kurzarbeit.py` (Text-Berichte, unabhängig von `Dashboard`).
- `tests/` – gespiegelt nach den sechs Bausteinen + `darstellung/`/`util/`/`webapp/`;
  `conftest.py` (gemeinsame Fixtures/Helfer) und `test_pre_commit_hook.py` bleiben direkt
  in `tests/`. Jeder Unterordner trägt ein leeres `__init__.py` (verhindert
  Modulnamen-Kollisionen gleichnamiger Testdateien).
- `notebooks/` – siehe unten.
- `spec/` – `spec-umsatzprognose-clockodo-modul.md` (Bestand), `spec-schulungsanmeldungen.md`,
  `spec-kosten.md`, `spec-kurzarbeit.md`, `clocodo-api.yaml` (OpenAPI der Clockodo-API).

### Kernregeln

- Die Domäne kennt kein JSON/HTTP; Clockodo-Eigenheiten stehen in `clockodo/`.
- Die Simulation gehört an `Bestand`, nicht an `Projekt` – der Kapazitätsdeckel wirkt je
  Person über alle ihre Projekte, ein Lauf ist eine Ziehung über das gesamte Portfolio.
- Fachobjekte bleiben unveränderlich; der Lauf-Zustand der Simulation (Restvolumen je
  Projekt/Lauf, numpy-Array) liegt daneben, nicht in den Objekten.
- Euro-Beträge laufen als `decimal.Decimal`, nie `float` – einzige Ausnahme: die
  vektorisierte Monte-Carlo-Schleife selbst rechnet intern mit `float`-numpy-Arrays und
  wandelt an ihren Rändern um (siehe Rechenkern). Reine Verhältnis-/Stunden-/Prozentgrößen
  bleiben `float`.
- Die sieben Abrufe einer Prognose laufen gleichzeitig (`ClockodoClient`-Methoden sind
  Coroutinen, `BestandRepository.laden_async()` nutzt `gleichzeitig()`); erst danach
  bildet `ProjektRepository.abbilden()` ab, weil das fertige Objekte braucht. Zwei der
  sieben Abrufe sind dieselbe Doppelgruppierung von `/v2/entrygroups` (einmal nach
  Person, einmal nach Monat).
- Öffentliche Einstiege sind gewöhnliche Funktionen: `Dashboard.laden()`/
  `BestandRepository.laden()` legen `synchron()` um die Coroutine (führt sie in eigenem
  Thread/Loop aus – mehr als `asyncio.run`, weil in Colab/Jupyter schon ein Loop läuft).
  Wer selbst in einem Loop steht, ruft `laden_async()` direkt.
- Nebenläufigkeitsprimitive gehören nicht an ein langlebiges Objekt: `gleichzeitig()`
  erzeugt seine Sperre je Aufruf, bricht bei Fehler die übrigen Abrufe ab.
- Zeitbuchungen werden nie einzeln geladen; `/v2/entrygroups` mit
  `grouping[]=projects_id&grouping[]=users_id` liefert die Aufteilung fertig
  aggregiert (`Projektanteil`).
- Der Verlaufscache (`clockodo/cache.py`) ist striktes Opt-in
  (`CLOCKODO_CACHE_TTL_SEKUNDEN`, sonst kein Cache): spaltet die Vollhistorien-Abfrage an
  einem Cutoff (Standard 6 Monate vor Abfrageende, übersteuerbar über
  `cache_cutoff_monate`/`CLOCKODO_CACHE_CUTOFF_MONATE`) in einen stabilen, cachefähigen
  und einen frisch geholten Teil; `entrygroups_zusammenfuehren()` fügt beide zusammen.
  Abgelegt außerhalb des Repositories in `~/.cache/umsatzprognose-clockodo/`.

### Notebooks

Zielwerkzeug Google Colab; Notebook-Layer dünn, Rechenlogik im Paket. Gemeinsame
Ladelogik in `notebooks/setup.py` (`setup.dashboard(stichtag=…, horizont_monate=…,
auslastung_monate=…)`, merkt sich das Ergebnis je Kernel) – bewusst ein importierbares
`.py`-Modul statt einer geteilten `.ipynb` mit `%run`, damit ruff/mypy den Code sehen.

- `00_datencheck.ipynb` – Umsatzprognose/Gewinn-Verlust im Überblick, rein lesend.
- `01_dashboard.ipynb` – für Fachexperten, ein `Dashboard`-Aufruf je Zelle.
- `02_technik_pruefung.ipynb` – für die Entwicklung: Prüfsummen, Aufteilungsschlüssel,
  offene Fragen (`ENTSCHEIDEN`-Abschnitte).
- `03_schulungsanmeldungen.ipynb` – unabhängig vom Bestand, Anmeldungsverlauf
  (`setup.anmeldungsverlauf()`); Kategorie-Zuordnung aus `SCHULUNGEN_KATEGORIEN`.
- `04_kurzarbeit.ipynb` – unabhängig vom Bestand, Baustein Kurzarbeitsbereitschaft
  (`setup.kurzarbeit_rohdaten()`); ignoriert `KURZARBEIT_AKTIV` bewusst.

### Web-Frontend

`webapp/` ist ein zweites, gehostetes Frontend neben den Notebooks, ohne eigene
Fachlogik oder Benutzerverwaltung – alle Besuchenden sehen denselben, periodisch
aktualisierten Stand. Serverseitig gerendert: FastAPI + Jinja2 (`app.py`,
`templates/`), Plotly-Figuren/pandas-Tabellen unverändert per `to_html()` eingebettet.
`plotly.js` wird lokal aus dem installierten Paket ausgeliefert (kein CDN) – einzige
Ausnahme von „nur `darstellung/` nutzt plotly".

Vier Seiten, je Inhalt einer Notebook-Zelle: `/` (≈ `00_datencheck`), `/dashboard`
(≈ `01_dashboard`, plus Regler für den Anteil fakturierbarer Arbeit in der Simulation,
siehe Rechenkern), `/schulungen` (≈ `03_schulungsanmeldungen`, plus Mehrfach-Filter und
Kategorie-Drilldown „Schulungsdetails" – Details in `app.py`/`schulungen.html`),
`/kurzarbeit` (≈ `04_kurzarbeit`, eigener `KurzarbeitCache`, hinter Feature-Flag
`KURZARBEIT_AKTIV`).

URL-Parameter als kuratierte Dropdowns (`typing.Literal`, Optionsliste über
`typing.get_args()`): `horizont_monate` (3-6 Monate, auf `/`+`/dashboard`),
`gewinn_verlust_monate` (3/6/12/24/„alle", nur `/`), `ab_jahr` (zusammenhängender
Bereich, nur `/schulungen`, filtert nur in-memory). `laeufe` (Anzahl Simulationsläufe,
Schieberegler 1–1.000.000, Standard `STANDARD_LAEUFE=10_000`) ist die Ausnahme: freier
Bereich statt Dropdown, kein Teil des Cache-Schlüssels. `stichtag`/`auslastung_monate`
sind bewusst keine URL-Parameter (kein sinnvoller gemeinsamer Standard bzw. eine feste
Standardkombination genügt).

Abschnitt „Simulations-Parameter" (`_regler.html`, auf `/` und `/dashboard`):
`horizont_monate`+`laeufe` oben, darunter Modus-Dropdown `interne_arbeit_modus`
(Pauschal/Weibull/Gauss) für den Anteil fakturierbarer Arbeit – Regler-Werte ohne
eigene Wahl aus der Historie per Momentenmethode vorbelegt
(`_interne_arbeit_regler_werte()`/`_interne_arbeit_kontext()` in `app.py`; Mechanik der
Regler/Slider selbst siehe dort und in `_regler.html`). Jeder Modus hat einen eigenen
Zurücksetzen-Link. Weitere, rein darstellende Parameter (kein Teil des Cache-
Schlüssels): `restvolumen_top`, `ohne_budget_filter`, `verbrauchsplan` (Projekt→
Zielmonat-Übersteuerung), `interne_arbeit_verteilung_min/max_prozent`.
`verbrauchsplan`/`anteil_fakturierbar`/`laeufe` lösen bei Abweichung eine transiente
Neusimulation aus (`_simuliertes_dashboard()`) statt das geteilte, gecachte `Dashboard`
zu verändern.

Zwei Cache-Strategien (`webapp/cache.py`): `DashboardCache` hält je (`horizont_monate`,
`auslastung_monate`)-Kombination einen eigenen Eintrag (lädt tatsächlich
unterschiedlich); `AnmeldungsverlaufCache`/`KurzarbeitCache` laden immer die
größte/älteste Auswahl und schneiden eine engere Anfrage nur in-memory heraus. Laden
ist nicht blockierend (`bereit()`/`anstossen()`, `laedt.html`-Zwischenseite,
`_vorladen()` beim Start).

Google-Auth: Server loggt sich nie interaktiv ein, nutzt eine vorbereitete Token-Datei
(`GOOGLE_OAUTH_TOKEN_PFAD`). Offener Punkt vor Produktivbetrieb: prüfen, ob die
OAuth-Client-ID in der Google-Cloud-Konsole auf „In production" steht (in „Testing"
laufen Refresh-Tokens nach 7 Tagen ab). Clockodo-Auth unverändert service-artig.

Gehört zum optionalen `web`-Extra (`fastapi`, `jinja2`, `uvicorn`). Start: `uvx tox -e
web`. Bewusst ohne `--reload` (verdoppelt den schweren Modulimport, verlangsamt den
Start) – für aktive Entwicklung mit `--reload-dir src/umsatzprognose/webapp`
zuschaltbar.

## Keine gelesenen Werte im Repository

Werte aus der Clockodo-API oder den Schulungs-Sheets (Umsätze, Stundensätze, Budgets,
Anzahlen, IDs, Kunden-/Projekt-/Personennamen) gehören in keine Datei dieses
öffentlichen Repositories – weder Code, Tests, Spec noch Notizen. Erlaubt: Beschreibung
des Verhaltens (Envelope, Feldnamen, Typen, Grenzen); Testfixtures mit frei erfundenen
IDs/Namen/Beträgen.

Notebooks werden ohne Zellausgaben und mit eingeklappten Code-Zellen committet,
durchgesetzt vom Pre-Commit-Hook `.githooks/pre-commit` (`scripts/notebook_ausgaben.py`:
entfernt Ausgaben, klappt Code-Zellen ohne `metadata.jupyter.source_hidden` ein).
`scripts/notebooks_formatieren.py` macht dieselbe Bereinigung unabhängig vom Commit.
Derselbe Hook formatiert staged `.py`-Dateien mit `ruff format` und bricht den ersten
Commit-Versuch ab, damit Bereinigung/Formatierung sichtbar bleibt. Aktivierung pro
Klon: `git config core.hooksPath .githooks`.

## Was das Modul fachlich tut

Rollierende 1-3-Monats-Umsatzprognose (**Baustein Bestand**) für bereits in Clockodo
angelegte Projekte, als Bandbreite (95/85/50 % Konfidenz), kein Punktwert. Zwei
Annahmen: ein angelegtes Projekt gilt als beauftragt (kein Storno-Modell); die einzige
modellierte Unsicherheit ist die Abrufquote. Nicht im Modell: Pipeline,
Kurzfristgeschäft, Cash-Schicht, Abwesenheitsabschlag.

Additiv daneben:
- **Schulungsanmeldungen** (`schulungen/`, `spec/spec-schulungsanmeldungen.md`): Umsatz
  bereits geplanter öffentlicher Schulungstermine aus Google Sheets, Betrag steht schon
  fest, keine Simulation. Unabhängig vom Bestand.
- **Kosten** (`kosten/`, `spec/spec-kosten.md`): Kostenprognose je Monat, gleiche
  Sheets-Datei, eigenes Tabellenblatt. Gilt anders als Schulungsanmeldungen auch für
  vergangene Monate (Clockodo liefert keine Ist-Kosten). `Gewinn` wird nur in der
  Darstellungsschicht gebildet (Umsatz minus Kosten), kein eigenes Domänenobjekt.
- **Kurzarbeitsbereitschaft** (`domaene.kurzarbeit`, `spec/spec-kurzarbeit.md`):
  komplett losgelöst, Kapazitäts-/Personalsignal statt Umsatz/Kosten – prüft
  rückblickend je Monat, ob die Organisation Kurzarbeit-Voraussetzungen erfüllt hätte
  (Schwellenwerte: Quote kurzarbeitsfähiger Personen ≥30 %, Anteil interner Arbeit je
  Person ≥24 %, Überstundenstand <14 Std. – siehe `domaene.kurzarbeit.Schwellenwerte`).
  Rollenzuordnung aus `KURZARBEIT_ROLLENZUORDNUNG`. Hinter Feature-Flag
  `KURZARBEIT_AKTIV` (Standard aus) an allen Konsumenten außer dem eigenen Notebook und
  der eigenen Datenquelle.

## Rechenkern (Monte Carlo, Standard 10.000 Läufe)

`Bestand.simulieren()` → `domaene.simulation.simulieren()`. Gerechnet in Euro als
Leitgröße, Stunden nur als Zwischenschritt für den Kapazitätsdeckel. Euro-Größen laufen
an den Fachobjekten als `Decimal`, in der Schleife selbst als `float`-numpy-Arrays
(`_aufbauen()`/`_ergebnis()` konvertieren an den Rändern, `_ergebnis()` rundet auf den
Cent).

Horizont beginnt mit dem laufenden Monat ab Stichtag; Monat 1 ist nur der Rest, skaliert
auf verbleibende Arbeitstage. Vor dem Stichtag Gebuchtes ist Verbrauch; danach
Datiertes ist Untergrenze: `Monatsumsatz = max(simulierter Umsatz, bereits gebuchter
Umsatz)`.

Ablauf je Lauf und Horizontmonat:
1. Restvolumen je Projekt (`budget.amount − revenue_kumuliert`, bei Pauschalleistung
   über effektiven Stundensatz); prognosewirksam = `max(0, …)`.
2. Abrufquote aus der portfolioweiten empirischen Verteilung ziehen → Euro-Verbrauch,
   begrenzt aufs Restvolumen. Projekte mit `Projekt.verbrauchsplan_zielmonat` werden
   stattdessen linear bis zu diesem Monat verteilt (Kapazitätsdeckel gilt trotzdem).
3. Über effektiven Stundensatz in Stunden, per `Projekt.anteil_je_mitarbeiter()` auf
   Personen aufgeteilt. Stundensatz 0/`None` bleibt ungedeckelt.
4. Je Person Bedarf über alle Projekte gegen `Mitarbeiter.verfuegbare_kapazitaet()`
   deckeln, anteilig kürzen bei Überschreitung.
5. Stunden zurück in Euro → Monatsumsatz je Projekt.
6. Restvolumen um tatsächlichen Verbrauch reduzieren, in nächsten Monat übertragen
   (≥0).

`Prognose` liefert zusätzlich den Anteil Läufe mit Kapazität als limitierendem Faktor,
`horizontmonate()`, `gebucht()`. `Mitarbeiter.verfuegbare_kapazitaet(jahr, monat)` =
Sollstunden − Feiertage − Abwesenheit (Urlaub/Krankheit ab „beantragt"), taggenau.

**Anteil fakturierbarer Arbeit**: kein fixer Abzug im Modell, sondern standardmäßig ein
Pauschalwert neben der Abrufquote, wahlweise selbst gezogen. `verfuegbare_kapazitaet()`
nimmt optional `interne_arbeit_abschlag` (0.0-1.0, gleichmäßiger Abzug über den ganzen
Horizont). Auf `simulieren()`-Ebene zieht `fakturierbare_arbeit_verteilung`
(`FakturierbareArbeitZiehung`-Protocol, `ziehen_array(form, zufall)`) stattdessen je
Lauf/Monat/Person unabhängig – schließen sich gegenseitig aus (sonst `ValueError`). Drei
Erfüller: `domaene.auslastung.FakturierbareArbeitVerteilung` (historisch/empirisch, aus
`anteile_fakturierbarer_arbeit()` – **ohne** Ausschluss ausschließlich nicht
fakturierbarer Personen-Monate, anders als die Aggregatzahlen
`FakturierbareArbeitBandbreite.je_monat()`/`durchschnittlicher_anteil_fakturierbarer_arbeit()`),
`WeibullFakturierbareArbeit`, `GaussFakturierbareArbeit` (beide mit
`aus_stichprobe()`-Momentenschätzer, Weibull braucht ≥2 Werte, auf `[0.0, 1.0]`
gekappt).

`Dashboard.simuliere()`/`.simuliere_async()` lösen die Automatik auf: Parameter
`anteil_fakturierbar`/`fakturierbare_arbeit_ziehung` (beide `float | None` bzw.
`FakturierbareArbeitZiehung | None`, schließen sich aus). Beide `None` (Modus
„Pauschal" ohne Regler-Wert) → `durchschnittlicher_anteil_fakturierbarer_arbeit()` als
fester Wert (Standard 1.0 ganz ohne Auslastung). Gesetztes `anteil_fakturierbar`
erzwingt einen festen Wert (Modus „Pauschal" mit Regler-Wert); ein
`fakturierbare_arbeit_ziehung`-Objekt ersetzt die Pauschale durch eine je Lauf gezogene
Verteilung (Modus „Weibull"/„Gauss"). `Bestand.simulieren()` kennt diese Automatik
nicht (alte Standardwerte `0.0`/`None`) – lebt bewusst nur in `Dashboard.simuliere()`,
das die Auslastungsmonate hält. In den Notebooks dieselbe Wahl über zwei Variablen vor
„Simulation ausführen" statt eines Dropdowns.

## Clockodo-API

Vier API-Generationen, Basis-URL `https://my.clockodo.com/api`, Auth über drei Header
(`X-ClockodoApiUser`, `X-ClockodoApiKey`, `X-Clockodo-External-Application`).

| Zweck | Endpunkt | Felder |
|---|---|---|
| Auftragsvolumen | `GET /v4/projects[/{id}]` | `budget.amount`, `budget.hard` |
| Verbrauch, effektiver Satz | `GET /v2/entrygroups`, `grouping[]=projects_id` | `revenue`, `duration` |
| Anteil je Person | `/v2/entrygroups`, zusätzlich `grouping[]=users_id` | `sub_groups` |
| Umsatz je Monat | `/v2/entrygroups`, `grouping[]=month` | `group`, `revenue`, `duration` |
| Abrufquote/Horizont | `/v2/entrygroups`, `grouping[]=projects_id&grouping[]=month` | `sub_groups` |
| Kundenname | `GET /v3/customers` | `id`, `name` |
| Personen | `GET /v3/users` | `id`, `name`, `active` (nicht `default_target_hours`) |
| Sollarbeitszeit | `GET /targethours` (unversioniert) | Stunden je Wochentag |
| Abwesenheit | `GET /v4/absences`, `filter[year]` | → `Mitarbeiter.abwesenheiten` |
| Feiertage | `GET /v2/usersNonbusinessDays`, `year` | → `Mitarbeiter.feiertage` |
| Einzeleinträge | `GET /v2/entries` | wird nicht benutzt – `/v2/entrygroups` deckt alles ab |

`budget.hard=false` (weiche Grenze) → `Projekt` führt `restvolumen_roh`
(vorzeichenbehaftet) und `restvolumen_prognosewirksam` (bei 0 gekappt) getrennt.

Fehler immer im Body diagnostizieren (`{"error": {...}}`), nicht am Status –
`ClockodoError`. 429 (Ratenbegrenzung) und 504 (Gateway Timeout) sowie ein
`httpx2.TransportError` vor jeder Antwort werden mit Backoff+Streuung wiederholt
(`_wartezeit_vor_wiederholung()` bzw. eigener `try`/`except` in `get()`); bleibt ein
reiner Verbindungsabbruch bestehen, wird die `httpx2`-Ausnahme weitergereicht statt
eines `ClockodoError`.

Abweichungen von `spec/clocodo-api.yaml` (verifiziert): `EntryGroupV2.group` als
`string` deklariert, kommt aber als Zahl (`group==0`, `grouping[]=year`);
`.revenue` als `integer` deklariert, ist Float; `.duration` ist Sekunden (nicht
dokumentiert). Weitere Fallen: Projekt-ID kommt als String, `group==0` = Kunde ohne
Projekt; `hourly_rate` unbrauchbar als effektiver Satz (nur bei
`hourly_rate_is_equal_and_has_no_lumpsums`), stattdessen `revenue/(duration/3600)`;
`grouping` ist Array-Parameter (`grouping[]=…`), `grouping`+`time_since`/`time_until`
Pflicht; Monats-`sub_groups` kommen nach `duration` sortiert, nicht chronologisch
(`Verbrauchsverlauf.fuer()` sortiert selbst); `group==0` kommt darin mehrfach vor,
`VerbrauchsverlaufRepository.abbilden()` faltet je Projekt-ID zusammen.

`/targethours`: `type` `weekly` (Wochentagsfelder) oder `monthly`. `users.
default_target_hours` (Firmenstandard) bedeutet keine eigene Zeile;
`Mitarbeiter.wochenstunden()` liefert dann `None`. `/v4/absences` ist der richtige
Endpunkt für geplante Abwesenheiten (ältere Versionen deprecated), Jahresfilter als
`deepObject` (`filter[year]`).

## Google Sheets (Schulungen und Kosten)

Kein Service-Account, nur OAuth-Client-ID: Colab nutzt
`google.colab.auth.authenticate_user`, lokal ein einmaliger interaktiver Login
(`google_sheets.client._lokale_credentials()`, Basis `GOOGLE_OAUTH_CLIENT_JSON`, Token
in `.google_oauth_token.json`, gitignored). `KOSTEN_SHEET_IDS` (Jahr→Spreadsheet-ID) und
`SCHULUNGEN_KATEGORIEN` (Kategorie→Schulungstypen) kommen aus
Umgebungsvariablen/Colab-Secrets. Ein fehlender/nicht lesbarer Eintrag führt zu einem
`Hinweis`, nicht zum Fehler.

**Schulungsanmeldungen**: Tabellenblatt `Öffentliche Schulungen`, Spalten über
Kopfzeile namentlich zugeordnet. `Umsatz gesamt` über `domaene.zahlen.euro_parsen()`.
Leere `TN Zahl`-Zelle zählt als 0, nicht als übersprungen.

**Kosten**: Tabellenblatt `Kosten {jahr}`, kein fester Zeilen-/Spaltenbereich –
`kopfzeile_finden()` sucht inhaltsbasiert (`Gesamtkosten`+`Allgemeinkosten`),
`_monat_spalte_ermitteln()` erkennt die Monatsspalte am Inhalt. `Monat` als
ausgeschriebener deutscher Name, nicht als Zahl.
