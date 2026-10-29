"""Tests for services/common/db_seeds.py: the statement splitter and the seed order."""

import re
import unittest
from unittest import mock

from services.common import db_seeds
from services.common.db_seeds import SEED_FILES, SEEDS_DIR, seed, split_statements


class SplitStatementsTest(unittest.TestCase):
    """The splitter cuts on a statement-level `;` only."""

    def test_splits_on_semicolons_and_drops_empty_statements(self):
        self.assertEqual(split_statements('SELECT 1;\n\nSELECT 2;;\n'), ['SELECT 1', 'SELECT 2'])

    def test_keeps_a_last_statement_without_a_semicolon(self):
        self.assertEqual(split_statements('SELECT 1; SELECT 2'), ['SELECT 1', 'SELECT 2'])

    def test_a_semicolon_inside_a_single_quoted_string_does_not_split(self):
        self.assertEqual(
            split_statements("INSERT INTO t VALUES ('a;b'); SELECT 1"), ["INSERT INTO t VALUES ('a;b')", 'SELECT 1']
        )

    def test_a_doubled_quote_stays_inside_the_string(self):
        sql = "INSERT INTO t VALUES ('Peacock''s; Exclusives'); SELECT 2"
        self.assertEqual(split_statements(sql), ["INSERT INTO t VALUES ('Peacock''s; Exclusives')", 'SELECT 2'])

    def test_a_backslash_escaped_quote_stays_inside_the_string(self):
        sql = "INSERT INTO t VALUES ('it\\'s; here'); SELECT 3"
        self.assertEqual(split_statements(sql), ["INSERT INTO t VALUES ('it\\'s; here')", 'SELECT 3'])

    def test_a_single_quote_inside_a_double_quoted_string_does_not_open_a_string(self):
        sql = 'INSERT INTO t VALUES ("We Love The 90\'s; Festival"); SELECT 4'
        self.assertEqual(split_statements(sql), ['INSERT INTO t VALUES ("We Love The 90\'s; Festival")', 'SELECT 4'])

    def test_a_backtick_identifier_may_hold_a_semicolon(self):
        self.assertEqual(split_statements('SELECT `a;b` FROM t; SELECT 5'), ['SELECT `a;b` FROM t', 'SELECT 5'])

    def test_line_comments_are_dropped_with_their_semicolons_and_quotes(self):
        sql = "-- a comment; with ' a quote\nSELECT 1; -- trailing; comment\n-- another\nSELECT 2;"
        self.assertEqual(split_statements(sql), ['SELECT 1', 'SELECT 2'])

    def test_a_comment_inside_a_values_list_is_dropped(self):
        sql = "INSERT INTO t VALUES\n    ('a'),\n    -- the halves; of it\n    ('b');"
        self.assertEqual(split_statements(sql), ["INSERT INTO t VALUES\n    ('a'),\n    \n    ('b')"])

    def test_two_dashes_without_a_space_are_not_a_comment(self):
        self.assertEqual(split_statements('SELECT 1--1; SELECT 2'), ['SELECT 1--1', 'SELECT 2'])

    def test_dashes_inside_a_string_are_not_a_comment(self):
        self.assertEqual(split_statements("SELECT '-- no; comment'; SELECT 3"), ["SELECT '-- no; comment'", 'SELECT 3'])

    def test_block_comments_are_dropped(self):
        self.assertEqual(split_statements('SELECT /* x; y */ 1; SELECT 2'), ['SELECT   1', 'SELECT 2'])

    def test_a_file_of_only_comments_has_no_statements(self):
        self.assertEqual(split_statements('-- one\n--\n-- two;\n'), [])


class SeedFilesTest(unittest.TestCase):
    """The seed files themselves: present, parseable and idempotent by construction."""

    def test_every_listed_file_exists_and_every_file_is_listed(self):
        on_disk = sorted(path.name for path in SEEDS_DIR.glob('*.sql'))
        self.assertEqual(sorted(SEED_FILES), on_disk)

    def test_rules_ignored_artists_is_seeded_before_rules_artists_copies_it(self):
        self.assertLess(SEED_FILES.index('rules_ignored_artists.sql'), SEED_FILES.index('rules_artists.sql'))

    def test_every_insert_into_a_real_table_is_idempotent(self):
        for name in SEED_FILES:
            for statement in db_seeds.seed_statements(name):
                match = re.match(r'INSERT\s+(IGNORE\s+)?INTO\s+(\w+)', statement, re.IGNORECASE)
                if not match or match.group(2).startswith(('_', 'tmp_')):
                    continue
                with self.subTest(file=name, table=match.group(2)):
                    self.assertTrue(
                        match.group(1) or re.search(r'WHERE\s+existing\.\w+\s+IS\s+NULL', statement),
                        'an INSERT into a real table must be INSERT IGNORE or an anti-join',
                    )

    def test_no_seed_file_alters_or_deletes(self):
        for name in SEED_FILES:
            for statement in db_seeds.seed_statements(name):
                with self.subTest(file=name, statement=statement[:60]):
                    self.assertNotRegex(statement, r'^\s*(ALTER|DELETE|UPDATE|TRUNCATE)\b')
                    if re.match(r'^\s*(CREATE|DROP)\b', statement, re.IGNORECASE):
                        self.assertRegex(statement, r'^\s*(CREATE|DROP)\s+TEMPORARY\s+TABLE\b')


class SeedTest(unittest.TestCase):
    """seed() runs every file's statements, in SEED_FILES order, on the one cursor."""

    def test_runs_every_statement_of_every_file_in_order(self):
        files = {
            'b.sql': 'INSERT IGNORE INTO b VALUES (1); INSERT IGNORE INTO b VALUES (2);',
            'a.sql': '-- only\nSELECT 1;',
        }
        cursor = mock.Mock()
        with (
            mock.patch.object(db_seeds, 'SEED_FILES', ('b.sql', 'a.sql')),
            mock.patch.object(db_seeds, 'seed_statements', side_effect=lambda name: split_statements(files[name])),
        ):
            seed(cursor)

        self.assertEqual(
            [call.args[0] for call in cursor.execute.call_args_list],
            ['INSERT IGNORE INTO b VALUES (1)', 'INSERT IGNORE INTO b VALUES (2)', 'SELECT 1'],
        )

    def test_the_real_files_run_in_the_listed_order(self):
        cursor = mock.Mock()
        seed(cursor)

        executed = [call.args[0] for call in cursor.execute.call_args_list]
        expected = [statement for name in SEED_FILES for statement in db_seeds.seed_statements(name)]
        self.assertEqual(executed, expected)
        first_insert_per_table = [
            re.search(r'INSERT\s+(?:IGNORE\s+)?INTO\s+(rules_\w+)', statement).group(1)
            for statement in executed
            if re.search(r'INSERT\s+(?:IGNORE\s+)?INTO\s+rules_', statement)
        ]
        tables = list(dict.fromkeys(first_insert_per_table))
        self.assertEqual(
            tables,
            [
                'rules_genres',
                'rules_festivals',
                'rules_festival_aliases',
                'rules_label_name_choices',
                'rules_ignored_artists',
                'rules_artists',
                'rules_scene_group_date_format',
            ],
        )

    def test_a_failing_statement_stops_the_seed(self):
        cursor = mock.Mock()
        cursor.execute.side_effect = RuntimeError('boom')

        with self.assertRaises(RuntimeError):
            seed(cursor)
        self.assertEqual(cursor.execute.call_count, 1)


if __name__ == '__main__':
    unittest.main()
