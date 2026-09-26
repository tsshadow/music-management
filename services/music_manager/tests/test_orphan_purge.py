"""Which fileless track rows the purge deletes, and which it keeps for a person (bug report 104).

The SQL runs against MariaDB in tests/integration/test_track_relink.py; these tests pin down the
survey, the batching and the dry run on a scripted cursor.
"""

import unittest
from unittest.mock import MagicMock, patch

from services.music_manager import orphan_purge
from services.music_manager.tests.scripted_cursor import ScriptedCursor

ORPHANS = [
    {'id': 1, 'track_uid': 'uid-1', 'title': 'plain stub'},
    {'id': 2, 'track_uid': 'uid-2', 'title': 'listened to'},
    {'id': 3, 'track_uid': 'uid-3', 'title': 'rated'},
    {'id': 4, 'track_uid': 'uid-4', 'title': 'pinned'},
    {'id': 5, 'track_uid': 'uid-5', 'title': 'reviewed label'},
    {'id': 6, 'track_uid': None, 'title': 'no uid'},
]


def survey_rules(orphans=ORPHANS):
    """The five survey reads, with one reference of each kind on orphans 2 to 5."""
    return [
        ('FROM scrobble_listens WHERE track_id IS NOT NULL GROUP BY', None, [{'track_id': 2, 'n': 3}]),
        ("FROM rating_tracks WHERE entity_type = 'track' GROUP BY", None, [{'entity_id': 'uid-3', 'n': 1}]),
        ('SELECT pinned_track_id AS track_id FROM library_works', None, [{'track_id': 4}]),
        ('FROM library_track_ml_labels WHERE', None, [{'track_id': 'uid-5', 'n': 1}]),
        ('SELECT t.id, t.track_uid, t.title', None, orphans),
    ]


class SurveyTest(unittest.TestCase):
    def test_each_kind_of_reference_keeps_its_orphan(self):
        purge, kept = orphan_purge.survey_orphans(ScriptedCursor(survey_rules()))
        self.assertEqual(purge, [1, 6])
        self.assertEqual([row['id'] for row in kept], [2, 3, 4, 5])
        self.assertEqual(
            kept[0], {'id': 2, 'title': 'listened to', 'listens': 3, 'ratings': 0, 'pinned': 0, 'reviewed_labels': 0}
        )
        self.assertEqual((kept[1]['ratings'], kept[2]['pinned'], kept[3]['reviewed_labels']), (1, 1, 1))


class PurgeBatchTest(unittest.TestCase):
    def test_only_the_confirmed_rows_and_their_links_are_deleted(self):
        cursor = ScriptedCursor(
            [
                ('FOR UPDATE', None, [{'id': 1, 'track_uid': 'uid-1'}]),
                ('SELECT id FROM library_works WHERE canonical_track_id IN', None, [{'id': 40}]),
            ]
        )
        with patch.object(orphan_purge, 'recompute_canonicals') as recompute:
            counts = orphan_purge.purge_batch(cursor, [1, 2])

        confirm_sql, confirm_params = cursor.statements_matching('FOR UPDATE')[0]
        self.assertEqual(confirm_params, (1, 2))
        for guard in (
            'scrobble_listens',
            'rating_tracks',
            'pinned_track_id',
            'library_media_files',
            'ml_review_status',
        ):
            self.assertIn(guard, confirm_sql)
        for table in orphan_purge.LINK_TABLES:
            self.assertEqual(cursor.statements_matching(f'DELETE FROM {table}')[0][1], (1,))
        self.assertEqual(cursor.statements_matching('DELETE FROM library_tracks WHERE id IN')[0][1], (1,))
        ml_sql, ml_params = cursor.statements_matching('DELETE FROM library_track_ml_labels')[0]
        self.assertIn('AND NOT', ml_sql)
        self.assertEqual(ml_params, ('uid-1',))
        self.assertEqual(cursor.statements_matching('SET previous_canonical_track_id = NULL')[0][1], (1,))
        self.assertEqual(cursor.statements_matching('SET canonical_track_id = NULL')[0][1], (1,))
        recompute.assert_called_once_with(cursor, {40})
        self.assertEqual(counts['purged'], 1)
        # The track row goes last: every reference to it is gone first.
        statements = [sql for sql, _p in cursor.executed]
        self.assertEqual(
            statements.index(cursor.statements_matching('DELETE FROM library_tracks')[0][0]), len(statements) - 1
        )

    def test_a_batch_whose_rows_all_changed_writes_nothing(self):
        cursor = ScriptedCursor()
        counts = orphan_purge.purge_batch(cursor, [1])
        self.assertEqual(counts['purged'], 0)
        self.assertEqual([sql for sql, _p in cursor.executed if not sql.lstrip().startswith('SELECT')], [])


class PurgeOrphanedTracksTest(unittest.TestCase):
    def _conn(self, cursor):
        conn = MagicMock()
        conn.cursor.return_value = cursor
        return conn

    def test_a_dry_run_counts_and_lists_and_writes_nothing(self):
        cursor = ScriptedCursor(survey_rules())
        conn = self._conn(cursor)
        totals = orphan_purge.purge_orphaned_tracks(conn, dry_run=True)

        conn.begin.assert_not_called()
        self.assertEqual([sql for sql, _p in cursor.executed if not sql.startswith('SELECT')], [])
        self.assertTrue(totals['dry_run'])
        self.assertEqual((totals['orphans'], totals['purged'], totals['kept']), (6, 2, 4))
        self.assertEqual(
            (totals['kept_listens'], totals['kept_ratings'], totals['kept_pinned'], totals['kept_reviewed_labels']),
            (1, 1, 1, 1),
        )
        self.assertEqual([row['id'] for row in totals['kept_list']], [2, 3, 4, 5])

    def test_batches_split_the_plan_and_a_failing_one_is_rolled_back(self):
        orphans = [{'id': i, 'track_uid': f'free-{i}', 'title': 't'} for i in range(10, 15)]
        conn = self._conn(ScriptedCursor(survey_rules(orphans)))
        ok = {'purged': 2, 'links_deleted': 3, 'ml_labels_deleted': 0, 'works_cleared': 0}
        with patch.object(
            orphan_purge,
            'purge_batch',
            side_effect=[ok, RuntimeError('lock wait timeout'), ok | {'purged': 0}],
        ) as batch:
            totals = orphan_purge.purge_orphaned_tracks(conn, batch_size=2)

        self.assertEqual([call.args[1] for call in batch.call_args_list], [[10, 11], [12, 13], [14]])
        self.assertEqual((conn.begin.call_count, conn.commit.call_count), (3, 2))
        conn.rollback.assert_called_once()
        self.assertEqual((totals['purged'], totals['failed_batches'], totals['skipped_changed']), (2, 1, 1))
        self.assertEqual(totals['links_deleted'], 6)

    def test_a_second_run_finds_only_the_kept_orphans(self):
        kept_only = [row for row in ORPHANS if row['id'] in (2, 3, 4, 5)]
        conn = self._conn(ScriptedCursor(survey_rules(kept_only)))
        with patch.object(orphan_purge, 'purge_batch') as batch:
            totals = orphan_purge.purge_orphaned_tracks(conn)
        batch.assert_not_called()
        conn.begin.assert_not_called()
        self.assertEqual((totals['purged'], totals['kept']), (0, 4))


if __name__ == '__main__':
    unittest.main()
