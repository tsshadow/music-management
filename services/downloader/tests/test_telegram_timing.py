import sys
import types
import unittest
from datetime import datetime, timedelta

from services.tests.mock_base import setup_mocks

setup_mocks()

# Telethon is not installed in the test environment; stand in for it before the
# downloader imports TelegramClient.
_telethon = types.ModuleType('telethon')
_errors = types.ModuleType('telethon.errors')


class FloodWaitError(Exception):
    def __init__(self, seconds=60):
        super().__init__(f'A wait of {seconds} seconds is required')
        self.seconds = seconds


_errors.FloodWaitError = FloodWaitError
_telethon.errors = _errors
sys.modules['telethon'] = _telethon
sys.modules['telethon.errors'] = _errors

RECORDED_CLIENTS = []


class DummyClient:
    raise_on_iter = None

    def __init__(self, *args, **kwargs):
        RECORDED_CLIENTS.append(kwargs)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def iter_messages(self, *_args, **_kwargs):
        error = DummyClient.raise_on_iter

        async def _generator():
            if error is not None:
                raise error
            return
            yield  # pragma: no cover - makes this an async generator

        return _generator()

    async def download_media(self, *_args, **_kwargs):
        return None


_telethon.TelegramClient = DummyClient

from services.downloader.account_schedule import AccountSchedule, InMemoryCheckStore
from services.downloader.rate_state import InMemoryRateStateStore, RateState
from services.downloader.telegram.telegram import TelegramDownloader
from services.downloader.timing import load_timing

NOW = datetime(2026, 7, 30, 12, 0, 0)


class StubNotifier:
    """Stub notifier for test isolation — prevents sweep.py lazy import."""

    def notify(self, message, title='Music Management'):
        return True


class TelegramTimingTestBase(unittest.TestCase):
    overrides: dict = {}

    def setUp(self):
        RECORDED_CLIENTS.clear()
        DummyClient.raise_on_iter = None
        self.now = NOW
        self.timing = load_timing('telegram', overrides=self.overrides)
        self.rate_store = InMemoryRateStateStore()
        self.check_store = InMemoryCheckStore()
        self.downloaded_channels = []

    def _rate_state(self):
        return RateState('telegram', self.timing, store=self.rate_store, now=lambda: self.now, jitter=lambda: 1.0)

    def _downloader(self, tmpdir='/tmp/telegram'):
        downloader = TelegramDownloader(
            timing=self.timing,
            rate_state=self._rate_state(),
            schedule=AccountSchedule('telegram', store=self.check_store, now=lambda: self.now),
            notifier=StubNotifier(),
        )
        downloader.output_folder = tmpdir
        downloader.api_id = '1'
        downloader.api_hash = 'hash'
        downloader.session = 'test'
        original = downloader._download_channel

        async def _record(client, channel, limit=None):
            self.downloaded_channels.append(channel)
            return await original(client, channel, limit)

        downloader._download_channel = _record
        return downloader


class ConcurrencyTest(TelegramTimingTestBase):
    overrides = {'max_concurrent': 7, 'account_cooldown': 0}

    def test_the_concurrency_limit_comes_from_the_settings(self):
        self.assertEqual(self._downloader().max_concurrent_downloads, 7)


class FloodThresholdTest(TelegramTimingTestBase):
    overrides = {'flood_sleep_threshold': 120, 'account_cooldown': 0}

    def test_telethon_is_told_how_long_it_may_wait_by_itself(self):
        self._downloader().run('some_channel')
        self.assertEqual(RECORDED_CLIENTS[0]['flood_sleep_threshold'], 120)


class ChannelCooldownTest(TelegramTimingTestBase):
    overrides = {'account_cooldown': 3600}

    def test_a_first_run_visits_the_channel(self):
        self._downloader().run('some_channel')
        self.assertEqual(self.downloaded_channels, ['some_channel'])

    def test_a_second_run_right_after_skips_the_channel(self):
        self._downloader().run('some_channel')
        self.downloaded_channels.clear()
        self._downloader().run('some_channel')
        self.assertEqual(self.downloaded_channels, [])

    def test_the_channel_comes_back_once_the_cooldown_expires(self):
        self._downloader().run('some_channel')
        self.downloaded_channels.clear()
        self.now = NOW + timedelta(seconds=3601)
        self._downloader().run('some_channel')
        self.assertEqual(self.downloaded_channels, ['some_channel'])

    def test_channels_have_their_own_cooldown(self):
        self._downloader().run('channel_a')
        self.downloaded_channels.clear()
        self._downloader().run('channel_b')
        self.assertEqual(self.downloaded_channels, ['channel_b'])


class FloodWaitTest(TelegramTimingTestBase):
    overrides = {'account_cooldown': 0, 'backoff_429_base': 3600, 'max_multiplier': 16}

    def test_a_flood_wait_raises_the_multiplier(self):
        DummyClient.raise_on_iter = FloodWaitError(seconds=300)
        self._downloader().run('some_channel')
        self.assertEqual(self._rate_state().multiplier, 2)

    def test_a_flood_wait_parks_telegram(self):
        DummyClient.raise_on_iter = FloodWaitError(seconds=300)
        self._downloader().run('some_channel')
        self.assertEqual(self._rate_state().cooldown_remaining(), 7200)

    def test_the_next_run_stays_away_while_telegram_is_parked(self):
        DummyClient.raise_on_iter = FloodWaitError(seconds=300)
        self._downloader().run('some_channel')
        DummyClient.raise_on_iter = None
        self.downloaded_channels.clear()
        self._downloader().run('some_channel')
        self.assertEqual(self.downloaded_channels, [])

    def test_a_failed_channel_is_not_marked_as_checked(self):
        DummyClient.raise_on_iter = FloodWaitError(seconds=300)
        self._downloader().run('some_channel')
        DummyClient.raise_on_iter = None
        self.now = NOW + timedelta(seconds=7201)
        self.downloaded_channels.clear()
        self._downloader().run('some_channel')
        self.assertEqual(self.downloaded_channels, ['some_channel'])


if __name__ == '__main__':
    unittest.main()
