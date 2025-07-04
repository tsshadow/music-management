import os

from telethon import TelegramClient


class TelegramDownloader:
    def __init__(self):
        self.output_folder = os.getenv("telegram_folder")
        self.api_id = os.getenv("telegram_api_id")
        self.api_hash = os.getenv("telegram_api_hash")
        self.session = os.getenv("telegram_session", "telegram")

        if not self.output_folder or not self.api_id or not self.api_hash:
            raise ValueError(
                "Missing required environment variables: telegram_folder, telegram_api_id, telegram_api_hash"
            )

    def _is_audio(self, message) -> bool:
        mime = getattr(getattr(message, "file", None), "mime_type", "")
        return bool(mime) and mime.startswith("audio")

    async def _download_channel(self, client, channel: str, limit: int | None = None):
        # Determine the folder specific to the channel
        channel_folder = os.path.join(self.output_folder, channel)
        os.makedirs(channel_folder, exist_ok=True)

        async for msg in client.iter_messages(channel, limit=limit):
            if self._is_audio(msg):
                await client.download_media(msg, file=channel_folder)

    def run(self, channel: str, limit: int | None = None):
        if not channel:
            raise ValueError("Channel must be provided")
        with TelegramClient(self.session, int(self.api_id), self.api_hash) as client:
            client.loop.run_until_complete(self._download_channel(client, channel, limit))

