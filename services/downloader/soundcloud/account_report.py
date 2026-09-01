"""What one account's download run actually told us.

yt-dlp runs with ``ignoreerrors``, so nothing it meets on the way surfaces as an
exception -- a track it cannot fetch is a line in the log and nothing more. That
left the downloader reading every 403 as "SoundCloud is pushing back", parking
all 1110 accounts over a single Go+ or geo-blocked track.

The two are distinguishable. A 403 among tracks we *did* manage to read is a
track that is not for us. A 403 with nothing read at all is an account that gave
us nothing, and only a run of those is evidence of an actual block. A 429 is the
one unambiguous "slow down".
"""

from __future__ import annotations

import logging
import re

# A run that needs no reaction: everything readable was read.
CLEAN = 'clean'
# Individual tracks answered 403; the account itself was fine.
UNAVAILABLE_TRACKS = 'unavailable_tracks'
# Nothing could be read and at least one 403 came back.
BLANK = 'blank'
# The source asked us to slow down.
THROTTLED = 'throttled'

# Anchored on how an HTTP status is actually written, so a track called
# "dj-403-live-set" or a "403 bytes" progress line no longer parks the source.
_STATUS = re.compile(
    r'(?:HTTP\s+Error\s+|status(?:\s+code)?[:\s]+|\b)'
    r'(403|429)\b\s*[:\s]\s*(?:Forbidden|Too\s+Many\s+Requests)',
    re.IGNORECASE,
)


def detect_http_status(message: str) -> int | None:
    """The HTTP status a log line is reporting, or None if it reports none."""
    match = _STATUS.search(message or '')
    return int(match.group(1)) if match else None


def classify_account(extracted: int, forbidden: int, throttled: bool) -> str:
    """Read one account's counters as a single outcome."""
    if throttled:
        return THROTTLED
    if forbidden <= 0:
        return CLEAN
    return UNAVAILABLE_TRACKS if extracted > 0 else BLANK


class AccountReport:
    """Collects what yt-dlp said while working through one account.

    Doubles as the yt-dlp logger, which is the only place these signals appear.
    """

    def __init__(self) -> None:
        self.extracted = 0
        self.throttled = False
        self.forbidden = 0
        self.newest_timestamp: int | None = None
        self._current_track: str | None = None
        self._forbidden: list[str] = []

    def note_extracted(self, track_id: str | None, timestamp: int | None = None) -> None:
        """Register that metadata for a track came back; called from the match filter.

        The timestamp comes along for free -- the full extraction already carries
        it -- and the newest one is what places the account in a check tier.
        """
        self.extracted += 1
        self._current_track = track_id
        if timestamp is not None and (self.newest_timestamp is None or timestamp > self.newest_timestamp):
            self.newest_timestamp = timestamp

    @property
    def forbidden_tracks(self) -> list[str]:
        """The tracks that answered 403, in the order they did."""
        return list(self._forbidden)

    @property
    def outcome(self) -> str:
        return classify_account(self.extracted, self.forbidden, self.throttled)

    def debug(self, msg):
        if not str(msg).startswith('[debug] '):
            self._log('debug', msg)

    def info(self, msg):
        self._log('info', msg)

    def warning(self, msg):
        self._log('warning', msg)

    def error(self, msg):
        self._log('error', msg)

    def _log(self, level: str, msg) -> None:
        getattr(logging, level)(msg)
        status = detect_http_status(str(msg))
        if status == 429:
            self.throttled = True
        elif status == 403:
            self.forbidden += 1
            track = self._current_track
            if track is not None and track not in self._forbidden:
                self._forbidden.append(track)
