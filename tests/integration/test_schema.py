"""The schema this project declares can actually be built, and it holds what the code reads.

Nothing else in the suite checks this: the unit tests mock the cursor, so a CREATE TABLE
that MariaDB rejects would go unnoticed until a deploy. The tables are declared once, in
services/common/schema_tables.py; test_schema_snapshot.py compares them with production.
"""

import pytest

from tests.integration import schema_sources

pytestmark = pytest.mark.integration

EXPECTED_TABLES = schema_sources.declared_tables()


def test_every_declared_table_and_view_exists_in_a_fresh_database(fresh_schema):
    """Checked against a schema built from nothing, the way a fresh stack gets it."""
    assert len(EXPECTED_TABLES) > 60, 'schema_tables.TABLES looks suspiciously short'
    missing = EXPECTED_TABLES - set(fresh_schema.tables)
    assert not missing, f'the init does not create: {sorted(missing)}'
    assert schema_sources.declared_views() <= set(fresh_schema.views)


def test_no_other_file_declares_a_table():
    """One declaration per table: a CREATE TABLE elsewhere would never reach the snapshot test."""
    assert schema_sources.stray_declarations() == {}


def test_every_init_db_runs_at_startup():
    """An init_db that main.py never calls seeds nothing."""
    # users.init_db calls rbac.init_db, so that one is reached all the same.
    called_indirectly = {'services.music_manager.rbac'}
    orphaned = schema_sources.modules_defining_init_db() - schema_sources.startup_init_db_modules()
    assert orphaned <= called_indirectly, f'init_db never called at startup: {sorted(orphaned)}'


def test_the_bpm_tag_writeback_columns_exist(database):
    """Issue #139: db_init and migrate_v52 give library_track_bpm the writeback's bookkeeping."""
    with database.cursor() as cursor:
        cursor.execute('SHOW COLUMNS FROM library_track_bpm')
        columns = {row['Field'] for row in cursor.fetchall()}
    assert {'tag_bpm', 'tag_action', 'tag_checked_at'} <= columns


def test_the_bpm_octave_tables_are_expected_tables():
    """Bug report 140: the priors and the manual-tempo tables are declared."""
    for table in ('library_bpm_priors', 'library_track_bpm_manual'):
        assert table in EXPECTED_TABLES


def test_the_bpm_octave_columns_and_the_manual_source_exist(database):
    """Bug report 140: db_init and migrate_v53 add the octave choice's columns and the 'manual' source."""
    with database.cursor() as cursor:
        cursor.execute('SHOW COLUMNS FROM library_track_bpm')
        columns = {row['Field'] for row in cursor.fetchall()}
        cursor.execute("SHOW COLUMNS FROM library_track_effective_bpm LIKE 'source'")
        source = cursor.fetchone()['Type']
    assert {
        'raw_confidence', 'strength', 'half_score', 'double_score', 'fold_evidence', 'fold_margin', 'fold_version'
    } <= columns  # fmt: skip
    assert source == "enum('measured','tag','analyzer','manual')"


def test_the_extractor_can_file_a_standing_file(db):
    """Bug report 119: migrate_v46 lets the extract step record a file, with its reason, and refresh it."""
    from services.importer import conflict_store

    row = ('k' * 64, conflict_store.EXTRACTOR, '/import/clip.mp4', '', 'f' * 64, conflict_store.NOT_MUSIC_VIDEO)
    with db.cursor() as cursor:
        cursor.execute(conflict_store.RECORD_QUERY, row)
        cursor.execute(conflict_store.RECORD_QUERY, row)
        cursor.execute('SELECT step, reason, target FROM importer_conflicts')
        rows = cursor.fetchall()
    assert rows == [{'step': 'extractor', 'reason': 'not-music-video', 'target': ''}]


def test_the_curated_genre_columns_exist(database):
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
            cursor.execute("INSERT INTO users (username, api_key) VALUES ('User', 'k2')")
        cursor.execute("SELECT username FROM users WHERE LOWER(username) = LOWER('USER')")
        assert [row['username'] for row in cursor.fetchall()] == ['user']


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

        cursor.execute(RECORD_QUERY, ('NOPE123 - Release', 'NOPE', None, 'none', 0, 'a' * 64, None, None))
        cursor.execute("UPDATE rules_label_proposals SET status = 'rejected', decided_at = NOW()")
        cursor.execute(
            RECORD_QUERY, ('NOPE123 - Release', 'NOPE', 'Other', 'tag:label', 90, 'b' * 64, 'Second', 'second')
        )
        cursor.execute(KNOWN_QUERY)
        row = cursor.fetchone()
        cursor.execute('SELECT alternative_label, label_choice_key FROM rules_label_proposals')
        options = cursor.fetchone()
    assert row['status'] == 'rejected'
    assert row['resolved_fingerprint'] == 'b' * 64
    assert row['decided_at'] is not None
    # The two-option columns (#164) follow the proposal, which a decided row keeps as it was.
    assert (options['alternative_label'], options['label_choice_key']) == (None, None)


def test_a_deleted_audio_less_folder_takes_only_its_open_proposal_off_the_list(db):
    """#167: the mover deletes a queue folder without audio and marks its open proposal stale;
    a proposal someone already decided keeps its decision."""
    from services.importer.label_proposal_store import MARK_GONE_QUERY, RECORD_QUERY

    with db.cursor() as cursor:
        for folder in ('GONE123 - Release', 'DECIDED123 - Release'):
            cursor.execute(RECORD_QUERY, (folder, None, None, 'none', 0, None, None, None))
        cursor.execute("UPDATE rules_label_proposals SET status = 'rejected' WHERE folder = 'DECIDED123 - Release'")
        cursor.execute(MARK_GONE_QUERY, ('GONE123 - Release',))
        cursor.execute(MARK_GONE_QUERY, ('DECIDED123 - Release',))
        cursor.execute('SELECT folder, status, decided_at FROM rules_label_proposals ORDER BY folder')
        rows = {row['folder']: row for row in cursor.fetchall()}
    assert rows['GONE123 - Release']['status'] == 'stale'
    assert rows['GONE123 - Release']['decided_at'] is not None
    assert rows['DECIDED123 - Release']['status'] == 'rejected'


def test_a_track_carries_its_form_and_performance_date(fresh_schema):
    """library_tracks has the two columns the form filter and the year filter read
    (docs/designs/track-form/), and the form is indexed."""
    table = fresh_schema.tables['library_tracks']
    assert {'form', 'performance_date'} <= set(table.columns)
    assert table.columns['form'].nullable == 'YES'
    assert any(index.columns == ('form',) for index in table.indexes.values())
