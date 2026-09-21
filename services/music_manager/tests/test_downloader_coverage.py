"""The coverage page's numbers, from the counts the deep sweep left behind."""

import unittest
from datetime import datetime, timedelta

from services.tests.mock_base import setup_mocks

setup_mocks()

from services.downloader.account_schedule import AccountCheck
from services.downloader.account_snapshot import SNAPSHOT_CAPPED, SNAPSHOT_COMPLETE, AccountSnapshot
from services.music_manager.downloader_coverage import (
    ConfiguredAccount,
    build_coverage,
    totals,
    write_off_rows,
    youtube_key,
)

NOW = datetime(2026, 9, 21, 12, 0, 0)
DAY = timedelta(days=1)


def snapshot(listed=10, held=7, excluded=1, remaining=2, state=SNAPSHOT_CAPPED, taken_at=NOW - DAY):
    return AccountSnapshot(listed, held, excluded, remaining, state, taken_at)


def check(snap=None, **overrides):
    values = {'last_checked_at': NOW, 'last_deep_sweep_at': None, 'snapshot': snap}
    values.update(overrides)
    return AccountCheck(**values)


def coverage(configured, checks, last_downloads=None, write_offs=None, rate_state=None, week=0, month=0):
    return build_coverage(
        'soundcloud', configured, checks, last_downloads or {}, week, month, write_offs or {}, rate_state, NOW
    )


class AccountRowsTest(unittest.TestCase):
    def test_a_counted_account_carries_its_snapshot(self):
        body = coverage([ConfiguredAccount('dj_a', 'dj_a')], {'dj_a': check(snapshot())})
        row = body['accounts'][0]
        self.assertEqual((10, 7, 1, 2), (row['listed'], row['held'], row['excluded'], row['remaining']))
        self.assertEqual(0.7, row['coverage'])
        self.assertEqual('capped', row['state'])
        self.assertEqual((NOW - DAY).isoformat(), row['snapshot_at'])

    def test_an_account_never_counted_is_all_nulls_but_still_listed(self):
        body = coverage([ConfiguredAccount('dj_a', 'dj_a')], {'dj_a': check()})
        row = body['accounts'][0]
        self.assertIsNone(row['listed'])
        self.assertIsNone(row['coverage'])
        self.assertEqual(NOW.isoformat(), row['last_checked_at'])

    def test_an_account_never_checked_at_all_is_still_listed(self):
        body = coverage([ConfiguredAccount('dj_a', 'dj_a')], {})
        row = body['accounts'][0]
        self.assertEqual('dj_a', row['account'])
        self.assertIsNone(row['last_checked_at'])

    def test_a_check_row_without_a_configured_account_is_not_listed(self):
        # The account was deleted; its old count is not a channel any more.
        body = coverage([ConfiguredAccount('dj_a', 'dj_a')], {'dj_a': check(), 'gone': check(snapshot())})
        self.assertEqual(['dj_a'], [row['account'] for row in body['accounts']])

    def test_the_last_download_comes_from_the_archive(self):
        body = coverage([ConfiguredAccount('dj_a', 'dj_a')], {}, last_downloads={'dj_a': NOW - 3 * DAY})
        self.assertEqual((NOW - 3 * DAY).isoformat(), body['accounts'][0]['last_download_at'])

    def test_no_archive_row_with_a_timestamp_means_unknown(self):
        body = coverage([ConfiguredAccount('dj_a', 'dj_a')], {})
        self.assertIsNone(body['accounts'][0]['last_download_at'])

    def test_the_biggest_backlog_comes_first_then_by_name(self):
        configured = [ConfiguredAccount(name, name) for name in ('b', 'a', 'c', 'd')]
        checks = {
            'a': check(snapshot(remaining=5)),
            'b': check(snapshot(remaining=0)),
            'c': check(snapshot(remaining=5)),
        }
        body = coverage(configured, checks)
        self.assertEqual(['a', 'c', 'b', 'd'], [row['account'] for row in body['accounts']])

    def test_a_youtube_video_channel_is_keyed_apart_from_its_audio_form(self):
        self.assertEqual('@dj_a', youtube_key('@dj_a', 'audio'))
        self.assertEqual('@dj_a#video', youtube_key('@dj_a', 'video'))
        self.assertEqual('@dj_a', youtube_key('@dj_a', None))

    def test_the_youtube_row_keeps_its_download_type(self):
        configured = [ConfiguredAccount('@dj_a', '@dj_a#video', 'video')]
        body = coverage(configured, {'@dj_a#video': check(snapshot())}, last_downloads={'@dj_a#video': NOW})
        row = body['accounts'][0]
        self.assertEqual('video', row['download_type'])
        self.assertEqual(10, row['listed'])
        self.assertEqual(NOW.isoformat(), row['last_download_at'])


class TotalsTest(unittest.TestCase):
    def _rows(self, *remaining):
        return [
            {'listed': None if r is None else 10, 'held': 5, 'excluded': 1, 'remaining': r, 'account': str(i)}
            for i, r in enumerate(remaining)
        ]

    def test_the_three_groups_add_up_to_configured(self):
        summary = totals(self._rows(0, 3, None, 0, None, 1))
        self.assertEqual(6, summary['configured'])
        self.assertEqual(4, summary['counted'])
        self.assertEqual((2, 2, 2), (summary['complete'], summary['with_backlog'], summary['never_counted']))
        self.assertEqual(
            summary['configured'], summary['complete'] + summary['with_backlog'] + summary['never_counted']
        )

    def test_the_track_totals_sum_only_the_counted_accounts(self):
        summary = totals(self._rows(2, None, 3))
        self.assertEqual(
            (20, 10, 2, 5), (summary['listed'], summary['held'], summary['excluded'], summary['remaining'])
        )

    def test_no_accounts_at_all(self):
        summary = totals([])
        self.assertEqual(0, summary['configured'])
        self.assertEqual(0, summary['remaining'])

    def test_the_body_carries_the_recent_downloads_and_the_backoff(self):
        body = coverage([], {}, week=12, month=80, rate_state={'multiplier': 2})
        self.assertEqual(12, body['totals']['downloads_7d'])
        self.assertEqual(80, body['totals']['downloads_30d'])
        self.assertEqual({'multiplier': 2}, body['totals']['rate_state'])
        self.assertEqual(NOW.isoformat(), body['generated_at'])


class WriteOffRowsTest(unittest.TestCase):
    def test_every_known_reason_is_listed_even_at_zero(self):
        rows = write_off_rows({'too_short': 5})
        self.assertEqual(['too_short', 'too_long', '403', 'failing', 'failed'], [row['reason'] for row in rows])
        self.assertEqual([5, 0, 0, 0, 0], [row['count'] for row in rows])

    def test_a_reason_the_page_does_not_know_is_appended_not_dropped(self):
        rows = write_off_rows({'quarantined': 2, 'failed': 1})
        self.assertEqual('quarantined', rows[-1]['reason'])
        self.assertEqual(2, rows[-1]['count'])


class SnapshotStateInRowsTest(unittest.TestCase):
    def test_a_complete_pass_with_nothing_remaining_counts_as_complete(self):
        body = coverage(
            [ConfiguredAccount('dj_a', 'dj_a')], {'dj_a': check(snapshot(remaining=0, state=SNAPSHOT_COMPLETE))}
        )
        self.assertEqual(1, body['totals']['complete'])
        self.assertEqual('complete', body['accounts'][0]['state'])


if __name__ == '__main__':
    unittest.main()
