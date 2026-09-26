"""Centralized configuration store with persistence and change notifications."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import threading
from collections import defaultdict
from collections.abc import Callable, Iterable, MutableMapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

#: Stands in for a stored secret wherever a value leaves the process.
#:
#: Bullets rather than a word, because this travels to a browser and lands in a
#: password field, where it reads as "something is set" without saying what. A real
#: secret equal to this string would be indistinguishable from "leave it alone" -- an
#: accepted risk: it is not a value any credential generator produces.
SECRET_SENTINEL = '\u2022' * 8


@dataclass(frozen=True)
class ConfigField:
    """Describe a single configuration entry."""

    key: str
    type: str
    default: Any = None
    env: str | None = None
    group: str = 'General'
    description: str = ''
    nullable: bool = True
    #: Never leaves the process in the clear. Readable in-process, masked at the API
    #: boundary. Set it for credentials, not for identifiers: a Spotify client id is
    #: public, its client secret is not.
    secret: bool = False
    #: Shown on the config page for information only. Its value comes from the
    #: environment and cannot be changed or persisted through the API, because the
    #: code that uses it reads the environment directly (the database connection is
    #: opened long before any page could change it).
    read_only: bool = False


#: Default age, in days, after which the events-retention loop deletes an event of
#: each level. Tuned to production volume in bug report 072: INFO, WARNING and the
#: per-video yt-dlp ERRORs are the bulk, CRITICAL is rare and worth a year.
EVENTS_RETENTION_DEFAULT_DAYS = {'DEBUG': 3, 'INFO': 14, 'WARNING': 30, 'ERROR': 90, 'CRITICAL': 365}


def _events_retention_fields() -> list[ConfigField]:
    """The per-level retention windows and the size cap of the `events` table."""
    fields = [
        ConfigField(
            key=f'events_retention_{level.lower()}_days',
            type='integer',
            default=days,
            env=f'EVENTS_RETENTION_{level}_DAYS',
            group='Events',
            description=f'How many days a {level} event stays in the event log before the daily retention '
            'pass deletes it. 0 or empty falls back to the default.',
        )
        for level, days in EVENTS_RETENTION_DEFAULT_DAYS.items()
    ]
    fields.append(
        ConfigField(
            key='events_max_rows',
            type='integer',
            default=10_000_000,
            env='EVENTS_MAX_ROWS',
            group='Events',
            description='Safety net for the event log: when it still holds more rows than this after the '
            'per-level pass, the oldest DEBUG/INFO rows go first, then WARNING, then ERROR. CRITICAL is never '
            'removed by size. 0 or empty switches the cap off.',
        )
    )
    return fields


def _config_fields() -> list[ConfigField]:
    """Return the ordered list of supported configuration fields."""
    return [
        ConfigField(
            key='debug',
            type='boolean',
            default=False,
            env='debug',
            description='Enable verbose debug logging for import jobs.',
        ),
        ConfigField(
            key='rescan',
            type='boolean',
            default=False,
            env='rescan',
            description='Force a rescan of already processed files.',
        ),
        ConfigField(
            key='dryrun',
            type='boolean',
            default=False,
            env='dryrun',
            description='Run processors without modifying files on disk.',
        ),
        ConfigField(
            key='import_folder_path',
            type='string',
            default='',
            env='import_folder_path',
            group='Paths',
            description='The import queue: where archives are extracted and releases wait until they are '
            'filed under a label. Unset means its historical place inside eps_folder_path. Every walker of the label tree asks '
            'services/common/import_queue.py, so moving it is this setting plus a folder move.',
        ),
        ConfigField(
            key='eps_folder_path',
            type='string',
            default='',
            env='eps_folder_path',
            group='Paths',
            description='Location for extracted EPs.',
        ),
        ConfigField(
            key='music_folder_path',
            type='string',
            default='',
            env='music_folder_path',
            group='Paths',
            description='Destination library for processed tracks.',
        ),
        ConfigField(
            key='quarantine_folder_path',
            type='string',
            default='',
            env='quarantine_folder_path',
            group='Paths',
            description=(
                'Where files the pipeline would otherwise delete are parked, under a folder per '
                'day. Empty falls back to a .quarantine folder beside the music root.'
            ),
        ),
        ConfigField(
            key='quarantine_retention_days',
            type='integer',
            default=30,
            env='quarantine_retention_days',
            group='Paths',
            description='How long a quarantined file is kept before the importer sweeps it.',
        ),
        ConfigField(
            key='import_settle_minutes',
            type='integer',
            default=5,
            env='import_settle_minutes',
            group='Paths',
            description=(
                'How long a release folder in the import folder must sit unchanged before the importer '
                'renames, flattens or moves it, so a copy still in progress is never picked up half-done. '
                '0 switches the wait off.'
            ),
        ),
        ConfigField(
            key='delimiter',
            type='string',
            default=os.sep,
            env='delimiter',
            group='General',
            description='Path delimiter used when parsing artist/title strings.',
        ),
        ConfigField(
            key='tagger_deep_run_days',
            type='integer',
            default=30,
            env='TAGGER_DEEP_RUN_DAYS',
            group='Tagger',
            description='How old a file\'s last tagging round may get before the tagger reads it again with the current rules. 0 switches the deep run off.',
        ),
        ConfigField(
            key='max_retag_files',
            type='integer',
            default=2000,
            env='MAX_RETAG_FILES',
            group='Tagger',
            description='Ceiling on how many files one "apply now" on an artist or label rule may retag. The job holds the tagger lock for the whole batch, so a high number means the ordinary tagging round waits. Past the ceiling the page asks for a full tagger run instead.',
        ),
        ConfigField(
            key='analyze_bpm',
            type='boolean',
            default=False,
            env='analyze_bpm',
            group='Tagger',
            description='Estimate BPM with librosa while tagging. Only runs for files without a BPM tag, but the first pass still decodes every file. Do not switch this on at the same time as a full rescan.',
        ),
        ConfigField(
            key='tagger_walk_interval_hours',
            type='integer',
            default=24,
            env='TAGGER_WALK_INTERVAL_HOURS',
            group='Tagger',
            description='How often the tagger walks every folder looking for files nobody announced. The five-minute round serves the queue (decisions, downloads, imports, files the scanner found) without a walk; 0 walks every round, as before 0.67.',
        ),
        ConfigField(
            key='tagger_deep_run_batch',
            type='integer',
            default=200,
            env='TAGGER_DEEP_RUN_BATCH',
            group='Tagger',
            description='How many files one tagging round may hand back to the deep run. Bounds the extra work per round, not the length of a cycle.',
        ),
        ConfigField(
            key='lms_hosts',
            type='string',
            default='',
            env='LMS_HOSTS',
            group='LMS',
            description='Comma-separated host:port list of LMS servers to trigger a scan on after a tagging or scanning run.',
        ),
        ConfigField(
            key='lms_subsonic_api_key',
            type='string',
            default='',
            secret=True,
            env='LMS_SUBSONIC_API_KEY',
            group='LMS',
            description='Subsonic API key for LMS: the scan trigger and the radio scheduler both use it. Empty falls back to MUMA_SERVER_SUBSONIC_API_KEY / LMS_SUBSONIC_API_KEY.',
        ),
        ConfigField(
            key='youtube_folder',
            type='string',
            default='',
            env='youtube_folder',
            group='YouTube',
            description='Target folder for YouTube downloads.',
        ),
        ConfigField(
            key='youtube_video_folder',
            type='string',
            default='',
            env='youtube_video_folder',
            group='YouTube',
            description='Target folder for channels marked as video. Nothing indexes the files: the tagger and importer only accept audio extensions, and LMS only indexes audio formats.',
        ),
        ConfigField(
            key='youtube_archive',
            type='string',
            default='',
            env='youtube_archive',
            group='YouTube',
            description='Archive directory or file that library_tracks downloaded YouTube videos.',
        ),
        ConfigField(
            key='ffmpeg_location',
            type='string',
            default='/usr/bin',
            env='ffmpeg-location',
            group='YouTube',
            description='Location of the ffmpeg binary used by yt-dlp.',
        ),
        ConfigField(
            key='yt_cookies',
            type='string',
            default='',
            env='YT_COOKIES',
            group='YouTube',
            description='Path to a cookies.txt file for YouTube downloads.',
        ),
        ConfigField(
            key='yt_user_agent',
            type='string',
            default='',
            env='YT_USER_AGENT',
            group='YouTube',
            description='Optional custom user agent for YouTube requests.',
        ),
        ConfigField(
            key='soundcloud_folder',
            type='string',
            default='',
            env='soundcloud_folder',
            group='SoundCloud',
            description='Target folder for SoundCloud downloads.',
        ),
        ConfigField(
            key='soundcloud_archive',
            type='string',
            default='',
            env='soundcloud_archive',
            group='SoundCloud',
            description='Archive directory or file for SoundCloud downloads.',
        ),
        ConfigField(
            key='soundcloud_cookies',
            type='string',
            default='soundcloud.com_cookies.txt',
            env='soundcloud_cookies',
            group='SoundCloud',
            description='Cookies file used to access private or follower-only tracks.',
        ),
        ConfigField(
            key='telegram_folder',
            type='string',
            default='',
            env='telegram_folder',
            group='Telegram',
            description='Base folder for Telegram downloads.',
        ),
        ConfigField(
            key='telegram_api_id',
            type='string',
            default='',
            env='telegram_api_id',
            group='Telegram',
            description='Telegram API ID used for the downloader client.',
        ),
        ConfigField(
            key='telegram_api_hash',
            type='string',
            default='',
            secret=True,
            env='telegram_api_hash',
            group='Telegram',
            description='Telegram API hash used for the downloader client.',
        ),
        ConfigField(
            key='telegram_session',
            type='string',
            default='telegram',
            env='telegram_session',
            group='Telegram',
            description='Session name for the Telegram client.',
        ),
        ConfigField(
            key='telegram_max_concurrent',
            type='integer',
            default=4,
            env='telegram_max_concurrent',
            group='Telegram',
            description='Maximum number of concurrent Telegram downloads.',
        ),
        ConfigField(
            key='telegram_accounts',
            type='string',
            default='',
            env='telegram_accounts',
            group='Telegram',
            description='Comma-separated list of Telegram channels to download from.',
        ),
        ConfigField(
            key='db_host',
            type='string',
            default='',
            env='DB_HOST',
            group='Database',
            read_only=True,
            description='Database host for metadata storage. Read-only: set DB_HOST in the environment.',
        ),
        ConfigField(
            key='db_port',
            type='integer',
            default=None,
            env='DB_PORT',
            group='Database',
            read_only=True,
            description='Database port for metadata storage. Read-only: set DB_PORT in the environment.',
        ),
        ConfigField(
            key='db_user',
            type='string',
            default='',
            env='DB_USER',
            group='Database',
            read_only=True,
            description='Database user for metadata storage. Read-only: set DB_USER in the environment.',
        ),
        ConfigField(
            key='db_pass',
            type='string',
            default='',
            secret=True,
            env='DB_PASS',
            group='Database',
            read_only=True,
            description='Database password for metadata storage. Read-only: set DB_PASS in the environment.',
        ),
        ConfigField(
            key='db_name',
            type='string',
            default='',
            env='DB_DB',
            group='Database',
            read_only=True,
            description='Database name for metadata storage. Read-only: set DB_DB in the environment.',
        ),
        ConfigField(
            key='db_connect_timeout',
            type='integer',
            default=5,
            env='DB_CONNECT_TIMEOUT',
            group='Database',
            read_only=True,
            description='Connection timeout (seconds) when connecting to the database. Read-only: set DB_CONNECT_TIMEOUT in the environment.',
        ),
        ConfigField(
            key='discogs_token',
            type='string',
            default='',
            secret=True,
            env='DISCOGS_TOKEN',
            group='3rd Party APIs',
            description='Discogs personal access token for artist lookup.',
        ),
        ConfigField(
            key='lastfm_api_key',
            type='string',
            default='',
            secret=True,
            env='LASTFM_API_KEY',
            group='3rd Party APIs',
            description='Last.fm API key for artist lookup.',
        ),
        ConfigField(
            key='spotify_client_id',
            type='string',
            default='',
            env='SPOTIFY_CLIENT_ID',
            group='3rd Party APIs',
            description='Spotify client ID for artist lookup.',
        ),
        ConfigField(
            key='spotify_client_secret',
            type='string',
            default='',
            secret=True,
            env='SPOTIFY_CLIENT_SECRET',
            group='3rd Party APIs',
            description='Spotify client secret for artist lookup.',
        ),
        ConfigField(
            key='notify_url',
            type='string',
            default='',
            env='NOTIFY_URL',
            group='Notifications',
            description='URL for ntfy.sh integration.',
        ),
        ConfigField(
            key='notify_topic',
            type='string',
            default='music-management',
            env='notify_topic',
            group='Notifications',
            description='Topic name for ntfy.sh notifications.',
        ),
        ConfigField(
            key='notify_topic_alerts',
            type='string',
            default='music-management-alerts',
            env='notify_topic_alerts',
            group='Notifications',
            description='Topic for warnings and errors. Subscribe separately so alerts can have their own sound.',
        ),
        ConfigField(
            key='crash_hook_url',
            type='string',
            default='',
            env='CRASH_HOOK_URL',
            group='Notifications',
            description='URL that receives a POST with the report id after a mobile crash report is stored. Empty switches the hook off.',
        ),
        *_events_retention_fields(),
        ConfigField(
            key='feeds_starting_genres',
            type='string',
            default='',
            env='FEEDS_STARTING_GENRES',
            group='Feeds',
            description='Comma-separated genres a feed falls back to when nobody on the server has any '
            'listening history yet. Empty means no configured fallback -- the feed reports not_enough_data.',
        ),
        ConfigField(
            key='feeds_hardness_edges',
            type='string',
            default='',
            env='FEEDS_HARDNESS_EDGES',
            group='Feeds',
            description='Two comma-separated hardness values, "<soft/mid>,<mid/hard>", e.g. "50,75", fixing '
            'where the three spectrum daily mixes split. Empty or unparsable falls back to 50,75.',
        ),
        ConfigField(
            key='feeds_size',
            type='integer',
            default=100,
            env='FEEDS_SIZE',
            group='Feeds',
            description='How many tracks every feed (Release Radar and the daily mixes) holds before "Meer '
            'laden". 10-200; anything else falls back to 100. A change rebuilds today\'s feeds on their next read.',
        ),
        ConfigField(
            key='lms_listen_backfill_enabled',
            type='boolean',
            default=True,
            env='LMS_LISTEN_BACKFILL_ENABLED',
            group='Scrobbling',
            description='Every few minutes, insert the listens LMS recorded in its own history but never '
            'relayed to MuMa (lost during a MuMa restart or deploy). Only recent listens with no MuMa listen '
            'of the same user within ten minutes are inserted; nothing existing is ever changed.',
        ),
        ConfigField(
            key='lms_listen_backfill_interval_minutes',
            type='integer',
            default=15,
            env='LMS_LISTEN_BACKFILL_INTERVAL_MINUTES',
            group='Scrobbling',
            description='Minutes between two rounds of the LMS listen backfill.',
        ),
        ConfigField(
            key='lms_listen_backfill_window_hours',
            type='integer',
            default=48,
            env='LMS_LISTEN_BACKFILL_WINDOW_HOURS',
            group='Scrobbling',
            description='How many hours of LMS listens each backfill round reads. Older history is left to the '
            'manual reconcile (POST /api/scrobble/reconcile/lms with insert_lms_only).',
        ),
        ConfigField(
            key='prefer_lossless',
            type='boolean',
            default=True,
            env='PREFER_LOSSLESS',
            group='Song versions',
            description='Which file of a song plays when several versions exist. On: lossless (FLAC) first, then '
            'MP3 320, AAC, lower bitrates. Off (saves storage and bandwidth): MP3 320 first, then AAC, then '
            'lossless. The version kind (pro edit, radio edit, ...) decides within a format. Changing it rescores '
            'every song within the hour; songs pinned on the Versions page keep their pin.',
        ),
    ]


#: Marks a config.json written by a store that persists overrides only. A file
#: without it predates that and held a snapshot of every value, secrets from the
#: environment included; see `ConfigStore._load_from_disk`.
FILE_FORMAT_KEY = '__format__'
FILE_FORMAT = 2


class ConfigStore:
    """Runtime configuration store shared across the application.

    Precedence, highest first:

    1. a value explicitly changed through the API (`update`), persisted in
       `config.json`;
    2. the environment, read at start-up;
    3. the field's declared default.

    Only (1) is ever written to disk, and only while it differs from what (2)/(3)
    would give: a value set back to its environment value or default is removed
    from the file, so the next deploy's environment applies again. Up to 0.72 every
    value was written, the file was loaded after the environment, and whatever was
    in the environment on the day of the first save -- secrets included -- won
    over every later deploy.
    """

    _instance: ConfigStore | None = None
    _instance_lock = threading.Lock()
    _initialized = False

    def __new__(cls) -> ConfigStore:
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        with self._instance_lock:
            if self._initialized:
                return
            self._fields = _config_fields()
            self._field_map = {field.key: field for field in self._fields}
            self._lock = threading.RLock()
            self._listeners: MutableMapping[str, list[Callable[[Any], None]]] = defaultdict(list)
            config_path = os.getenv('CONFIG_PATH')
            if config_path:
                self._config_path = Path(config_path)
            else:
                self._config_path = Path('data') / 'config.json'
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            self._env_values: dict[str, Any] = {}
            self._overrides: dict[str, Any] = {}
            self._values: dict[str, Any] = {field.key: field.default for field in self._fields}
            self._load_from_env()
            self._load_from_disk()
            for field in self._fields:
                self._recompute(field)
            self._initialized = True

    def _initialize(self) -> None:
        """Legacy initialization method."""

    def _baseline(self, field: ConfigField) -> Any:
        """What the field is without an override: the environment's value, else the default."""
        if field.key in self._env_values:
            return self._env_values[field.key]
        return field.default

    def _recompute(self, field: ConfigField) -> None:
        """Refresh the effective value of `field` from override, environment and default."""
        if field.key in self._overrides:
            self._values[field.key] = self._overrides[field.key]
        else:
            self._values[field.key] = self._baseline(field)

    def _public_value(self, field: ConfigField) -> Any:
        """The value as it may leave the process.

        A secret that is set reads as the sentinel; a secret that is not set reads as
        its empty value, because masking nothing would claim a credential exists.
        """
        value = self._values.get(field.key)
        if field.secret and value:
            return SECRET_SENTINEL
        return value

    def describe(self) -> list[dict[str, Any]]:
        """Return schema information with current values for API responses."""
        with self._lock:
            return [
                {
                    'key': field.key,
                    'type': field.type,
                    'group': field.group,
                    'description': field.description,
                    'nullable': field.nullable,
                    'default': field.default,
                    'secret': field.secret,
                    'read_only': field.read_only,
                    'value': self._public_value(field),
                }
                for field in self._fields
            ]

    def get(self, key: str, default: Any = None) -> Any:
        """The effective value of `key`, unmasked; for in-process readers only."""
        field = self._field_map.get(key)
        if not field:
            return os.getenv(key, default)
        with self._lock:
            return self._values.get(key, default)

    def __getattr__(self, item: str) -> Any:
        if item.startswith('_'):
            raise AttributeError(item)
        field = self._field_map.get(item)
        if field:
            return self.get(item)
        return os.getenv(item)

    def all_configs(self) -> dict[str, Any]:
        """Every value, with secrets masked.

        This is what `GET /api/config` hands out. In-process readers use `get`, which
        returns the real value -- the database connector needs the actual password.
        """
        with self._lock:
            return {field.key: self._public_value(field) for field in self._fields}

    def groups(self) -> list[str]:
        """Every configuration group name."""
        return list({field.group for field in self._fields})

    def fields(self) -> list[dict[str, Any]]:
        """Alias of `describe`, kept for the `/api/config/fields` route."""
        return self.describe()

    def get_many(self, keys: Iterable[str]) -> dict[str, Any]:
        """Read several keys at once, unmasked."""
        return {key: self.get(key) for key in keys}

    def is_overridden(self, key: str) -> bool:
        """Whether `key` holds a value set through the API rather than env/default."""
        with self._lock:
            return key in self._overrides

    def update(self, updates: dict[str, Any]) -> dict[str, Any]:
        """Apply values posted by the config page and return them as the API may show them.

        The whole payload is validated before anything changes. The returned mapping is
        the public (masked) value of every key in `updates` -- the same thing
        `all_configs` reports -- so a secret that was just typed in is not echoed back.
        """
        if not updates:
            return {}
        changed: dict[str, Any] = {}
        with self._lock:
            staged: dict[str, Any] = {}
            for key, raw_value in updates.items():
                field = self._field_map.get(key)
                if field is None:
                    raise KeyError(f'Unknown configuration key: {key}')
                # The config page reads every value and posts them all back, so each
                # secret it did not touch arrives as the sentinel. Storing that would
                # replace the credential with the mask.
                if field.secret and raw_value == SECRET_SENTINEL:
                    continue
                value = self._coerce(field, raw_value)
                if field.read_only:
                    # Posting the page back carries these unchanged; anything else is
                    # an attempt to set what nothing would read.
                    if value != self._values.get(key):
                        raise ValueError(f'{key} is read-only here: it is read from the environment')
                    continue
                staged[key] = value
            overrides_before = dict(self._overrides)
            for key, value in staged.items():
                field = self._field_map[key]
                if value == self._baseline(field):
                    self._overrides.pop(key, None)
                else:
                    self._overrides[key] = value
                before = self._values.get(key)
                self._recompute(field)
                if self._values.get(key) != before:
                    changed[key] = self._values[key]
            if self._overrides != overrides_before:
                self._persist_locked()
            result = {key: self._public_value(self._field_map[key]) for key in updates}
        for key, value in changed.items():
            self._notify_listeners(key, value)
        return result

    def subscribe(self, key: str, callback: Callable[[Any], None], *, immediate: bool = False) -> Callable[[], None]:
        """Register a callback that receives the new value when a key changes."""
        field = self._field_map.get(key)
        if field is None:
            raise KeyError(f'Unknown configuration key: {key}')
        with self._lock:
            self._listeners[key].append(callback)
            current_value = self._values.get(key)
        if immediate:
            callback(current_value)

        def _unsubscribe() -> None:
            with self._lock:
                callbacks = self._listeners.get(key)
                if callbacks and callback in callbacks:
                    callbacks.remove(callback)

        return _unsubscribe

    def _coerce(self, field: ConfigField, value: Any) -> Any:
        if value is None:
            if not field.nullable:
                raise ValueError(f'{field.key} may not be null')
            return None
        if field.type == 'boolean':
            return self._coerce_boolean(field, value)
        if field.type == 'integer':
            return self._coerce_integer(field, value)
        if field.type == 'string':
            return self._coerce_string(field, value)
        raise ValueError(f'Unsupported field type {field.type} for {field.key}')

    def _coerce_boolean(self, field: ConfigField, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {'1', 'true', 'yes', 'on'}:
                return True
            if lowered in {'0', 'false', 'no', 'off'}:
                return False
            raise ValueError(f'Cannot parse boolean value for {field.key}: {value!r}')
        if isinstance(value, (int, float)):
            return bool(value)
        raise ValueError(f'Invalid type for boolean field {field.key}')

    def _coerce_integer(self, field: ConfigField, value: Any) -> int | None:
        if value == '':
            return None if field.nullable else 0
        if isinstance(value, bool):
            raise ValueError(f'Invalid boolean for integer field {field.key}')
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            if value.is_integer():
                return int(value)
            raise ValueError(f'Non-integer value for {field.key}')
        if isinstance(value, str):
            try:
                return int(value.strip())
            except ValueError as exc:
                raise ValueError(f'Cannot parse integer value for {field.key}') from exc
        raise ValueError(f'Invalid type for integer field {field.key}')

    def _coerce_string(self, field: ConfigField, value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, (int, float, bool)):
            return str(value)
        raise ValueError(f'Invalid type for string field {field.key}')

    def _load_from_env(self) -> None:
        """Record every field the environment sets; these are the baseline, not overrides."""
        for field in self._fields:
            env_key = field.env or field.key
            candidates = [env_key]
            if env_key.upper() != env_key:
                candidates.append(env_key.upper())
            for candidate in candidates:
                if candidate in os.environ:
                    raw_value = os.environ[candidate]
                    try:
                        value = self._coerce(field, raw_value)
                    except ValueError:
                        continue
                    self._env_values[field.key] = value
                    break

    def _load_from_disk(self) -> None:
        """Read the persisted overrides.

        A file in the current format holds overrides only; an entry that happens to
        equal the environment or the default is dropped. A file without the format
        marker was written by 0.72 or earlier and holds a snapshot of every value. It still
        loads, with three filters, because such a file cannot tell a value typed on the
        config page from one copied out of the environment on the day of the save:

        * an entry equal to the environment value or the default is not an override;
        * a secret the environment also sets is left to the environment -- a stale
          copy of a since-rotated credential is exactly what that file preserved;
        * read-only fields are ignored.

        What survives is rewritten in the current format straight away, so the
        environment's secrets are off the persistent volume from the first start.
        """
        if not self._config_path.exists():
            return
        try:
            data = json.loads(self._config_path.read_text(encoding='utf-8'))
        except Exception:
            return
        if not isinstance(data, dict):
            return
        legacy = data.get(FILE_FORMAT_KEY) != FILE_FORMAT
        for key, value in data.items():
            field = self._field_map.get(key)
            if not field or field.read_only:
                continue
            try:
                coerced = self._coerce(field, value)
            except ValueError:
                continue
            if coerced == self._baseline(field):
                continue
            if legacy and field.secret and field.key in self._env_values:
                continue
            self._overrides[key] = coerced
        if legacy:
            with contextlib.suppress(OSError):
                self._persist_locked()
        else:
            self._restrict_permissions()

    def _persist_locked(self) -> None:
        """Write the overrides -- nothing else -- to config.json, readable by the owner only."""
        payload: dict[str, Any] = {FILE_FORMAT_KEY: FILE_FORMAT}
        payload.update({key: value for key, value in self._overrides.items() if not self._field_map[key].read_only})
        text = json.dumps(payload, indent=2, sort_keys=True)
        # mkstemp creates the file 0600 under a unique name: several worker containers
        # share one data volume, and each is PID 1 in its own namespace.
        fd, tmp_name = tempfile.mkstemp(prefix=f'.{self._config_path.name}.', dir=self._config_path.parent)
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                handle.write(text)
            os.replace(tmp_path, self._config_path)
        except BaseException:
            with contextlib.suppress(OSError):
                tmp_path.unlink()
            raise
        self._restrict_permissions()

    def _restrict_permissions(self) -> None:
        """Make config.json owner-only; it may hold a credential typed on the config page."""
        with contextlib.suppress(OSError):
            os.chmod(self._config_path, 0o600)

    def _notify_listeners(self, key: str, value: Any) -> None:
        listeners: list[Callable[[Any], None]]
        with self._lock:
            listeners = list(self._listeners.get(key, ()))
        for callback in listeners:
            try:
                callback(value)
            except Exception:
                continue

    @property
    def config_path(self) -> Path:
        """Where the overrides are persisted."""
        return self._config_path


def credential(config_key: str, env_name: str) -> str | None:
    """A third-party credential: the Beheer > Config value first, the environment second.

    The store seeds itself from the environment at start-up and persists what the config
    page changes, so on its own it would do -- except that it is a process-wide singleton
    created before a test (or a CLI) can set the variable, so the environment is read again
    as the fallback. `None` when neither has it, so `bool()` reads as "configured".

    Every consumer of a Spotify or Last.fm key goes through here. Until 2026-09-21 the
    artist-image fetcher and the tagger's artist verification each read `os.getenv` only,
    and the config page's fields for the same keys were stored and read by nobody.
    """
    try:
        value = ConfigStore().get(config_key)
    except Exception:
        value = None
    return (value or os.getenv(env_name)) or None


__all__ = ['ConfigField', 'ConfigStore', 'credential']
