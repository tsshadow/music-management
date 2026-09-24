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

What it raises matters. The downloaders run yt-dlp with ``ignoreerrors``, and
under that option yt-dlp swallows every exception an entry raises -- except
``DownloadCancelled`` and a few of its own. A plain ``Exception`` abandoned one
video and yt-dlp went straight on to the next, until SIGKILL. ``ShuttingDown``
is therefore a ``DownloadCancelled``, which ``YoutubeDL.download`` re-raises.

The flag itself lives in ``services.common.shutdown`` so the importer can share
it; the names are re-exported here so the downloader keeps one import.

Nothing here decides *what* to clean up. It only says "stop soon", and the
existing checkpoints -- ``SweepPolicy.guard`` between tracks and the ``finally``
in the deep pass -- do the rest.
"""

from __future__ import annotations

from services.common.shutdown import (  # noqa: F401 - re-exported for the downloader
    _announced,
    _requested,
    install_handlers,
    is_requested,
    request,
    reset,
    wait,
)

try:
    from yt_dlp.utils import DownloadCancelled as _Cancelled
except ImportError:  # pragma: no cover - only under the test stub that replaces yt_dlp
    _Cancelled = Exception


class ShuttingDown(_Cancelled):  # type: ignore[misc, valid-type]
    """Raised inside yt-dlp to abandon the whole download call the moment a stop is asked for."""


def abort_hook(_progress: dict) -> None:
    """A yt-dlp progress hook that abandons the download once a stop is asked for."""
    if _requested.is_set():
        raise ShuttingDown('shutting down')
