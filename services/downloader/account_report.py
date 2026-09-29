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


# yt-dlp lines that describe an expected outcome, not a fault (bug report 130).
# Each is logged at the level given here instead of the WARNING/ERROR yt-dlp
# chose, because every WARNING and up is pushed to the phone's alerts topic.
# Deliberately a short list of exact phrasings: an unknown yt-dlp warning still
# arrives as a warning.
BENIGN_MESSAGES: tuple[tuple[re.Pattern[str], str], ...] = (
    # EmbedThumbnail on a merged webm: yt-dlp switches the container to mkv.
    # Says what it did, not that anything failed.
    (re.compile(r"webm doesn't support embedding a thumbnail, mkv will be used"), 'info'),
    # SoundCloud answers 404 for a stream it does not offer for this track, and
    # yt-dlp moves on to the next one. A track with no stream at all still ends in
    # an ERROR of its own.
    (re.compile(r'\b(?:http|hls)_(?:mp3|aac|opus) format not found\b'), 'info'),
    # A verdict about one track, not a fault. The SoundCloud downloader writes it
    # off (reason `drm`) so it is not asked for again until the retry window
    # passes; YouTube's deep pass writes it off like any other failed video.
    (re.compile(r'This video is DRM protected'), 'info'),
)

# How yt-dlp names the item a DRM refusal is about: "[soundcloud] 2394393894: This video ...".
_DRM_ITEM = re.compile(r'\[[\w:]+\]\s+([^\s:]+):\s+This video is DRM protected')


def clean_message(msg) -> str:
    """A yt-dlp line with its carriage returns taken out.

    yt-dlp writes a ``\\r`` to return the terminal cursor over a progress line, and
    passes it on to a logger too: ``report_error(f'\\r[download] Got error: ...')``.
    The event log splits the title on line breaks, ``\\r`` among them, so every such
    ERROR arrived titled ``root: ERROR: `` with the actual failure out of sight.
    """
    return str(msg).replace('\r\n', '\n').replace('\r', '')


def logged_level(level: str, message: str) -> str:
    """The level a yt-dlp line is logged at: its own, unless it is a known-benign one."""
    if level not in ('warning', 'error'):
        return level
    for pattern, demoted in BENIGN_MESSAGES:
        if pattern.search(message):
            return demoted
    return level


def drm_item(message: str) -> str | None:
    """The id of the item a DRM refusal is about, or None if the line is not one."""
    match = _DRM_ITEM.search(message)
    return match.group(1) if match else None


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
        self._drm: list[str] = []

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
    def drm_tracks(self) -> list[str]:
        """The tracks yt-dlp refused because they are DRM protected, in the order it did."""
        return list(self._drm)

    def note_listed(self, track_id: str | None) -> None:
        """Register the playlist entry yt-dlp is about to extract; called from the match filter.

        The full extraction of that entry is what fails with a 403, before the
        filter sees it complete, so this is the track a following 403 belongs to.
        """
        if track_id is not None:
            self._current_track = track_id

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

        The lines in `BENIGN_MESSAGES` are logged at the level listed there, and a
        DRM refusal is remembered in `drm_tracks` for the downloader to write off.
        """
        text = clean_message(msg)
        if self.breaker is not None and level in ('warning', 'error'):
            if is_bot_check(text):
                self.bot_checks += 1
                logging.debug(text)
                if self.breaker.record_refusal(text):
                    raise BotCheckTripped(text)
                return
            if is_bot_check_side_effect(text):
                logging.debug(text)
                return
        getattr(logging, logged_level(level, text))(text)
        drm = drm_item(text) if level in ('warning', 'error') else None
        if drm is not None and drm not in self._drm:
            self._drm.append(drm)
        status = detect_http_status(text)
        if status == 429:
            self.throttled = True
        elif status == 403:
            self.forbidden += 1
            if level == 'error':
                self.forbidden_errors += 1
            track = self._current_track
            if track is not None and track not in self._forbidden:
                self._forbidden.append(track)
