# CLAUDE.md

Diese Datei gibt Claude Code Orientierung in diesem Repository.

## Kommandos

Abhängigkeits- und Python-Verwaltung läuft ausschließlich über **uv**; die Version ist
in `.python-version` auf 3.13 gepinnt. Kein `pip install` im Projekt-venv, kein manuell
angelegtes venv. Colab läuft auf Python 3.13.

```bash
uv sync --extra notebook       # Umgebung herstellen
git config core.hooksPath .githooks  # einmalig: Pre-Commit-Hook aktivieren (siehe unten)
uv run pytest                  # alle Tests
uv run pytest tests/domaene/test_projekt.py::test_restvolumen_ist_budget_minus_verbrauch  # ein Test
uv run ruff check .            # Lint
uv run ruff format .           # Formatierung
uv run jupyter lab             # Notebooks lokal
uvx tox                        # Tests unter Python 3.12-3.14 + Coverage + Lint, ein Kommando
uvx tox -e jupyter             # Notebooks starten (wie uv run jupyter lab, mit --autoreload)
uv sync --extra bericht && uv run python scripts/diagramme_exportieren.py     # Diagramme als PNG exportieren, inkl. Anmeldungsverlauf (--help für Optionen)
uvx tox -e web                 # Web-Frontend lokal starten (siehe Abschnitt "Web-Frontend")
```

`tox` ist nicht Projektabhängigkeit, sondern läuft über `uvx` (`[tool.tox]` in
`pyproject.toml`). `env_list` (`py312`, `py313`, `py314`, `coverage`, `ruff`, `mypy`,
`mypy-notebooks`) läuft bei `uvx tox` ohne weitere Angabe; `jupyter` und `web` sind
zusätzliche Umgebungen und laufen nur mit `-e jupyter` bzw. `-e web`.

## Aufbau

Sechs Pakete mit genau einer erlaubten Abhängigkeitsrichtung. `clockodo/`,
`schulungen/` und `kosten/` sind drei gleichrangige, voneinander unabhängige
Quellschichten für die Domäne – `schulungen/` und `kosten/` hängen aber beide von
`google_sheets/` ab, weil sie exakt dieselbe Google-Sheets-Infrastruktur (Zugangsdaten,
HTTP-Client) nutzen, nur unterschiedliche Tabellenblätter derselben jährlichen Datei
lesen:

```
darstellung  ──►  domaene  ◄──  clockodo
                      ▲
          ┌───────────┼───────────┐
      schulungen                kosten
          │                       │
          └──────►  google_sheets  ◄──────┘
```

Dazu `src/umsatzprognose/util/` als siebtes, aber unsichtbares Paket: keine der obigen
Bibliotheksabhängigkeiten, keine Kenntnis von einem der sechs Bausteine, deshalb nicht
im Diagramm – nur Umgebungserkennung (`in_colab()`), das gemeinsame Lesen von
Umgebungsvariablen/Colab-Secrets (`umgebungsvariable()`, `colab_secret()`, siehe
`clockodo/config.py` und `google_sheets/config.py`) und die Monat-als-Zahlenpaar-
Arithmetik (`Monat`, `ordnung()`, `aus_ordnung()`, `monatsfolge()`), die an mehreren
Stellen in `domaene/`, `clockodo/`, `schulungen/` und `kosten/` gebraucht wird. Jedes
der sechs Pakete darf `util/` importieren.

- `src/umsatzprognose/domaene/` – die Fachobjekte, unveränderlich (`frozen=True`) und
  ohne jede Bibliotheksabhängigkeit außer `numpy` (nur in `simulation.py`) und dem
  abhängigkeitsfreien `util/`. `projekt.py`
  (`Projekt`, `Budget` – Restvolumen roh und prognosewirksam, effektiver Stundensatz,
  Prognose-Scope, `anteil_je_mitarbeiter()`), `kunde.py`, `mitarbeiter.py`
  (`Mitarbeiter.verfuegbare_kapazitaet()`, `Wochenarbeitszeit`, `Abwesenheit`,
  `Feiertag`), `projektanteil.py` (der Aufteilungsschlüssel), `umsatzhistorie.py`
  (`Monatsumsatz`, `Umsatzhistorie`), `verbrauchsverlauf.py` (`Verbrauchsverlauf` – der
  Monatsverbrauch je Projekt, Rückrechnung des Restvolumens, Beobachtungsfenster),
  `abrufquote.py` (`Abrufquote`, `Abrufquotenverteilung` – empirische Verteilung samt
  Ziehung mit Zurücklegen), `bestand.py` (`Bestand`, das Aggregat), `simulation.py`
  (`simulieren()`, `MonteCarloPrognose` – der Rechenkern, siehe unten), `prognose.py`
  (`Prognose`-ABC, `NochKeinePrognose`), `hinweis.py`, `zahlen.py` (deutsche
  Zahlformate ohne `locale`), `kurzarbeit.py` (`Personenmonat`, `Rollenzuordnung`,
  `Schwellenwerte`, `Kurzarbeitsbewertung`, `bewerten()`/`bewertungen()` – siehe
  „Was das Modul fachlich tut" unten, eigenständiger Baustein ohne Bezug zum Rest).
- `src/umsatzprognose/clockodo/` – **alles, was Clockodo weiß, weiß nur dieses Paket.**
  `config.py` (Zugangsdaten, benannte Konstruktoren `automatisch`, `aus_umgebung`,
  `aus_colab_secrets`), `client.py` (`ClockodoClient`: HTTP, Paginierung, verifizierte
  Parameterform je Endpunkt, `ClockodoError` mit Antwortkörper), `nebenlaeufig.py`
  (`synchron`, `gleichzeitig`, siehe unten), `cache.py` (optionaler lokaler
  Verlaufscache für die beiden Vollhistorien-Abrufe, siehe unten), dazu je Endpunkt ein
  Repository: `kunden.py`, `mitarbeiter.py`, `projekte.py`, `umsatz.py`,
  `verbrauchsverlauf.py` und `bestand.py` (`BestandRepository`, der eine Einstieg),
  dazu additiv `kurzarbeit.py` (`KurzarbeitRepository`,
  `rollenzuordnung_automatisch()` – eigenständiger Baustein, kein Teil von
  `BestandRepository`s sieben gleichzeitigen Abrufen).
- `src/umsatzprognose/google_sheets/` – **der gemeinsame Google-Sheets-Zugriff, den
  `schulungen/` und `kosten/` beide nutzen.** `config.py` (`GoogleSheetsConfig`,
  dieselben benannten Konstruktoren wie bei `ClockodoCredentials`, liest u. a.
  `KOSTEN_SHEET_IDS`), `client.py` (`GoogleSheetsClient`: Google-Sheets-API über
  OAuth-Client-ID statt Service-Account, synchron, `werte()` nimmt Spreadsheet-ID und
  Zellbereich entgegen – kennt selbst keinen bestimmten Reiter). Kennt weder
  `schulungen/` noch `kosten/`.
- `src/umsatzprognose/schulungen/` – **alles, was vom Tabellenblatt der
  Schulungsanmeldungen weiß, weiß nur dieses Paket** (Baustein Schulungsanmeldungen,
  siehe unten). `schulungen.py` (`SchulungenRepository` – Header-basiertes
  Spalten-Mapping, deutsches Euro-Format parsen über `domaene.zahlen.euro_parsen()`,
  ein nicht ladbares Jahr wird zum `Hinweis`, nicht zum Fehler). Keine Abhängigkeit zu
  `clockodo/` oder `kosten/`.
- `src/umsatzprognose/kosten/` – **alles, was vom Tabellenblatt der Kostenprognose
  weiß, weiß nur dieses Paket** (Baustein Kosten, siehe unten). `kosten.py`
  (`KostenRepository` – Zeilen 3–15 ohne festen Spaltenbereich (die Spaltenlage
  unterscheidet sich je Jahrgang, siehe unten), Header-basiertes Spalten-Mapping wie
  bei `schulungen/`, Monatsname ausgeschrieben statt Zahl). Keine Abhängigkeit zu
  `clockodo/` oder `schulungen/`.
- `src/umsatzprognose/darstellung/` – der einzige Ort mit plotly (`diagramme.py`,
  `gestaltung.py`) und pandas (`tabellen.py`), dazu `dashboard.py` mit der Fassade
  `Dashboard`, die die Notebooks benutzen.
- `tests/` – pytest, in Unterordnern gespiegelt nach den sechs Bausteinen plus
  `darstellung/`, `util/` und `webapp/` (z. B. `tests/domaene/test_bestand.py` für
  `src/umsatzprognose/domaene/bestand.py`); `conftest.py` (gemeinsame Fixtures) und
  `test_pre_commit_hook.py` (testet `.githooks/pre-commit`, gehört zu keinem der
  Bausteine) bleiben direkt in `tests/`. Die Antwortausschnitte in `conftest.py` sind
  gekürzte, aber echte Antworten samt ihrer Fallen. Jeder Unterordner trägt ein
  (leeres) `__init__.py` - ohne das würden gleichnamige Testdateien in
  verschiedenen Unterordnern (z. B. je ein `test_config.py` unter `clockodo/` und
  unter `util/`) mit demselben Modulnamen kollidieren.
- `notebooks/` – fünf Notebooks mit verschiedenen Zielgruppen plus ein gemeinsames
  Start-Modul, siehe unten.
- `spec/spec-umsatzprognose-clockodo-modul.md` – die Spezifikation des Bausteins Bestand.
- `spec/spec-schulungsanmeldungen.md` – die Spezifikation des Bausteins
  Schulungsanmeldungen.
- `spec/spec-kosten.md` – die Spezifikation des Bausteins Kosten.
- `spec/spec-kurzarbeit.md` – die Spezifikation des Bausteins Kurzarbeitsbereitschaft.
- `spec/clocodo-api.yaml` – OpenAPI-Beschreibung der Clockodo-API.

### Kernregeln

- **Die Domäne kennt kein JSON und keinen HTTP-Client.** Wissen über Clockodos
  Eigenheiten steht in `clockodo/`, je Endpunkt dort, wo seine Abbildung liegt.
- **Die Simulation gehört an den `Bestand`, nicht an das `Projekt`.** Der
  Kapazitätsdeckel wirkt je Person über *alle* ihre Projekte; ein Lauf ist eine Ziehung
  über das gesamte Portfolio. Projekt und Mitarbeiter liefern Regeln und Zustand, keine
  fertigen Prognosen.
- **Die Fachobjekte bleiben unveränderlich.** Der Lauf-Zustand der Simulation
  (Restvolumen je Projekt und Lauf, als numpy-Array) liegt neben den Objekten, nicht in
  ihnen – siehe Moduldocstring von `simulation.py`.
- **Die Abrufe laufen gleichzeitig, die Abbildung nacheinander.** Die sieben Antworten
  einer Prognose hängen nicht voneinander ab; aufeinander angewiesen ist erst das
  Zusammensetzen, weil Projekte Kunde und Person als Objekt tragen und
  Verbrauchsverläufe das fertige Projekt samt Budget brauchen. Deshalb sind die
  Methoden von `ClockodoClient` Coroutinen, `BestandRepository.laden_async()` fächert
  sie mit `gleichzeitig()` auf, und erst danach bildet `ProjektRepository.abbilden()`
  ab. Zwei der sieben Abrufe sind dieselbe Doppelgruppierung von `/v2/entrygroups` –
  einmal nach Person, einmal nach Monat. Ohne `mit_verbrauchsverlauf=False` gibt es
  keine geschätzte Abrufquote-Verteilung.
- **Öffentliche Einstiege sind gewöhnliche Funktionen.** `Dashboard.laden()` und
  `BestandRepository.laden()` legen `synchron()` um die Coroutine – mehr als
  `asyncio.run`, weil in Colab/Jupyter bereits ein Event-Loop läuft.
  `synchron()` führt die Coroutine dann in einem eigenen Thread mit eigenem Loop aus.
  Wer selbst in einem Loop steht, ruft `laden_async()` direkt auf.
- **Nebenläufigkeitsprimitive gehören nicht an ein langlebiges Objekt.**
  `gleichzeitig()` erzeugt seine Sperre je Aufruf und bricht bei einem Fehler die
  übrigen Abrufe ab. `tests/clockodo/test_nebenlaeufig.py` prüft mit einer `asyncio.Barrier`,
  dass die Abrufe wirklich überlappen.
- **Zeitbuchungen werden nicht einzeln geladen.** `/v2/entrygroups` mit
  `grouping[]=projects_id&grouping[]=users_id` liefert die Aufteilung fertig
  aggregiert; der Begriff bleibt als `Projektanteil` im Modell.
- **Der Verlaufscache ist striktes Opt-in.** `entrygroups_je_projekt_und_person` und
  `entrygroups_je_projekt_und_monat` fragen die komplette Historie seit `HISTORIE_VON`
  ab (siehe unten) – bei Clockodo dauert das mehrere Sekunden, weil dort über Jahre
  aggregiert wird. Der längst abgeschlossene Teil dieser Historie ändert sich nach
  Beobachtung nicht mehr (Abrechnungen älterer Monate werden nicht nachträglich
  korrigiert); nur die letzten Monate sind noch in Bewegung. `clockodo/cache.py`
  spaltet die Abfrage deshalb an einem Cutoff (Standard: 6 Monate vor dem Abfrageende,
  übersteuerbar über den Parameter `cache_cutoff_monate` oder die Umgebungsvariable
  `CLOCKODO_CACHE_CUTOFF_MONATE`) in einen stabilen, cachefähigen und einen immer
  frisch geholten Teil; `entrygroups_zusammenfuehren()` in `client.py` führt beide
  wieder zu einer Antwort zusammen, die exakt der eines einzelnen Abrufs entspricht.
  Ohne gesetzte `CLOCKODO_CACHE_TTL_SEKUNDEN` bleibt der Cache aus – das bisherige
  Verhalten, unverändert. Abgelegt wird außerhalb des Repositories im
  Nutzerverzeichnis (`~/.cache/umsatzprognose-clockodo/`), aus demselben Grund wie beim
  gecachten Google-OAuth-Token: gelesene Werte gehören in keine Datei dieses
  Repositories.

### Notebooks

Zielwerkzeug ist ein Notebook in **Google Colab**; der Notebook-Layer bleibt dünn und
beginnt mit einer nur in Colab greifenden Installationszelle. Rechenlogik gehört ins
Paket, nicht ins Notebook.

Die gemeinsame Ladelogik – `Dashboard.laden()` mit Cache – steckt in `notebooks/setup.py`
statt dreifach dupliziert zu sein. Die drei fachlichen Notebooks importieren es in
ihrer ersten Codezelle (`import setup`) und rufen `setup.dashboard(stichtag=…,
horizont_monate=…, auslastung_monate=…)` auf. In Colab holt
dieselbe Zelle vorher per `curl` von GitHub, weil dort außer dem per `pip install
git+…` installierten Paket keine Repository-Dateien liegen; das `pip install` selbst
bleibt in jedem Notebook, weil `setup.py` erst importierbar ist, nachdem
`umsatzprognose` installiert ist. `setup.dashboard()` merkt sich das geladene
Dashboard in einer Modulvariable und liefert bei jedem weiteren Aufruf im selben
Kernel dasselbe Objekt zurück, ohne neu zu laden – ein echter Neuabruf braucht einen
Kernel-Neustart. Bewusst ein normales, importierbares `.py`-Modul und keine geteilte
`.ipynb` mit `%run`: ruff und mypy sehen `import setup` und `dashboard =
setup.dashboard(...)` als gewöhnlichen Code, eine IPython-Magic wie `%run -i` bliebe
für die statische Analyse unsichtbar und ließe `dashboard` in jeder folgenden Zelle
als undefiniert erscheinen. `setup.py` wird nicht eigenständig geöffnet.

- `notebooks/00_datencheck.ipynb` – Umsatzprognose, Gewinn/Verlust und Auslastung im
  Überblick, rein lesend.
- `notebooks/01_dashboard.ipynb` – für Fachexperten. Je Zelle ein Aufruf auf
  `Dashboard`, Fachsprache, keine Endpunkte, keine IDs, keine technischen Marker.
- `notebooks/02_technik_pruefung.ipynb` – für die Entwicklung. Prüfsummen,
  Aufteilungsschlüssel, Sollarbeitszeiten, Kapazität je Person und je Projekt und
  offene fachliche Fragen (`ENTSCHEIDEN`-Abschnitte).
- `notebooks/03_schulungsanmeldungen.ipynb` – unabhängig vom Baustein Bestand: der
  Anmeldungsverlauf öffentlicher Schulungen (Teilnehmerzahl je Monat und Kategorie,
  `setup.anmeldungsverlauf()`), nicht der Umsatz. Die Kategorie-Zuordnung
  (`KATEGORIEN`) ist frei konfigurierbar und steht im Notebook, nicht im Paket.
- `notebooks/04_kurzarbeit.ipynb` – wie `03_schulungsanmeldungen.ipynb` vollständig
  unabhängig, hier vom Baustein Kurzarbeitsbereitschaft
  (`setup.kurzarbeit_rohdaten()`, Rollenzuordnung/Schwellenwerte als eigene,
  editierbare Zelle). Kein Bezug zu `Dashboard` oder zur Umsatzprognose.

### Web-Frontend

`src/umsatzprognose/webapp/` ist ein zweites Frontend neben den Notebooks – eine
gehostete Webseite, die dieselben Daten zeigt, ohne dass Betrachtende Jupyter/Colab
brauchen. Kein eigener Baustein, keine eigene Fachlogik: strukturell nur ein weiterer
Konsument von `Dashboard`, wie `notebooks/`. **Keine eigene Benutzerverwaltung** – es
gibt keine Accounts für Besucher der Seite; alle sehen denselben, periodisch
aktualisierten Stand aus genau einer Clockodo-/Google-Sheets-Anbindung, wie beim
Dashboard-Notebook auch.

- **Rendering**: serverseitig über FastAPI + Jinja2 (`webapp/app.py`,
  `webapp/templates/`) statt einer eigenen JS-Anwendung – die vorhandenen
  Plotly-Figuren aus `darstellung/diagramme.py` und die pandas-Tabellen aus
  `darstellung/tabellen.py` lassen sich unverändert per `to_html()` einbetten, ohne
  eine eigene JSON-API zu brauchen.
- **Vier navigierbare Seiten**, verlinkt über eine gemeinsame Navigation
  (`webapp/templates/basis.html`), jede mit dem Inhalt genau einer Notebook-Zelle
  statt einer eigenen Auswahl: `/` deckt sich mit `notebooks/00_datencheck.ipynb`
  (Gewinn/Verlust je Monat, Gewinn/Verlust je Jahr, kumulierte Umsatzrendite);
  `/dashboard` mit `notebooks/01_dashboard.ipynb` (Umsatzverlauf, die zugehörige
  Monatstabelle `Dashboard.umsatztabelle()`, offenes Auftragsvolumen je Projekt);
  `/schulungen` mit `notebooks/03_schulungsanmeldungen.ipynb` (der
  Anmeldungsverlauf über `diagramme.anmeldungsverlauf()`, samt der dort gepflegten
  `KATEGORIEN`-Zuordnung, als Konstante in `webapp/app.py` übernommen); `/kurzarbeit`
  mit `notebooks/04_kurzarbeit.ipynb` (Baustein Kurzarbeitsbereitschaft,
  `spec/spec-kurzarbeit.md` – rückblickend je Monat, ob die Organisation die
  Voraussetzungen für Kurzarbeit erfüllt hätte, ausschließlich Aggregatzahlen).
  Anders als die anderen drei Seiten **kein Bezug zu `Dashboard`/`DashboardCache`** –
  ein eigenständiger `KurzarbeitCache`, weil der Baustein kein Umsatz- oder
  Kostensignal ist, sondern ein Kapazitäts-/Personalsignal (Spec Abschnitt 2/7).
- **Parameter der Notebook-Ladezellen sind hier URL-Parameter, wählbar über ein
  Dropdown** statt eines freien Zahlenbereichs (via `typing.Literal` - zugleich die
  Dropdown-Optionsliste über `typing.get_args()`, siehe `HorizontMonate`,
  `GewinnVerlustMonate` in `webapp/app.py`): `horizont_monate` (Prognosehorizont – 3,
  4, 5 oder 6 Monate, auf `/` und `/dashboard`, weil beide denselben geladenen
  `Dashboard` zeigen) und `gewinn_verlust_monate` (historisches Fenster – 3, 6, 12,
  24 Monate oder "alle", nur auf `/`). `ab_jahr` (nur auf `/schulungen`, filtert
  einen unabhängig geladenen `Anmeldungsverlauf`) bleibt ein zusammenhängender
  Zahlenbereich (`Query(ge=STANDARD_AB_JAHR, le=aktuelles Jahr)`), weil Jahre
  lückenlos sind; seine Dropdown-Optionen sind einfach dieser Bereich. Ohne Angabe
  gilt nicht starr `STANDARD_AB_JAHR`, sondern `_standard_anzeige_ab_jahr()`: das
  laufende Jahr, wenn davon schon mindestens `STANDARD_ANZEIGE_MINDESTMONAT` (6)
  Monate vorüber sind, sonst zusätzlich das Vorjahr – eine Standardansicht mit nur
  ein oder zwei Monaten wäre zu dünn für einen sinnvollen Blick auf den
  Anmeldungsverlauf.
  `auslastung_monate` aus `Dashboard.laden_async()` ist **kein** URL-Parameter
  (mehr): keine der drei Seiten zeigt etwas, das davon abhängt – eine feste
  Standardkombination genügt, ein Dropdown ohne sichtbare Wirkung wäre nur
  verwirrend. `stichtag` bleibt ebenfalls kein URL-Parameter: anders als die
  anderen gibt es dafür keinen sinnvollen Standard für alle Besuchenden
  gleichzeitig. `Dashboard.gewinn_verlust_monatlich()` akzeptiert seit der
  "alle"-Option auch `monate=None` (zeigt die gesamte geladene Historie, nicht nur
  `STANDARD_HISTORIE_MONATE`).
- **Zwei verschiedene Cache-Strategien, je nachdem, ob ein engerer Parameter
  wirklich weniger laedt oder nur anders anzeigt** (siehe Klassendocstrings in
  `webapp/cache.py`): `DashboardCache` haelt je angefragter
  (`horizont_monate`, `auslastung_monate`)-Kombination einen **eigenen** Eintrag -
  ein anderer `horizont_monate` fragt bei Clockodo tatsaechlich ein anderes
  Zeitfenster ab, und ein neuer Simulationslauf ist dann auch fachlich richtig,
  keine Abkuerzung ueber einen breiteren Lauf. `gewinn_verlust_monate` ist dagegen
  bewusst **kein** Teil dieses Cache-Schluessels: es schneidet nur das schon
  geladene `Dashboard` unterschiedlich zurecht (`Dashboard.gewinn_verlust_monatlich`
  liest lediglich einen anderen Ausschnitt derselben geladenen Historie), ein
  Wechsel zwischen 3/6/12/24/"alle" laedt deshalb nie neu. `AnmeldungsverlaufCache`
  haelt dagegen ganz bewusst **nur einen einzigen** Eintrag, ab dem im Konstruktor
  fest hinterlegten `STANDARD_AB_JAHR`: die Google-Sheets-Dateien sind unabhaengig
  vom gewaehlten `ab_jahr` dieselben, ein engerer Beginn ("seit 2024" statt "seit
  2022") ist immer eine Teilmenge dieses einen geladenen Bereichs -
  `Anmeldungsverlauf.ab_jahr()` filtert dafuer nur noch in-memory, ganz ohne
  erneuten Abruf. `KurzarbeitCache` folgt derselben Logik wie `AnmeldungsverlaufCache`,
  nicht wie `DashboardCache`: anders als beim vorwaerts simulierenden Dashboard haengt
  die Bewertung eines einzelnen Monats ausschliesslich von dessen eigenen
  Personenmonat-Daten ab, nicht davon, wie viele Monate insgesamt angefragt wurden -
  ein engerer Zeitraum ist deshalb immer eine Teilmenge eines breiteren. Der Cache
  laedt deshalb **immer** mit der groessten waehlbaren `anzahl_monate`
  (`MAXIMALE_KURZARBEIT_MONATE`, aktuell 12) und schneidet engere Dropdown-Auswahlen
  nur noch in-memory heraus (`_juengste_monate()`) - ein Wechsel zwischen 1/3/6/12
  Monaten loest also nie einen neuen Ladevorgang bei Clockodo aus.
- **Caching, nicht blockierend**: `webapp/cache.py` erneuert seine Eintraege nach
  Ablauf einer TTL (`WEBAPP_CACHE_TTL_SEKUNDEN`, Standard eine Stunde). Anders
  als `notebooks/setup.py` – eine Modulvariable je Kernel – bedient ein Webserver
  mehrere gleichzeitige Anfragen aus demselben Prozess; ein Neuladen je Anfrage wäre
  wegen des Abrufs und der Monte-Carlo-Simulation zu langsam, ein Cache je Besucher
  unnötig, da es keine Benutzertrennung gibt. `bereit()`/`anstossen()` (statt eines
  blockierenden `holen()`) prüfen, ob etwas schon geladen ist, bzw.
  stoßen einen fehlenden Ladevorgang im Hintergrund an, ohne auf ihn zu warten -
  `/`, `/dashboard` und `/schulungen` liefern in diesem Fall sofort eine schlichte
  "Daten werden geladen"-Seite (`webapp/templates/laedt.html`, Meta-Refresh alle
  zwei Sekunden) statt die Anfrage offenzuhalten. `_vorladen()` (FastAPIs
  `lifespan`) stößt die Standardkombination zusätzlich schon beim Start an, damit
  sie im üblichen Fall längst fertig ist, bevor die ersten Besuchenden eintreffen.
  Ein fehlgeschlagener Hintergrund-Ladevorgang wird auf der Konsole gemeldet (sonst
  wäre er nicht diagnostizierbar) und beim nächsten Aufruf automatisch erneut
  versucht; ein erfolgreicher dagegen bewusst **ohne** Statusausgabe - anders als in
  einer früheren Fassung, die nach jedem Laden einen Ladebericht ausgab.
- **Google-Auth**: der Webserver loggt sich nie selbst interaktiv ein. Der lokale
  OAuth-Login (`google_sheets/client.py`, `_lokale_credentials()`) läuft einmalig auf
  dem Rechner einer administrierenden Person; die entstandene Token-Datei wird dem
  Server als Secret unter einem eigenen Pfad zur Verfügung gestellt
  (`GOOGLE_OAUTH_TOKEN_PFAD`, siehe `token_pfad()` in `google_sheets/client.py`) statt
  am Notebook-Pfad `.google_oauth_token.json`. Offener Punkt vor dem produktiven
  Einsatz: prüfen, ob die OAuth-Client-ID in der Google-Cloud-Konsole im Status "In
  production" statt "Testing" steht – im Testing-Status laufen Refresh-Tokens nach 7
  Tagen ab, ungeeignet für einen dauerhaft laufenden Server.
- **Clockodo-Auth**: unverändert – die API-Key-Authentifizierung ist bereits
  service-artig und funktioniert unverändert aus einem Serverprozess heraus.
- Gehört zum optionalen `web`-Extra (`fastapi`, `jinja2`, `uvicorn`) – keine
  Basisabhängigkeit, weil nur dieses Paket sie braucht. Start lokal: `uvx tox -e web`
  bzw. `uv run --extra web uvicorn umsatzprognose.webapp.app:app`. **Bewusst ohne
  `--reload`** als Standard (siehe Moduldocstring von `webapp/app.py`): `--reload`
  startet zusätzlich einen Reloader-Prozess, der den ohnehin schweren Modulimport
  (FastAPI/Pydantic, pandas, googleapiclient) ein zweites Mal durchläuft und den Start
  spürbar verlangsamt. Für aktive Entwicklung an `webapp/` weiterhin per Posargs
  zuschaltbar, dann aber mit `--reload-dir src/umsatzprognose/webapp` eingeschränkt –
  ohne diese Einschränkung beobachtet `--reload` das gesamte Arbeitsverzeichnis, auch
  z. B. `.tox/`, was bei parallel laufendem `uvx tox` zu ständigen Neustarts führt.

## Keine gelesenen Werte im Repository

**Werte, die aus der Clockodo-API oder den Schulungs-Sheets gelesen wurden, gehören in
keine Datei dieses Repositories** – weder in Code, Tests, Spec, diese Datei noch in
Notizen. Gemeint sind
Umsätze, Stundensätze, Budgets, Anzahlen von Projekten, Personen oder Gruppen, IDs sowie
Kunden-, Projekt- und Personennamen. Das Repository ist öffentlich, die Werte sind echte
Geschäfts- und Personendaten.

Erlaubt bleibt die Beschreibung des **Verhaltens**: Envelope, Feldnamen, Typen,
Sonderfälle, Statuscodes, Grenzen der API. Testfixtures bilden die **Struktur** der
echten Antwort nach, mit frei erfundenen IDs, Namen und Beträgen. Notebooks werden
**ohne Zellausgaben** committet – durchgesetzt durch den Pre-Commit-Hook
`.githooks/pre-commit` (reine Standardbibliothek, kein zusätzliches Paket): er entfernt
Ausgaben und Ausführungszähler aus staged `.ipynb`-Dateien, staged sie neu und bricht
den ersten Commit-Versuch ab, damit die Bereinigung sichtbar bleibt statt unbemerkt
unter den Ursprungsstand zu rutschen. Aktivierung ist pro Klon nötig (kein Git-Standard):
`git config core.hooksPath .githooks`.

## Was das Modul fachlich tut

Rollierende 1–3-Monats-Umsatzprognose für den **Baustein Bestand**: Umsatz aus bereits
in Clockodo angelegten Projekten. Ausgabe ist eine **Bandbreite** (Konfidenzniveaus
95 % / 85 % / 50 % je Monat und als Summe), kein Punktwert.

Zwei Annahmen prägen das Modell:

- Ein in Clockodo angelegtes Projekt gilt als beauftragt; Storno auf Projektebene wird
  nicht modelliert.
- Die einzige modellierte Unsicherheit ist die **Abrufquote**: wie viel des beauftragten
  Restvolumens im Prognosezeitraum tatsächlich abgerufen wird.

Nicht im Modell: Pipeline, Kurzfristgeschäft, Cash-Schicht, Projekte ohne
Clockodo-Eintrag, ein Abschlag für ungeplante Abwesenheit in der Kapazitätsrechnung.

Additiv daneben steht der **Baustein Schulungsanmeldungen**
(`spec/spec-schulungsanmeldungen.md`, `domaene.schulung.Schulungsplan`,
`schulungen/`): der Umsatz bereits geplanter öffentlicher Schulungstermine aus einer
externen Google-Sheets-Tabelle, eine Datei je Jahr. Anders als beim Bestand steht der
Betrag je Termin schon fest – keine Simulation, keine Bandbreite. Die einzige
Unsicherheit ist die Pflegequalität der Quelle, sichtbar über `Schulungsplan.hinweise()`
statt über eine Kennzahl. Der Baustein bleibt unabhängig von der Bestand-Simulation und
verändert weder Restvolumen noch Abrufquote noch Kapazitätsdeckel.

Der **Baustein Kosten** (`spec/spec-kosten.md`, `domaene.kosten.Kostenplan`, `kosten/`)
stellt der Umsatzseite eine Kostenprognose gegenüber: die Gesamtkosten je Monat aus
derselben jährlichen Google-Sheets-Datei wie die Schulungsanmeldungen, aber einem
eigenen Tabellenblatt (`Kosten {jahr}`, gelesen wird Zeile 1–20 ohne festen Zeilen- oder
Spaltenbereich, Kopfzeile inhaltsbasiert ermittelt – siehe unten). Wie bei den
Schulungsanmeldungen steht der Betrag schon fest – keine Simulation, keine Bandbreite.
**Anders als die Schulungsanmeldungen gilt die Kostenprognose auch für bereits
vergangene Monate**, nicht nur für den Prognosehorizont: Clockodo liefert keine
Ist-Kosten, nur Umsätze aus Einsätzen, also gibt es keine andere Quelle für die
Vergangenheit. `Gewinn` (Gesamtumsatz aus Bestand und Schulungsanmeldungen minus
Kosten) wird ausschließlich in der Darstellungsschicht gebildet
(`tabellen.umsatztabelle()`, `diagramme.umsatzverlauf()`) – es gibt kein eigenes
Domänenobjekt, das Umsatz und Kosten gegeneinander verrechnet.

Der **Baustein Kurzarbeitsbereitschaft** (`spec/spec-kurzarbeit.md`,
`domaene.kurzarbeit`, `clockodo.kurzarbeit.KurzarbeitRepository`) steht **komplett
losgelöst** von den drei vorigen Bausteinen: kein Umsatz- oder Kostensignal, sondern
ein Kapazitäts-/Personalsignal, das rückblickend je abgeschlossenem Kalendermonat
prüft, ob die Organisation die Voraussetzungen für Kurzarbeit erfüllt hätte (Quote
kurzarbeitsfähiger Personen ≥ 30 %, je Person Anteil interner Arbeit ≥ 24 % und
kumulierter Überstundenstand < 14 Std. – alle drei Schwellenwerte als Parameter,
siehe `domaene.kurzarbeit.Schwellenwerte`). Wie bei Schulungsanmeldungen/Kosten keine
Simulation, keine Bandbreite. Die Rollenzuordnung (wer aus Geschäftsführung/Vertrieb
nie in den Zähler kurzarbeitsfähiger Personen eingeht) ist eine personenbezogene
Angabe und wird zur Laufzeit aus der Umgebungsvariable `KURZARBEIT_ROLLENZUORDNUNG`
gelesen (`clockodo.kurzarbeit.rollenzuordnung_automatisch()`), nie im Repository
geführt. Der kumulierte Überstundenstand lässt sich nicht direkt aus
`/userreports` lesen: `month_details[].diff` ist live verifiziert **nicht**
kumuliert, sondern nur die Abweichung des einzelnen Monats – `KurzarbeitRepository`
bildet ihn deshalb selbst aus `overtime_carryover` plus der aufsummierten
Monats-`diff`-Werte (siehe Spec Abschnitt 8). Kein Anschluss an `Dashboard` (Spec
Abschnitt 2/7) – ein eigenständiges Notebook (`notebooks/04_kurzarbeit.ipynb`, wie
beim Anmeldungsverlauf) und eine eigenständige Webapp-Seite (`/kurzarbeit`, eigener
`KurzarbeitCache`) zeigen ausschließlich Aggregatzahlen, nie Einzelwerte je Person.

## Rechenkern (Monte Carlo, 10.000 Läufe)

`Bestand.simulieren()` delegiert an `domaene.simulation.simulieren()`. Gerechnet wird
**in Euro als Leitgröße**, Stunden nur als Zwischenschritt für den Kapazitätsdeckel
(`/targethours` liefert Stunden je Wochentag, keine Taglänge).

Der Horizont **beginnt mit dem laufenden Monat**, genauer am Stichtag. Monat 1 ist nur
der Rest des Monats; gezogene Abrufquote und Kapazität werden mit dem Anteil der
verbleibenden Arbeitstage skaliert. Was **vor** dem Stichtag gebucht wurde, ist
Verbrauch und vom Restvolumen abgezogen. Was **nach** dem Stichtag datiert ist, ist die
Untergrenze, nicht Verbrauch:

    Monatsumsatz = max(simulierter Umsatz, bereits gebuchter Umsatz dieses Monats)

Ablauf je Lauf und Horizontmonat:

1. Restvolumen je Projekt: `budget.amount − revenue_kumuliert`. Pauschalleistungen
   laufen über einen abgeleiteten effektiven Stundensatz. Start ist das
   **prognosewirksame** Restvolumen (`max(0, …)`); ein Projekt nach `deadline` mit
   `automatic_completion` trägt ab dem Folgemonat nichts mehr bei.
2. Abrufquote je Monat aus der **portfolioweiten** empirischen Verteilung ziehen →
   gewünschter Euro-Verbrauch, **begrenzt auf das verbleibende Restvolumen**.
3. Über den effektiven Stundensatz in Stunden umrechnen und auf Personen aufteilen –
   Schlüssel ist `Projekt.anteil_je_mitarbeiter()`, der historische Anteil je Person an
   den Gesamtstunden, unverändert fortgeschrieben. Stundensatz `0` oder `None` bleibt
   ungedeckelt (kein Stundenbedarf ableitbar), begrenzt nur durchs Restvolumen.
4. Je Person Bedarf über **alle** Projekte gegen `Mitarbeiter.verfuegbare_kapazitaet()`
   deckeln; bei Überschreitung anteilig kürzen. Der Deckel ist projektübergreifend.
5. Gelieferte Stunden zurück in Euro → Monatsumsatz je Projekt.
6. Restvolumen um den tatsächlichen Euro-Verbrauch reduzieren, in den nächsten Monat
   übertragen (bleibt ≥ 0).

`Prognose` liefert neben den Konfidenzniveaus den **Anteil der Läufe, in denen Kapazität
der limitierende Faktor war** (unterscheidet Nachfrage- von Kapazitätsengpass), sowie
`horizontmonate()` und `gebucht()` (bereits gebuchter Betrag je Horizontmonat, 0 im
Stichtagsmonat). `Bestand.simulieren()` liefert `NochKeinePrognose`, wenn kein Projekt
im Prognose-Scope liegt oder keine Abrufquote-Verteilung vorliegt.

`Mitarbeiter.verfuegbare_kapazitaet(jahr, monat)` = Sollstunden − Feiertage − geplante
Abwesenheit, taggenau gerechnet (ein Tag zählt nie doppelt). Feiertag setzt die
Sollstunden seines Wochentags auf 0, ob ganz oder halb. Als Abwesenheit vom Arbeiten
zählen nur Urlaub und Krankheit, schon ab Status „beantragt" – siehe
`domaene.mitarbeiter.TYPEN_ABWESEND` und `Abwesenheit.zaehlt_als_kapazitaetsabzug`.

## Clockodo-API

Die benötigten Daten liegen über vier API-Generationen verteilt:

| Zweck | Endpunkt | Felder |
|---|---|---|
| Auftragsvolumen | `GET /v4/projects`, `/v4/projects/{id}` | `budget.amount`, `budget.hard` |
| Verbrauch, effektiver Satz | `GET /v2/entrygroups`, `grouping[]=projects_id` | `revenue`, `duration` (nicht `hourly_rate`, siehe unten) |
| Anteil je Person | `GET /v2/entrygroups`, zusätzlich `grouping[]=users_id` | `sub_groups` mit `duration`, `revenue` |
| Umsatz je Monat | `GET /v2/entrygroups`, `grouping[]=month` | `group` (`"JJJJMM"`), `revenue`, `duration` |
| Abrufquote, gebuchter Horizont | `GET /v2/entrygroups`, `grouping[]=projects_id&grouping[]=month` | `sub_groups` mit `group` (`"JJJJMM"`), `revenue` |
| Kundenname | `GET /v3/customers` | `id`, `name` |
| Personen | `GET /v3/users` | `id`, `name`, `active` – **nicht** `default_target_hours` |
| Sollarbeitszeit | `GET /targethours` (unversioniert) | `users_id`, `date_since`/`date_until`, Stunden je Wochentag |
| Geplante Abwesenheit | `GET /v4/absences`, `filter[year]` | `Mitarbeiter.abwesenheiten` |
| Feiertage je Person | `GET /v2/usersNonbusinessDays`, `year` | `users_id`, `days[]` → `Mitarbeiter.feiertage` |
| Einzeleinträge | `GET /v2/entries` | **wird nicht benutzt** – `/v2/entrygroups` deckt alles ab |

`budget.hard` ist `false` – Budgets sind weiche Grenzen, der Verbrauch kann sie
übersteigen, das rohe Restvolumen wird dann negativ (Kalibrierungssignal). Für die
Prognose gilt trotzdem eine harte Grenze: eine Überschreitung kann nur historisch
entstehen, die Prognose überschreitet das Budget nicht. Deshalb führt `Projekt` beide
Größen getrennt – `restvolumen_roh` (vorzeichenbehaftet) und
`restvolumen_prognosewirksam` (bei 0 gekappt).

Basis-URL `https://my.clockodo.com/api`. Authentifizierung über drei Pflicht-Header:
`X-ClockodoApiUser` (E-Mail), `X-ClockodoApiKey`, `X-Clockodo-External-Application`
(Format `name;email`, max. 50 Zeichen) – gekapselt in `clockodo.config.ClockodoCredentials`.

**Fehler immer im Body diagnostizieren, nicht am Status.** Clockodo begründet 400er als
`{"error": {"message": …, "fields": [...]}}`. `get()` wirft deshalb einen eigenen
`ClockodoError` mit angehängtem Antwortkörper statt `raise_for_status()`.

**Ratenbegrenzung (429) ist kein Fehler, sondern ein Hinweis, kurz zu warten.**
Manche Routen begrenzen auf wenige Anfragen pro Minute (`"... limit exceeded (N
requests per 1 minute)"`) - beim gleichzeitigen Abruf vieler Endpunkte
(`nebenlaeufig.gleichzeitig()`) real erreichbar, siehe Web-Frontend oben. `get()`
wiederholt einen 429 deshalb bis zu `RATE_LIMIT_MAX_VERSUCHE`-mal nach
`RATE_LIMIT_WARTEZEIT_SEKUNDEN` (plus Streuung über das gesamte Wartefenster, nicht
nur ein paar Sekunden – gegen mehrere gleichzeitig wartende Zweige derselben
`gleichzeitig()`-Abfrage, die sich sonst mit fast identischer Wartezeit gegenseitig
das Kontingent wieder auffüllen und so trotz mehrerer Wiederholungen weiter
scheitern, live beobachtet bei `KurzarbeitRepository`s vier gleichzeitigen
entrygroups-Aufrufen), bevor doch ein `ClockodoError` geworfen wird.

**Ein 504 (Gateway Timeout) wird ebenfalls wiederholt, kürzer und seltener als ein
429.** Bei großen, ungecachten `/v2/entrygroups`-Abfragen über mehrere Jahre (z. B.
`entrygroups_je_monat` ohne Verlaufscache) antwortet Clockodo vereinzelt mit einer
HTML-Fehlerseite statt JSON, weil das Aggregieren zu lange dauert - kein dauerhafter
Zustand wie bei der Ratenbegrenzung, deshalb `GATEWAY_TIMEOUT_MAX_VERSUCHE`-mal nach nur
`GATEWAY_TIMEOUT_WARTEZEIT_SEKUNDEN` (plus einer knapperen Streuung von 0–5 Sekunden -
anders als beim 429 geht es hier um einen einzelnen Aussetzer, nicht um mehrere
gleichzeitig um dasselbe Kontingent konkurrierende Zweige). Beide Wiederholungsfälle
laufen über dieselbe Fallunterscheidung, `_wartezeit_vor_wiederholung()` in
`client.py`.

Abweichungen von `spec/clocodo-api.yaml`, verifiziert über echte Antworten:

- `EntryGroupV2.group` ist als `string` deklariert, kommt aber bei `group == 0` und bei
  `grouping[]=year` als Zahl → immer `str()` vor dem Zerlegen.
- `EntryGroupV2.revenue` ist als `integer` deklariert, ist aber ein Float → `float()`.
- `EntryGroupV2.duration` ist **Sekunden**, ohne dass die Doku das für `/v2/entrygroups`
  nennt.

Weitere Fallen bei `/v2/entrygroups`:

- Die Projekt-ID kommt als String. `group == 0` steht für Buchungen auf einen Kunden
  ohne Projekt (Phantom-Projekt ohne Filter).
- `hourly_rate` ist als effektiver Stundensatz unbrauchbar – nur gesetzt, wenn
  `hourly_rate_is_equal_and_has_no_lumpsums` `true` ist. Der effektive Satz muss aus
  `revenue / (duration/3600)` abgeleitet werden; Gruppen mit `duration == 0` und
  Umsatz sind reine Pauschalleistungen.
- `grouping` ist ein Array-Parameter (`grouping[]=…`, nicht `grouping=…`). Gültige
  Zeitgruppierungen sind `month`, `year`, `week`, `day` (Singular, ohne `_id`-Suffix).
  `grouping` und `time_since`/`time_until` (volle ISO-Form mit Uhrzeit) sind Pflicht.
- Bei `grouping[]=projects_id&grouping[]=month` kommen die Monats-`sub_groups` nach
  `duration` absteigend, nie chronologisch – `Verbrauchsverlauf.fuer()` sortiert
  deshalb selbst. Die Monatssummen gehen nur auf den Cent auf (Clockodo rundet jede
  Gruppe einzeln). `group == 0` kommt darin mehrfach vor (je Kunde ohne Projekt einmal);
  `VerbrauchsverlaufRepository.abbilden()` faltet deshalb je Projekt-ID zusammen.
- `is_lumpsum` (Untergruppen `"0"`/`"1"` als String) trennt Pauschalleistungen von
  Zeitbuchungen.

### Sollarbeitszeit

`/targethours` (unversioniert, `/v2`/`/v3` → 404) liefert Zeilen mit `type` (`weekly`
mit Wochentagsfeldern, oder `monthly` mit `monthly_target` – in dieser Anlage bisher nur
`weekly`), Stunden als `number` (halbe Stunden möglich). `users.default_target_hours`
(Firmenstandard) bedeutet **keine eigene Zeile** in `/targethours`;
`Mitarbeiter.wochenstunden()` liefert dann `None`.

`/v4/absences` ist der richtige Endpunkt für geplante Abwesenheiten (ältere Versionen →
410 deprecated); Jahresfilter als `deepObject` (`filter[year]`), Envelope-Key `data`,
kein `paging`.

## Google Sheets (Schulungen und Kosten)

**Kein Service-Account** – für diese Anlage gibt Google nur eine OAuth-Client-ID aus
(Anwendungstyp „Desktopanwendung"), kein Service-Account-Key. Deshalb zwei
unterschiedliche Logins statt eines: in Colab meldet sich die aufrufende Person über ihr
eigenes Google-Konto an (`google.colab.auth.authenticate_user`, kein JSON, kein
Secret dafür nötig – sie braucht selbst Lesezugriff auf die betreffenden Sheets); lokal
startet `google_sheets.client._lokale_credentials()` einen einmaligen interaktiven Login
im Browser (`google_auth_oauthlib.flow.InstalledAppFlow`) auf Basis des Client-JSON aus
`GOOGLE_OAUTH_CLIENT_JSON` und speichert das Ergebnis in `.google_oauth_token.json`
(gitignored) zwischen; folgende Aufrufe erneuern den Token automatisch. Dieser gesamte
Zugriff liegt in `google_sheets/`, gemeinsam genutzt von `schulungen/` und `kosten/`
(siehe Aufbau) – **welcher Reiter/Zellbereich gelesen wird, weiß nur der jeweilige
Aufrufer**, nicht `google_sheets.client.GoogleSheetsClient`.

`KOSTEN_SHEET_IDS` (JSON-Objekt Jahr → Spreadsheet-ID) wird in beiden Umgebungen und
von beiden Bausteinen gebraucht, gelesen über `google_sheets.config.GoogleSheetsConfig`
– dieselben drei benannten Konstruktoren wie bei `ClockodoCredentials`, aber ohne
Abhängigkeit zu `clockodo/` (bewusste kleine Dopplung von
`in_colab()`/`MissingCredentialsError`). Der Zugriff läuft über `google-api-python-client`, synchron und ohne
`nebenlaeufig()` – bei ein bis zwei Dateien im Horizont lohnt sich eigene
Nebenläufigkeit nicht.

**Schulungsanmeldungen:** Tabellenblatt `Öffentliche Schulungen`, Spalten werden **über
die Kopfzeile namentlich** zugeordnet (`Jahr`, `Monat`, `Umsatz gesamt`), nicht über die
Position – robust gegenüber den vielen ungenutzten Spalten. `Umsatz gesamt` ist
uneinheitlich formatiertes deutsches Zahlenformat mit Euro-Zeichen, geparst über
`domaene.zahlen.euro_parsen()` (entfernt alles außer Ziffern/Punkt/Komma, dann den
Tausenderpunkt, dann Komma → Punkt).

**Kosten:** Tabellenblatt `Kosten {jahr}` – **ohne festen Zeilen- oder Spaltenbereich**:
gelesen wird pauschal `1:20`, weder Kopfzeilen-Zeile noch Spaltenlage stimmen
jahrgangsweise verlässlich überein (verifiziert am Jahrgang 2022, wo der eigentlichen
Monatsübersicht im selben Zeilenbereich noch eine andere Tabelle vorausgeht, etwa eine
Mitarbeiteraufstellung mit eigener, ähnlicher aber nicht identischer Kopfzeile).
`_kopfzeile_finden()` sucht deshalb inhaltsbasiert die erste Zeile, die sowohl
`Gesamtkosten` als auch `Allgemeinkosten` trägt. `Monat` hat aber nicht in jedem
Jahrgang eine eigene Kopfzeilen-Bezeichnung – ohne sie ermittelt
`_monat_spalte_ermitteln()` die Monatsspalte anhand
ihres Inhalts (die Spalte mit den meisten als deutscher Monatsname erkannten Zellen)
statt über eine feste Position. `Monat` steht als ausgeschriebener deutscher
Monatsname (`Januar`…`Dezember`), nicht als Zahl wie bei den Schulungsanmeldungen.
`Gesamtkosten` wird mit derselben `euro_parsen()` geparst.
`KostenRepository.laden()` deckt anders als `SchulungenRepository.laden()` nicht nur
den Prognosehorizont ab, sondern auch die bereits geladene Umsatzhistorie (Parameter
`historie_monate`) – siehe Moduldocstring von `domaene.kosten`.

Ein für ein Jahr fehlender Eintrag in `KOSTEN_SHEET_IDS` oder eine nicht lesbare Datei
führt **nicht** zu einem Fehler (anders als bei Clockodo), sondern zu einem `Hinweis` an
`Schulungsplan.abbildungshinweise` bzw. `Kostenplan.abbildungshinweise` – Spec-Vorgabe
(Abschnitt 6 der jeweiligen Spec).
