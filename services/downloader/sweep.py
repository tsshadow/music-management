"""The pacing policy shared by the downloaders.

SoundCloud and YouTube ask a remote service for the same thing in the same shape:
walk a list of accounts, in batches, and hold back when the service pushes back.
Keeping that policy in one place means "how do we behave when we get a 429" has a
single answer rather than one per downloader.
"""
from __future__ import annotations

import logging
import random
import threading
import time
from collections.abc import Iterable

from services.downloader.account_schedule import AccountSchedule
from services.downloader.rate_state import (
    RateLimited,
    RateState,
    SweepAborted,
    backoff_403_wait,
)
from services.downloader.settings_store import load_timing_for
from services.downloader.timing import DownloaderTiming

MINUTE = 60
HOUR = 3600


def format_wait(seconds: int) -> str:
    """A short Dutch duration, for a notification that has to read at a glance."""
    if seconds < MINUTE:
        return f'{seconds} sec'
    if seconds < HOUR:
        return f'{round(seconds / MINUTE)} min'
    hours = round(seconds / HOUR, 1)
    if hours == int(hours):
        return f'{int(hours)} uur'
    return f'{hours} uur'.replace('.', ',')


class SweepPolicy:
    """Owns the timing, the backoff state and the check schedule of one source.

    Callers may hand in any of the three; anything left out is built from the
    database. Tests hand in all three and stay off the database entirely.
    """

    def __init__(self, source: str, timing: DownloaderTiming | None = None,
                 rate_state=None, schedule=None, notifier=None) -> None:
        self.source = source
        self.timing = timing if timing is not None else load_timing_for(source)
        self.rate_state = rate_state if rate_state is not None else RateState(source, self.timing)
        if timing is None:
            # The stored multiplier decides how far the stored waits get stretched.
            self.timing = self.timing.with_multiplier(self.rate_state.multiplier)
        self.schedule = schedule if schedule is not None else AccountSchedule(source)
        self.stop = threading.Event()
        self._blank_run = 0
        self._notifier = notifier

    def begin(self) -> bool:
        """Return whether a sweep may start, or False while the source is parked."""
        remaining = self.rate_state.cooldown_remaining()
        if remaining > 0:
            logging.warning('%s is still cooling down for %ds; skipping this sweep.',
                            self.source, remaining)
            return False
        self.stop.clear()
        self._blank_run = 0
        return True

    def note_progress(self) -> None:
        """Register an account that gave something back, ending any run of blanks."""
        self._blank_run = 0

    def note_blank(self, account: str) -> RateLimited | None:
        """Register an account that came back empty-handed after a 403.

        One of those proves nothing: an account whose only track is subscriber-only
        looks the same from here. Only once `block_threshold` of them arrive in a
        row is the source parked, and the caller is handed the reason to stop.
        """
        self._blank_run += 1
        threshold = self.timing.block_threshold
        if self._blank_run < threshold:
            logging.info('%s returned nothing for %s (%d of %d before backing off).',
                         self.source, account, self._blank_run, threshold)
            return None
        return self.park('403', f'{self._blank_run} accounts in a row ending at {account}')

    def due(self, accounts: Iterable[str]) -> list[str]:
        """The accounts whose own tier cooldown has passed."""
        return self.schedule.due(accounts, self.timing)

    def guard(self, name: str) -> None:
        """Raise if the sweep is already stopping, so queued accounts are skipped."""
        if self.stop.is_set():
            raise SweepAborted(f'Skipped {name}; the {self.source} sweep is already stopping.')

    def park(self, reason: str, target: str) -> RateLimited:
        """Record the rejection, stop the sweep, and report how long we stay away."""
        previous = self._current_403_wait()
        wait = self.rate_state.record_429() if reason == '429' else self.rate_state.record_403()
        self.stop.set()
        logging.warning('HTTP %s for %s. Pausing %s for %ds (multiplier %sx).',
                        reason, target, self.source, wait, self.rate_state.multiplier)
        if reason == '403':
            self._announce_403(target, previous, wait)
        return RateLimited(self.source, wait, reason)

    def _current_403_wait(self) -> int:
        """The wait the running 403 streak has already earned; 0 before the first one."""
        count = self.rate_state.snapshot().consecutive_403
        if count <= 0:
            return 0
        return backoff_403_wait(count, self.timing.backoff_403_base,
                                self.timing.backoff_403_factor, self.timing.backoff_403_cap)

    def _announce_403(self, target: str, previous: int, wait: int) -> None:
        """Push a 403 to ntfy, but only while the wait is still climbing.

        A 403 means the service is refusing us outright rather than asking us to
        slow down, so it is worth a phone buzz. Once the ladder has hit its cap the
        wait stops growing and so do the notifications, otherwise a parked source
        would keep repeating the same message every sweep.
        """
        if wait <= previous:
            return
        if previous:
            change = f'Pauze loopt op van {format_wait(previous)} naar {format_wait(wait)}.'
        else:
            change = f'Pauze is nu {format_wait(wait)}.'
        self._notify(f'403 (Forbidden) van {self.source} bij {target}. {change}',
                     f'{self.source} 403 Forbidden')

    def _notify(self, message: str, title: str) -> None:
        """Send a notification without letting the notifier break the backoff."""
        notifier = self._notifier
        if notifier is None:
            from services.common.Helpers.NotificationService import notification_service
            notifier = notification_service
        try:
            notifier.notify(message, title=title)
        except Exception as exc:  # pragma: no cover - the service already swallows its own
            logging.warning('Could not notify about the %s 403: %s', self.source, exc)

    def rate_limit_from(self, error: Exception, target: str) -> RateLimited | None:
        """Turn a 403 or 429 into a `RateLimited`; return None for anything else."""
        message = str(error)
        if '429' in message:
            return self.park('429', target)
        if '403' in message:
            return self.park('403', target)
        return None

    def throttle(self) -> None:
        """Wait between two batches."""
        pause = random.randint(self.timing.min_pause, self.timing.max_pause)
        if pause <= 0:
            return
        logging.info('Throttling %s: sleeping %d seconds...', self.source, pause)
        time.sleep(pause)

    def mark_checked(self, account: str, last_upload_at=None,
                     last_seen_track_id: str | None = None) -> None:
        self.schedule.mark_checked(account, last_upload_at=last_upload_at,
                                   last_seen_track_id=last_seen_track_id)

    def deep_due(self, account: str) -> bool:
        """Whether this account is due a deep sweep rather than a probe."""
        return self.schedule.deep_due(account, self.timing.deep_sweep_days)

    def mark_deep_swept(self, account: str) -> None:
        self.schedule.mark_deep_swept(account)

    def finish(self) -> None:
        """Register a sweep that completed without being pushed back."""
        self.rate_state.record_success()
