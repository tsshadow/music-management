"""Covers the pieces of the SoundCloud downloader around the actual download:
account lookup, the yt-dlp match filter, the options it builds and the
configuration that decides whether it runs at all."""

import unittest
from unittest.mock import MagicMock, patch

from services.tests.connector_fakes import wire_connector
from services.tests.mock_base import setup_mocks

setup_mocks()

from services.downloader.soundcloud import soundcloud as soundcloud_module  # isort:skip
from services.downloader.soundcloud.soundcloud import (  # isort:skip
    FIREFOX_USER_AGENT,
    SoundcloudDownloader,
    account_from_url,
    get_accounts_from_db,
)


class AccountFromUrlTest(unittest.TestCase):
    def test_the_account_is_the_first_path_segment(self):
        self.assertEqual(account_from_url('https://soundcloud.com/angerfist/tracks'), 'angerfist')

    def test_a_trailing_slash_does_not_shift_the_segments(self):
        self.assertEqual(account_from_url('https://soundcloud.com/angerfist/'), 'angerfist')

    def test_something_that_is_not_a_url_is_returned_as_is(self):
        self.assertEqual(account_from_url('angerfist'), 'angerfist')


class GetAccountsFromDbTest(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(soundcloud_module, 'DatabaseConnector')
        self.addCleanup(patcher.stop)
        self.connector_cls = patcher.start()
        self.cursor = MagicMock()
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = self.cursor
        wire_connector(self.connector_cls.return_value, connection)

    def test_the_configured_accounts_are_returned(self):
        self.cursor.fetchall.return_value = [('angerfist',), ('outsiders',)]

        self.assertEqual(get_accounts_from_db(), ['angerfist', 'outsiders'])

    def test_a_database_failure_yields_no_accounts_rather_than_raising(self):
        self.cursor.execute.side_effect = Exception('DB Error')

        self.assertEqual(get_accounts_from_db(), [])


def downloader_with(config_values, **attributes):
    """A downloader whose __init__ is bypassed, wired for one method under test."""
    downloader = SoundcloudDownloader.__new__(SoundcloudDownloader)
    downloader._config = MagicMock()
    downloader._config.get_many.return_value = config_values
    downloader.dry_run = False
    downloader.default_break_on_existing = False
    downloader.redownload_mode = False
    downloader._profile_snapshot = None
    # `timing` is a read-only property backed by the sweep policy.
    downloader.policy = MagicMock()
    downloader.policy.timing.to_ydl_opts.return_value = {}
    for name, value in attributes.items():
        setattr(downloader, name, value)
    return downloader


CONFIG = {
    'soundcloud_folder': '/music/soundcloud',
    'soundcloud_archive': '/data/archive',
    'soundcloud_cookies': 'soundcloud.com_cookies.txt',
    'ffmpeg_location': '/usr/bin',
    'soundcloud_user_agent': '',
}


class MatchFilterTest(unittest.TestCase):
    def setUp(self):
        self.downloader = downloader_with(CONFIG, unavailable=MagicMock())
        self.downloader.unavailable.should_skip.return_value = False
        self.archive_patcher = patch.object(soundcloud_module, 'SoundcloudArchive')
        self.addCleanup(self.archive_patcher.stop)
        self.archive = self.archive_patcher.start()
        self.archive.exists.return_value = False

    def track(self, **overrides):
        return {'id': 'track-1', 'title': 'Raise Your Fist', 'duration': 300, 'channel_id': 'angerfist', **overrides}

    def test_a_normal_track_passes(self):
        self.assertIsNone(self.downloader._match_filter(self.track()))

    def test_a_track_that_is_too_short_is_skipped(self):
        self.assertEqual(self.downloader._match_filter(self.track(duration=30)), 'Outside allowed duration range')

    def test_a_track_that_is_too_long_is_skipped(self):
        self.assertEqual(self.downloader._match_filter(self.track(duration=21601)), 'Outside allowed duration range')

    def test_a_track_without_a_duration_is_skipped(self):
        self.assertEqual(self.downloader._match_filter(self.track(duration=None)), 'Outside allowed duration range')

    def test_a_track_already_in_the_archive_is_skipped(self):
        self.archive.exists.return_value = True

        self.assertEqual(self.downloader._match_filter(self.track()), 'Already in database archive')

    def test_a_redownload_ignores_the_archive(self):
        self.archive.exists.return_value = True
        self.downloader.redownload_mode = True

        self.assertIsNone(self.downloader._match_filter(self.track()))

    def test_the_uploader_id_stands_in_for_a_missing_channel_id(self):
        self.downloader._match_filter(self.track(channel_id=None, uploader_id='angerfist'))

        self.archive.exists.assert_called_once_with('angerfist', 'track-1')

    def test_every_track_the_filter_sees_is_reported_as_extracted(self):
        report = MagicMock()

        self.downloader._make_match_filter('angerfist', report)(self.track(timestamp=1750000000))

        report.note_extracted.assert_called_once_with('track-1', 1750000000)

    def test_a_track_without_a_timestamp_is_still_reported(self):
        report = MagicMock()

        self.downloader._make_match_filter('angerfist', report)(self.track())

        report.note_extracted.assert_called_once_with('track-1', None)

    def test_a_track_that_answered_403_before_is_not_tried_again(self):
        self.downloader.unavailable.should_skip.return_value = True
        report = MagicMock()

        result = self.downloader._make_match_filter('angerfist', report)(self.track())

        self.assertEqual(result, 'Known to be unavailable')


class PrepareYdlOptsTest(unittest.TestCase):
    def downloader(self, **config):
        base = {'ydl_opts': {'break_on_existing': True}, 'archive_file': None, 'archive_dir': '/data/archive'}
        return downloader_with(CONFIG, downloader_config={**base, **config})

    def test_a_dry_run_only_simulates(self):
        downloader = self.downloader()
        downloader.dry_run = True

        self.assertTrue(downloader._prepare_ydl_opts('angerfist', None, False)['simulate'])

    def test_breaking_on_an_existing_item_can_be_forced_on(self):
        opts = self.downloader()._prepare_ydl_opts('angerfist', True, False)

        self.assertTrue(opts['break_on_existing'])

    def test_breaking_on_an_existing_item_can_be_forced_off(self):
        opts = self.downloader()._prepare_ydl_opts('angerfist', False, False)

        self.assertNotIn('break_on_existing', opts)

    def test_without_an_override_the_downloader_default_applies(self):
        downloader = self.downloader()
        downloader.default_break_on_existing = True

        self.assertTrue(downloader._prepare_ydl_opts('angerfist', None, False)['break_on_existing'])

    def test_a_shared_archive_file_is_used_for_every_account(self):
        opts = self.downloader(archive_file='/data/archive.txt')._prepare_ydl_opts('angerfist', None, False)

        self.assertEqual(opts['download_archive'], '/data/archive.txt')

    def test_without_a_shared_file_each_account_gets_its_own_archive(self):
        opts = self.downloader()._prepare_ydl_opts('angerfist', None, False)

        self.assertEqual(opts['download_archive'], '/data/archive/angerfist.txt')

    def test_a_redownload_ignores_the_archive_entirely(self):
        opts = self.downloader(archive_file='/data/archive.txt')._prepare_ydl_opts('angerfist', None, True)

        self.assertNotIn('download_archive', opts)


class SnapshotProfileTest(unittest.TestCase):
    def setUp(self):
        self.downloader = downloader_with(CONFIG)

    def test_no_profile_means_nothing_to_snapshot(self):
        self.assertIsNone(self.downloader._snapshot_profile(None))

    def test_a_profile_is_replaced_by_its_snapshot(self):
        with patch.object(soundcloud_module, 'snapshot_cookie_profile', return_value='/tmp/snap'):
            self.assertEqual(self.downloader._snapshot_profile('/home/firefox/default'), '/tmp/snap')

        self.assertEqual(self.downloader._profile_snapshot, '/tmp/snap')

    def test_a_failed_snapshot_falls_back_to_the_live_profile(self):
        with patch.object(soundcloud_module, 'snapshot_cookie_profile', return_value=None):
            self.assertEqual(self.downloader._snapshot_profile('/home/firefox/default'), '/home/firefox/default')

    def test_the_previous_snapshot_is_cleaned_up_first(self):
        self.downloader._profile_snapshot = '/tmp/old'

        with (
            patch.object(soundcloud_module, 'snapshot_cookie_profile', return_value='/tmp/new'),
            patch.object(soundcloud_module.shutil, 'rmtree') as rmtree,
        ):
            self.downloader._snapshot_profile('/home/firefox/default')

        rmtree.assert_called_once_with('/tmp/old', ignore_errors=True)


class ApplyConfigTest(unittest.TestCase):
    def apply(self, config=None, isfile=False):
        downloader = downloader_with({**CONFIG, **(config or {})})
        with (
            patch.object(soundcloud_module.os, 'makedirs'),
            patch.object(soundcloud_module.os.path, 'isfile', return_value=isfile),
        ):
            downloader._apply_config()
        return downloader.downloader_config

    def test_a_complete_configuration_enables_the_downloader(self):
        config = self.apply()

        self.assertTrue(config['enabled'])
        self.assertEqual(config['ydl_opts']['outtmpl'], '/music/soundcloud/%(uploader)s/%(title)s.%(ext)s')
        self.assertEqual(config['ydl_opts']['http_headers']['User-Agent'], FIREFOX_USER_AGENT)

    def test_a_custom_user_agent_wins_over_the_default(self):
        config = self.apply({'soundcloud_user_agent': 'muma/1.0'})

        self.assertEqual(config['ydl_opts']['http_headers']['User-Agent'], 'muma/1.0')

    def test_without_an_output_folder_the_downloader_is_disabled(self):
        config = self.apply({'soundcloud_folder': ''})

        self.assertFalse(config['enabled'])
        self.assertEqual(config['ydl_opts'], {})

    def test_without_an_archive_the_downloader_is_disabled(self):
        config = self.apply({'soundcloud_archive': ''})

        self.assertFalse(config['enabled'])

    def test_an_archive_that_is_a_file_is_shared_by_every_account(self):
        config = self.apply(isfile=True)

        self.assertEqual(config['archive_file'], '/data/archive')

    def test_an_archive_that_is_a_directory_gives_each_account_its_own(self):
        config = self.apply(isfile=False)

        self.assertIsNone(config['archive_file'])

    def test_a_cookies_file_is_passed_through(self):
        config = self.apply()

        self.assertEqual(config['ydl_opts']['cookies'], 'soundcloud.com_cookies.txt')

    def test_a_firefox_profile_is_snapshotted_before_use(self):
        downloader = downloader_with({**CONFIG, 'soundcloud_cookies': 'firefox:/home/firefox/default'})
        with (
            patch.object(soundcloud_module.os, 'makedirs'),
            patch.object(soundcloud_module.os.path, 'isfile', return_value=False),
            patch.object(soundcloud_module, 'snapshot_cookie_profile', return_value='/tmp/snap'),
        ):
            downloader._apply_config()

        self.assertEqual(downloader.downloader_config['ydl_opts']['cookiesfrombrowser'], ('firefox', '/tmp/snap'))

    def test_an_empty_cookie_setting_falls_back_to_the_default_file(self):
        config = self.apply({'soundcloud_cookies': ''})

        self.assertEqual(config['ydl_opts']['cookies'], 'soundcloud.com_cookies.txt')

    def test_the_dead_playlist_random_key_is_gone(self):
        # YoutubeDL reads 'playlistrandom'; the 'playlist_random' key an API
        # caller passes is never read by anything, so it shuffled nothing. It is
        # dropped rather than corrected: newest-first is the order both
        # break_on_existing and the account probe rely on.
        self.assertNotIn('playlist_random', self.apply()['ydl_opts'])

    def test_downloads_go_through_a_part_file(self):
        # yt-dlp writes `<name>.part` and renames it once complete unless `nopart`
        # is set, so a cut-off download never sits under its real name for the
        # tagger to pick up. The inert `no_part` key that used to stand here is
        # gone too, so nobody reads it as the opposite.
        opts = self.apply()['ydl_opts']
        self.assertNotIn('nopart', opts)
        self.assertNotIn('no_part', opts)

    def test_lazy_playlist_is_on_so_break_on_existing_stops_the_paging(self):
        # Without it __process_playlist materialises every entry before a single
        # download starts, so break_on_existing can only stop the download loop.
        self.assertIs(self.apply()['ydl_opts']['lazy_playlist'], True)


if __name__ == '__main__':
    unittest.main()
