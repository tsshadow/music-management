import asyncio
import os
import sys
import tempfile
import types
import unittest
import unittest.mock
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

    async def download_media(self, _message, file=None, **_kwargs):
        # Behaves like Telethon: writes the bytes to the path it was given and
        # returns that path.
        with open(file, 'wb') as handle:
            handle.write(b'audio')
        return file


_telethon.TelegramClient = DummyClient

from services.downloader.account_schedule import AccountSchedule, InMemoryCheckStore
from services.downloader.rate_state import InMemoryRateStateStore, RateState
from services.downloader.telegram.telegram import TelegramDownloader, download_target, legacy_target
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


class TaggingTest(TelegramTimingTestBase):
    """A Telegram download is tagged by the worker, like SoundCloud and YouTube -- until
    0.67 nothing tagged it and the file waited for the walk to reach Telegram/."""

    def _message(self, mime, name='set.mp3', size=None, message_id=1, ext=None):
        message = types.SimpleNamespace()
        message.file = types.SimpleNamespace(mime_type=mime, name=name, size=size, ext=ext)
        message.id = message_id
        return message

    def _download(self, message, prepare=None):
        from services.downloader.telegram import telegram as telegram_module

        with tempfile.TemporaryDirectory() as folder:
            if prepare is not None:
                prepare(folder)
            downloader = self._downloader(folder)
            with (
                unittest.mock.patch.object(telegram_module.Tagger, 'parse_song', return_value=object()) as parse,
                unittest.mock.patch.object(telegram_module, 'announce') as announce,
            ):
                asyncio.run(downloader._download_if_needed(DummyClient(), message, folder, asyncio.Semaphore(1)))
            self.files = sorted(os.listdir(folder))
            return parse, announce, folder

    def test_an_audio_download_is_tagged_and_announced(self):
        parse, announce, folder = self._download(self._message('audio/mpeg'))
        parse.assert_called_once()
        self.assertEqual(parse.call_args.args[1].name, 'TELEGRAM')
        announce.assert_called_once_with(f'{folder}/set [1].mp3')

    def test_the_part_file_is_renamed_once_the_download_is_done(self):
        self._download(self._message('audio/mpeg'))
        self.assertEqual(['set [1].mp3'], self.files)

    def test_a_file_already_there_under_the_old_name_is_not_downloaded_again(self):
        def _old_file(folder):
            with open(os.path.join(folder, 'set.mp3'), 'wb') as handle:
                handle.write(b'audio')

        parse, _announce, _folder = self._download(self._message('audio/mpeg', size=5), prepare=_old_file)
        parse.assert_not_called()
        self.assertEqual(['set.mp3'], self.files)

    def test_a_name_that_climbs_out_of_the_folder_lands_inside_it(self):
        parse, announce, folder = self._download(self._message('audio/mpeg', name='../../evil.mp3'))
        announce.assert_called_once_with(f'{folder}/evil [1].mp3')
        self.assertEqual(['evil [1].mp3'], self.files)

    def test_a_video_download_is_left_alone(self):
        parse, announce, _ = self._download(self._message('video/mp4', name='clip.mp4'))
        parse.assert_not_called()
        announce.assert_not_called()

    def test_a_failed_download_is_not_tagged(self):
        async def failing(*_args, **_kwargs):
            raise RuntimeError('network')

        with unittest.mock.patch.object(DummyClient, 'download_media', failing):
            parse, announce, _ = self._download(self._message('audio/mpeg'))
        parse.assert_not_called()
        announce.assert_not_called()
        # Neither a truncated file under the real name nor a stray .part is left.
        self.assertEqual([], self.files)

    def test_a_download_that_wrote_nothing_is_a_failure(self):
        async def silent(*_args, **_kwargs):
            return None

        with unittest.mock.patch.object(DummyClient, 'download_media', silent):
            parse, _announce, _ = self._download(self._message('audio/mpeg'))
        parse.assert_not_called()
        self.assertEqual([], self.files)


class DownloadTargetTest(unittest.TestCase):
    """The path a Telegram file is written to; the sender picks the name."""

    FOLDER = '/music/Telegram/chan'

    def test_an_ordinary_name_keeps_its_stem_and_gains_the_message_id(self):
        self.assertEqual(
            f'{self.FOLDER}/Angerfist - Set [42].mp3', download_target(self.FOLDER, 42, 'Angerfist - Set.mp3')
        )

    def test_a_relative_climb_is_reduced_to_the_last_component(self):
        self.assertEqual(f'{self.FOLDER}/passwd [7].mp3', download_target(self.FOLDER, 7, '../../../etc/passwd.mp3'))

    def test_an_absolute_path_is_reduced_to_the_last_component(self):
        self.assertEqual(f'{self.FOLDER}/x [7].flac', download_target(self.FOLDER, 7, '/tmp/x.flac'))

    def test_a_windows_style_path_is_reduced_too(self):
        self.assertEqual(f'{self.FOLDER}/x [7].mp3', download_target(self.FOLDER, 7, '..\\..\\x.mp3'))

    def test_a_bare_dot_dot_leaves_only_the_message_id(self):
        self.assertEqual(f'{self.FOLDER}/7.mp3', download_target(self.FOLDER, 7, '..', ext_hint='.mp3'))

    def test_unsafe_characters_are_replaced(self):
        self.assertEqual(f'{self.FOLDER}/a_b_c_ d [7].mp3', download_target(self.FOLDER, 7, 'a:b?c\x00 d.mp3'))

    def test_two_messages_with_the_same_name_get_different_paths(self):
        self.assertNotEqual(download_target(self.FOLDER, 1, 'set.mp3'), download_target(self.FOLDER, 2, 'set.mp3'))

    def test_a_nameless_message_takes_telethons_extension(self):
        self.assertEqual(f'{self.FOLDER}/9.m4a', download_target(self.FOLDER, 9, None, ext_hint='.m4a'))

    def test_a_nameless_message_without_a_hint_takes_the_mime_types_extension(self):
        self.assertEqual(f'{self.FOLDER}/9.flac', download_target(self.FOLDER, 9, None, mime='audio/flac'))

    def test_bin_is_only_the_last_resort(self):
        self.assertEqual(f'{self.FOLDER}/9.bin', download_target(self.FOLDER, 9, None))

    def test_a_very_long_name_is_cut_to_fit_the_filesystem(self):
        path = download_target(self.FOLDER, 9, 'x' * 400 + '.mp3')
        self.assertLess(len(os.path.basename(path).encode('utf-8')), 255 - len('.part'))
        self.assertTrue(path.endswith(' [9].mp3'))

    def test_a_symlinked_escape_is_refused(self):
        with tempfile.TemporaryDirectory() as root:
            folder = os.path.join(root, 'chan')
            os.makedirs(folder)
            os.symlink('/tmp', os.path.join(folder, 'link [1].mp3'))
            with self.assertRaises(ValueError):
                download_target(folder, 1, 'link.mp3')

    def test_the_legacy_name_is_the_bare_basename(self):
        self.assertEqual(f'{self.FOLDER}/set.mp3', legacy_target(self.FOLDER, '../set.mp3'))

    def test_there_is_no_legacy_name_without_a_remote_name(self):
        self.assertIsNone(legacy_target(self.FOLDER, None))
        self.assertIsNone(legacy_target(self.FOLDER, '..'))


if __name__ == '__main__':
    unittest.main()
