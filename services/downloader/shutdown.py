"""Stopping a downloader without losing what the current pass learned.

A deploy replaces the worker containers, which means SIGTERM and then, ten
seconds later, SIGKILL. Python's default handling of SIGTERM ends the process
outright: no ``finally`` runs, so a deep pass loses the write-offs and the
attempt counts it was about to record, and a download caught mid-postprocess can
leave an untagged file that ``nooverwrites`` then protects from ever being
fetched properly again.

Ten seconds is not enough to finish a download -- one video here takes minutes --
so the flag alone would never be seen: the worker spends nearly all of its time
inside a single yt-dlp call. ``abort_hook`` is what makes the flag reachable. It
is handed to yt-dlp as a progress hook, fires on every block, and raises as soon
as a stop has been asked for, which drops the sweep back to its own loop within a
second.

Nothing here decides *what* to clean up. It only says "stop soon", and the
existing checkpoints -- ``SweepPolicy.guard`` between tracks and the ``finally``
in the deep pass -- do the rest.
"""

from __future__ import annotations

import logging
import signal
import threading

_requested = threading.Event()
_announced = threading.Event()


class ShuttingDown(Exception):
    """Raised inside yt-dlp to abandon a download the moment a stop is asked for."""


def request(signum=None, _frame=None) -> None:
    """Ask every downloader to stop at its next checkpoint.

    Installed directly as the signal handler, so it has to accept the
    ``(signum, frame)`` pair as well as being called with nothing at all.
    """
    _requested.set()
    if not _announced.is_set():
        _announced.set()
        name = signal.Signals(signum).name if signum is not None else 'a stop request'
        logging.info('Received %s; finishing the current step and shutting down.', name)


def is_requested() -> bool:
    """Whether a stop has been asked for."""
    return _requested.is_set()


def abort_hook(_progress: dict) -> None:
    """A yt-dlp progress hook that abandons the download once a stop is asked for."""
    if _requested.is_set():
        raise ShuttingDown('shutting down')


def install_handlers() -> None:
    """Arm SIGTERM and SIGINT. Safe to call more than once."""
    signal.signal(signal.SIGTERM, request)
    signal.signal(signal.SIGINT, request)


def reset() -> None:
    """Forget any stop that was asked for; used by tests."""
    _requested.clear()
    _announced.clear()
