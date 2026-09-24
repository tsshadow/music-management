import asyncio
import contextlib
import logging
import mimetypes
import os
import re
from pathlib import Path

from telethon import TelegramClient

from services.common.config_store import ConfigStore
from services.downloader.sweep import SweepPolicy
from services.tagger.announce import announce
from services.tagger.constants import SongTypeEnum
from services.tagger.tagger import Tagger

SOURCE = 'telegram'

# Characters no filesystem the library lives on accepts, plus the ASCII controls.
# The path separators are in here too, but `os.path.basename` has already taken
# anything before the last one off.
_UNSAFE_CHARS = re.compile(r'[\x00-\x1f\x7f<>:"/\\|?*]')
# Well under the 255-byte limit of ext4 and CIFS, leaving room for the message id,
# the extension and the `.part` suffix.
_MAX_STEM_BYTES = 180
# yt-dlp's own suffix for an unfinished download; the tagger and the scanner skip it.
PART_SUFFIX = '.part'


def _safe_stem(stem: str) -> str:
    """A filename stem with every character that could escape or break a path removed."""
    cleaned = _UNSAFE_CHARS.sub('_', stem).strip().strip('.').strip()
    encoded = cleaned.encode('utf-8')
    if len(encoded) > _MAX_STEM_BYTES:
        cleaned = encoded[:_MAX_STEM_BYTES].decode('utf-8', 'ignore').rstrip()
    return cleaned


def _extension(remote_ext: str, ext_hint: str | None, mime: str | None) -> str:
    """The extension to store a file under: the sender's, else Telethon's, else the mime type's.

    A bare `.bin` is the last resort only. The tagger picks files up by extension,
    so the fallback that used to be the default here left every nameless audio
    message untagged forever.
    """
    for candidate in (remote_ext, ext_hint, mimetypes.guess_extension(mime or '') if mime else None):
        if not candidate:
            continue
        candidate = '.' + _safe_stem(candidate.lstrip('.')).lower()
        if 1 < len(candidate) <= 10:
            return candidate
    return '.bin'


def _inside(folder: str, path: str) -> bool:
    """Whether `path` resolves to somewhere under `folder`."""
    root = os.path.realpath(folder)
    return os.path.commonpath([root, os.path.realpath(path)]) == root


def download_target(
    folder: str, message_id: int, remote_name: str | None, ext_hint: str | None = None, mime: str | None = None
) -> str:
    """Where a Telegram message's file is stored, built from nothing the sender can abuse.

    The sender chooses `remote_name`, so only its last path component is kept and
    anything unsafe in it is replaced: a name like `../../etc/x` or `/tmp/x` lands
    as a plain file in `folder`. The message id goes into the name as well, because
    two messages carrying the same filename used to overwrite each other while
    `asyncio.gather` downloaded them side by side. Raises ValueError if the result
    would still end up outside `folder`.
    """
    name = os.path.basename((remote_name or '').replace('\\', '/'))
    stem, remote_ext = os.path.splitext(name)
    if not stem and remote_ext:
        # A dotfile such as `.mp3`: splitext reads the whole thing as a stem.
        stem, remote_ext = remote_ext, ''
    stem = _safe_stem(stem)
    extension = _extension(remote_ext, ext_hint, mime)
    filename = f'{stem} [{message_id}]{extension}' if stem else f'{message_id}{extension}'
    path = os.path.join(folder, filename)
    if not _inside(folder, path):
        raise ValueError(f'Refusing to write {filename!r} outside {folder}')
    return path


def legacy_target(folder: str, remote_name: str | None) -> str | None:
    """Where this worker stored the same file before the message id was part of the name.

    Only consulted to recognise a file that is already there, so a channel does not
    download everything again after the naming change. None when there is no remote
    name or it would not resolve inside `folder`.
    """
    name = os.path.basename((remote_name or '').replace('\\', '/'))
    if not name or name in ('.', '..'):
        return None
    path = os.path.join(folder, name)
    return path if _inside(folder, path) else None


def _is_flood_wait(error: Exception) -> bool:
    """Recognise Telethon's flood wait without importing it.

    Telethon raises `FloodWaitError` once a wait exceeds `flood_sleep_threshold`.
    Matching on the type name keeps this working with the stand-in module the
    tests install.
    """
    return 'floodwait' in type(error).__name__.lower() or hasattr(error, 'seconds')


def tag_downloaded_file(path: str) -> None:
    """Tag a file this worker just downloaded, then announce it.

    Until 0.67 nobody tagged a Telegram download: the file sat untagged until the
    folder walk in music-manager reached `Telegram/`, which comes after EPs, Soundcloud
    and Youtube -- days, with a queue in front of it. Same shape as the SoundCloud and
    YouTube postprocessors. Never raises: a download that landed is a download.
    """
    try:
        if Tagger.parse_song(Path(path), SongTypeEnum.TELEGRAM):
            announce(path)
    except Exception as e:
        logging.error(f'Telegram: could not tag {path}: {e}')


class TelegramDownloader:
    """Downloads audio and video from Telegram channels.

    Pacing comes from the same settings and backoff state as the other
    downloaders, so a flood wait parks Telegram in the database rather than being
    forgotten on the next restart.
    """

    def __init__(self, dry_run=False, timing=None, rate_state=None, schedule=None, notifier=None):
        self.dry_run = dry_run
        self._config = ConfigStore()
        values = self._config.get_many(['telegram_folder', 'telegram_api_id', 'telegram_api_hash', 'telegram_session'])
        self.policy = SweepPolicy(SOURCE, timing=timing, rate_state=rate_state, schedule=schedule, notifier=notifier)
        self.output_folder = values.get('telegram_folder')
        self.api_id = values.get('telegram_api_id')
        self.api_hash = values.get('telegram_api_hash')
        session_name = values.get('telegram_session') or 'telegram'
        if os.path.exists('/app/data'):
            self.session = os.path.join('/app/data', session_name)
        else:
            self.session = session_name
        self.max_concurrent_downloads = self.policy.timing.max_concurrent
        if not self.output_folder or not self.api_id or (not self.api_hash):
            logging.warning(
                'Missing required configuration: telegram_folder, telegram_api_id, telegram_api_hash. Telegram downloads will be disabled.'
            )
            self.output_folder = None
            self.api_id = None
            self.api_hash = None

    def _is_audio(self, message) -> bool:
        mime = getattr(getattr(message, 'file', None), 'mime_type', '')
        return bool(mime) and mime.startswith('audio')

    def _is_media(self, message) -> bool:
        mime = getattr(getattr(message, 'file', None), 'mime_type', '')
        return bool(mime) and (mime.startswith('audio') or mime.startswith('video'))

    @staticmethod
    def _complete(path: str | None, expected_size) -> bool:
        """Whether a file is already on disk at its full size."""
        if not path or not os.path.isfile(path):
            return False
        return expected_size is not None and os.path.getsize(path) == expected_size

    async def _download_if_needed(self, client, msg, folder: str, semaphore: asyncio.Semaphore):
        """Download one message's file unless it is already there, then tag it if it is audio.

        The file is written to `<name>.part` and renamed only once Telethon is done
        with it, so a download cut short never sits in the library under its real
        name for the tagger and the scanner to pick up.
        """
        remote_name = getattr(msg.file, 'name', None)
        try:
            target = download_target(
                folder, msg.id, remote_name, getattr(msg.file, 'ext', None), getattr(msg.file, 'mime_type', None)
            )
        except ValueError as e:
            logging.warning('Telegram: skipping message %s: %s', msg.id, e)
            return
        expected_size = getattr(msg.file, 'size', None)
        if self._complete(target, expected_size) or self._complete(legacy_target(folder, remote_name), expected_size):
            return
        if os.path.exists(target):
            logging.info('Telegram: incomplete or unknown file found, downloading again: %s', target)
        elif self.dry_run:
            logging.info('Telegram: [DRY RUN] would download %s', target)
            return
        else:
            logging.info('Telegram: downloading %s', target)
        partial = target + PART_SUFFIX
        async with semaphore:
            try:
                written = await client.download_media(msg, file=partial)
                written = written if isinstance(written, str) else partial
                if not os.path.isfile(written):
                    raise OSError(f'Telethon reported success but wrote nothing at {written}')
                os.replace(written, target)
            except Exception as e:
                logging.error('Telegram: could not download %s: %s', target, e)
                with contextlib.suppress(OSError):
                    os.remove(partial)
                return
        if self._is_audio(msg):
            # Off the event loop: the rules are CPU work and the tag pass writes the file.
            await asyncio.to_thread(tag_downloaded_file, target)

    async def _download_channel(self, client, channel: str, limit: int | None = None):
        channel_folder = os.path.join(self.output_folder, channel)
        os.makedirs(channel_folder, exist_ok=True)
        semaphore = asyncio.Semaphore(self.max_concurrent_downloads)
        download_tasks = []
        async for msg in client.iter_messages(channel, limit=limit):
            if self._is_media(msg) and msg.file:
                task = self._download_if_needed(client, msg, channel_folder, semaphore)
                download_tasks.append(task)
        await asyncio.gather(*download_tasks)

    async def _run_async(self, channel: str, limit: int | None = None):
        loop = asyncio.get_running_loop()
        async with TelegramClient(
            self.session,
            int(self.api_id),
            self.api_hash,
            loop=loop,
            flood_sleep_threshold=self.policy.timing.flood_sleep_threshold,
        ) as client:
            await self._download_channel(client, channel, limit)

    def run(self, channel: str, limit: int | None = None):
        if not self.output_folder or not self.api_id or (not self.api_hash):
            logging.warning('Telegram is not configured; skipping run().')
            return
        if not channel:
            raise ValueError('Channel must be provided')
        if not self.policy.begin():
            return
        if not self.policy.due([channel]):
            logging.info('Telegram channel %s was checked recently; skipping.', channel)
            return
        try:
            asyncio.run(self._run_async(channel, limit))
        except Exception as e:
            if _is_flood_wait(e):
                logging.warning('Telegram asked us to wait: %s', e)
                self.policy.park('429', channel)
                return
            logging.error('Telegram download failed for %s: %s', channel, e, exc_info=True)
            return
        self.policy.mark_checked(channel)
        self.policy.finish()
