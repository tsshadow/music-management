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
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple

SOURCES: Tuple[str, ...] = ('soundcloud', 'youtube', 'telegram')

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


def _fields(*specs: TimingField) -> Tuple[TimingField, ...]:
    return tuple(specs)


def _scheduling(sweep_interval: int) -> Tuple[TimingField, ...]:
    return _fields(
        TimingField('sweep_interval', sweep_interval, 60, 7 * DAY, 'seconden',
                    'Hoe lang de worker wacht tussen twee rondes langs de accounts.'),
        TimingField('account_cooldown', 6 * 3600, 0, 30 * DAY, 'seconden',
                    'Minimale tijd tussen twee controles van hetzelfde account. 0 schakelt de cooldown uit.'),
        TimingField('retry_attempts', 3, 1, 10, 'pogingen',
                    'Aantal pogingen per account voordat de worker doorgaat naar het volgende.'),
    )


def _self_regulation(backoff_429_base: int) -> Tuple[TimingField, ...]:
    return _fields(
        TimingField('backoff_429_base', backoff_429_base, 60, 7 * DAY, 'seconden',
                    'Basiswachttijd na een 429 (Too Many Requests), voordat de multiplier erop wordt losgelaten.'),
        TimingField('max_multiplier', 16, 1, 256, 'x',
                    'Hoever de zelfregeling de wachttijden maximaal mag oprekken.'),
        TimingField('recovery_runs', 3, 1, 100, 'rondes',
                    'Aantal schone rondes voordat de multiplier halveert.'),
    )


def _batching(ratelimit_kbps: int, backoff_403_base: int) -> Tuple[TimingField, ...]:
    return _fields(
        TimingField('max_workers', 1, 1, 16, 'threads',
                    'Aantal accounts dat tegelijk wordt opgehaald.'),
        TimingField('burst_size', 5, 1, 100, 'accounts',
                    'Aantal accounts per batch; tussen batches wordt gepauzeerd.'),
        TimingField('min_pause', 30, 0, DAY, 'seconden',
                    'Kortste pauze tussen twee batches.'),
        TimingField('max_pause', 120, 0, DAY, 'seconden',
                    'Langste pauze tussen twee batches.'),
        TimingField('sleep_requests', 2, 0, 60, 'seconden',
                    'Pauze die yt-dlp aanhoudt tussen losse metadata-verzoeken.'),
        TimingField('sleep_interval', 15, 0, 3600, 'seconden',
                    'Kortste pauze die yt-dlp aanhoudt voor elke download.'),
        TimingField('max_sleep_interval', 90, 0, 7200, 'seconden',
                    'Langste pauze die yt-dlp aanhoudt voor elke download.'),
        TimingField('ratelimit_kbps', ratelimit_kbps, 16, 100000, 'KB/s',
                    'Maximale downloadsnelheid.'),
        TimingField('backoff_403_base', backoff_403_base, 10, DAY, 'seconden',
                    'Wachttijd na de eerste 403 (Forbidden).'),
        TimingField('backoff_403_factor', 4, 2, 10, 'x',
                    'Waarmee de 403-wachttijd bij elke volgende fout wordt vermenigvuldigd.'),
        TimingField('backoff_403_cap', DAY, 60, 7 * DAY, 'seconden',
                    'Bovengrens voor de 403-wachttijd.'),
    )


TIMING_FIELDS: Dict[str, Tuple[TimingField, ...]] = {
    'soundcloud': _scheduling(900) + _batching(512, 240) + _self_regulation(3600),
    'youtube': _scheduling(900) + _batching(1024, 60) + _self_regulation(3600),
    'telegram': _scheduling(3600) + _self_regulation(3600) + _fields(
        TimingField('max_concurrent', 4, 1, 32, 'downloads',
                    'Aantal gelijktijdige downloads per kanaal.'),
        TimingField('flood_sleep_threshold', 60, 0, DAY, 'seconden',
                    'Tot hoe lang Telethon een flood-wait zelf uitzit voordat het een fout opgooit.'),
    ),
}

# Knobs that express "wait this long". The self-regulating multiplier stretches
# these; counts and rate limits stay untouched, because slowing down should mean
# waiting longer, not fetching less per request.
SCALED_KEYS = frozenset({
    'sweep_interval',
    'account_cooldown',
    'min_pause',
    'max_pause',
    'sleep_interval',
    'max_sleep_interval',
})


def field_map(source: str) -> Dict[str, TimingField]:
    """Return the fields of ``source`` keyed by their name."""
    if source not in TIMING_FIELDS:
        raise ValueError(f'Unknown downloader source: {source}')
    return {item.key: item for item in TIMING_FIELDS[source]}


def describe(source: str) -> list[Dict[str, Any]]:
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


def validate_settings(source: str, updates: Mapping[str, Any]) -> Dict[str, int]:
    """Coerce and bounds-check ``updates``, raising ``ValueError`` on anything invalid."""
    known = field_map(source)
    validated: Dict[str, int] = {}
    for key, raw_value in updates.items():
        item = known.get(key)
        if item is None:
            raise ValueError(f'Unknown setting for {source}: {key}')
        value = _as_int(key, raw_value)
        if value < item.minimum or value > item.maximum:
            raise ValueError(f'{key} must be between {item.minimum} and {item.maximum}, got {value}')
        validated[key] = value
    return validated


def sanitize_settings(source: str, overrides: Mapping[str, Any]) -> Dict[str, int]:
    """Keep the overrides that are usable and drop the rest with a warning."""
    known = field_map(source)
    clean: Dict[str, int] = {}
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
            logging.warning('Ignoring out-of-range %s timing setting %s=%s; using default %s',
                            source, key, value, item.default)
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

    def to_ydl_opts(self) -> Dict[str, int]:
        """The subset of the settings that yt-dlp itself understands."""
        sleep_interval = self.get('sleep_interval')
        max_sleep_interval = max(self.get('max_sleep_interval'), sleep_interval)
        return {
            'sleep_requests': self.get('sleep_requests'),
            'sleep_interval': sleep_interval,
            'max_sleep_interval': max_sleep_interval,
            'ratelimit': self.get('ratelimit_kbps') * 1024,
        }

    def with_multiplier(self, multiplier: int) -> 'DownloaderTiming':
        return DownloaderTiming(source=self.source, values=self.values, multiplier=multiplier)


def load_timing(source: str, *, overrides: Mapping[str, Any],
                multiplier: int = 1) -> DownloaderTiming:
    """Build the effective timing for ``source`` from what came out of storage.

    ``overrides`` is required so this module never has to reach for the database
    itself; `services.downloader.settings_store.load_timing_for` is the version
    that does.
    """
    return DownloaderTiming(source=source, values=sanitize_settings(source, overrides),
                            multiplier=max(1, multiplier))
