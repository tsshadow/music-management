"""Grouping and canonical selection against a real MariaDB.

The unit suite pins the rules down (test_song_versions.py); this proves the SQL
that applies them, including that a second pass changes nothing and that a manual
pin and a manual split both survive one.
"""

import pytest

from services.music_manager import song_version_worker

pytestmark = pytest.mark.integration


def _add_track(cursor, uid, title, artist_id, path, size=7_200_000, duration=300.0, label_id=None):
    cursor.execute(
        'INSERT INTO library_tracks (track_uid, title, duration_secs, primary_artist_id) VALUES (%s, %s, %s, %s)',
        (uid, title, duration, artist_id),
    )
    track_id = cursor.lastrowid
    cursor.execute(
        'INSERT INTO library_media_files (file_path, file_path_hash, track_id, file_size, duration_secs) '
        'VALUES (%s, SHA2(%s, 256), %s, %s, %s)',
        (path, path, track_id, size, duration),
    )
    if label_id:
        cursor.execute(
            'INSERT INTO library_track_labels (track_id, label_id) VALUES (%s, %s)',
            (track_id, label_id),
        )
    return track_id


@pytest.fixture()
def library(database):
    with database.cursor() as cursor:
        for table in (
            'library_track_labels',
            'library_media_files',
            'library_tracks',
            'library_works',
            'library_labels',
            'library_artists',
            'downloads_soundcloud_archive',
        ):
            cursor.execute(f'DELETE FROM {table}')

        cursor.execute('INSERT INTO library_artists (name) VALUES (%s)', ('Angerfist',))
        artist_id = cursor.lastrowid
        cursor.execute('INSERT INTO library_labels (name) VALUES (%s)', ('Masters of Hardcore',))
        label_id = cursor.lastrowid

        official = _add_track(
            cursor,
            'uid-radio',
            'Raise Your Fist (Radio Edit)',
            artist_id,
            '/mnt/music/MOH/Angerfist - Raise Your Fist (Radio Edit).mp3',
            size=7_200_000,
            label_id=label_id,
        )
        extended = _add_track(
            cursor,
            'uid-ext',
            'Raise Your Fist (Extended Mix)',
            artist_id,
            '/mnt/music/MOH/Angerfist - Raise Your Fist (Extended Mix).flac',
            size=60_000_000,
            label_id=label_id,
        )
        rip = _add_track(
            cursor,
            'uid-rip',
            'Raise Your Fist',
            artist_id,
            '/mnt/music/soundcloud/Angerfist - Raise Your Fist.mp3',
            size=12_000_000,
        )
        cursor.execute(
            'INSERT INTO downloads_soundcloud_archive (url, filename) VALUES (%s, %s)',
            ('https://soundcloud.example/x', 'Angerfist - Raise Your Fist.mp3'),
        )
        remix = _add_track(
            cursor,
            'uid-remix',
            'Raise Your Fist (Wildstylez Remix)',
            artist_id,
            '/mnt/music/MOH/Angerfist - Raise Your Fist (Wildstylez Remix).mp3',
            size=7_200_000,
            label_id=label_id,
        )
    database.commit()
    return {'artist_id': artist_id, 'official': official, 'extended': extended, 'rip': rip, 'remix': remix}


def _work_of(database, track_id):
    with database.cursor() as cursor:
        cursor.execute('SELECT work_id FROM library_tracks WHERE id = %s', (track_id,))
        return cursor.fetchone()['work_id']


def _canonical_of_work(database, work_id):
    with database.cursor() as cursor:
        cursor.execute('SELECT canonical_track_id FROM library_works WHERE id = %s', (work_id,))
        return cursor.fetchone()['canonical_track_id']


def test_a_batch_that_fails_before_its_canonicals_assigns_nothing(database, library, monkeypatch):
    """Bug report 115: a grouped track is never looked at again, so a half-done batch stuck.

    With the canonical UPDATE refused, the batch rolls back whole: no track has a work and
    no work exists. The next pass then groups everything and gives each work a canonical.
    """
    from tests.integration.test_router_sql import fail_on_statement

    with monkeypatch.context() as patcher:
        fail_on_statement(patcher, 'UPDATE library_works SET canonical_track_id')
        with pytest.raises(RuntimeError):
            song_version_worker.group_once(database)
    with database.cursor() as cursor:
        cursor.execute('SELECT COUNT(*) AS n FROM library_tracks WHERE work_id IS NOT NULL')
        assert cursor.fetchone()['n'] == 0
        cursor.execute('SELECT COUNT(*) AS n FROM library_works')
        assert cursor.fetchone()['n'] == 0

    song_version_worker.group_once(database)
    with database.cursor() as cursor:
        cursor.execute('SELECT COUNT(*) AS n FROM library_works WHERE canonical_track_id IS NULL')
        assert cursor.fetchone()['n'] == 0


def test_length_variants_and_the_rip_land_in_one_work(database, library):
    song_version_worker.group_once(database)
    works = {_work_of(database, library[name]) for name in ('official', 'extended', 'rip')}
    assert len(works) == 1
    assert None not in works


def test_the_remix_is_a_work_of_its_own(database, library):
    song_version_worker.group_once(database)
    assert _work_of(database, library['remix']) != _work_of(database, library['official'])


def test_the_format_decides_first_so_the_flac_wins(database, library):
    # docs/designs/song-versions/: format first (lossless by default), then the kind. The
    # extended FLAC beats the MP3 radio edit; the old ranking chose the radio edit.
    song_version_worker.group_once(database)
    work_id = _work_of(database, library['official'])
    assert _canonical_of_work(database, work_id) == library['extended']


def test_a_second_pass_changes_nothing(database, library):
    song_version_worker.group_once(database)
    with database.cursor() as cursor:
        cursor.execute('SELECT id, work_id, version_kind, version_score FROM library_tracks ORDER BY id')
        before = cursor.fetchall()
    stats = song_version_worker.group_once(database)
    with database.cursor() as cursor:
        cursor.execute('SELECT id, work_id, version_kind, version_score FROM library_tracks ORDER BY id')
        after = cursor.fetchall()
    assert before == after
    assert stats['assigned'] == 0


def test_a_pin_beats_the_computed_canonical_and_survives_a_pass(database, library):
    song_version_worker.group_once(database)
    work_id = _work_of(database, library['official'])
    with database.cursor() as cursor:
        cursor.execute(
            'UPDATE library_works SET pinned_track_id = %s WHERE id = %s',
            (library['extended'], work_id),
        )
    database.commit()

    song_version_worker.group_once(database)
    assert _canonical_of_work(database, work_id) == library['extended']


def test_title_less_tracks_do_not_become_one_song(database, library):
    # The defect that shipped: every title that normalizes away produced the key
    # ':::', and one production work collected 117 unrelated recordings that way.
    with database.cursor() as cursor:
        blank = _add_track(cursor, 'uid-blank', '', None, '/mnt/music/soundcloud/blank.mp3')
        dove = _add_track(cursor, 'uid-dove', '🕊', None, '/mnt/music/soundcloud/dove.mp3')
        marks = _add_track(cursor, 'uid-marks', '᳄᳄᳄᳄᳆᳇᳇', None, '/mnt/music/soundcloud/marks.mp3')
    database.commit()

    song_version_worker.group_once(database)

    works = [_work_of(database, track_id) for track_id in (blank, dove, marks)]
    assert None not in works
    assert len(set(works)) == 3
    # Each is its own canonical: a work of one version has nothing to choose between.
    for track_id, work_id in zip((blank, dove, marks), works, strict=True):
        assert _canonical_of_work(database, work_id) == track_id


def test_a_track_is_scored_on_all_of_its_files_even_at_the_batch_edge(database, library):
    # LIMIT counts joined rows, so limiting after the media-file join cut the last
    # track of a batch off from its remaining files -- and it left the pass with a
    # work, so it never came back for them. Two files, batch of one.
    with database.cursor() as cursor:
        cursor.execute('UPDATE library_tracks SET work_id = NULL, version_kind = NULL, version_score = NULL')
        path = '/mnt/music/MOH/Angerfist - Raise Your Fist (Radio Edit).flac'
        cursor.execute(
            'INSERT INTO library_media_files (file_path, file_path_hash, track_id, file_size, duration_secs) '
            'VALUES (%s, SHA2(%s, 256), %s, %s, %s)',
            (path, path, library['official'], 60_000_000, 300.0),
        )
    database.commit()

    with database.cursor() as cursor:
        _touched, assigned = song_version_worker.assign_works(cursor, limit=1)
    database.commit()

    assert assigned == 1
    with database.cursor() as cursor:
        cursor.execute('SELECT version_score FROM library_tracks WHERE id = %s', (library['official'],))
        scored = cursor.fetchone()['version_score']
        cursor.execute('SELECT version_score FROM library_tracks WHERE id = %s', (library['extended'],))
        assert cursor.fetchone()['version_score'] is None, 'the batch of one took a second track'
    # The FLAC is the best file of that track, and it has to be the one that scored.
    assert scored == song_version_worker.version_score('radio', '.flac', 1600, is_official=True)


def test_a_locked_track_is_left_out_of_the_group(database, library):
    song_version_worker.group_once(database)
    with database.cursor() as cursor:
        cursor.execute(
            'UPDATE library_tracks SET work_id = NULL, work_locked = 1 WHERE id = %s',
            (library['rip'],),
        )
    database.commit()

    song_version_worker.group_once(database)
    assert _work_of(database, library['rip']) is None


LOSSLESS = song_version_worker.RankingContext(prefer_lossless=True)
LOSSY = song_version_worker.RankingContext(prefer_lossless=False)


def _work_row(database, work_id):
    with database.cursor() as cursor:
        cursor.execute(
            'SELECT canonical_track_id, previous_canonical_track_id, canonical_changed_at, ranking_signature '
            'FROM library_works WHERE id = %s',
            (work_id,),
        )
        return cursor.fetchone()


def test_a_new_work_is_stamped_with_the_ranking_it_was_scored_under(database, library):
    song_version_worker.group_once(database, LOSSLESS)
    work_id = _work_of(database, library['official'])
    assert _work_row(database, work_id)['ranking_signature'] == LOSSLESS.signature
    assert song_version_worker.rescore_pending(database, LOSSLESS) is False


def test_flipping_the_setting_rescores_moves_the_canonical_and_flags_it(database, library):
    song_version_worker.group_once(database, LOSSLESS)
    work_id = _work_of(database, library['official'])
    assert _canonical_of_work(database, work_id) == library['extended']

    preview = song_version_worker.rescore_once(database, LOSSY, dry_run=True)
    assert preview['canonicals_changed'] == 1
    assert _canonical_of_work(database, work_id) == library['extended'], 'the dry run wrote'

    applied = song_version_worker.rescore_once(database, LOSSY)
    assert applied['canonicals_changed'] == preview['canonicals_changed']
    row = _work_row(database, work_id)
    # Storage setting: the MP3 at 320 beats the FLAC. The rip's archive row holds a bare
    # basename, so it is not recognised as a rip here -- which is the point: format decides.
    assert row['canonical_track_id'] == library['rip']
    assert row['previous_canonical_track_id'] == library['extended']
    assert row['canonical_changed_at'] is not None
    assert row['ranking_signature'] == LOSSY.signature


def test_a_rescore_is_idempotent(database, library):
    song_version_worker.group_once(database, LOSSLESS)
    song_version_worker.rescore_once(database, LOSSY)
    with database.cursor() as cursor:
        cursor.execute('SELECT id, version_kind, version_score FROM library_tracks ORDER BY id')
        before = cursor.fetchall()

    again = song_version_worker.rescore_once(database, LOSSY)
    assert again == {'works': 0, 'tracks_rescored': 0, 'canonicals_changed': 0}
    with database.cursor() as cursor:
        cursor.execute('SELECT id, version_kind, version_score FROM library_tracks ORDER BY id')
        assert cursor.fetchall() == before


def test_a_rescore_never_regroups(database, library):
    song_version_worker.group_once(database, LOSSLESS)
    with database.cursor() as cursor:
        cursor.execute('SELECT id, work_id FROM library_tracks ORDER BY id')
        before = cursor.fetchall()
        cursor.execute('UPDATE library_works SET ranking_signature = NULL')
    database.commit()
    song_version_worker.rescore_once(database, LOSSLESS)
    with database.cursor() as cursor:
        cursor.execute('SELECT id, work_id FROM library_tracks ORDER BY id')
        assert cursor.fetchall() == before


def test_a_pin_wins_through_a_rescore(database, library):
    song_version_worker.group_once(database, LOSSLESS)
    work_id = _work_of(database, library['official'])
    with database.cursor() as cursor:
        cursor.execute('UPDATE library_works SET pinned_track_id = %s WHERE id = %s', (library['official'], work_id))
    database.commit()
    song_version_worker.group_once(database, LOSSLESS)

    song_version_worker.rescore_once(database, LOSSY)
    row = _work_row(database, work_id)
    assert row['canonical_track_id'] == library['official']
    assert row['canonical_changed_at'] is None


def test_the_python_canonical_matches_the_sql_one(database, library):
    # best_track() and _BEST_TRACK decide the same thing; after a rescore the SQL
    # recompute must not move the canonical again.
    song_version_worker.group_once(database, LOSSLESS)
    song_version_worker.rescore_once(database, LOSSY)
    work_id = _work_of(database, library['official'])
    chosen = _canonical_of_work(database, work_id)
    with database.cursor() as cursor:
        song_version_worker.recompute_canonicals(cursor, {work_id})
    database.commit()
    assert _canonical_of_work(database, work_id) == chosen
