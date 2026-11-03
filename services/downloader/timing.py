"""Timing settings for the downloaders.

Every knob that decides how often and how fast a downloader talks to a remote
service lives here. The schema (default, bounds, unit, description) is code so
that there is a single source of truth for what a valid value is; the stored
values live in the ``downloads_settings`` table, which is reachable from both the
music-manager container and the worker containers.

Only values that differ from the default are stored. Anything unknown or out of
range that somehow ends up in the table is ignored in favour of the default, so a
bad row can never stop a downloader from running.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

SOURCES: tuple[str, ...] = ('soundcloud', 'youtube', 'telegram')

DAY = 86400


@dataclass(frozen=True)
class TimingField:
    """One configurable knob, including everything the UI needs to render it."""

    key: str
    default: int
    minimum: int
    maximum: int
    unit: str
    description: str


def _fields(*specs: TimingField) -> tuple[TimingField, ...]:
    return tuple(specs)


def _scheduling(sweep_interval: int) -> tuple[TimingField, ...]:
    return _fields(
        TimingField(
            'sweep_interval',
            sweep_interval,
            60,
            7 * DAY,
            'seconds',
            'How long the worker waits between two rounds over the accounts.',
        ),
        TimingField(
            'account_cooldown',
            6 * 3600,
            0,
            30 * DAY,
            'seconds',
            'Minimum time between two checks of the same account. 0 turns the cooldown off. '
            'Applies to accounts that uploaded this week, and to accounts whose last upload is not known yet.',
        ),
        TimingField(
            'recent_cooldown',
            DAY,
            3600,
            30 * DAY,
            'seconds',
            'Wait time for an account whose newest upload is 1 week to 1 month old.',
        ),
        TimingField(
            'monthly_cooldown',
            3 * DAY,
            3600,
            30 * DAY,
            'seconds',
            'Wait time for an account whose newest upload is 1 to 3 months old.',
        ),
        TimingField(
            'occasional_cooldown',
            7 * DAY,
            3600,
            90 * DAY,
            'seconds',
            'Wait time for an account whose newest upload is 3 to 12 months old.',
        ),
        TimingField(
            'dormant_cooldown',
            30 * DAY,
            6 * 3600,
            90 * DAY,
            'seconds',
            'Wait time for an account that has not uploaded for more than a year. '
            'It is also the longest time a return can go unnoticed.',
        ),
        TimingField(
            'retry_attempts',
            3,
            1,
            10,
            'attempts',
            'Number of attempts per account before the worker moves on to the next one.',
        ),
    )


def _self_regulation(backoff_429_base: int) -> tuple[TimingField, ...]:
    return _fields(
        TimingField(
            'backoff_429_base',
            backoff_429_base,
            60,
            7 * DAY,
            'seconds',
            'Base wait time after a 429 (Too Many Requests), before the multiplier is applied.',
        ),
        TimingField(
            'max_multiplier', 16, 1, 256, 'x', 'How far the self-regulation may stretch the wait times at most.'
        ),
        TimingField('recovery_runs', 3, 1, 100, 'rounds', 'Number of clean rounds before the multiplier halves.'),
    )


def _batching(ratelimit_kbps: int, backoff_403_base: int) -> tuple[TimingField, ...]:
    return _fields(
        TimingField('max_workers', 1, 1, 16, 'threads', 'Number of accounts fetched at the same time.'),
        TimingField(
            'burst_size', 5, 1, 100, 'accounts', 'Number of accounts per batch; the worker pauses between batches.'
        ),
        TimingField('min_pause', 30, 0, DAY, 'seconds', 'Shortest pause between two batches.'),
        TimingField('max_pause', 120, 0, DAY, 'seconds', 'Longest pause between two batches.'),
        TimingField('sleep_requests', 2, 0, 60, 'seconds', 'Pause yt-dlp keeps between single metadata requests.'),
        TimingField('sleep_interval', 15, 0, 3600, 'seconds', 'Shortest pause yt-dlp keeps before each download.'),
        TimingField('max_sleep_interval', 90, 0, 7200, 'seconds', 'Longest pause yt-dlp keeps before each download.'),
        TimingField('ratelimit_kbps', ratelimit_kbps, 16, 100000, 'KB/s', 'Maximum download speed.'),
        TimingField(
            'backoff_403_base', backoff_403_base, 10, DAY, 'seconds', 'Wait time after the first 403 (Forbidden).'
        ),
        TimingField(
            'backoff_403_factor',
            4,
            2,
            10,
            'x',
            'Factor the 403 wait time is multiplied by at each next error.',
        ),
        TimingField('backoff_403_cap', 3600, 60, 7 * DAY, 'seconds', 'Upper limit for the 403 wait time.'),
        TimingField(
            'backoff_403_decay',
            6 * 3600,
            0,
            7 * DAY,
            'seconds',
            'Quiet time after which the 403 counter drops one step. 0 turns the drop off.',
        ),
        TimingField(
            'block_threshold',
            3,
            1,
            50,
            'accounts',
            'Number of accounts in a row that yield nothing before the source is parked.',
        ),
        TimingField(
            'unavailable_retry_days',
            30,
            0,
            3650,
            'days',
            'After how many days a track that gave a 403 is tried again. 0 always tries again.',
        ),
        TimingField(
            'deep_sweep_days',
            30,
            0,
            365,
            'days',
            'How often an account is walked through completely to find old tracks that were '
            'never fetched. Only happens when the account is due anyway. '
            '0 turns the deep round off.',
        ),
        TimingField(
            'deep_sweep_max_downloads',
            50,
            1,
            1000,
            'tracks',
            'How many missing tracks a deep round fetches per account at a time. The rest follows in the next round.',
        ),
    )


def _bot_check() -> tuple[TimingField, ...]:
    """YouTube's "Sign in to confirm you're not a bot" breaker (bug report 076)."""
    return _fields(
        TimingField(
            'bot_check_threshold',
            5,
            1,
            100,
            'videos',
            'Number of videos in a row with "Sign in to confirm you\'re not a bot" before YouTube is '
            'paused. One warning instead of one error per video.',
        ),
        TimingField(
            'bot_check_pause',
            6 * 3600,
            600,
            7 * DAY,
            'seconds',
            'How long YouTube stays paused after the bot check. Only logging in again in the '
            'Firefox container fixes it; after that the pause can be lifted with "Reset backoff".',
        ),
    )


TIMING_FIELDS: dict[str, tuple[TimingField, ...]] = {
    'soundcloud': _scheduling(900) + _batching(512, 240) + _self_regulation(3600),
    'youtube': _scheduling(900) + _batching(1024, 60) + _self_regulation(3600) + _bot_check(),
    'telegram': _scheduling(3600)
    + _self_regulation(3600)
    + _fields(
        TimingField('max_concurrent', 4, 1, 32, 'downloads', 'Number of simultaneous downloads per channel.'),
        TimingField(
            'flood_sleep_threshold',
            60,
            0,
            DAY,
            'seconds',
            'Up to how long Telethon sits out a flood wait itself before it raises an error.',
        ),
    ),
}

# Knobs that express "wait this long". The self-regulating multiplier stretches
# these; counts and rate limits stay untouched, because slowing down should mean
# waiting longer, not fetching less per request.
SCALED_KEYS = frozenset(
    {
        'sweep_interval',
        'account_cooldown',
        'recent_cooldown',
        'monthly_cooldown',
        'occasional_cooldown',
        'dormant_cooldown',
        'min_pause',
        'max_pause',
        'sleep_interval',
        'max_sleep_interval',
    }
)


def field_map(source: str) -> dict[str, TimingField]:
    """Return the fields of ``source`` keyed by their name."""
    if source not in TIMING_FIELDS:
        raise ValueError(f'Unknown downloader source: {source}')
    return {item.key: item for item in TIMING_FIELDS[source]}


def describe(source: str) -> list[dict[str, Any]]:
    """Return the schema of ``source`` in a shape the UI can render directly."""
    return [
        {
            'key': item.key,
            'default': item.default,
            'minimum': item.minimum,
            'maximum': item.maximum,
            'unit': item.unit,
            'description': item.description,
        }
        for item in TIMING_FIELDS[source]
    ]


def _as_int(key: str, value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError(f'{key} must be a number, got a boolean')
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f'{key} must be a whole number')
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError as exc:
            raise ValueError(f'{key} must be a number, got {value!r}') from exc
    raise ValueError(f'{key} must be a number, got {type(value).__name__}')


def validate_settings(source: str, updates: Mapping[str, Any]) -> dict[str, int]:
    """Coerce and bounds-check ``updates``, raising ``ValueError`` on anything invalid."""
    known = field_map(source)
    validated: dict[str, int] = {}
    for key, raw_value in updates.items():
        item = known.get(key)
        if item is None:
            raise ValueError(f'Unknown setting for {source}: {key}')
        value = _as_int(key, raw_value)
        if value < item.minimum or value > item.maximum:
            raise ValueError(f'{key} must be between {item.minimum} and {item.maximum}, got {value}')
        validated[key] = value
    return validated


def sanitize_settings(source: str, overrides: Mapping[str, Any]) -> dict[str, int]:
    """Keep the overrides that are usable and drop the rest with a warning."""
    known = field_map(source)
    clean: dict[str, int] = {}
    for key, raw_value in overrides.items():
        item = known.get(key)
        if item is None:
            logging.warning('Ignoring unknown %s timing setting %r', source, key)
            continue
        try:
            value = _as_int(key, raw_value)
        except ValueError as exc:
            logging.warning('Ignoring %s timing setting %s: %s', source, key, exc)
            continue
        if value < item.minimum or value > item.maximum:
            logging.warning(
                'Ignoring out-of-range %s timing setting %s=%s; using default %s', source, key, value, item.default
            )
            continue
        clean[key] = value
    return clean


@dataclass(frozen=True)
class DownloaderTiming:
    """The effective timing for one source, with the multiplier already applied."""

    source: str
    values: Mapping[str, int] = field(default_factory=dict)
    multiplier: int = 1

    def raw(self, key: str) -> int:
        """The stored value, or the default, without the multiplier."""
        if key in self.values:
            return self.values[key]
        return field_map(self.source)[key].default

    def get(self, key: str) -> int:
        value = self.raw(key)
        if key in SCALED_KEYS:
            return value * max(1, self.multiplier)
        return value

    @property
    def sweep_interval(self) -> int:
        return self.get('sweep_interval')

    @property
    def account_cooldown(self) -> int:
        return self.get('account_cooldown')

    @property
    def recent_cooldown(self) -> int:
        return self.get('recent_cooldown')

    @property
    def monthly_cooldown(self) -> int:
        return self.get('monthly_cooldown')

    @property
    def occasional_cooldown(self) -> int:
        return self.get('occasional_cooldown')

    @property
    def dormant_cooldown(self) -> int:
        return self.get('dormant_cooldown')

    @property
    def retry_attempts(self) -> int:
        return self.get('retry_attempts')

    @property
    def max_workers(self) -> int:
        return self.get('max_workers')

    @property
    def burst_size(self) -> int:
        return self.get('burst_size')

    @property
    def min_pause(self) -> int:
        return self.get('min_pause')

    @property
    def max_pause(self) -> int:
        return max(self.get('max_pause'), self.min_pause)

    @property
    def backoff_429_base(self) -> int:
        return self.get('backoff_429_base')

    @property
    def backoff_403_base(self) -> int:
        return self.get('backoff_403_base')

    @property
    def backoff_403_factor(self) -> int:
        return self.get('backoff_403_factor')

    @property
    def backoff_403_cap(self) -> int:
        return self.get('backoff_403_cap')

    @property
    def backoff_403_decay(self) -> int:
        return self.get('backoff_403_decay')

    @property
    def block_threshold(self) -> int:
        return self.get('block_threshold')

    @property
    def unavailable_retry_days(self) -> int:
        return self.get('unavailable_retry_days')

    @property
    def deep_sweep_days(self) -> int:
        return self.get('deep_sweep_days')

    @property
    def deep_sweep_max_downloads(self) -> int:
        return self.get('deep_sweep_max_downloads')

    @property
    def bot_check_threshold(self) -> int:
        return self.get('bot_check_threshold')

    @property
    def bot_check_pause(self) -> int:
        return self.get('bot_check_pause')

    @property
    def max_multiplier(self) -> int:
        return self.get('max_multiplier')

    @property
    def recovery_runs(self) -> int:
        return self.get('recovery_runs')

    @property
    def max_concurrent(self) -> int:
        return self.get('max_concurrent')

    @property
    def flood_sleep_threshold(self) -> int:
        return self.get('flood_sleep_threshold')

    def to_ydl_opts(self) -> dict[str, int]:
        """The subset of the settings that yt-dlp itself understands."""
        sleep_interval = self.get('sleep_interval')
        max_sleep_interval = max(self.get('max_sleep_interval'), sleep_interval)
        return {
            'sleep_requests': self.get('sleep_requests'),
            'sleep_interval': sleep_interval,
            'max_sleep_interval': max_sleep_interval,
            'ratelimit': self.get('ratelimit_kbps') * 1024,
        }

    def with_multiplier(self, multiplier: int) -> DownloaderTiming:
        return DownloaderTiming(source=self.source, values=self.values, multiplier=multiplier)


def load_timing(source: str, *, overrides: Mapping[str, Any], multiplier: int = 1) -> DownloaderTiming:
    """Build the effective timing for ``source`` from what came out of storage.

    ``overrides`` is required so this module never has to reach for the database
    itself; `services.downloader.settings_store.load_timing_for` is the version
    that does.
    """
    return DownloaderTiming(source=source, values=sanitize_settings(source, overrides), multiplier=max(1, multiplier))
