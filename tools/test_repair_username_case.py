"""tools/repair_username_case.py: the plan it prints and the merge it applies.

The LMS half runs against a real in-memory SQLite shaped like the production fork
(bug report 074): user 1 `user` linked to MuMa, user 13 `User` created by the login.
The MuMa half runs against a fake cursor, since what matters there is which rows the
statements select, not MariaDB itself.
"""

import os
import sqlite3
import tempfile
import unittest

from tools import repair_username_case as repair


def lms_fixture():
    """An lms.db with the user-owned tables the repair has to find by itself."""
    conn = sqlite3.connect(':memory:')
    conn.executescript(
        """
        CREATE TABLE user (id INTEGER PRIMARY KEY, login_name TEXT, type INTEGER, muma_id INTEGER);
        CREATE TABLE listen (id INTEGER PRIMARY KEY, date_time TEXT, track_id INTEGER,
            user_id INTEGER REFERENCES user(id) ON DELETE CASCADE);
        CREATE TABLE rated_track (id INTEGER PRIMARY KEY, rating INTEGER, track_id INTEGER,
            user_id INTEGER REFERENCES user(id) ON DELETE CASCADE);
        CREATE TABLE starred_track (id INTEGER PRIMARY KEY, backend INTEGER, track_id INTEGER,
            user_id INTEGER REFERENCES user(id) ON DELETE CASCADE);
        CREATE TABLE playqueue (id INTEGER PRIMARY KEY, name TEXT,
            user_id INTEGER REFERENCES user(id) ON DELETE CASCADE);
        CREATE TABLE tracklist (id INTEGER PRIMARY KEY, name TEXT,
            user_id INTEGER REFERENCES user(id) ON DELETE CASCADE);
        CREATE TABLE auth_token (id INTEGER PRIMARY KEY, value TEXT, user_id INTEGER);
        CREATE TABLE track (id INTEGER PRIMARY KEY, name TEXT);

        INSERT INTO user VALUES (1, 'user', 1, 1), (13, 'User', 0, NULL), (2, 'anna', 0, 2);
        INSERT INTO listen (date_time, track_id, user_id) VALUES
            ('2026-09-24', 1, 1), ('2026-09-25', 2, 13), ('2026-09-25', 3, 13), ('2026-09-25', 4, 2);
        INSERT INTO rated_track (rating, track_id, user_id) VALUES (3, 7, 1), (5, 7, 13), (4, 8, 13);
        INSERT INTO starred_track (backend, track_id, user_id) VALUES (0, 9, 13);
        INSERT INTO playqueue (name, user_id) VALUES ('current', 1), ('current', 13);
        INSERT INTO tracklist (name, user_id) VALUES ('mine', 13);
        INSERT INTO auth_token (value, user_id) VALUES ('t', 13);
        """
    )
    return conn


class LmsPlanTest(unittest.TestCase):
    def test_every_table_with_a_user_id_is_found_from_the_schema(self):
        self.assertEqual(
            repair.lms_user_tables(lms_fixture()),
            ['auth_token', 'listen', 'playqueue', 'rated_track', 'starred_track', 'tracklist'],
        )

    def test_the_fork_folds_into_the_muma_linked_user(self):
        (merge,) = repair.plan_lms(lms_fixture(), ['user', 'anna'])
        self.assertEqual((merge.variant_id, merge.canonical_id, merge.target_login), (13, 1, 'user'))
        self.assertEqual(
            merge.rows,
            {'auth_token': 1, 'listen': 2, 'playqueue': 1, 'rated_track': 2, 'starred_track': 1, 'tracklist': 1},
        )
        # The variant's newer rating of track 7 and its play queue replace the canonical user's.
        self.assertEqual(merge.replaced, {'rated_track': 1, 'playqueue': 1})

    def test_without_a_link_the_muma_spelling_then_the_oldest_wins(self):
        conn = lms_fixture()
        conn.execute('UPDATE user SET muma_id = NULL')
        conn.execute("UPDATE user SET login_name = 'USER' WHERE id = 1")
        (merge,) = repair.plan_lms(conn, ['User'])
        self.assertEqual((merge.canonical_id, merge.variant_id), (13, 1))

    def test_nothing_to_merge_is_an_empty_plan(self):
        conn = lms_fixture()
        conn.execute('DELETE FROM user WHERE id = 13')
        self.assertEqual(repair.plan_lms(conn, ['user']), [])


class LmsApplyTest(unittest.TestCase):
    def test_the_merge_moves_everything_and_deletes_the_fork(self):
        conn = lms_fixture()
        repair.apply_lms(conn, repair.plan_lms(conn, ['user', 'anna']))

        self.assertEqual(
            conn.execute('SELECT id, login_name, muma_id FROM user ORDER BY id').fetchall(),
            [(1, 'user', 1), (2, 'anna', 2)],
        )
        for table in repair.lms_user_tables(conn):
            self.assertEqual(conn.execute(f'SELECT COUNT(*) FROM {table} WHERE user_id = 13').fetchone()[0], 0, table)
        self.assertEqual(conn.execute('SELECT COUNT(*) FROM listen WHERE user_id = 1').fetchone()[0], 3)
        self.assertEqual(
            conn.execute('SELECT track_id, rating FROM rated_track WHERE user_id = 1 ORDER BY track_id').fetchall(),
            [(7, 5), (8, 4)],
        )
        self.assertEqual(conn.execute('SELECT COUNT(*) FROM playqueue WHERE user_id = 1').fetchone()[0], 1)
        self.assertEqual(conn.execute('SELECT COUNT(*) FROM listen WHERE user_id = 2').fetchone()[0], 1)

    def test_a_second_run_finds_nothing(self):
        conn = lms_fixture()
        repair.apply_lms(conn, repair.plan_lms(conn, ['user']))
        self.assertEqual(repair.plan_lms(conn, ['user']), [])

    def test_a_failure_leaves_the_database_untouched(self):
        conn = lms_fixture()
        merges = repair.plan_lms(conn, ['user'])
        # The last step of the merge fails: everything before it must roll back with it.
        conn.execute("CREATE TRIGGER refuse BEFORE DELETE ON user BEGIN SELECT RAISE(ABORT, 'no'); END")
        with self.assertRaises(sqlite3.DatabaseError):
            repair.apply_lms(conn, merges)
        self.assertEqual(conn.execute('SELECT COUNT(*) FROM listen WHERE user_id = 13').fetchone()[0], 2)
        self.assertEqual(conn.execute('SELECT rating FROM rated_track WHERE user_id = 1').fetchall(), [(3,)])

    def test_the_backup_is_a_full_copy(self):
        conn = lms_fixture()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'lms.db.bak')
            repair.backup_lms(conn, path)
            copy = sqlite3.connect(path)
            try:
                self.assertEqual(copy.execute('SELECT COUNT(*) FROM user').fetchone()[0], 3)
            finally:
                copy.close()


class FakeMumaCursor:
    """Answers the planner's queries from a table of rows, comparing names the way MariaDB does."""

    def __init__(self, accounts, tables):
        self.accounts = accounts
        self.tables = tables  # table -> list of usernames
        self.result = []
        self.executed = []

    def execute(self, sql, params=()):
        self.executed.append((sql, params))
        if sql.startswith('SELECT username FROM users'):
            self.result = [{'username': a} for a in self.accounts]
        elif 'information_schema.columns' in sql:
            self.result = [{'name': t} for t in sorted(self.tables)]
        elif sql.startswith('SELECT username, COUNT(*)'):
            table = sql.split('`')[1]
            account = params[0]
            counts = {}
            for name in self.tables[table]:
                if name.lower() == account.lower() and name != account:
                    counts[name] = counts.get(name, 0) + 1
            self.result = [{'username': n, 'n': c} for n, c in counts.items()]
        else:
            self.result = []

    def fetchall(self):
        return self.result

    def fetchone(self):
        return self.result[0] if self.result else None


class MumaPlanTest(unittest.TestCase):
    def test_variants_are_found_in_every_username_table(self):
        cursor = FakeMumaCursor(
            ['user', 'anna'],
            {
                'scrobble_listens': ['user', 'User', 'User', 'anna'],
                'scrobble_unmatched_listens': ['USER'],
                'rating_tracks': ['user'],
            },
        )
        rewrites = repair.plan_muma(cursor)
        self.assertEqual(
            [(r.table, r.username, r.variants) for r in rewrites],
            [
                ('scrobble_listens', 'user', {'User': 2}),
                ('scrobble_unmatched_listens', 'user', {'USER': 1}),
            ],
        )
        self.assertEqual(sum(r.rows for r in rewrites), 3)

    def test_the_rewrite_statement_selects_only_exact_mismatches(self):
        sql = repair._variant_condition()
        self.assertIn('LOWER(username) = LOWER(%s)', sql)
        self.assertIn('BINARY username <> BINARY %s', sql)

    def test_the_plan_reads_nothing_when_all_is_canonical(self):
        cursor = FakeMumaCursor(['user'], {'scrobble_listens': ['user']})
        self.assertEqual(repair.plan_muma(cursor), [])

    def test_the_description_names_counts_and_never_more(self):
        text = repair.describe(
            [repair.MumaRewrite('scrobble_listens', 'user', {'User': 31})],
            repair.plan_lms(lms_fixture(), ['user']),
        )
        self.assertIn("scrobble_listens", text)
        self.assertIn("'User': 31", text)
        self.assertIn("user 13 'User' -> user 1 'user'", text)
        self.assertIn('replaces 1 of the canonical user', text)


class MumaApplyTest(unittest.TestCase):
    def test_leftovers_a_unique_key_refused_are_reported_not_deleted(self):
        executed = []

        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def execute(self, sql, params=()):
                executed.append(sql)

            def fetchone(self):
                return {'n': 2}

        class Conn:
            committed = False

            def cursor(self):
                return Cursor()

            def commit(self):
                Conn.committed = True

        leftovers = repair.apply_muma(Conn(), [repair.MumaRewrite('scrobble_listens', 'user', {'User': 5})])
        self.assertEqual(leftovers, {'scrobble_listens': 2})
        self.assertTrue(Conn.committed)
        self.assertTrue(executed[0].startswith('UPDATE IGNORE `scrobble_listens`'))
        self.assertFalse([s for s in executed if s.startswith('DELETE')])


if __name__ == '__main__':
    unittest.main()
