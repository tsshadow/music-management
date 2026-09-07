"""What the arrival record captures, and what it refuses to overwrite.

The claim under test is narrow and worth stating: this records the file *as it arrived*,
so the one thing it must never do is let a later pass -- which sees a file the tagger has
already rewritten -- replace an earlier, truer answer.
"""

import json
import re
import unittest
from unittest.mock import MagicMock, patch

from services.tests.connector_fakes import fake_connector
from services.tests.mock_base import setup_mocks

setup_mocks()

from services.tagger import ingestion  # noqa: E402


class FakeTag:
    def __init__(self, values):
        self.values = values

    def to_array(self):
        return self.values


class IngestionTestCase(unittest.TestCase):
    def setUp(self):
        self.connector, self.connection = fake_connector()
        self.cursor = self.connection.cursor.return_value.__enter__.return_value
        self.cursor.rowcount = 1
        patcher = patch.object(ingestion, 'DatabaseConnector', return_value=self.connector)
        patcher.start()
        self.addCleanup(patcher.stop)
        # Cached for the life of the process by design; a test must not inherit another's.
        ingestion._rules_fingerprint = None
        self.addCleanup(setattr, ingestion, '_rules_fingerprint', None)

    def song(self, tags=None, path='/mnt/music/EPs/Texcore/TEX001 - Release/01.mp3'):
        # `tags={}` has to survive as an empty file, not fall back to the default.
        if tags is None:
            tags = {'artist': ['Lil Texas & Albino']}
        song = MagicMock()
        song._path = path
        song.tag_collection.get.return_value = {name: FakeTag(values) for name, values in tags.items()}
        return song

    def written(self):
        for call in self.cursor.execute.call_args_list:
            if 'library_ingestion_records' in call.args[0]:
                return call.args[1]
        return None


class RecordTest(IngestionTestCase):
    def test_the_whole_tag_set_is_stored_as_it_was_read(self):
        song = self.song({'artist': ['Lil Texas & Albino'], 'genre': ['Uptempo Hardcore'], 'date': ['2026']})

        with patch.object(ingestion.os.path, 'getsize', return_value=1234):
            self.assertTrue(ingestion.record(song, 'LABEL'))

        params = self.written()
        stored = json.loads(params[4])
        self.assertEqual(['Lil Texas & Albino'], stored['artist'])
        self.assertEqual(['Uptempo Hardcore'], stored['genre'])
        self.assertEqual(['2026'], stored['date'])

    def test_the_row_says_where_the_file_was_and_what_kind_of_source_it_is(self):
        with patch.object(ingestion.os.path, 'getsize', return_value=1234):
            ingestion.record(self.song(), 'LABEL')

        params = self.written()
        self.assertEqual('/mnt/music/EPs/Texcore/TEX001 - Release/01.mp3', params[0])
        self.assertEqual(1234, params[2])
        self.assertEqual('LABEL', params[3])

    def test_an_earlier_answer_is_never_replaced(self):
        """INSERT IGNORE, keyed on the path hash. A later pass sees a file this tagger
        already rewrote, so its idea of "arrival" is worth less than the first one's."""
        with patch.object(ingestion.os.path, 'getsize', return_value=1234):
            ingestion.record(self.song(), 'LABEL')

        statement = next(
            c.args[0] for c in self.cursor.execute.call_args_list if 'library_ingestion_records' in c.args[0]
        )
        self.assertIn('INSERT IGNORE', statement)
        self.assertNotIn('ON DUPLICATE', statement)

    def test_a_file_with_no_tags_at_all_is_not_recorded(self):
        """The record would say nothing the path does not already say."""
        self.assertFalse(ingestion.record(self.song(tags={}), 'LABEL'))
        self.assertIsNone(self.written())

    def test_a_song_that_never_loaded_is_not_recorded(self):
        """BaseSong returns early on an unreadable file without building a tag_collection."""
        song = MagicMock()
        song._path = '/mnt/music/broken.m4a'
        song.tag_collection = None
        self.assertFalse(ingestion.record(song, 'YOUTUBE'))

    def test_an_unreachable_database_does_not_stop_the_tagging_round(self):
        self.connection.cursor.side_effect = RuntimeError('database gone')
        with patch.object(ingestion.os.path, 'getsize', return_value=1234):
            self.assertFalse(ingestion.record(self.song(), 'LABEL'))  # must not raise

    def test_a_file_whose_size_cannot_be_read_is_still_recorded(self):
        with patch.object(ingestion.os.path, 'getsize', side_effect=OSError('gone')):
            self.assertTrue(ingestion.record(self.song(), 'LABEL'))
        self.assertIsNone(self.written()[2])


class FingerprintTest(IngestionTestCase):
    COUNTS = (12, 3, 477, 49, 88, 7, 640)

    def test_the_rule_tables_are_counted_once_per_process(self):
        """One query per tagging round, not one per file."""
        self.cursor.fetchone.return_value = self.COUNTS

        first = ingestion.rules_fingerprint()
        calls_after_first = self.cursor.execute.call_count
        second = ingestion.rules_fingerprint()

        self.assertEqual(first, second)
        self.assertEqual(calls_after_first, self.cursor.execute.call_count)

    def test_a_different_ruleset_gets_a_different_fingerprint(self):
        self.cursor.fetchone.return_value = self.COUNTS
        first = ingestion.rules_fingerprint()
        self.cursor.fetchone.return_value = (13, *self.COUNTS[1:])
        second = ingestion.rules_fingerprint(refresh=True)

        self.assertNotEqual(first, second)

    def test_a_change_in_any_table_moves_the_fingerprint(self):
        """A digest that only reacted to the first column would be worse than none."""
        self.cursor.fetchone.return_value = self.COUNTS
        base = ingestion.rules_fingerprint()
        for index in range(len(self.COUNTS)):
            changed = list(self.COUNTS)
            changed[index] += 1
            self.cursor.fetchone.return_value = tuple(changed)
            self.assertNotEqual(base, ingestion.rules_fingerprint(refresh=True), ingestion.RULE_TABLES[index])

    def test_an_unreachable_database_is_a_fingerprint_of_its_own(self):
        self.connection.cursor.side_effect = RuntimeError('database gone')
        self.assertEqual('unknown', ingestion.rules_fingerprint())

    def test_a_query_that_comes_back_empty_is_not_fingerprinted(self):
        """Better than a digest built on nothing, which would compare equal to itself
        across two different rulesets."""
        self.cursor.fetchone.return_value = None
        self.assertEqual('unknown', ingestion.rules_fingerprint())


class RulesFingerprintQueryTest(unittest.TestCase):
    """The query is written out rather than built from RULE_TABLES.

    That is deliberate -- a formatted SQL string is a shape `security:sast` flags on
    sight, and accepting it into the baseline would leave a permanent entry for a query
    that needs no interpolation. The cost is that the two can drift, and the fingerprint
    would then label its counts with the wrong table names. This is what stops that.
    """

    def test_every_rule_table_is_counted_by_the_query(self):
        for table in ingestion.RULE_TABLES:
            self.assertIn(f'FROM {table})', ingestion.RULE_COUNT_QUERY)

    def test_the_query_counts_nothing_the_table_list_does_not_name(self):
        counted = re.findall(r'FROM (\w+)\)', ingestion.RULE_COUNT_QUERY)
        self.assertEqual(list(ingestion.RULE_TABLES), counted)

    def test_the_query_carries_no_interpolation(self):
        self.assertNotIn('{', ingestion.RULE_COUNT_QUERY)


if __name__ == '__main__':
    unittest.main()
