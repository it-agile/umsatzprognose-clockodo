"""Tests fuer scripts/_fortschritt.py - der gemeinsamen Ladeanzeige von
scripts/wochenbericht.py und scripts/diagramme_exportieren.py."""

from __future__ import annotations

import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
import _fortschritt


def test_mehrzeilenanzeige_uebersteht_gleichzeitige_aktualisierungen_aus_mehreren_threads():
    """Regression fuer die beobachtete Balken-Korruption (Statuszeilen doppelt
    gedruckt bzw. durcheinandergewuerfelt, Terminal am Ende sichtbar kaputt): mehrere
    ``fortschritt()``-Quellen liefen aus verschiedenen Threads gleichzeitig auf
    dieselbe Anzeige ein. Hier mit vielen echten Threads, die alle gleichzeitig
    dieselbe Zeile aktualisieren - ohne die interne Sperre wuerde das zu
    Race-Conditions/Exceptions in ``_neu_zeichnen`` fuehren."""
    anzeige = _fortschritt.Mehrzeilenanzeige(["Bestand", "Kurzarbeit-Rohdaten"])

    def _viele_updates(name: str) -> None:
        for i in range(50):
            anzeige.aktualisieren(name, f"{name} laden ({i})")

    threads = [
        threading.Thread(target=_viele_updates, args=(name,))
        for name in ("Bestand", "Kurzarbeit-Rohdaten")
        for _ in range(3)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert all(not thread.is_alive() for thread in threads)


def test_fortschrittsbalken_zeigt_anteil_als_gefuellte_und_leere_bloecke():
    assert _fortschritt.fortschrittsbalken(0, 4) == "[" + "░" * 24 + "]"
    assert _fortschritt.fortschrittsbalken(4, 4) == "[" + "█" * 24 + "]"


def test_spinner_rotiert_durch_die_zeichen():
    assert _fortschritt.spinner(0) == "|"
    assert _fortschritt.spinner(1) == "/"


def test_relativer_pfad_macht_absoluten_pfad_relativ_zum_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ziel = tmp_path / "unterordner" / "datei.png"

    assert _fortschritt.relativer_pfad(ziel) == Path("unterordner/datei.png")
