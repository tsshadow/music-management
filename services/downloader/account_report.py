"""What one account's download run actually told us.

yt-dlp runs with ``ignoreerrors``, so nothing it meets on the way surfaces as an
exception -- a track it cannot fetch is a line in the log and nothing more. That
left the downloader reading every 403 as "SoundCloud is pushing back", parking
all 1110 accounts over a single Go+ or geo-blocked track.

The two are distinguishable. A 403 among tracks we *did* manage to read is a
track that is not for us. A 403 with nothing read at all is an account that gave
us nothing, and only a run of those is evidence of an actual block. A 429 is the
one unambiguous "slow down".

Shared by both yt-dlp downloaders. YouTube reads the counters more bluntly than
SoundCloud does (see ``YoutubeDownloader._blocked``), but it needs the same
logger for the same reason: without it the 403 never leaves yt-dlp's stderr, and
the source is never parked at all.
"""

from __future__ import annotations

import logging
import re

from services.downloader.bot_check import (
    BotCheckBreaker,
    BotCheckTripped,
    is_bot_check,
    is_bot_check_side_effect,
)

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

    def __init__(self, breaker: BotCheckBreaker | None = None) -> None:
        # YouTube only: counts sign-in refusals across the sweep and ends the
        # download call once enough arrived in a row. See services/downloader/bot_check.py.
        self.breaker = breaker
        self.bot_checks = 0
        self.extracted = 0
        self.throttled = False
        self.forbidden = 0
        # The 403s yt-dlp gave up on. A 403 it logs as a warning is usually one
        # request it retried, or one of several player clients it tried in turn,
        # and the item still came back -- not evidence that anything was refused.
        self.forbidden_errors = 0
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
        """The run's counters read as one of CLEAN, UNAVAILABLE_TRACKS, BLANK or THROTTLED."""
        return classify_account(self.extracted, self.forbidden, self.throttled)

    def debug(self, msg):
        """yt-dlp's debug channel; its own ``[debug]`` chatter is dropped."""
        if not str(msg).startswith('[debug] '):
            self._log('debug', msg)

    def info(self, msg):
        """yt-dlp's info channel, passed on to `logging`."""
        self._log('info', msg)

    def warning(self, msg):
        """yt-dlp's warning channel, passed on to `logging`."""
        self._log('warning', msg)

    def error(self, msg):
        """yt-dlp's error channel, passed on to `logging` -- and so to the event log."""
        self._log('error', msg)

    def _log(self, level: str, msg) -> None:
        """Log one yt-dlp line and count the HTTP status it reports, if any.

        With a breaker attached, YouTube's sign-in wall is counted instead of logged
        as an ERROR per video: the breaker's single WARNING stands for all of them.
        Raises `BotCheckTripped` once the breaker trips, which ends the download call.
        """
        if self.breaker is not None and level in ('warning', 'error'):
            text = str(msg)
            if is_bot_check(text):
                self.bot_checks += 1
                logging.debug(msg)
                if self.breaker.record_refusal(text):
                    raise BotCheckTripped(text)
                return
            if is_bot_check_side_effect(text):
                logging.debug(msg)
                return
        getattr(logging, level)(msg)
        status = detect_http_status(str(msg))
        if status == 429:
            self.throttled = True
        elif status == 403:
            self.forbidden += 1
            if level == 'error':
                self.forbidden_errors += 1
            track = self._current_track
            if track is not None and track not in self._forbidden:
                self._forbidden.append(track)
