"""The BPM tag writeback (issue #139): the rule, the per-format writers on real files, the round.

The writers run against real mutagen and real (tiny) audio files: the point is that only the
BPM frame changes and every other tag and the audio bytes come out as they went in, which a
stub cannot show. docs/designs/bpm-tag-writeback/.
"""

from __future__ import annotations

import os
import shutil
import struct
from datetime import datetime
from pathlib import Path

import mutagen
import pytest
from mutagen.id3 import COMM, ID3, TBPM, TCON, TIT2, TPE1, TXXX, ID3NoHeaderError, delete
from mutagen.mp4 import MP4, MP4FreeForm
from mutagen.ogg import OggPage
from mutagen.wave import WAVE

from services.music_manager.bpm import tag_writeback as tw
from services.music_manager.bpm.octave import FOLD_VERSION

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = {
    'mp3': ROOT / 'tests' / 'fixtures' / 'music' / 'ci-test-track-001.mp3',
    'm4a': ROOT / 'tests' / 'unit' / 'fixtures' / 'tone.m4a',
    'flac': ROOT / 'tests' / 'unit' / 'fixtures' / 'tone.flac',
    'opus': ROOT / 'tests' / 'unit' / 'fixtures' / 'tone.opus',
    'wav': ROOT / 'tests' / 'unit' / 'fixtures' / 'tone.wav',
}


# ----------------------------------------------------------------------------- the rule


@pytest.mark.parametrize(
    ('existing', 'measured', 'write', 'value', 'reason'),
    [
        (None, 150.02, True, 150, 'missing'),
        ('', 150.02, True, 150, 'missing'),
        ('abc', 150.02, True, 150, 'missing'),
        ('0', 150.02, True, 150, 'missing'),  # a zero tag is noise
        ('1500', 150.02, True, 150, 'missing'),  # so is a mis-parsed one
        ('150', 150.02, False, 150, 'matches'),
        ('150.00', 150.2, False, 150, 'matches'),
        ('150,4', 150.6, False, 151, 'matches'),  # within half a BPM, whatever the rounding
        ('151', 150.5, False, 151, 'matches'),  # half up, not half even
        ('150', 150.9, False, 151, 'kept'),  # a genuine off-grid integer within 1 BPM stays
        ('155', 154.1, False, 154, 'kept'),
        ('150', 151.2, True, 151, 'differs'),  # more than 1 BPM off: the measurement wins
        ('152', 150.02, True, 150, 'differs'),  # the old analyzer's 152 step
        ('152', 151.2, True, 151, 'differs'),  # on the grid: no benefit of the doubt
        ('161', 160.3, True, 160, 'differs'),
        ('76', 152.4, True, 152, 'octave'),  # half
        ('300', 150.0, True, 150, 'octave'),  # double
        ('304', 152.0, True, 152, 'octave'),
    ],
)
def test_the_decision_rule(existing, measured, write, value, reason):
    assert tw.decide(existing, measured) == tw.Decision(write, value, reason)


def test_the_librosa_grid_is_the_old_analyzers_steps():
    for value in (152, 161, 172, 144, 148, 157, 99, 103):
        assert tw.on_librosa_grid(value), value
    for value in (150, 155, 160, 200, 210, 175):
        assert not tw.on_librosa_grid(value), value
    assert not tw.on_librosa_grid(152.5)


def test_the_method_is_the_estimators():
    """Spelled out in tag_writeback to keep numpy out of the API's start-up; must not drift."""
    pytest.importorskip('numpy')
    from services.music_manager.bpm import estimator  # pylint: disable=import-outside-toplevel

    assert tw.MEASURED_METHOD == estimator.METHOD


def test_rounding_is_half_up():
    assert [tw.round_bpm(v) for v in (150.49, 150.5, 151.5, 149.999)] == [150, 151, 152, 150]


# ----------------------------------------------------------------------------- the formats


def _copy(tmp_path: Path, kind: str) -> str:
    target = tmp_path / f'track.{kind}'
    shutil.copyfile(FIXTURES[kind], target)
    return str(target)


def _mp3_audio(path: str) -> bytes:
    """Everything after the ID3v2 tag (the frames themselves)."""
    data = Path(path).read_bytes()
    if data[:3] != b'ID3':
        return data
    size = 0
    for byte in data[6:10]:
        size = (size << 7) | (byte & 0x7F)
    start = 10 + size + (10 if data[5] & 0x10 else 0)
    return data[start:]


def _flac_audio(path: str) -> bytes:
    data = Path(path).read_bytes()
    assert data[:4] == b'fLaC'
    offset, last = 4, False
    while not last:
        header = data[offset]
        last = bool(header & 0x80)
        length = int.from_bytes(data[offset + 1 : offset + 4], 'big')
        offset += 4 + length
    return data[offset:]


def _atom(data: bytes, name: bytes) -> bytes:
    offset = 0
    while offset + 8 <= len(data):
        size, kind = struct.unpack('>I4s', data[offset : offset + 8])
        if size == 1:
            size = struct.unpack('>Q', data[offset + 8 : offset + 16])[0]
        if kind == name:
            return data[offset + 8 : offset + size]
        offset += size
    raise AssertionError(f'no {name!r} atom')


def _mp4_audio(path: str) -> bytes:
    return _atom(Path(path).read_bytes(), b'mdat')


def _ogg_audio(path: str) -> list:
    packets = []
    with open(path, 'rb') as handle:
        while True:
            try:
                page = OggPage(handle)
            except EOFError:
                break
            if page.position > 0:  # the header pages carry granule position 0
                packets.append(page.packets)
    return packets


def _wav_audio(path: str) -> bytes:
    data = Path(path).read_bytes()
    offset = 12
    while offset + 8 <= len(data):
        kind = data[offset : offset + 4]
        size = int.from_bytes(data[offset + 4 : offset + 8], 'little')
        if kind == b'data':
            return data[offset + 8 : offset + 8 + size]
        offset += 8 + size + (size & 1)
    raise AssertionError('no data chunk')


def _id3_frames(tags) -> dict:
    return {key: repr(frame) for key, frame in tags.items() if not key.startswith('TBPM')}


def _prepare_mp3(path: str, version: int = 4, bpm: str | None = '152') -> None:
    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        tags = ID3()
    tags.add(TIT2(encoding=3, text=['Fixture Title']))
    tags.add(TPE1(encoding=3, text=['Fixture Artist', 'Second Artist']))
    tags.add(TCON(encoding=3, text=['Hardstyle']))
    tags.add(TXXX(encoding=3, desc='FESTIVAL', text=['Defqon.1']))
    tags.add(COMM(encoding=3, lang='eng', desc='', text=['a comment']))
    if bpm is not None:
        tags.add(TBPM(encoding=3, text=[bpm]))
    tags.save(path, v2_version=version)


@pytest.mark.parametrize('version', [3, 4])
def test_mp3_gets_tbpm_and_keeps_everything_else(tmp_path, version):
    path = _copy(tmp_path, 'mp3')
    _prepare_mp3(path, version=version)
    before_frames = _id3_frames(ID3(path))
    before_audio = _mp3_audio(path)
    assert tw.read_bpm_tag(path) == '152'

    tw.write_bpm_tag(path, 150)

    after = ID3(path)
    assert tw.read_bpm_tag(path) == '150'
    assert [str(t) for t in after.getall('TBPM')[0].text] == ['150']
    assert len(after.getall('TBPM')) == 1
    assert after.version[:2] == (2, version)  # the file's own ID3 version is kept
    assert _id3_frames(after) == before_frames
    assert _mp3_audio(path) == before_audio


def test_an_mp3_without_a_tag_gets_one(tmp_path):
    path = _copy(tmp_path, 'mp3')
    delete(path)
    before_audio = Path(path).read_bytes()
    assert tw.read_bpm_tag(path) is None
    tw.write_bpm_tag(path, 172)
    assert tw.read_bpm_tag(path) == '172'
    assert _mp3_audio(path) == before_audio


def test_m4a_gets_the_integer_tmpo_atom_and_keeps_everything_else(tmp_path):
    path = _copy(tmp_path, 'm4a')
    audio = MP4(path)
    if audio.tags is None:
        audio.add_tags()
    audio.tags['\xa9nam'] = ['Fixture Title']
    audio.tags['\xa9ART'] = ['Fixture Artist']
    audio.tags['----:com.apple.iTunes:FESTIVAL'] = [MP4FreeForm(b'Defqon.1')]
    audio.tags['tmpo'] = [76]
    audio.save()
    before = {k: v for k, v in MP4(path).tags.items() if k != 'tmpo'}
    before_audio = _mp4_audio(path)
    assert tw.read_bpm_tag(path) == '76'

    tw.write_bpm_tag(path, 152)

    after = MP4(path).tags
    assert after['tmpo'] == [152]
    assert not [k for k in after if k.startswith('----') and k.upper().endswith('BPM')]  # no freeform twin
    assert {k: v for k, v in after.items() if k != 'tmpo'} == before
    assert _mp4_audio(path) == before_audio


@pytest.mark.parametrize(('kind', 'audio_of'), [('flac', _flac_audio), ('opus', _ogg_audio)])
def test_vorbis_comment_formats_get_bpm_and_keep_everything_else(tmp_path, kind, audio_of):
    path = _copy(tmp_path, kind)
    audio = mutagen.File(path)
    audio['ARTIST'] = ['Fixture Artist', 'Second Artist']
    audio['FESTIVAL'] = ['Defqon.1']
    audio['bpm'] = ['152']  # lower case: any spelling is replaced, never doubled
    audio.save()
    before = sorted((k.upper(), v) for k, v in mutagen.File(path).tags if k.upper() != 'BPM')
    before_audio = audio_of(path)
    assert tw.read_bpm_tag(path) == '152'

    tw.write_bpm_tag(path, 150)

    after = mutagen.File(path).tags
    assert [v for k, v in after if k.upper() == 'BPM'] == ['150']
    assert sorted((k.upper(), v) for k, v in after if k.upper() != 'BPM') == before
    assert audio_of(path) == before_audio


def test_wav_gets_tbpm_in_its_id3_chunk(tmp_path):
    path = _copy(tmp_path, 'wav')
    audio = WAVE(path)
    if audio.tags is None:
        audio.add_tags()
    audio.tags.add(TIT2(encoding=3, text=['Fixture Title']))
    audio.save()
    before_audio = _wav_audio(path)
    assert tw.read_bpm_tag(path) is None

    tw.write_bpm_tag(path, 160)

    after = WAVE(path).tags
    assert str(after['TBPM'].text[0]) == '160'
    assert str(after['TIT2'].text[0]) == 'Fixture Title'
    assert _wav_audio(path) == before_audio


def test_an_unknown_format_is_refused(tmp_path):
    path = tmp_path / 'track.aiff'
    path.write_bytes(b'FORM')
    with pytest.raises(tw.UnsupportedFormat):
        tw.read_bpm_tag(str(path))
    with pytest.raises(tw.UnsupportedFormat):
        tw.write_bpm_tag(str(path), 150)


# ----------------------------------------------------------------------------- settings


def test_settings_are_read_and_clamped():
    values = {
        'bpm_tag_writeback_enabled': 'false',
        'bpm_tag_writeback_per_round': 99999,
        'bpm_tag_writeback_min_confidence': 'x',
        'bpm_analysis_skip_forms': 'Set, podcast,,',
    }
    config = tw.read_settings(values.get)
    assert config['bpm_tag_writeback_enabled'] is False
    assert config['bpm_tag_writeback_paused'] is False
    assert config['bpm_tag_writeback_per_round'] == 5000
    assert config['bpm_tag_writeback_min_confidence'] == 75
    assert config['skip_forms'] == ['podcast', 'set']


def test_the_roots_are_the_taggers_own_track_folders():
    settings = {'eps_folder_path': '/mnt/music/EPs', 'music_folder_path': '/mnt/music'}

    class Settings:
        def get(self, key):
            return settings.get(key)

    assert tw.library_roots(Settings()) == [
        '/mnt/music/EPs',
        '/mnt/music/Soundcloud',
        '/mnt/music/Youtube',
        '/mnt/music/Telegram',
        '/mnt/music/Top 100',
    ]


def test_the_queue_statement_binds_every_value():
    config = tw.read_settings({}.get)
    sql, params = tw._due_params(config, ['/mnt/music/EPs', '/mnt/music/Top_100'], 300)
    assert sql.count('%s') == len(params)
    assert params[0] == 'acf-comb-v1'
    assert params[1] == FOLD_VERSION  # only rows the current octave rule chose (bug report 140)
    assert params[2] == 0.75
    assert '/mnt/music/Top\\_100/%' in params  # a LIKE wildcard in a folder name is literal
    assert params[-1] == 300
    count_sql, count_params = tw._due_params(config, ['/mnt/music/EPs'], None)
    assert 'LIMIT' not in count_sql
    assert count_sql.count('%s') == len(count_params)


# ----------------------------------------------------------------------------- the round


class FakeStore:
    """Stands in for BpmTagStore: hands out rows, keeps what was recorded."""

    def __init__(self, rows):
        self.rows = rows
        self.limits = []
        self.recorded = []
        self.written = []
        self.fail_written = False

    def due(self, _config, _roots, limit):
        self.limits.append(limit)
        return self.rows[:limit]

    def remaining(self, _config, _roots):
        return 7

    def record(self, row, action, _now):
        self.recorded.append((row['file_path'], action))

    def record_written(self, row, before, after, _now):
        if self.fail_written:
            raise RuntimeError('database gone')
        self.written.append((row['file_path'], before, after))


def _row(path: str, bpm: float = 150.0, **overrides) -> dict:
    stat = os.stat(path) if os.path.exists(path) else None
    row = {
        'track_id': 1,
        'track_uid': f'uid-{path}',
        'bpm': bpm,
        'confidence': 0.9,
        'file_mtime': stat.st_mtime if stat else 1.0,
        'file_size': stat.st_size if stat else 10,
        'media_id': 1,
        'file_path': path,
    }
    row.update(overrides)
    return row


def _settings(**overrides):
    config = tw.read_settings({}.get)
    config.update(overrides)
    return lambda: config


def _runner(store, notified=None, sleeps=None, **settings):
    return tw.BpmTagWriteback(
        store=store,
        settings=_settings(**settings),
        roots=lambda: ['/mnt/music/EPs'],
        notify=(notified.append if notified is not None else lambda folders: None),
        sleep=(sleeps.append if sleeps is not None else lambda seconds: None),
        now=lambda: datetime(2026, 9, 30, 12, 0),
    )


def test_a_round_writes_records_and_tells_lms_once_per_folder(tmp_path):
    first, second = _copy(tmp_path, 'mp3'), str(tmp_path / 'other.mp3')
    shutil.copyfile(first, second)
    _prepare_mp3(first, bpm='152')
    _prepare_mp3(second, bpm='76')
    store = FakeStore([_row(first, 150.02), _row(second, 151.6)])
    notified: list = []

    result = _runner(store, notified).run_round()

    assert result.counts == {'written': 2}
    assert tw.read_bpm_tag(first) == '150' and tw.read_bpm_tag(second) == '152'
    assert [path for path, _, _ in store.written] == [first, second]
    _, before, after = store.written[0]
    assert (before.st_mtime, before.st_size) == (store.rows[0]['file_mtime'], store.rows[0]['file_size'])
    assert (after.st_mtime, after.st_size) == (os.stat(first).st_mtime, os.stat(first).st_size)
    assert notified == [[str(tmp_path)]]
    assert store.limits == [300]


def test_a_matching_or_kept_tag_is_recorded_without_touching_the_file(tmp_path):
    path = _copy(tmp_path, 'mp3')
    _prepare_mp3(path, bpm='150')
    stamp = os.stat(path)
    store = FakeStore([_row(path, 150.9)])
    notified: list = []

    result = _runner(store, notified).run_round()

    assert result.counts == {'kept': 1}
    assert store.recorded == [(path, 'kept')]
    assert os.stat(path).st_mtime == stamp.st_mtime
    assert not notified


def test_a_file_changed_since_the_measurement_is_left_queued(tmp_path):
    path = _copy(tmp_path, 'mp3')
    _prepare_mp3(path, bpm='152')
    store = FakeStore([_row(path, file_size=1)])

    result = _runner(store).run_round()

    assert result.counts == {'stale': 1}
    assert not store.recorded and not store.written
    assert tw.read_bpm_tag(path) == '152'


def test_missing_unsupported_and_unreadable_files_are_stamped_not_retried(tmp_path):
    aiff = tmp_path / 'a.aiff'
    aiff.write_bytes(b'FORM')
    broken = tmp_path / 'b.flac'
    broken.write_bytes(b'not a flac file at all')
    store = FakeStore([_row(str(tmp_path / 'gone.mp3')), _row(str(aiff)), _row(str(broken))])

    result = _runner(store).run_round()

    assert result.counts == {'missing': 1, 'unsupported': 1, 'failed': 1}
    assert [action for _, action in store.recorded] == ['missing', 'unsupported', 'failed']


def test_switched_off_paused_or_zero_does_nothing():
    for settings, reason in (
        ({'bpm_tag_writeback_enabled': False}, 'off'),
        ({'bpm_tag_writeback_paused': True}, 'paused'),
        ({'bpm_tag_writeback_per_round': 0}, 'nothing to do'),
    ):
        store = FakeStore([_row('/x.mp3')])
        result = _runner(store, **settings).run_round()
        assert result.skipped == reason
        assert not store.limits


def test_the_cap_is_the_queue_limit():
    store = FakeStore([])
    _runner(store, bpm_tag_writeback_per_round=25).run_round()
    assert store.limits == [25]


def test_a_stop_request_ends_the_round_between_files(tmp_path):
    first, second = _copy(tmp_path, 'mp3'), str(tmp_path / 'other.mp3')
    shutil.copyfile(first, second)
    store = FakeStore([_row(first), _row(second)])
    calls = []

    def should_stop():
        calls.append(1)
        return len(calls) > 1

    result = _runner(store).run_round(should_stop)
    assert result.handled == 1


def test_the_round_pauses_after_every_slice_of_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(tw, 'SLICE', 2)
    rows = []
    for index in range(5):
        path = str(tmp_path / f'{index}.mp3')
        shutil.copyfile(FIXTURES['mp3'], path)
        rows.append(_row(path, 150.0 + index))
    sleeps: list = []

    result = _runner(FakeStore(rows), sleeps=sleeps).run_round()

    assert result.counts == {'written': 5}
    assert sleeps == [tw.DEFAULT_PAUSE_SECONDS, tw.DEFAULT_PAUSE_SECONDS]


def test_a_write_that_cannot_be_recorded_still_counts_and_warns(tmp_path, caplog):
    path = _copy(tmp_path, 'mp3')
    store = FakeStore([_row(path)])
    store.fail_written = True
    with caplog.at_level('WARNING', logger='music-manager.bpm.tags'):
        result = _runner(store).run_round()
    assert result.counts == {'written': 1}
    assert 'not recorded' in caplog.text


def test_a_round_that_did_something_logs_one_summary(tmp_path, caplog):
    path = _copy(tmp_path, 'mp3')
    _prepare_mp3(path, bpm='150')
    with caplog.at_level('INFO', logger='music-manager.bpm.tags'):
        _runner(FakeStore([_row(path, 150.0)])).run_round()
    assert 'BPM tags: matches 1; 7 file(s) still to reconcile' in caplog.text


class RecordingCursor:
    """A cursor that remembers statements and answers the tagger-row lookup."""

    def __init__(self, processed):
        self.processed = processed
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.statements.append((' '.join(sql.split()), params))

    def fetchone(self):
        return self.processed


class RecordingConnection:
    def __init__(self, processed):
        self.cursor_obj = RecordingCursor(processed)
        self.events = []

    def cursor(self):
        return self.cursor_obj

    def begin(self):
        self.events.append('begin')

    def commit(self):
        self.events.append('commit')

    def rollback(self):
        self.events.append('rollback')

    def close(self):
        self.events.append('close')


class Stat:
    def __init__(self, mtime, size):
        self.st_mtime, self.st_size = mtime, size


@pytest.mark.parametrize(
    ('processed', 'refreshed'),
    [
        ({'mtime': 100.0, 'needs_rescan': 0}, True),  # up to date before: stays up to date
        ({'mtime': 50.0, 'needs_rescan': 0}, False),  # already behind the file: the tagger's call
        ({'mtime': 100.0, 'needs_rescan': 1}, False),  # queued: left queued
        (None, False),  # never seen by the tagger: it finds the file itself
    ],
)
def test_a_write_moves_the_taggers_mtime_only_when_it_was_up_to_date(processed, refreshed):
    conn = RecordingConnection(processed)
    store = tw.BpmTagStore(connect=lambda: conn)
    row = _row('/mnt/music/EPs/a.mp3', 150.0)

    store.record_written(row, Stat(100.0, 10), Stat(200.0, 12), datetime(2026, 9, 30))

    sql = [statement for statement, _ in conn.cursor_obj.statements]
    assert any(s.startswith('UPDATE library_track_bpm b') and 'SET b.tag_bpm' in s for s in sql)
    assert any(s.startswith('UPDATE library_track_bpm SET file_mtime') for s in sql)
    assert any(s.startswith('UPDATE library_media_files') for s in sql)
    assert any(s.startswith('UPDATE tagger_processed_files') for s in sql) is refreshed
    assert conn.events == ['begin', 'commit', 'close']


def test_a_failed_bookkeeping_write_is_rolled_back():
    conn = RecordingConnection(None)

    def boom(sql, params=None):
        raise RuntimeError('lost')

    conn.cursor_obj.execute = boom
    store = tw.BpmTagStore(connect=lambda: conn)
    with pytest.raises(RuntimeError):
        store.record_written(_row('/a.mp3'), Stat(1.0, 1), Stat(2.0, 2), datetime(2026, 9, 30))
    assert conn.events == ['begin', 'rollback', 'close']


def test_the_queue_prefers_a_tempo_set_by_hand_and_requeues_what_it_once_wrote():
    """Bug report 140: the value is the manual tempo when there is one, else a measurement the
    current octave rule chose; a file this step wrote is queued again whenever its value changes,
    even when the new value is not confident -- the old one came from a rule that was wrong."""
    sql = ' '.join(tw.DUE_SQL.split())
    assert 'COALESCE(mb.bpm, b.bpm) AS bpm' in sql
    assert 'LEFT JOIN library_track_bpm_manual mb ON mb.track_uid = b.track_uid' in sql
    assert "(mb.bpm IS NOT NULL OR (b.fold_version = %s AND (b.confidence >= %s OR b.tag_action = 'written')))" in sql
    assert 'NOT (b.tag_bpm <=> COALESCE(mb.bpm, b.bpm))' in sql


def test_an_outcome_is_stamped_with_the_value_that_was_read():
    conn = RecordingConnection(None)
    store = tw.BpmTagStore(connect=lambda: conn)
    store.record(_row('/mnt/music/EPs/a.mp3', 128.0), 'matches', datetime(2026, 9, 30))
    statement, params = conn.cursor_obj.statements[0]
    assert 'WHERE b.track_uid = %s AND COALESCE(mb.bpm, b.bpm) = %s' in statement
    assert params[0] == 128.0 and params[1] == 'matches' and params[-1] == 128.0


def test_a_written_octave_error_is_rewritten_by_the_rule():
    """The ~835 files written at 256 for a ballad now measured at 128: `decide` writes again."""
    decision = tw.decide('256', 128.0)
    assert (decision.write, decision.value, decision.reason) == (True, 128, 'octave')
