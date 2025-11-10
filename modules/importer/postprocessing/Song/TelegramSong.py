import logging

from data.settings import Settings
from postprocessing.Song.SoundcloudSong import SoundcloudSong

s = Settings()

class TelegramSong(SoundcloudSong):
    def __init__(self, path, extra_info=None):
        super().__init__(path, extra_info)
        self._publisher = "Telegram"

