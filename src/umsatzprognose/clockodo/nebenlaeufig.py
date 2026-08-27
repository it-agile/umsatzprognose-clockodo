"""Helfer fuer nebenlaeufige Abrufe.

Die Abrufe einer Prognose haengen **nicht** voneinander ab: Kunden, Personen,
Sollzeiten, Projekte, Verbrauch und Umsatzhistorie sind sechs unabhaengige Antworten,
die erst beim Zusammensetzen aufeinandertreffen.

Deshalb ist der Abruf async - und deshalb steht hier :func:`synchron`, denn die
Notebooks rufen eine gewoehnliche Funktion auf und sollen es weiter tun.

**In Colab und Jupyter laeuft bereits ein Event-Loop.** ``asyncio.run`` bricht dort mit
``RuntimeError: asyncio.run() cannot be called from a running event loop`` ab, und
``loop.run_until_complete`` mit ``This event loop is already running`` - das ist der
Grund fuer den Umweg ueber einen eigenen Thread. Dieser Thread wartet nicht auf den
Notebook-Loop, sondern bringt seinen eigenen mit; ein Deadlock ist damit ausgeschlossen.
Die verbreitete Alternative ``nest_asyncio`` flickt den fremden Loop und waere eine
zusaetzliche Abhaengigkeit, die in Colab nur an dieser einen Stelle gebraucht wuerde.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Coroutine
    from typing import Any

import asyncio
from concurrent.futures import ThreadPoolExecutor

# Notbremse fuer einen Faecher unbekannter Breite - bei der Paginierung ist die
# Seitenzahl erst nach der ersten Antwort bekannt. Die sechs Abrufe einer Prognose
# liegen weit darunter; der Deckel gilt je Faecher und nicht als globale Quote.
MAX_GLEICHZEITIG = 8


def synchron[T](coro: Coroutine[Any, Any, T]) -> T:
    """Eine Coroutine zu Ende fuehren, auch wenn schon ein Event-Loop laeuft.

    Ohne laufenden Loop (Skript, pytest) ist das ein gewoehnliches ``asyncio.run``.
    Laeuft schon einer - in Colab, Jupyter, IPython immer -, uebernimmt ein eigener
    Thread mit eigenem Loop; siehe Modul-Docstring.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="clockodo") as pool:
        return pool.submit(asyncio.run, coro).result()


async def gleichzeitig(*coroutinen: Coroutine[Any, Any, Any]) -> list[Any]:
    """Coroutinen nebenlaeufig ausfuehren, hoechstens :data:`MAX_GLEICHZEITIG` zugleich.

    Die Ergebnisse kommen in der Reihenfolge der Argumente zurueck, unabhaengig davon,
    welche Antwort zuerst da war.

    * Die Sperre entsteht **hier** und nicht am Client. Ein ``asyncio.Semaphore``
      bindet sich an den Loop, in dem es zuerst benutzt wird; als Objektattribut
      gehalten wuerde es beim zweiten Ladevorgang - der laeuft in einem neuen Loop -
      mit einem ``RuntimeError`` brechen. Jeder Faecher bekommt darum seine eigene,
      womit auch verschachtelte Aufrufe nicht aufeinander warten koennen.
    * Faellt ein Abruf aus, werden die uebrigen abgebrochen. ``asyncio.gather`` laesst
      sie sonst weiterlaufen: ein 400 auf die Entrygroups wuerde erst gemeldet, wenn
      auch die fuenf anderen Antworten da sind, deren Ergebnis niemand mehr braucht.
    """
    sperre = asyncio.Semaphore(MAX_GLEICHZEITIG)

    async def begrenzt(coro: Coroutine[Any, Any, Any]) -> Any:
        async with sperre:
            return await coro

    aufgaben = [asyncio.create_task(begrenzt(coro)) for coro in coroutinen]
    try:
        return await asyncio.gather(*aufgaben)
    except BaseException:
        for aufgabe in aufgaben:
            aufgabe.cancel()
        await asyncio.gather(*aufgaben, return_exceptions=True)
        raise
