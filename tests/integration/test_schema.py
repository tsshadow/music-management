"""The schema this project ships can actually be built, and rebuilt.

Nothing else in the suite checks this: the unit tests mock the cursor, so a
CREATE TABLE that MariaDB rejects, or a migrate_*.sql that only works on a
database that has already been migrated, would go unnoticed until a deploy.
"""

import contextlib

import pytest

from tests.integration import schema_sources
from tests.integration.conftest import ROOT, _apply_migrations, _split_statements

pytestmark = pytest.mark.integration

# Every table the code or a migration declares, read from their CREATE TABLE
# statements. This used to be a hand-kept list, and some twenty tables -- channels,
# the feed snapshot, radio, news, the festival and podcast rules, the downloader's
# own tables -- never made it onto it. See tests/integration/schema_sources.py.
EXPECTED_TABLES = schema_sources.declared_tables()


def table_names(connection):
    with connection.cursor() as cursor:
        cursor.execute('SHOW TABLES')
        return {next(iter(row.values())) for row in cursor.fetchall()}


def test_every_table_the_code_reads_exists(built_schemas):
    """Checked against a schema built from nothing by the code alone, the way a fresh
    stack gets it -- not against the session database, which also ran every migration
    and so would hide a table that only a migration creates."""
    assert len(EXPECTED_TABLES) > 60, 'the CREATE TABLE extraction found suspiciously little'
    missing = EXPECTED_TABLES - set(built_schemas['code'])
    assert not missing, f'schema bootstrap does not create: {sorted(missing)}'


def test_the_migration_ledger_is_an_expected_table():
    """schema_migrations is the deploy's ledger (tools/apply_migrations.py, bug report 068):
    db_init creates it, migrate_v39 declares it, and a deployed stack must have it."""
    assert 'schema_migrations' in EXPECTED_TABLES
    assert 'schema_migrations' in schema_sources.code_declared_tables()
    assert 'schema_migrations' in schema_sources.migration_declared_tables()


def test_the_migrations_are_re_runnable(database):
    """scripts/deploy.sh applies every migrate_*.sql on each deploy, so the
    second run must be a no-op rather than an error."""
    _apply_migrations(database)
    _apply_migrations(database)


def test_every_migration_parses_into_statements():
    migrations = sorted(ROOT.glob('migrate_*.sql'))
    assert migrations, 'no migrate_*.sql found; the deploy applies these'
    for migration in migrations:
        statements = _split_statements(migration.read_text(encoding='utf-8'))
        assert statements, f'{migration.name} contains no statements'


def test_the_curated_genre_columns_survived_the_migrations(database):
    """migrate_v3 introduces the white/black/unknown model the tagger depends on."""
    with database.cursor() as cursor:
        cursor.execute('SHOW COLUMNS FROM rules_genres')
        columns = {row['Field'] for row in cursor.fetchall()}
    assert {'state', 'canonical_id', 'occurrences', 'decided_at', 'decided_by'} <= columns


def test_a_label_can_be_identified_and_filed_under_a_parent(database):
    """migrate_v13 gives library_labels the columns the label edit page writes."""
    with database.cursor() as cursor:
        cursor.execute('SHOW COLUMNS FROM library_labels')
        columns = {row['Field'] for row in cursor.fetchall()}
    assert {'mbid', 'parent_label_id'} <= columns


def test_a_listenbrainz_import_records_where_it_stopped(database):
    """migrate_v35 gives scrobble_imports the resume point a truncated import continues from."""
    with database.cursor() as cursor:
        cursor.execute('SHOW COLUMNS FROM scrobble_imports')
        columns = {row['Field'] for row in cursor.fetchall()}
    assert 'oldest_listened_ts' in columns


def test_the_song_key_compares_byte_for_byte(database):
    """migrate_v19: utf8mb4_general_ci gives every character outside the BMP the same
    weight, so two work keys of equal length built from such characters compare equal
    and the UNIQUE index merges two unrelated songs into one work."""
    with database.cursor() as cursor:
        cursor.execute(
            'SELECT collation_name FROM information_schema.columns '
            'WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s',
            ('library_works', 'work_key'),
        )
        assert cursor.fetchone()['collation_name'] == 'utf8mb4_bin'

        # The comparison the collation decides, rather than its name.
        cursor.execute('DELETE FROM library_works')
        cursor.execute('INSERT INTO library_works (work_key, title) VALUES (%s, %s)', ('𝙁𝙍𝘼𝙉𝙏𝙄𝘾:::a', 'one'))
        cursor.execute('INSERT INTO library_works (work_key, title) VALUES (%s, %s)', ('𝗕𝗔𝗗𝗞𝗜𝗖𝗞:::a', 'two'))
        cursor.execute('SELECT COUNT(*) AS n FROM library_works')
        assert cursor.fetchone()['n'] == 2
        cursor.execute('DELETE FROM library_works')
    database.commit()


def test_a_rule_records_who_wrote_it(database):
    """Without created_by a hand-made rule and a generated one are indistinguishable."""
    with database.cursor() as cursor:
        for table in ('rules_artist_genres', 'rules_label_genres'):
            cursor.execute(f'SHOW COLUMNS FROM {table}')
            columns = {row['Field'] for row in cursor.fetchall()}
            assert 'created_by' in columns, f'{table} cannot record who wrote a rule'


def test_a_subgenre_cannot_be_filed_under_the_same_parent_twice(db):
    """The edit page deletes one row per parent, so a duplicate pair would resurrect it."""
    import pymysql

    with db.cursor() as cursor:
        cursor.execute(
            "INSERT INTO rules_subgenre_hierarchy (subgenre, genre) VALUES ('Industrial Hardcore', 'Hardcore')"
        )
        with pytest.raises(pymysql.err.IntegrityError):
            cursor.execute(
                "INSERT INTO rules_subgenre_hierarchy (subgenre, genre) VALUES ('Industrial Hardcore', 'Hardcore')"
            )


def test_a_genre_can_expand_into_several_others(db):
    """migrate_v4's expansion table, exercised the way management.py writes it."""
    with db.cursor() as cursor:
        cursor.execute(
            "INSERT INTO rules_genres (name, normalized_name, state) VALUES ('Upterror', 'upterror', 'black')"
        )
        source = cursor.lastrowid
        cursor.execute(
            "INSERT INTO rules_genres (name, normalized_name, state) VALUES ('Uptempo Hardcore', 'uptempo hardcore', 'white')"
        )
        first = cursor.lastrowid
        cursor.execute("INSERT INTO rules_genres (name, normalized_name, state) VALUES ('Terror', 'terror', 'white')")
        second = cursor.lastrowid
        cursor.executemany(
            'INSERT INTO rules_genre_expansions (genre_id, target_id, position) VALUES (%s, %s, %s)',
            [(source, first, 0), (source, second, 1)],
        )
        cursor.execute(
            'SELECT t.name FROM rules_genre_expansions e JOIN rules_genres t ON t.id = e.target_id '
            'WHERE e.genre_id = %s ORDER BY e.position',
            (source,),
        )
        assert [row['name'] for row in cursor.fetchall()] == ['Uptempo Hardcore', 'Terror']


def test_deleting_a_track_takes_its_join_rows_with_it(db):
    """The FK cascades are what keep the library tables consistent."""
    with db.cursor() as cursor:
        cursor.execute("INSERT INTO library_artists (name) VALUES ('Angerfist')")
        artist = cursor.lastrowid
        cursor.execute(
            "INSERT INTO library_tracks (track_uid, title, primary_artist_id) VALUES ('uid-1', 'Raise Your Fist', %s)",
            (artist,),
        )
        track = cursor.lastrowid
        cursor.execute(
            "INSERT INTO library_track_artists (track_id, artist_id, role, position) VALUES (%s, %s, 'primary', 0)",
            (track, artist),
        )
        cursor.execute('DELETE FROM library_tracks WHERE id = %s', (track,))
        cursor.execute('SELECT COUNT(*) AS n FROM library_track_artists WHERE track_id = %s', (track,))
        assert cursor.fetchone()['n'] == 0


def test_a_genre_name_is_unique_after_normalization(db):
    """rules_genres.normalized_name is the key the tagger dedupes on."""
    import pymysql

    with db.cursor() as cursor:
        cursor.execute("INSERT INTO rules_genres (name, normalized_name) VALUES ('Hardcore', 'hardcore')")
        with pytest.raises(pymysql.err.IntegrityError):
            cursor.execute("INSERT INTO rules_genres (name, normalized_name) VALUES ('HARDCORE', 'hardcore')")


def test_an_account_name_is_unique_whatever_its_case(db):
    """users.username refuses a case variant of an existing name.

    Account names are case-insensitive (services/music_manager/identity.py, bug report 074);
    the application refuses the variant with a 409 before the INSERT, and this is the
    database backing it up through the column's case-insensitive collation.
    """
    import pymysql

    with db.cursor() as cursor:
        cursor.execute("INSERT INTO users (username, api_key) VALUES ('user', 'k1')")
        with pytest.raises(pymysql.err.IntegrityError):
            cursor.execute("INSERT INTO users (username, api_key) VALUES ('Teun', 'k2')")
        cursor.execute("SELECT username FROM users WHERE LOWER(username) = LOWER('TEUN')")
        assert [row['username'] for row in cursor.fetchall()] == ['user']


def test_a_blind_image_verdict_is_undone_but_a_real_one_survives(database):
    """migrate_v32: migrate_v30 asked "has any portrait landed since the blackout?" once, for
    the whole table, and 22 hand-fetched ones answered yes before it first ran -- so 45.044
    artists kept a `failed` a fetcher without credentials had written for them."""
    with database.cursor() as cursor:
        cursor.execute("INSERT INTO library_artists (name) VALUES ('Blind Verdict')")
        blind_id = cursor.lastrowid
        cursor.execute("INSERT INTO library_artists (name) VALUES ('Real Verdict')")
        real_id = cursor.lastrowid
        cursor.execute("INSERT INTO library_artists (name) VALUES ('Older Verdict')")
        older_id = cursor.lastrowid
        # One portrait from a provider closes the window at the moment it landed.
        cursor.execute(
            "INSERT INTO library_artist_images (artist_id, source, created_at) "
            "VALUES (%s, 'spotify', '2026-09-21 12:56:40')",
            (blind_id,),
        )
        cursor.execute(
            "UPDATE library_artists SET image_status = 'failed', image_updated_at = %s, "
            'primary_image_id = NULL WHERE id = %s',
            ('2026-08-23 04:00:00', blind_id),
        )
        cursor.execute(
            "UPDATE library_artists SET image_status = 'failed', image_updated_at = %s, "
            'primary_image_id = NULL WHERE id = %s',
            ('2026-09-22 09:00:00', real_id),
        )
        cursor.execute(
            "UPDATE library_artists SET image_status = 'failed', image_updated_at = %s, "
            'primary_image_id = NULL WHERE id = %s',
            ('2026-07-01 09:00:00', older_id),
        )

    _apply_migrations(database)

    with database.cursor() as cursor:
        cursor.execute(
            'SELECT id, image_status FROM library_artists WHERE id IN (%s, %s, %s)',
            (blind_id, real_id, older_id),
        )
        status = {row['id']: row['image_status'] for row in cursor.fetchall()}
    assert status[blind_id] is None, 'a verdict written while the fetcher was blind must be undone'
    assert status[real_id] == 'failed', 'a verdict written after sight returned is real'
    assert status[older_id] == 'failed', 'a verdict from before the blackout was never blind'


def test_the_tagger_stores_the_mtime_it_read(database):
    """migrate_v29: a FLOAT mtime has a 128 s step at today's epoch, so the value written
    back was never the real one and 70% of the library read as changed on every walk."""
    with database.cursor() as cursor:
        cursor.execute(
            'SELECT data_type FROM information_schema.columns '
            'WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s',
            ('tagger_processed_files', 'mtime'),
        )
        assert cursor.fetchone()['data_type'] == 'double'


LISTEN_TABLES = ('scrobble_listens', 'scrobble_unmatched_listens')


def _listened_at_extra(connection, table):
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT extra AS extra FROM information_schema.columns '
            "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = 'listened_at'",
            (table,),
        )
        return (cursor.fetchone()['extra'] or '').lower()


def test_listened_at_is_never_rewritten_by_an_update(database):
    """docs/bug-reports/039: without an explicit DEFAULT, MariaDB < 10.10 gives the first
    TIMESTAMP column ON UPDATE CURRENT_TIMESTAMP, and every UPDATE of a listen moved it."""
    for table in LISTEN_TABLES:
        assert 'on update' not in _listened_at_extra(database, table), table


@contextlib.contextmanager
def _listen_tables_created_the_old_way(connection):
    """Give both listened_at columns the ON UPDATE production's 10.6-era tables carry,
    and put back exactly what was there afterwards, so no other test is masked."""
    before = {table: _listened_at_extra(connection, table) for table in LISTEN_TABLES}
    try:
        with connection.cursor() as cursor:
            for table in LISTEN_TABLES:
                cursor.execute(
                    f'ALTER TABLE {table} MODIFY listened_at TIMESTAMP NOT NULL '
                    'DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'
                )
        assert all('on update' in _listened_at_extra(connection, table) for table in LISTEN_TABLES)
        yield
    finally:
        with connection.cursor() as cursor:
            for table in LISTEN_TABLES:
                on_update = ' ON UPDATE CURRENT_TIMESTAMP' if 'on update' in before[table] else ''
                cursor.execute(
                    f'ALTER TABLE {table} MODIFY listened_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP{on_update}'
                )


def test_migrate_v33_repairs_a_table_created_the_old_way(database):
    """The CREATE fix alone never reaches production's existing tables; the migration
    has to -- and twice in a row, as every deploy reapplies it."""
    with _listen_tables_created_the_old_way(database):
        _apply_migrations(database)
        _apply_migrations(database)

        for table in LISTEN_TABLES:
            assert 'on update' not in _listened_at_extra(database, table), table


def test_start_up_repairs_a_table_created_the_old_way(database):
    """A stack that never runs the migrations gets the same repair from init_db."""
    from services.music_manager.routers import scrobbler

    with _listen_tables_created_the_old_way(database):
        with database.cursor() as cursor:
            scrobbler.init_db(cursor)

        for table in LISTEN_TABLES:
            assert 'on update' not in _listened_at_extra(database, table), table


def _index_columns(connection, table, index):
    with connection.cursor() as cursor:
        cursor.execute(f'SHOW INDEX FROM {table} WHERE Key_name = %s', (index,))
        return [row['Column_name'] for row in sorted(cursor.fetchall(), key=lambda r: r['Seq_in_index'])]


def test_the_join_columns_are_indexed(database):
    """Every artist join goes through library_tracks.primary_artist_id and every per-track
    listen question through scrobble_listens.track_id; neither was indexed (migrate_v34)."""
    assert _index_columns(database, 'library_tracks', 'idx_tracks_primary_artist') == ['primary_artist_id']
    assert _index_columns(database, 'scrobble_listens', 'idx_listens_track_user') == ['track_id', 'username']


def test_the_importer_skips_an_unchanged_proposal_against_real_mariadb(db):
    """migrate_v38: the fingerprint is written whatever the status, and the rules version the
    mover compares against moves when a catalogue rule is added or its label edited."""
    from services.importer.label_proposal_store import KNOWN_QUERY, RECORD_QUERY, RULES_VERSION_QUERY

    def rules_version(cursor):
        cursor.execute(RULES_VERSION_QUERY)
        return tuple(cursor.fetchone().values())

    with db.cursor() as cursor:
        empty = rules_version(cursor)
        cursor.execute("INSERT INTO rules_catid_label (catid, label) VALUES ('SCAN', 'Scantraxx')")
        added = rules_version(cursor)
        cursor.execute("UPDATE rules_catid_label SET label = 'Scantraxx Records' WHERE catid = 'SCAN'")
        edited = rules_version(cursor)
        assert len({empty, added, edited}) == 3

        cursor.execute(RECORD_QUERY, ('NOPE123 - Release', 'NOPE', None, 'none', 0, 'a' * 64))
        cursor.execute("UPDATE rules_label_proposals SET status = 'rejected', decided_at = NOW()")
        cursor.execute(RECORD_QUERY, ('NOPE123 - Release', 'NOPE', 'Other', 'tag:label', 90, 'b' * 64))
        cursor.execute(KNOWN_QUERY)
        row = cursor.fetchone()
    assert row['status'] == 'rejected'
    assert row['resolved_fingerprint'] == 'b' * 64
    assert row['decided_at'] is not None
