"""The materialised effective BPM (bpm/effective_table.py): what a sync reads, compares and writes."""

import unittest
from decimal import Decimal
from unittest.mock import MagicMock

from services.music_manager.bpm import effective_table
from services.music_manager.bpm.effective import resolve_row, split_genres
from services.music_manager.bpm.index import INDEX_SQL, INPUTS_SQL


def measured(track_id, bpm=150.0, confidence=0.9):
    """An input row with a measurement."""
    return {
        'track_id': track_id,
        'bpm_tag': None,
        'tempo': None,
        'measured': bpm,
        'measured_confidence': confidence,
        'measured_folded': 0,
        'genres': 'Hardstyle',
    }


def tagged(track_id, tag=76.0, genres='Hardstyle'):
    """An input row with only a file tag."""
    return {'track_id': track_id, 'bpm_tag': tag, 'tempo': None, 'measured': None, 'genres': genres}


class ResolveRowTest(unittest.TestCase):
    def test_the_row_shape_maps_onto_resolve(self):
        found = resolve_row(tagged(1))
        self.assertEqual((found.bpm, found.source, found.approximate, found.folded), (152.0, 'tag', True, True))

    def test_genres_split_on_the_group_concat_separator(self):
        self.assertEqual(split_genres('Hardstyle|Raw Hardstyle||'), ('Hardstyle', 'Raw Hardstyle'))
        self.assertEqual(split_genres(None), ())


class InputsSqlTest(unittest.TestCase):
    def test_the_browse_reads_tracks_only_and_the_table_every_form(self):
        self.assertIn("t.form = 'track'", INDEX_SQL)
        self.assertNotIn('t.form', effective_table.inputs_sql(None))
        self.assertNotIn('{where}', effective_table.inputs_sql(None))

    def test_a_partial_sync_binds_its_ids(self):
        sql = effective_table.inputs_sql([4, 5])
        self.assertIn('AND t.id IN (%s, %s)', sql)
        self.assertEqual(sql, INPUTS_SQL.format(where='\n      AND t.id IN (%s, %s)'))


class DiffTest(unittest.TestCase):
    def test_an_unchanged_row_is_not_written_even_as_decimal_and_tinyint(self):
        existing = {1: effective_table._value(Decimal('150.00'), 'measured', 'high', 0, 0)}  # pylint: disable=protected-access
        upserts, deletes, resolved = effective_table.diff([measured(1)], existing, 0.75)
        self.assertEqual((upserts, deletes, resolved), ([], [], 1))

    def test_a_changed_or_new_row_is_upserted(self):
        existing = {1: (152.0, 'tag', 'low', 1, 1)}
        upserts, deletes, _ = effective_table.diff([measured(1), tagged(2)], existing, 0.75)
        self.assertEqual(upserts, [(1, 150.0, 'measured', 'high', 0, 0), (2, 152.0, 'tag', 'low', 1, 1)])
        self.assertEqual(deletes, [])

    def test_a_track_that_lost_its_tempo_or_its_inputs_is_deleted(self):
        existing = {1: (150.0, 'measured', 'high', 0, 0), 2: (152.0, 'tag', 'low', 1, 1)}
        noise = {'track_id': 1, 'bpm_tag': 0, 'tempo': None, 'measured': None, 'genres': None}
        upserts, deletes, resolved = effective_table.diff([noise], existing, 0.75)
        self.assertEqual((upserts, deletes, resolved), ([], [1, 2], 0))

    def test_the_reliable_confidence_decides_high_or_medium(self):
        upserts, _, _ = effective_table.diff([measured(1, confidence=0.7)], {}, 0.75)
        self.assertEqual(upserts[0][3], 'medium')


class FakeConnection:
    """A connection whose cursors answer from `existing` and `inputs` and record every write."""

    def __init__(self, db):
        self.db = db
        self.closed = False

    def cursor(self, *_args):
        return FakeCursor(self.db)

    def commit(self):
        self.db['commits'] += 1

    def close(self):
        self.closed = True


class FakeCursor:
    """Answers EXISTING_SQL from `existing`, the inputs query from `inputs`, and records writes."""

    def __init__(self, db):
        self.db = db
        self.pending = []

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def execute(self, sql, params=()):
        self.db['statements'].append((sql, list(params)))
        if sql.startswith(effective_table.EXISTING_SQL):
            self.pending = list(self.db['existing'])
        elif 'FROM library_tracks t' in sql:
            self.pending = list(self.db['inputs'])
        else:
            self.pending = []

    def executemany(self, sql, rows):
        self.db['written'].extend(rows)
        self.db['statements'].append((sql, rows))

    def fetchall(self):
        rows, self.pending = self.pending, []
        return rows

    def fetchmany(self, size):
        rows, self.pending = self.pending[:size], self.pending[size:]
        return rows

    def close(self):
        pass


class SyncTest(unittest.TestCase):
    def db(self, existing=(), inputs=()):
        return {'existing': list(existing), 'inputs': list(inputs), 'statements': [], 'written': [], 'commits': 0}

    def test_a_full_sync_upserts_the_difference_and_deletes_the_gone(self):
        db = self.db(
            existing=[
                {
                    'track_id': 1,
                    'bpm': Decimal('150.00'),
                    'source': 'measured',
                    'confidence': 'high',
                    'approximate': 0,
                    'folded': 0,
                },
                {
                    'track_id': 9,
                    'bpm': Decimal('140.00'),
                    'source': 'tag',
                    'confidence': 'low',
                    'approximate': 1,
                    'folded': 0,
                },
            ],
            inputs=[measured(1), tagged(2)],
        )
        result = effective_table.sync(lambda: FakeConnection(db), reliable_confidence=0.75)
        self.assertEqual(result, effective_table.SyncResult(resolved=2, upserted=1, deleted=1))
        self.assertEqual(db['written'], [(2, 152.0, 'tag', 'low', 1, 1)])
        deletes = [(sql, params) for sql, params in db['statements'] if sql.startswith('DELETE')]
        self.assertEqual(deletes, [(f'DELETE FROM {effective_table.TABLE} WHERE track_id IN (%s)', [9])])

    def test_a_sync_that_finds_nothing_changed_writes_nothing(self):
        db = self.db(
            existing=[{'track_id': 1, 'bpm': 150, 'source': 'measured', 'confidence': 'high', 'approximate': 0,
                       'folded': 0}],
            inputs=[measured(1)],
        )  # fmt: skip
        effective_table.sync(lambda: FakeConnection(db))
        self.assertEqual((db['written'], db['commits']), ([], 0))

    def test_a_partial_sync_reads_and_deletes_only_its_tracks(self):
        db = self.db(existing=[], inputs=[measured(3)])
        effective_table.sync(lambda: FakeConnection(db), track_ids=[3, 3, 4])
        reads = [(sql, params) for sql, params in db['statements'] if 'SELECT' in sql]
        self.assertTrue(reads[0][0].endswith('WHERE track_id IN (%s, %s)'))
        self.assertEqual(reads[0][1], [3, 4])
        self.assertEqual(reads[1][1], [3, 4])
        self.assertEqual(db['written'], [(3, 150.0, 'measured', 'high', 0, 0)])

    def test_no_ids_asks_nothing(self):
        connect = MagicMock()
        self.assertEqual(effective_table.sync(connect, track_ids=[]), effective_table.SyncResult(0, 0, 0))
        connect.assert_not_called()

    def test_tuple_rows_from_an_unbuffered_cursor_are_read_by_column(self):
        rows = list(effective_table._stream(_TupleCursor([(5, None, 76.0, None, None, None, None, 'Hardstyle')])))  # pylint: disable=protected-access
        self.assertEqual(rows[0]['track_id'], 5)
        self.assertEqual(rows[0]['genres'], 'Hardstyle')

    def test_a_missing_connection_is_an_error(self):
        with self.assertRaises(RuntimeError):
            effective_table.sync(lambda: None)


class _TupleCursor:
    """An unbuffered cursor stand-in that yields plain tuples, as pymysql's SSCursor does."""

    def __init__(self, rows):
        self.rows = rows

    def fetchmany(self, _size):
        rows, self.rows = self.rows, []
        return rows


if __name__ == '__main__':
    unittest.main()
