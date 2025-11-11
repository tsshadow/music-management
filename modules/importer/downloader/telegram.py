import asyncio
import logging
import os
from pathlib import Path

from telethon import TelegramClient

from api.config_store import ConfigStore


class TelegramDownloader:
    def __init__(self):
        self._config = ConfigStore()
        self._subscriptions = []
        self._apply_config()
        for key in [
            "telegram_folder",
            "telegram_api_id",
            "telegram_api_hash",
            "telegram_session",
            "telegram_max_concurrent",
        ]:
            self._subscriptions.append(
                self._config.subscribe(key, lambda _value, k=key: self._apply_config())
            )

    def _is_audio(self, message) -> bool:
        mime = getattr(getattr(message, "file", None), "mime_type", "")
        return mime.startswith("audio/")

    async def _download_channel(self, client, channel: str, limit: int | None = None):
        from telethon.tl.types import MessageMediaDocument

        os.makedirs(self.output_folder, exist_ok=True)

        async for message in client.iter_messages(channel, limit=limit):
            if isinstance(message.media, MessageMediaDocument) and self._is_audio(message):
                file_path = os.path.join(self.output_folder, f"{message.id}.mp3")
                logging.info(f"Downloading {file_path}")
                await client.download_media(message, file_path)

    async def _download_messages(self, client, messages):
        semaphore = asyncio.Semaphore(self.max_concurrent_downloads)

        async def download_message(message):
            async with semaphore:
                if message.audio:
                    out = os.path.join(self.output_folder, f"{message.id}.mp3")
                    logging.info(f"Downloading {out}")
                    await client.download_media(message, out)

        download_tasks = [download_message(message) for message in messages]
        await asyncio.gather(*download_tasks)

    def run(self, channel: str, limit: int | None = None):
        if not self.enabled:
            logging.warning("Telegram downloader is not configured; skipping run().")
            return

        os.makedirs(self.output_folder, exist_ok=True)

        with TelegramClient(self.session, int(self.api_id), self.api_hash) as client:
            client.loop.run_until_complete(self._download_channel(client, channel, limit))

    def _apply_config(self) -> None:
        values = self._config.get_many(
            [
                "telegram_folder",
                "telegram_api_id",
                "telegram_api_hash",
                "telegram_session",
                "telegram_max_concurrent",
            ]
        )

        self.output_folder = values.get("telegram_folder") or None
        self.api_id = values.get("telegram_api_id") or None
        self.api_hash = values.get("telegram_api_hash") or None
        self.session = values.get("telegram_session") or "telegram"
        max_concurrent = values.get("telegram_max_concurrent")
        self.max_concurrent_downloads = int(max_concurrent) if max_concurrent else 4

        if not self.output_folder or not self.api_id or not self.api_hash:
            if getattr(self, "enabled", True):
                logging.warning(
                    "Missing required configuration for Telegram downloads. Telegram downloads will be disabled."
                )
            self.enabled = False
            return

        Path(self.output_folder).mkdir(parents=True, exist_ok=True)
        self.enabled = True
