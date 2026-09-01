"""Register van de threads die horen te blijven draaien.

Alleen oneindige lussen horen hier thuis. Eenmalige achtergrondtaken zoals
run_lms_db_sync en run_fetch_missing geven na afloop netjes terug; die zouden
de liveness-controle permanent rood zetten.
"""

from __future__ import annotations

import threading

_threads: dict[str, threading.Thread] = {}
_lock = threading.Lock()


def start_thread(name: str, target, args: tuple = ()) -> threading.Thread:
    thread = threading.Thread(target=target, args=args, name=name, daemon=True)
    with _lock:
        _threads[name] = thread
    thread.start()
    return thread


def thread_status() -> dict[str, bool]:
    with _lock:
        return {name: thread.is_alive() for name, thread in _threads.items()}


def reset() -> None:
    """Alleen voor tests: leeg het register."""
    with _lock:
        _threads.clear()
