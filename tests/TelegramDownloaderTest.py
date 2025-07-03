import sys
import types
import unittest
import os
import tempfile

# stub telethon module
telethon_mod = types.ModuleType('telethon')
class DummyClient:
    def __init__(self, *a, **k):
        self.loop = types.SimpleNamespace(run_until_complete=lambda coro: None)
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        pass
    async def iter_messages(self, *a, **k):
        if False:
            yield None
    async def download_media(self, *a, **k):
        pass
telethon_mod.TelegramClient = DummyClient
sys.modules['telethon'] = telethon_mod

from downloader.telegram import TelegramDownloader

class TelegramDownloaderTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        os.environ['telegram_folder'] = self.tempdir.name
        os.environ['telegram_api_id'] = '1'
        os.environ['telegram_api_hash'] = 'hash'

    def tearDown(self):
        self.tempdir.cleanup()
        sys.modules.pop('telethon', None)

    def test_is_audio(self):
        dl = TelegramDownloader()
        msg = types.SimpleNamespace(file=types.SimpleNamespace(mime_type='audio/mpeg'))
        self.assertTrue(dl._is_audio(msg))
        msg2 = types.SimpleNamespace(file=types.SimpleNamespace(mime_type='video/mp4'))
        self.assertFalse(dl._is_audio(msg2))

if __name__ == '__main__':
    unittest.main()
