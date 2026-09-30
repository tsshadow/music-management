"""The learned tempo priors and the refold pass (bug report 140)."""

import re
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from services.music_manager.bpm import octave, priors, refold
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
            {'kind': 'label', 'prior_key': 'x', 'centre': 7.0, 'spread': 0.1, 'samples': 9},
            {'kind': 'other', 'prior_key': '1', 'centre': 7.0, 'spread': 0.1, 'samples': 9},
        ]
    )
    assert loaded.coverage() == {'label': 1, 'artist': 1, 'genre': 1}
    assert loaded.for_artist('3') == Prior(7.0, 0.2, 8)
    assert loaded.for_artist(None) is None
    assert loaded.genre['hardstyle'].samples == 900


def test_the_best_sampled_label_wins():
    loaded = priors.Priors(label={1: Prior(7.0, 0.1, 10), 2: Prior(7.5, 0.1, 50)})
    assert loaded.best_label(['1', '2', 'junk']).samples == 50
    assert loaded.best_label([]) is None


def test_recompute_writes_each_kind_then_prunes_what_no_longer_qualifies():
    row = {'prior_key': '7', 'centre': 7.2, 'spread': None, 'samples': 12}
    connect, conns = fake_connect([row], [row], [row], [], [], [])
    result = priors.recompute(connect, NOW)
    assert result.coverage() == {'label': 1, 'artist': 1, 'genre': 1}
    write_cursor = conns[3].cursor.return_value.__enter__.return_value
    written = write_cursor.executemany.call_args[0][1]
    assert written == [('label', '7', 7.2, 0.0, 12, NOW)]
    assert write_cursor.execute.call_args[0] == (priors.PRUNE_SQL, ('label', NOW))
    conns[3].commit.assert_called_once()


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
    bpm, confidence, raw_confidence, corrected, evidence, _margin, version, uid, raw = updates[0]
    assert (bpm, corrected, version, uid, raw) == (128.0, 1, octave.FOLD_VERSION, 'uid-hazes', 64.0)
    assert raw_confidence == 0.5  # the old `confidence` becomes the estimator's own
    assert confidence <= 0.5
    assert evidence in (octave.EVIDENCE_NEUTRAL, octave.EVIDENCE_PATH)
    assert (result.above_200_before, result.above_200_after, result.bpm_changed) == (1, 0, 1)
    assert result.samples[0]['after'] == 128.0


def test_an_unchanged_row_is_not_written_again():
    first, _ = refold.compare([bpm_row()], priors.Priors())
    bpm, confidence, raw_confidence, corrected, evidence, margin, version, _, _ = first[0]
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
