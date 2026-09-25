"""YouTube's "Sign in to confirm you're not a bot", read as one incident instead of one per video.

When YouTube stops trusting the client -- the Firefox session behind the cookies
was logged out or rotated away, or the address got flagged -- every single video
answers with the same refusal. yt-dlp runs with ``ignoreerrors`` and reports each
one as an ERROR, so a single lost session became ~20,000 ERROR events a day, plus
a WARNING "No title found in player responses" before each of them (bug report
076). None of those videos can succeed until a person logs in again, so trying
the next one only adds another line.

``BotCheckBreaker`` counts refusals in a row across the whole sweep. A video that
does come back (the match filter saw its full metadata) resets the count. Once
``threshold`` refusals arrive in a row the breaker trips, and ``BotCheckTripped``
is raised from inside yt-dlp's logger. It is a ``DownloadCancelled`` for the same
reason ``ShuttingDown`` is: that is the one exception ``ignoreerrors`` re-raises,
so the ``download()`` call ends at once instead of walking on to the next video.
The sweep then parks the source once (``SweepPolicy.park_block``) with a single
WARNING that says what a person has to do.
"""

from __future__ import annotations

import re
import threading

try:
    from yt_dlp.utils import DownloadCancelled as _Cancelled
except ImportError:  # pragma: no cover - only under the test stub that replaces yt_dlp
    _Cancelled = Exception

# The reason stored in downloads_rate_state.block_reason and shown in Beheer.
BOT_CHECK = 'bot_check'
# yt-dlp could not load the cookie database at all (missing or unreadable profile).
COOKIES_MISSING = 'cookies_missing'

# YouTube writes the apostrophe as U+2019; yt-dlp passes it on unchanged. Either
# form, and any casing, is the same refusal.
_BOT_CHECK = re.compile(r"sign in to confirm you.{1,3}re not a bot", re.IGNORECASE)
# The warning yt-dlp logs just before the refusal: the player response it got back
# was the sign-in wall, not a video. Noise once the refusal itself is counted.
_NO_TITLE = re.compile(r'no title found in player responses', re.IGNORECASE)


def is_bot_check(message: str) -> bool:
    """Whether a yt-dlp log line is YouTube's sign-in wall."""
    return bool(_BOT_CHECK.search(message or ''))


def is_bot_check_side_effect(message: str) -> bool:
    """Whether a yt-dlp log line is the warning that accompanies the sign-in wall."""
    return bool(_NO_TITLE.search(message or ''))


class BotCheckTripped(_Cancelled):  # type: ignore[misc, valid-type]
    """Raised inside yt-dlp once the breaker trips; ends the whole ``download()`` call."""


class BotCheckBreaker:
    """Counts sign-in refusals in a row across one sweep; thread-safe.

    Shared by every worker thread of the sweep, so "in a row" means across
    channels too: the refusal is about the client, not about any one channel.
    """

    def __init__(self, threshold: int) -> None:
        self.threshold = max(1, int(threshold))
        self._lock = threading.Lock()
        self._count = 0
        self._tripped = False
        self.last_message: str | None = None

    @property
    def count(self) -> int:
        """Refusals in a row so far."""
        return self._count

    @property
    def tripped(self) -> bool:
        """Whether ``threshold`` refusals arrived in a row during this sweep."""
        return self._tripped

    def record_refusal(self, message: str) -> bool:
        """Register one refusal; return True when the breaker is (now) tripped."""
        with self._lock:
            self._count += 1
            self.last_message = message
            if self._count >= self.threshold:
                self._tripped = True
            return self._tripped

    def record_success(self) -> None:
        """Register a video whose metadata came back; the run of refusals is over."""
        with self._lock:
            if not self._tripped:
                self._count = 0

    def reset(self) -> None:
        """Start a new sweep with a clean count."""
        with self._lock:
            self._count = 0
            self._tripped = False
            self.last_message = None
