"""The process-wide stop flag every long-running worker shares.

A deploy replaces the worker containers, which means SIGTERM and then, ten
seconds later, SIGKILL. Python's default handling of SIGTERM ends the process
outright: no ``finally`` runs. The workers therefore arm a handler that only
raises this flag, and check it at their own checkpoints.

It lives in ``services.common`` rather than next to the downloader because the
importer needs the same flag and its image does not carry the downloader code.
The downloader-specific half -- the yt-dlp progress hook -- stays in
``services.downloader.shutdown``.
"""

from __future__ import annotations

import logging
import signal
import threading

_requested = threading.Event()
_announced = threading.Event()


def request(signum=None, _frame=None) -> None:
    """Ask every worker in this process to stop at its next checkpoint.

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


def wait(seconds: float) -> bool:
    """Sleep for up to ``seconds``, waking the moment a stop is asked for.

    Returns whether a stop was asked for. A plain ``time.sleep`` between two
    rounds would sit out the whole interval while Docker's grace period ran out,
    and SIGKILL would end the process instead of the loop.
    """
    return _requested.wait(max(0.0, float(seconds)))


def install_handlers() -> None:
    """Arm SIGTERM and SIGINT. Safe to call more than once."""
    signal.signal(signal.SIGTERM, request)
    signal.signal(signal.SIGINT, request)


def reset() -> None:
    """Forget any stop that was asked for; used by tests."""
    _requested.clear()
    _announced.clear()
