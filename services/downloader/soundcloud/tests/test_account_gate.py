"""The decision made before any downloading: does this account have anything new?"""
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from services.tests.mock_base import reset_database_helpers, setup_mocks

setup_mocks()

from services.downloader.rate_state import RateLimited  # isort:skip
from services.downloader.soundcloud.account_probe import ProbeResult  # isort:skip
from services.downloader.soundcloud.account_report import AccountReport  # isort:skip
from services.downloader.soundcloud.soundcloud import SoundcloudDownloader  # isort:skip


class AccountGateTestCase(unittest.TestCase):

    def setUp(self):
        reset_database_helpers()
        # The constructor reads accounts and touches the filesystem while it
        # builds its config; same scaffolding test_basic_run.py needs.
        patch('services.downloader.soundcloud.soundcloud.get_accounts_from_db',
              return_value=['monstercat']).start()
        patch('pathlib.Path.exists', return_value=True).start()
        patch('os.makedirs').start()
        self.addCleanup(patch.stopall)
        self.downloader = SoundcloudDownloader()
        self.downloader.policy = MagicMock()
        self.downloader.download_account = MagicMock()

    def probe_returns(self, result):
        return patch('services.downloader.soundcloud.soundcloud.newest_track',
                     return_value=result)

    def probe_raises(self, error):
        return patch('services.downloader.soundcloud.soundcloud.newest_track',
                     side_effect=error)

    def archive_holds(self, held):
        return patch('services.downloader.soundcloud.soundcloud.SoundcloudArchive.track_exists',
                     return_value=held)


class CheckAccountTest(AccountGateTestCase):

    def test_an_account_with_nothing_new_is_not_downloaded(self):
        probe = ProbeResult('2379459947', 'Dokho - Better Place', 'https://x')
        with self.probe_returns(probe), self.archive_holds(True):
            self.downloader._check_account('monstercat', {})
        self.downloader.download_account.assert_not_called()

    def test_an_account_with_nothing_new_still_counts_as_progress(self):
        # Otherwise a run of quiet accounts leaves _blank_run untouched, and the
        # next genuinely blank account can tip note_blank over block_threshold
        # and park the whole source.
        probe = ProbeResult('2379459947', 't', 'u')
        with self.probe_returns(probe), self.archive_holds(True):
            self.downloader._check_account('monstercat', {})
        self.downloader.policy.note_progress.assert_called_once()

    def test_the_probed_track_id_is_remembered(self):
        probe = ProbeResult('2379459947', 't', 'u')
        with self.probe_returns(probe), self.archive_holds(True):
            self.downloader._check_account('monstercat', {})
        self.assertEqual(self.downloader._seen_tracks['monstercat'], '2379459947')

    def test_an_unseen_newest_track_triggers_the_full_run(self):
        probe = ProbeResult('2999999999', 't', 'u')
        with self.probe_returns(probe), self.archive_holds(False):
            self.downloader._check_account('monstercat', {'break_on_existing': True})
        self.downloader.download_account.assert_called_once()

    def test_an_account_with_no_visible_tracks_falls_through_to_the_full_run(self):
        with self.probe_returns(None), self.archive_holds(False):
            self.downloader._check_account('monstercat', {})
        self.downloader.download_account.assert_called_once()

    def test_a_rate_limit_from_the_probe_stops_the_sweep(self):
        self.downloader.policy.rate_limit_from.return_value = RateLimited('soundcloud', 60, '403')
        with self.probe_raises(RuntimeError('HTTP Error 403: Forbidden')):
            with self.assertRaises(RateLimited):
                self.downloader._check_account('monstercat', {})
        self.downloader.download_account.assert_not_called()

    def test_any_other_probe_failure_falls_through_to_the_full_run(self):
        # The probe is an optimisation; it may never be the reason an account
        # goes unchecked.
        self.downloader.policy.rate_limit_from.return_value = None
        with self.probe_raises(RuntimeError('connection reset')), self.archive_holds(False):
            self.downloader._check_account('monstercat', {})
        self.downloader.download_account.assert_called_once()


class LearnedUploadDateTest(AccountGateTestCase):

    def test_a_run_that_saw_a_timestamp_reports_it_as_a_date(self):
        report = AccountReport()
        report.note_extracted('t1', 1750000000)

        self.downloader._record_upload_date('monstercat', report)

        self.assertEqual(self.downloader._checked_kwargs('monstercat'),
                         {'last_upload_at': datetime.fromtimestamp(1750000000)})

    def test_a_run_that_saw_no_timestamp_reports_nothing(self):
        self.downloader._record_upload_date('monstercat', AccountReport())

        self.assertEqual(self.downloader._checked_kwargs('monstercat'), {})

    def test_a_probed_track_id_is_reported_even_without_a_date(self):
        self.downloader._seen_tracks['monstercat'] = '2379459947'

        self.assertEqual(self.downloader._checked_kwargs('monstercat'),
                         {'last_seen_track_id': '2379459947'})

    def test_what_was_learned_is_reported_once_and_then_forgotten(self):
        report = AccountReport()
        report.note_extracted('t1', 1750000000)
        self.downloader._record_upload_date('monstercat', report)

        self.downloader._checked_kwargs('monstercat')

        self.assertEqual(self.downloader._checked_kwargs('monstercat'), {})


if __name__ == '__main__':
    unittest.main()
