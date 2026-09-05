"""The schema this project ships can actually be built, and rebuilt.

Nothing else in the suite checks this: the unit tests mock the cursor, so a
CREATE TABLE that MariaDB rejects, or a migrate_*.sql that only works on a
database that has already been migrated, would go unnoticed until a deploy.
"""

import pytest

from tests.integration.conftest import ROOT, _apply_migrations, _split_statements

pytestmark = pytest.mark.integration

# Tables the running code selects from. If one is missing, some endpoint 500s.
EXPECTED_TABLES = {
    'users',
    'user_identities',
    'user_refresh_tokens',
    'user_requests',
    'user_app_settings',
    'user_listenbrainz_accounts',
    'dynamic_playlists',
    'roles',
    'permissions',
    'role_permissions',
    'audit_events',
    'library_artists',
    'library_labels',
    'library_tracks',
    'library_media_files',
    'library_works',
    'library_track_artists',
    'library_track_genres',
    'library_track_labels',
    'library_track_audio_features',
    'library_track_ml_labels',
    'library_artist_images',
    'artist_external_ids',
    'label_external_ids',
    'rules_genres',
    'rules_genre_expansions',
    'rules_artist_genres',
    'rules_label_genres',
    'rules_catid_label',
    'rules_label_proposals',
    'rules_ignored_artists',
    'rules_ignored_genres',
    'rules_subgenre_hierarchy',
    'rules_genre_backlog',
    'downloads_soundcloud_accounts',
    'downloads_soundcloud_archive',
    'downloads_youtube_accounts',
    'downloads_youtube_archive',
    'scrobble_listens',
    'scrobble_unmatched_listens',
    'scrobble_imports',
    'events',
}


def table_names(connection):
    with connection.cursor() as cursor:
        cursor.execute('SHOW TABLES')
        return {next(iter(row.values())) for row in cursor.fetchall()}


def test_every_table_the_code_reads_exists(database):
    missing = EXPECTED_TABLES - table_names(database)
    assert not missing, f'schema bootstrap does not create: {sorted(missing)}'


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


def test_the_song_key_compares_byte_for_byte(database):
    """migrate_v18: utf8mb4_general_ci gives every character outside the BMP the same
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
