import os
import asyncio
from pathlib import Path
import logging

from telethon import TelegramClient


class TelegramDownloader:
    def __init__(self):
        self.output_folder = os.getenv("telegram_folder")
        self.api_id = os.getenv("telegram_api_id")
        self.api_hash = os.getenv("telegram_api_hash")
        self.session = os.getenv("telegram_session", "telegram")
        self.max_concurrent_downloads = int(os.getenv("telegram_max_concurrent", 4))

        if not self.output_folder or not self.api_id or not self.api_hash:
            logging.warning(
                "Missing required environment variables: telegram_folder, telegram_api_id, telegram_api_hash. "
                "Telegram downloads will be disabled."
            )
            self.output_folder = None
            self.api_id = None
            self.api_hash = None

    def _is_audio(self, message) -> bool:
        mime = getattr(getattr(message, "file", None), "mime_type", "")
        return bool(mime) and mime.startswith("audio")

    def _is_media(self, message) -> bool:
        mime = getattr(getattr(message, "file", None), "mime_type", "")
        return bool(mime) and (mime.startswith("audio") or mime.startswith("video"))

    async def _download_if_needed(self, client, msg, folder: str, semaphore: asyncio.Semaphore):
        base_name = msg.file.name or f"{msg.id}.bin"
        safe_path = os.path.join(folder, base_name)
        file_path = Path(safe_path)

        expected_size = getattr(msg.file, "size", None)
        if file_path.exists():
            if expected_size is not None and file_path.stat().st_size == expected_size:
                return  # Bestand bestaat en is volledig
            else:
                print(f"⚠️ Onvolledig of onbekend bestand gevonden, opnieuw downloaden: {safe_path}")
        else:
            print(f"⬇️ Downloaden: {safe_path}")

        async with semaphore:
            try:
                await client.download_media(msg, file=safe_path)
            except Exception as e:
                print(f"❌ Fout bij downloaden van {safe_path}: {e}")

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

    def run(self, channel: str, limit: int | None = None):
        if not self.output_folder or not self.api_id or not self.api_hash:
            logging.warning("Telegram downloader is not configured; skipping run().")
            return

        if not channel:
            raise ValueError("Channel must be provided")

        with TelegramClient(self.session, int(self.api_id), self.api_hash) as client:
            client.loop.run_until_complete(self._download_channel(client, channel, limit))
