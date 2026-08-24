"""Centralized configuration store with persistence and change notifications."""
from __future__ import annotations

import json
import os
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

def _config_fields() -> list[ConfigField]:
    """Return the ordered list of supported configuration fields."""
    return [ConfigField(key='debug', type='boolean', default=False, env='debug', description='Enable verbose debug logging for import jobs.'), ConfigField(key='rescan', type='boolean', default=False, env='rescan', description='Force a rescan of already processed files.'), ConfigField(key='dryrun', type='boolean', default=False, env='dryrun', description='Run processors without modifying files on disk.'), ConfigField(key='import_folder_path', type='string', default='', env='import_folder_path', group='Paths', description='Folder that contains newly downloaded music archives.'), ConfigField(key='eps_folder_path', type='string', default='', env='eps_folder_path', group='Paths', description='Location for extracted EPs.'), ConfigField(key='music_folder_path', type='string', default='', env='music_folder_path', group='Paths', description='Destination library for processed tracks.'), ConfigField(key='delimiter', type='string', default=os.sep, env='delimiter', group='General', description='Path delimiter used when parsing artist/title strings.'), ConfigField(key='tagger_deep_run_days', type='integer', default=30, env='TAGGER_DEEP_RUN_DAYS', group='Tagger', description='How old a file\'s last tagging round may get before the tagger reads it again with the current rules. 0 switches the deep run off.'), ConfigField(key='max_retag_files', type='integer', default=2000, env='MAX_RETAG_FILES', group='Tagger', description='Ceiling on how many files one "apply now" on an artist or label rule may retag. The job holds the tagger lock for the whole batch, so a high number means the ordinary tagging round waits. Past the ceiling the page asks for a full tagger run instead.'), ConfigField(key='tagger_deep_run_batch', type='integer', default=200, env='TAGGER_DEEP_RUN_BATCH', group='Tagger', description='How many files one tagging round may hand back to the deep run. Bounds the extra work per round, not the length of a cycle.'), ConfigField(key='youtube_folder', type='string', default='', env='youtube_folder', group='YouTube', description='Target folder for YouTube downloads.'), ConfigField(key='youtube_video_folder', type='string', default='', env='youtube_video_folder', group='YouTube', description='Target folder for channels marked as video. Nothing indexes the files: the tagger and importer only accept audio extensions, and LMS only indexes audio formats.'), ConfigField(key='youtube_archive', type='string', default='', env='youtube_archive', group='YouTube', description='Archive directory or file that library_tracks downloaded YouTube videos.'), ConfigField(key='ffmpeg_location', type='string', default='/usr/bin', env='ffmpeg-location', group='YouTube', description='Location of the ffmpeg binary used by yt-dlp.'), ConfigField(key='yt_cookies', type='string', default='', env='YT_COOKIES', group='YouTube', description='Path to a cookies.txt file for YouTube downloads.'), ConfigField(key='yt_user_agent', type='string', default='', env='YT_USER_AGENT', group='YouTube', description='Optional custom user agent for YouTube requests.'), ConfigField(key='soundcloud_folder', type='string', default='', env='soundcloud_folder', group='SoundCloud', description='Target folder for SoundCloud downloads.'), ConfigField(key='soundcloud_archive', type='string', default='', env='soundcloud_archive', group='SoundCloud', description='Archive directory or file for SoundCloud downloads.'), ConfigField(key='soundcloud_cookies', type='string', default='soundcloud.com_cookies.txt', env='soundcloud_cookies', group='SoundCloud', description='Cookies file used to access private or follower-only tracks.'), ConfigField(key='telegram_folder', type='string', default='', env='telegram_folder', group='Telegram', description='Base folder for Telegram downloads.'), ConfigField(key='telegram_api_id', type='string', default='', env='telegram_api_id', group='Telegram', description='Telegram API ID used for the downloader client.'), ConfigField(key='telegram_api_hash', type='string', default='', secret=True, env='telegram_api_hash', group='Telegram', description='Telegram API hash used for the downloader client.'), ConfigField(key='telegram_session', type='string', default='telegram', env='telegram_session', group='Telegram', description='Session name for the Telegram client.'), ConfigField(key='telegram_max_concurrent', type='integer', default=4, env='telegram_max_concurrent', group='Telegram', description='Maximum number of concurrent Telegram downloads.'), ConfigField(key='telegram_accounts', type='string', default='', env='telegram_accounts', group='Telegram', description='Comma-separated list of Telegram channels to download from.'), ConfigField(key='db_host', type='string', default='', env='DB_HOST', group='Database', description='Database host for metadata storage.'), ConfigField(key='db_port', type='integer', default=None, env='DB_PORT', group='Database', description='Database port for metadata storage.'), ConfigField(key='db_user', type='string', default='', env='DB_USER', group='Database', description='Database user for metadata storage.'), ConfigField(key='db_pass', type='string', default='', secret=True, env='DB_PASS', group='Database', description='Database password for metadata storage.'), ConfigField(key='db_name', type='string', default='', env='DB_DB', group='Database', description='Database name for metadata storage.'), ConfigField(key='db_connect_timeout', type='integer', default=5, env='DB_CONNECT_TIMEOUT', group='Database', description='Connection timeout (seconds) when connecting to the database.'), ConfigField(key='discogs_token', type='string', default='', secret=True, env='DISCOGS_TOKEN', group='3rd Party APIs', description='Discogs personal access token for artist lookup.'), ConfigField(key='lastfm_api_key', type='string', default='', secret=True, env='LASTFM_API_KEY', group='3rd Party APIs', description='Last.fm API key for artist lookup.'), ConfigField(key='spotify_client_id', type='string', default='', env='SPOTIFY_CLIENT_ID', group='3rd Party APIs', description='Spotify client ID for artist lookup.'), ConfigField(key='spotify_client_secret', type='string', default='', secret=True, env='SPOTIFY_CLIENT_SECRET', group='3rd Party APIs', description='Spotify client secret for artist lookup.'), ConfigField(key='notify_url', type='string', default='', env='NOTIFY_URL', group='Notifications', description='URL for ntfy.sh integration.'), ConfigField(key='notify_topic', type='string', default='music-management', env='notify_topic', group='Notifications', description='Topic name for ntfy.sh notifications.'), ConfigField(key='notify_topic_alerts', type='string', default='music-management-alerts', env='notify_topic_alerts', group='Notifications', description='Topic for warnings and errors. Subscribe separately so alerts can have their own sound.')]

class ConfigStore:
    """Runtime configuration store shared across the application."""
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
            self._values: dict[str, Any] = {field.key: field.default for field in self._fields}
            self._load_from_env()
            self._load_from_disk()
            self._initialized = True

    def _initialize(self) -> None:
        """Legacy initialization method."""

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
            return [{'key': field.key, 'type': field.type, 'group': field.group, 'description': field.description, 'nullable': field.nullable, 'default': field.default, 'secret': field.secret, 'value': self._public_value(field)} for field in self._fields]

    def get(self, key: str, default: Any = None) -> Any:
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
        return list({field.group for field in self._fields})

    def fields(self) -> list[dict[str, Any]]:
        return self.describe()

    def get_many(self, keys: Iterable[str]) -> dict[str, Any]:
        return {key: self.get(key) for key in keys}

    def update(self, updates: dict[str, Any]) -> dict[str, Any]:
        if not updates:
            return {}
        changed: dict[str, Any] = {}
        with self._lock:
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
                if self._values.get(key) != value:
                    self._values[key] = value
                    changed[key] = value
            if changed:
                self._persist_locked()
        for key, value in changed.items():
            self._notify_listeners(key, value)
        return {key: self.get(key) for key in updates}

    def subscribe(self, key: str, callback: Callable[[Any], None], *, immediate: bool=False) -> Callable[[], None]:
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
                    self._values[field.key] = value
                    break

    def _load_from_disk(self) -> None:
        if not self._config_path.exists():
            return
        try:
            data = json.loads(self._config_path.read_text(encoding='utf-8'))
        except Exception:
            return
        if not isinstance(data, dict):
            return
        for key, value in data.items():
            field = self._field_map.get(key)
            if not field:
                continue
            try:
                self._values[key] = self._coerce(field, value)
            except ValueError:
                continue

    def _persist_locked(self) -> None:
        payload = {key: self._values.get(key) for key in self._field_map}
        self._config_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding='utf-8')

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
        return self._config_path
__all__ = ['ConfigField', 'ConfigStore']