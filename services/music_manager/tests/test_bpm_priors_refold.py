"""The learned tempo priors and the refold pass (bug report 140)."""

import math
import re
import statistics
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from services.music_manager.bpm import getsongbpm, octave, priors, refold
from services.music_manager.bpm.octave import Prior

NOW = datetime(2026, 9, 30, 12, 0, 0)


def fake_connect(*answers):
    """A connect() handing out one MagicMock connection per answer (its fetchall result)."""
    conns = []
    for answer in answers:
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        conn.cursor.return_value.__exit__.return_value = False
        cursor.fetchall.return_value = answer
        cursor.fetchone.return_value = answer[0] if answer else None
        conns.append(conn)
    return MagicMock(side_effect=conns), conns


# ----------------------------------------------------------------------------- priors


@pytest.mark.parametrize('kind', priors.KINDS)
def test_every_value_in_the_priors_statement_is_bound(kind):
    sql, params = priors.priors_sql(kind)
    assert sql.count('%s') == len(params)
    assert params[0] == priors.TRAINING_MIN_CONFIDENCE
    assert 'COALESCE(b.raw_confidence, b.confidence)' in sql
    assert 'LOG2(b.raw_bpm)' in sql  # the raw estimate, never a folded value


def test_only_the_artist_leaves_remixes_out_and_counts_fast_genre_less_tracks():
    artist_sql, artist_params = priors.priors_sql(priors.KIND_ARTIST)
    label_sql, _ = priors.priors_sql(priors.KIND_LABEL)
    assert 'REGEXP %s' in artist_sql and priors.REMIX_PATTERN in artist_params
    assert 'REGEXP' not in label_sql
    assert 'b.raw_bpm > %s' in artist_sql and 'b.raw_bpm > %s' not in label_sql
    assert '/mnt/music/hitzone/%' in artist_params


def test_the_folder_prior_counts_uploads_only_and_keys_them_by_uploader_folder():
    """Issue #241: the two folders under the music root, over Soundcloud and YouTube files only,
    with the artist's fast genre-less rows and without its remix filter."""
    sql, params = priors.priors_sql(priors.KIND_FOLDER)
    assert "SUBSTRING_INDEX(fm.file_path, '/', 5), 12), 191)" in sql
    assert params[1:3] == ['/mnt/music/soundcloud/%/%', '/mnt/music/youtube/%/%']
    assert priors.REMIX_PATTERN not in params and 'REGEXP' not in sql
    assert 'b.raw_bpm > %s' in sql


def _sql_folder_key(path):
    """What _FOLDER_KEY_SQL gives for `path`, spelled with Python's string operations."""
    return '/'.join(path.split('/')[:5])[11:][:191]


@pytest.mark.parametrize('path', ['/mnt/music/Soundcloud/Rebelion/a.mp3', '/mnt/music/Youtube/Q-dance/2024/set.m4a'])
def test_the_sql_folder_key_matches_folder_key(path):
    assert _sql_folder_key(path).lower() == octave.folder_key(path)


@pytest.mark.parametrize(
    ('raw', 'confidence', 'genres', 'trains'),
    [
        (174.0, 0.9, [], True),
        (174.0, 0.6, [], False),  # not confident
        (234.0, 0.9, [], True),  # fast and genre-less
        (234.0, 0.9, ['Hardstyle'], False),  # fast with a genre that is not hard
        (234.0, 0.9, ['Uptempo Hardcore'], True),
        (60.0, 0.9, [], False),
        (None, 0.9, [], False),
        (174.0, None, [], False),
    ],
)
def test_training_value_is_the_priors_sql_row_test(raw, confidence, genres, trains):
    value = priors.training_value(raw, confidence, genres)
    assert (value is not None) is trains
    if trains:
        assert value == pytest.approx(math.log2(raw))


def test_without_takes_one_row_out_of_the_statistics():
    rows = [math.log2(bpm) for bpm in (170, 172, 174, 175, 176, 178, 230)]
    kept = rows[:-1]
    full = Prior(statistics.fmean(rows), statistics.pstdev(rows), len(rows))
    loo = priors.without(full, rows[-1])
    assert loo.samples == len(kept)
    assert loo.centre == pytest.approx(statistics.fmean(kept))
    assert loo.spread == pytest.approx(statistics.pstdev(kept))


def test_without_ignores_a_row_the_trim_left_out_and_drops_a_thin_prior():
    prior = Prior(math.log2(174.0), 0.05, 20)
    assert priors.without(prior, math.log2(87.0)) is prior
    assert priors.without(Prior(math.log2(174.0), 0.05, priors.MIN_SAMPLES), math.log2(174.0)) is None


def test_for_folder_leaves_the_track_itself_out():
    loaded = priors.Priors(folder={'youtube/liquicity': Prior(math.log2(174.0), 0.05, 6)})
    path = '/mnt/music/Youtube/Liquicity/x.m4a'
    assert loaded.for_folder(path).samples == 6
    assert loaded.for_folder(path, math.log2(174.0)).samples == 5
    assert loaded.for_folder('/mnt/music/EPs/x/y.mp3') is None


@pytest.mark.parametrize(
    ('title', 'remix'),
    [
        ("'t Rode Licht (Rectonize Remix)[FREE DOWNLOAD]", True),
        ('Leef (Unproven Uptempo Bootleg)', True),
        ('Leef (Unproven Bootleg) (Uptempo)', True),
        ('Song [Hardstyle Edit]', True),
        ('Song (Re-Edit)', True),
        ('Vaag en Stil', False),
        ('Donker Om Je Heen', False),
        ('Song (Radio Edit)', False),
        ('Song (Extended Mix)', False),
        ('Remix Culture', False),  # the word outside brackets is a title, not a credit
    ],
)
def test_the_remix_pattern(title, remix):
    """The pattern is written for MariaDB's PCRE; Python's re reads this subset the same way."""
    assert bool(re.search(priors.REMIX_PATTERN, title)) is remix


def test_the_hard_genres_are_the_ones_above_200():
    assert {'uptempo hardcore', 'terror', 'frenchcore', 'hardcore'} <= set(priors.HARD_GENRES)
    assert 'hardstyle' not in priors.HARD_GENRES


def test_from_rows_keys_labels_and_artists_by_id_and_genres_by_name():
    loaded = priors.from_rows(
        [
            {'kind': 'label', 'prior_key': '7', 'centre': 7.2, 'spread': 0.1, 'samples': 40},
            {'kind': 'artist', 'prior_key': '3', 'centre': 7.0, 'spread': 0.2, 'samples': 8},
            {'kind': 'genre', 'prior_key': 'Hardstyle ', 'centre': 7.27, 'spread': 0.05, 'samples': 900},
            {'kind': 'folder', 'prior_key': 'Soundcloud/Rebelion', 'centre': 7.6, 'spread': 0.1, 'samples': 50},
            {'kind': 'label', 'prior_key': 'x', 'centre': 7.0, 'spread': 0.1, 'samples': 9},
            {'kind': 'other', 'prior_key': '1', 'centre': 7.0, 'spread': 0.1, 'samples': 9},
        ]
    )
    assert loaded.coverage() == {'label': 1, 'artist': 1, 'genre': 1, 'folder': 1}
    assert loaded.for_artist('3') == Prior(7.0, 0.2, 8)
    assert loaded.for_folder('/mnt/music/SoundCloud/REBELION/x.mp3') == Prior(7.6, 0.1, 50)
    assert loaded.for_artist(None) is None
    assert loaded.genre['hardstyle'].samples == 900


def test_the_best_sampled_label_wins():
    loaded = priors.Priors(label={1: Prior(7.0, 0.1, 10), 2: Prior(7.5, 0.1, 50)})
    assert loaded.best_label(['1', '2', 'junk']).samples == 50
    assert loaded.best_label([]) is None


def test_recompute_writes_each_kind_then_prunes_what_no_longer_qualifies():
    row = {'prior_key': '7', 'centre': 7.2, 'spread': None, 'samples': 12}
    folder_row = {'prior_key': 'Youtube/Q-dance', 'centre': 7.25, 'spread': 0.04, 'samples': 30}
    connect, conns = fake_connect([row], [row], [row], [folder_row], [], [], [], [])
    result = priors.recompute(connect, NOW)
    assert result.coverage() == {'label': 1, 'artist': 1, 'genre': 1, 'folder': 1}
    write_cursor = conns[4].cursor.return_value.__enter__.return_value
    written = write_cursor.executemany.call_args[0][1]
    assert written == [('label', '7', 7.2, 0.0, 12, NOW)]
    assert write_cursor.execute.call_args[0] == (priors.PRUNE_SQL, ('label', NOW))
    conns[4].commit.assert_called_once()
    folder_cursor = conns[7].cursor.return_value.__enter__.return_value
    assert folder_cursor.executemany.call_args[0][1] == [('folder', 'Youtube/Q-dance', 7.25, 0.04, 30, NOW)]


def test_load_and_last_update():
    connect, _ = fake_connect([{'kind': 'genre', 'prior_key': 'house', 'centre': 7.0, 'spread': 0.06, 'samples': 380}])
    assert priors.load(connect).genre['house'].samples == 380
    connect, _ = fake_connect([{'updated_at': NOW}])
    assert priors.last_update(connect) == NOW
    with pytest.raises(RuntimeError):
        priors.load(lambda: None)


# ----------------------------------------------------------------------------- refold


def bpm_row(**overrides):
    """One FOLD_INPUTS_SQL row: André Hazes's "Vaag en Stil" as production had it."""
    row = {
        'track_uid': 'uid-hazes',
        'track_id': 146658,
        'raw_bpm': 64.0,
        'raw_confidence': None,
        'confidence': 0.5,
        'strength': None,
        'half_score': None,
        'double_score': None,
        'bpm': 256.0,
        'octave_corrected': 1,
        'fold_evidence': None,
        'fold_margin': None,
        'fold_version': None,
        'primary_artist_id': 37353,
        'file_path': '/mnt/music/Hitzone/Hitzone 33/CD/21 - André Hazes - Vaag en Stil.mp3',
        'genres': None,
        'labels': None,
    }
    row.update(overrides)
    return row


def test_the_hazes_row_is_refolded_to_128_keeping_its_raw_confidence():
    updates, result = refold.compare([bpm_row()], priors.Priors(), sample=5)
    assert len(updates) == 1
    bpm, confidence, raw_confidence, corrected, evidence, _margin, version, external, uid, raw = updates[0]
    assert (bpm, corrected, version, uid, raw) == (128.0, 1, octave.FOLD_VERSION, 'uid-hazes', 64.0)
    assert external is None  # GetSongBPM is off without a cache
    assert raw_confidence == 0.5  # the old `confidence` becomes the estimator's own
    assert confidence <= 0.5
    assert evidence in (octave.EVIDENCE_NEUTRAL, octave.EVIDENCE_PATH)
    assert (result.above_200_before, result.above_200_after, result.bpm_changed) == (1, 0, 1)
    assert result.samples[0]['after'] == 128.0


def test_a_neutral_halving_of_a_fast_upload_is_undone_by_the_refold():
    """Issue #153: a genre-less Soundcloud upload at 234 that FOLD_VERSION 2 halved to 117 on the
    neutral prior alone goes back to 234 -- unsettled, not reliable -- under the version 3 rule,
    when its uploader folder has no prior of its own."""
    row = bpm_row(
        track_uid='uid-upload',
        raw_bpm=234.0,
        raw_confidence=0.95,
        confidence=0.6,
        strength=0.5,
        half_score=0.45,
        bpm=117.0,
        fold_evidence=octave.EVIDENCE_NEUTRAL,
        fold_margin=0.4,
        fold_version=2,
        primary_artist_id=None,
        file_path='/mnt/music/Soundcloud/Some Uploader/track.mp3',
    )
    updates, result = refold.compare([row], priors.Priors())
    bpm, confidence, _, corrected, evidence, margin, version, _, uid, raw = updates[0]
    assert (bpm, corrected, evidence, margin, uid, raw) == (
        234.0,
        0,
        octave.EVIDENCE_UNSETTLED,
        0.0,
        'uid-upload',
        234.0,
    )
    assert version == octave.FOLD_VERSION == 4
    assert confidence <= octave.WEAK_FOLD_CAP
    assert (result.above_200_before, result.above_200_after) == (0, 1)


def test_an_uploader_folder_halves_a_fast_upload_but_not_with_its_own_vote():
    """Issue #241: a genre-less Liquicity upload read at 348 is halved to 174 by its folder. When
    the folder's prior is the track's own row and four others, the track's own reading is taken
    out and the four left are too few: the estimate stays, unsettled."""
    upload = {
        'track_uid': 'uid-liquid',
        'raw_bpm': 348.0,
        'raw_confidence': 0.9,
        'bpm': 348.0,
        'octave_corrected': 0,
        'fold_version': 3,
        'primary_artist_id': None,
        'file_path': '/mnt/music/Youtube/Liquicity/Track.m4a',
        'strength': 0.5,
        'half_score': 0.45,
    }
    loaded = priors.Priors(folder={'youtube/liquicity': Prior(math.log2(174.0), 0.05, 80)})
    updates, _ = refold.compare([bpm_row(**upload)], loaded)
    assert (updates[0][0], updates[0][3], updates[0][4]) == (174.0, 1, octave.EVIDENCE_FOLDER)

    trained = {**upload, 'raw_bpm': 174.0, 'bpm': 174.0}  # a confident 174: one of the folder's rows
    thin = priors.Priors(folder={'youtube/liquicity': Prior(math.log2(174.0), 0.05, priors.MIN_SAMPLES)})
    assert refold.evidence_from(bpm_row(**trained), thin).folder is None
    assert refold.evidence_from(bpm_row(**upload), thin).folder.samples == priors.MIN_SAMPLES


def test_an_unchanged_row_is_not_written_again():
    first, _ = refold.compare([bpm_row()], priors.Priors())
    bpm, confidence, raw_confidence, corrected, evidence, margin, version, _, _, _ = first[0]
    settled = bpm_row(
        bpm=bpm,
        confidence=confidence,
        raw_confidence=raw_confidence,
        octave_corrected=corrected,
        fold_evidence=evidence,
        fold_margin=margin,
        fold_version=version,
    )
    updates, result = refold.compare([settled], priors.Priors())
    assert updates == [] and result.changed == 0


HAZES_KEY = getsongbpm.lookup_key('André Hazes', 'Vaag en Stil')


def test_a_getsongbpm_tempo_makes_the_hazes_fold_reliable_and_is_recorded():
    """Issue #152: the listed 128 decides the octave, the confidence is no longer capped."""
    row = bpm_row(raw_confidence=0.9, artist_name='André Hazes', title='Vaag en Stil')
    updates, _ = refold.compare([row], priors.Priors(), external={HAZES_KEY: 128.0})
    bpm, confidence, _, _, evidence, _, _, external, _, _ = updates[0]
    assert (bpm, evidence, external) == (128.0, octave.EVIDENCE_EXTERNAL, 128.0)
    assert confidence >= 0.75


def test_a_getsongbpm_tempo_is_ignored_for_a_track_with_an_artist_prior():
    row = bpm_row(raw_confidence=0.9, artist_name='André Hazes', title='Vaag en Stil')
    loaded = priors.Priors(artist={37353: Prior.around(128.0, 0.2, 40)})
    updates, _ = refold.compare([row], loaded, external={HAZES_KEY: 128.0})
    assert updates[0][4] != octave.EVIDENCE_EXTERNAL and updates[0][7] is None


def test_a_stored_external_tempo_is_cleared_when_the_cache_is_off():
    row = bpm_row(artist_name='André Hazes', title='Vaag en Stil')
    first, _ = refold.compare([row], priors.Priors(), external={HAZES_KEY: 128.0})
    bpm, confidence, raw_confidence, corrected, evidence, margin, version, external, _, _ = first[0]
    settled = bpm_row(
        artist_name='André Hazes', title='Vaag en Stil', bpm=bpm, confidence=confidence,
        raw_confidence=raw_confidence, octave_corrected=corrected, fold_evidence=evidence,
        fold_margin=margin, fold_version=version, external_bpm=external,
    )  # fmt: skip
    assert refold.compare([settled], priors.Priors(), external={HAZES_KEY: 128.0})[0] == []
    off, _ = refold.compare([settled], priors.Priors(), external={})
    assert off and off[0][7] is None


def test_stored_comb_scores_are_used():
    row = bpm_row(
        raw_bpm=115.0,
        confidence=0.97,
        bpm=230.0,
        genres='Hardcore|Industrial Hardcore',
        file_path='/mnt/music/Soundcloud/The Silence/Nothing.mp3',
        strength=0.3345,
        double_score=0.15679,
    )
    updates, _ = refold.compare([row], priors.Priors())
    assert updates[0][0] == 115.0


def test_evidence_reads_genres_labels_artist_and_path():
    loaded = priors.Priors(label={7: Prior(7.3, 0.16, 65)}, artist={3: Prior(7.15, 0.19, 15)})
    evidence = refold.evidence_from(
        {'genres': 'Hardcore|Industrial Hardcore', 'labels': '7,9', 'primary_artist_id': 3},
        loaded,
        '/mnt/music/EPs/x.mp3',
    )
    assert evidence.genres == ('Hardcore', 'Industrial Hardcore')
    assert evidence.root == 'EPs'
    assert evidence.label.samples == 65 and evidence.artist.samples == 15


def test_refold_writes_only_the_changes_and_a_dry_run_writes_nothing():
    reading = MagicMock()
    stream = reading.cursor.return_value
    stream.fetchmany.side_effect = [[bpm_row()], []]
    writing = MagicMock()
    result = refold.refold(MagicMock(side_effect=[reading, writing]), priors.Priors())
    assert result.written == 1
    write_cursor = writing.cursor.return_value.__enter__.return_value
    assert write_cursor.executemany.call_args[0][0] == refold.UPDATE_SQL
    writing.commit.assert_called_once()

    reading = MagicMock()
    reading.cursor.return_value.fetchmany.side_effect = [[bpm_row()], []]
    connect = MagicMock(side_effect=[reading])
    dry = refold.refold(connect, priors.Priors(), dry_run=True)
    assert (dry.written, dry.bpm_changed) == (0, 1)
    assert connect.call_count == 1


def test_refold_by_track_ids_binds_them():
    assert refold.inputs_sql([1, 2]).rstrip().endswith('AND t.id IN (%s, %s)')
    assert refold.refold(MagicMock(), priors.Priors(), track_ids=[]).rows == 0


def test_evidence_for_asks_nothing_without_ids():
    connect = MagicMock()
    assert refold.evidence_for(connect, []) == {}
    connect.assert_not_called()


def test_the_dry_run_cli_refuses_to_write(capsys):
    with pytest.raises(SystemExit):
        refold.main([])
    assert 'only --dry-run' in capsys.readouterr().err
