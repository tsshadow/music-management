import asyncio
import logging
import os
from pathlib import Path
from telethon import TelegramClient
from services.common.config_store import ConfigStore
from services.downloader.sweep import SweepPolicy

SOURCE = 'telegram'

def _is_flood_wait(error: Exception) -> bool:
    """Recognise Telethon's flood wait without importing it.

    Telethon raises `FloodWaitError` once a wait exceeds `flood_sleep_threshold`.
    Matching on the type name keeps this working with the stand-in module the
    tests install.
    """
    return 'floodwait' in type(error).__name__.lower() or hasattr(error, 'seconds')

class TelegramDownloader:
    """Downloads audio and video from Telegram channels.

    Pacing comes from the same settings and backoff state as the other
    downloaders, so a flood wait parks Telegram in the database rather than being
    forgotten on the next restart.
    """

    def __init__(self, dry_run=False, timing=None, rate_state=None, schedule=None):
        self.dry_run = dry_run
        self._config = ConfigStore()
        values = self._config.get_many(['telegram_folder', 'telegram_api_id', 'telegram_api_hash',
                                        'telegram_session'])
        self.policy = SweepPolicy(SOURCE, timing=timing, rate_state=rate_state, schedule=schedule)
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
            logging.warning('Missing required configuration: telegram_folder, telegram_api_id, telegram_api_hash. Telegram downloads will be disabled.')
            self.output_folder = None
            self.api_id = None
            self.api_hash = None

    def _is_audio(self, message) -> bool:
        mime = getattr(getattr(message, 'file', None), 'mime_type', '')
        return bool(mime) and mime.startswith('audio')

    def _is_media(self, message) -> bool:
        mime = getattr(getattr(message, 'file', None), 'mime_type', '')
        return bool(mime) and (mime.startswith('audio') or mime.startswith('video'))

    async def _download_if_needed(self, client, msg, folder: str, semaphore: asyncio.Semaphore):
        base_name = msg.file.name or f'{msg.id}.bin'
        safe_path = os.path.join(folder, base_name)
        file_path = Path(safe_path)
        expected_size = getattr(msg.file, 'size', None)
        if file_path.exists():
            if expected_size is not None and file_path.stat().st_size == expected_size:
                return
            print(f'⚠️ Onvolledig of onbekend bestand gevonden, opnieuw downloaden: {safe_path}')
        else:
            if self.dry_run:
                print(f'⬇️ [DRY RUN] Downloaden: {safe_path}')
                return
            print(f'⬇️ Downloaden: {safe_path}')
        async with semaphore:
            try:
                await client.download_media(msg, file=safe_path)
            except Exception as e:
                print(f'❌ Fout bij downloaden van {safe_path}: {e}')

    async def _download_channel(self, client, channel: str, limit: int | None=None):
        channel_folder = os.path.join(self.output_folder, channel)
        os.makedirs(channel_folder, exist_ok=True)
        semaphore = asyncio.Semaphore(self.max_concurrent_downloads)
        download_tasks = []
        async for msg in client.iter_messages(channel, limit=limit):
            if self._is_media(msg) and msg.file:
                task = self._download_if_needed(client, msg, channel_folder, semaphore)
                download_tasks.append(task)
        await asyncio.gather(*download_tasks)

    async def _run_async(self, channel: str, limit: int | None=None):
        loop = asyncio.get_running_loop()
        async with TelegramClient(self.session, int(self.api_id), self.api_hash, loop=loop,
                                  flood_sleep_threshold=self.policy.timing.flood_sleep_threshold) as client:
            await self._download_channel(client, channel, limit)

    def run(self, channel: str, limit: int | None=None):
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
