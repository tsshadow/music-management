"""The BPM analysis worker: settings, queue, excerpt, folding, rounds, pause/resume, status."""

import json
import subprocess
import tempfile
import threading
import unittest
from concurrent.futures import Executor
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# The images and CI carry numpy (requirements.txt); a bare host interpreter may not.
np = pytest.importorskip('numpy')

from services.common import config_store  # noqa: E402
from services.music_manager.bpm import estimator, octave, refold, status, worker  # noqa: E402
from services.music_manager.bpm.priors import Priors  # noqa: E402

NOW = datetime(2026, 9, 29, 12, 0, 0)


class InlineExecutor(Executor):
    """Runs `map` in the calling thread, so a round needs no processes."""

    def __init__(self):
        self.shut = False

    def map(self, fn, *iterables, timeout=None, chunksize=1):  # pylint: disable=arguments-differ
        return [fn(*args) for args in zip(*iterables, strict=True)]

    def shutdown(self, wait=True, *, cancel_futures=False):
        self.shut = True


def job(track_id, path='/mnt/music/a.mp3', duration=240.0):
    """One DUE_SQL row."""
    return {
        'track_id': track_id,
        'track_uid': f'uid-{track_id}',
        'duration_secs': duration,
        'file_path': path,
        'file_mtime': 1.5,
        'file_size': 1000,
    }


def config(**overrides):
    """Settings as read_settings returns them."""
    values = worker.read_settings(Path('/nonexistent/config.json'), env={})
    values.update(overrides)
    return values


class SettingsTest(unittest.TestCase):
    def test_the_defaults_match_the_config_page(self):
        fields = {f.key: f for f in config_store._bpm_fields()}  # pylint: disable=protected-access
        for key, kind, default in worker.SETTINGS:
            with self.subTest(key=key):
                self.assertEqual((fields[key].type, fields[key].default), (kind, default))
                self.assertEqual(fields[key].env, key.upper())

    def test_defaults_without_a_file(self):
        values = config()
        self.assertTrue(values['bpm_analysis_enabled'])
        self.assertFalse(values['bpm_analysis_paused'])
        self.assertEqual(values['bpm_analysis_workers'], 2)
        self.assertEqual(values['skip_forms'], ['interview', 'liveset', 'podcast', 'preview', 'set'])

    def test_the_config_file_wins_over_the_environment_and_is_clamped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'config.json'
            path.write_text(json.dumps({'__format__': 2, 'bpm_analysis_paused': True, 'bpm_analysis_workers': 99}))
            values = worker.read_settings(
                path, env={'BPM_ANALYSIS_PAUSED': 'false', 'BPM_ANALYSIS_EXCERPT_SECONDS': '5'}
            )
        self.assertTrue(values['bpm_analysis_paused'])
        self.assertEqual(values['bpm_analysis_workers'], 8)
        self.assertEqual(values['bpm_analysis_excerpt_seconds'], 20)

    def test_a_broken_file_falls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'config.json'
            path.write_text('{nope')
            self.assertEqual(
                worker.read_settings(path, env={'BPM_ANALYSIS_ENABLED': 'off'})['bpm_analysis_enabled'], False
            )


class QueueSqlTest(unittest.TestCase):
    def test_every_skipped_form_is_a_bound_parameter(self):
        sql, params = worker._due_params(config(), NOW, 48)  # pylint: disable=protected-access
        self.assertEqual(sql.count('%s'), len(params))
        self.assertEqual(params[:6], ['interview', 'liveset', 'podcast', 'preview', 'set', ''])
        self.assertEqual(params[6], 15 * 60)
        self.assertEqual(params[7], estimator.METHOD)
        self.assertEqual(params[-1], 48)
        self.assertIn('ORDER BY t.id DESC', sql)

    def test_no_skipped_forms_still_makes_valid_sql(self):
        sql, params = worker._due_params(config(skip_forms=[]), NOW, 10)  # pylint: disable=protected-access
        self.assertEqual(sql.count('%s'), len(params))
        self.assertIn('NOT IN (%s)', sql)

    def test_the_later_tiers_add_the_unscored_measurements(self):
        first, _ = worker._due_params(config(), NOW, 48, 0)  # pylint: disable=protected-access
        doubt, doubt_params = worker._due_params(config(), NOW, 48, 1)  # pylint: disable=protected-access
        rest, _ = worker._due_params(config(), NOW, 48, 2)  # pylint: disable=protected-access
        self.assertNotIn('strength IS NULL', first)
        self.assertIn('b.bpm > 200 OR b.bpm < 70 OR b.octave_corrected = 1', doubt)
        self.assertIn(f'b.fold_margin < {octave.AMBIGUOUS_MARGIN}', doubt)
        self.assertEqual(doubt.count('%s'), len(doubt_params))
        self.assertIn("OR (b.status = 'ok' AND b.strength IS NULL)", rest)

    def test_the_count_has_no_limit(self):
        sql, params = worker._due_params(config(), NOW, None)  # pylint: disable=protected-access
        self.assertEqual(sql.count('%s'), len(params))
        self.assertNotIn('LIMIT', sql)
        self.assertTrue(sql.startswith('SELECT COUNT(*)'))


class StoreTest(unittest.TestCase):
    def store(self, *answers):
        conns = []
        for answer in answers:
            conn = MagicMock()
            cursor = conn.cursor.return_value.__enter__.return_value
            conn.cursor.return_value.__exit__.return_value = False
            cursor.fetchall.return_value = answer
            conns.append(conn)
        return worker.BpmStore(connect=MagicMock(side_effect=conns)), conns

    def test_the_evidence_comes_by_track_id_and_never_from_the_artists_other_tracks(self):
        store, conns = self.store([{'track_id': 1, 'genres': 'Hardstyle', 'labels': '7', 'primary_artist_id': 3}])
        self.assertEqual(store.evidence_for([1, 2])[1]['genres'], 'Hardstyle')
        sql = conns[0].cursor.return_value.__enter__.return_value.execute.call_args[0][0]
        # Bug report 140: no stand-in genre from the primary artist's other tracks any more.
        self.assertNotIn('primary_artist_id = t.primary_artist_id', sql)

    def test_no_ids_asks_nothing(self):
        store, conns = self.store()
        self.assertEqual(store.evidence_for([]), {})
        self.assertEqual(conns, [])

    def test_the_tiers_fill_a_batch_in_order_without_duplicates(self):
        store, conns = self.store(
            [job(9)],
            [job(9), job(5)],
            [job(9), job(5), job(4), job(3)],
        )
        found = store.due_tracks(config(), NOW, limit=3)
        self.assertEqual([j['track_id'] for j in found], [9, 5, 4])
        self.assertEqual(len(conns), 3)

    def test_a_full_first_tier_asks_no_further(self):
        store, conns = self.store([job(2), job(1)])
        self.assertEqual(len(store.due_tracks(config(), NOW, limit=2)), 2)
        self.assertEqual(len(conns), 1)

    def test_remaining_counts(self):
        store, _ = self.store([{'remaining': 1234}])
        self.assertEqual(store.remaining(config(), NOW), 1234)

    def test_save_commits_a_batch(self):
        store, conns = self.store([])
        store.save([('uid', 'ok')])
        conns[0].commit.assert_called_once()
        store.save([])  # nothing to write: no connection taken


class ExcerptTest(unittest.TestCase):
    def test_a_normal_track_starts_thirty_percent_in(self):
        self.assertEqual(worker.excerpt_window(240.0, 60), (72.0, 60.0))

    def test_the_excerpt_never_runs_past_the_end(self):
        self.assertEqual(worker.excerpt_window(80.0, 60), (20.0, 60.0))

    def test_a_short_track_is_read_whole(self):
        self.assertEqual(worker.excerpt_window(45.0, 60), (0.0, 45.0))

    def test_an_unknown_duration_starts_at_zero(self):
        self.assertEqual(worker.excerpt_window(None, 60), (0.0, 60.0))

    def test_ffmpeg_seeks_before_the_input_and_resamples(self):
        run = MagicMock(return_value=subprocess.CompletedProcess([], 0, np.zeros(4, np.float32).tobytes(), b''))
        samples = worker.decode_excerpt('/mnt/music/a.m4a', 72.0, 60.0, run=run)
        command = run.call_args.args[0]
        self.assertLess(command.index('-ss'), command.index('-i'))
        self.assertIn(str(estimator.SAMPLE_RATE), command)
        self.assertEqual(len(samples), 4)

    def test_an_ffmpeg_failure_is_a_decode_error(self):
        run = MagicMock(return_value=subprocess.CompletedProcess([], 1, b'', b'line\nInvalid data found'))
        with self.assertRaisesRegex(worker.DecodeError, 'Invalid data found'):
            worker.decode_excerpt('/x.mp3', 0, 60, run=run)

    def test_a_missing_ffmpeg_is_a_decode_error(self):
        with self.assertRaises(worker.DecodeError):
            worker.decode_excerpt('/x.mp3', 0, 60, run=MagicMock(side_effect=FileNotFoundError('ffmpeg')))

    def test_analyze_turns_a_failure_into_a_result(self):
        result = worker.analyze(job(7, path='/definitely/not/here.mp3'), 60)
        self.assertEqual((result['track_id'], result['ok']), (7, False))
        self.assertTrue(result['error'])


class ToRowTest(unittest.TestCase):
    def test_a_half_time_hardstyle_reading_is_folded_and_marked(self):
        evidence = octave.Evidence(genres=('Hardstyle',))
        result = {
            'ok': True,
            'raw': 75.02,
            'confidence': 0.9,
            'strength': 0.5,
            'half_score': None,
            'double_score': 0.45,
        }
        row = worker.to_row(job(1), result, evidence, NOW)
        self.assertEqual(row[:4], ('uid-1', 'ok', 150.04, 75.02))
        self.assertEqual(row[5:7], (estimator.METHOD, 1))
        self.assertEqual(row[7:11], (1.5, 1000, None, NOW))
        # The stored confidence is the pulse's discounted by the octave choice, never above it.
        self.assertLess(row[4], 0.9)
        self.assertEqual(row[11:15], (0.9, 0.5, None, 0.45))
        self.assertEqual(row[15], octave.EVIDENCE_BAND)
        self.assertEqual(row[17], octave.FOLD_VERSION)

    def test_without_any_evidence_a_raw_estimate_in_the_middle_stays(self):
        row = worker.to_row(job(1), {'ok': True, 'raw': 128.0, 'confidence': 0.8}, None, NOW)
        self.assertEqual((row[2], row[6]), (128.0, 0))

    def test_a_failure_keeps_the_file_facts_and_the_error(self):
        row = worker.to_row(job(1), {'ok': False, 'error': 'DecodeError: x'}, None, NOW)
        self.assertEqual(
            row,
            ('uid-1', 'failed', None, None, None, estimator.METHOD, 0, 1.5, 1000, 'DecodeError: x', NOW) + (None,) * 7,
        )

    def test_the_row_fills_every_upsert_placeholder(self):
        row = worker.to_row(job(1), {'ok': True, 'raw': 128.0, 'confidence': 0.8}, None, NOW)
        # attempts is the literal 1 in VALUES, so one fewer parameter than columns.
        self.assertEqual(worker.UPSERT_SQL.split('ON DUPLICATE', maxsplit=1)[0].count('%s'), len(row))


class FakeStore:
    """The queue as a list; `save` records what was written and takes it off the queue."""

    def __init__(self, jobs):
        self.jobs = list(jobs)
        self.saved = []
        #: (track_ids or None for a full sync, reliable_confidence) per effective-BPM sync.
        self.synced = []
        self.sync_error = None

    def sync_effective(self, track_ids, reliable_confidence):
        self.synced.append((track_ids, reliable_confidence))
        if self.sync_error:
            raise self.sync_error
        return worker.effective_table.SyncResult(resolved=5, upserted=1, deleted=0)

    def due_tracks(self, _config, _now, limit=worker.BATCH_SIZE):
        return self.jobs[:limit]

    def remaining(self, _config, _now):
        return len(self.jobs)

    def evidence_for(self, ids):
        return {track_id: {'track_id': track_id, 'genres': 'Hardstyle'} for track_id in ids}

    #: When the stored priors were last recomputed; NOW means fresh, None means never.
    priors_at = NOW
    refolds = 0
    recomputes = 0
    refold_written = 0
    maintain_error = None

    def priors_updated_at(self):
        if self.maintain_error:
            raise self.maintain_error
        return self.priors_at

    def load_priors(self):
        return Priors()

    def recompute_priors(self, _now):
        self.recomputes += 1
        return Priors()

    def refold(self, _priors, _reliable):
        self.refolds += 1
        return refold.RefoldResult(rows=10, written=self.refold_written)

    def save(self, rows):
        self.saved.extend(rows)
        done = {row[0] for row in rows}
        self.jobs = [j for j in self.jobs if j['track_uid'] not in done]


class WorkerTest(unittest.TestCase):
    def make(self, store, settings, analyze=None, clock=None):
        statuses = []
        pools = []

        def pool_factory(size):
            pool = InlineExecutor()
            pools.append((size, pool))
            return pool

        w = worker.Worker(
            store,
            settings=lambda: settings,
            analyze_fn=analyze
            or (lambda j, _e: {'track_id': j['track_id'], 'ok': True, 'raw': 76.0, 'confidence': 0.8}),
            pool_factory=pool_factory,
            status=lambda progress, _config: statuses.append(progress.state),
            clock=clock or (lambda: 1000.0),
            now=lambda: NOW,
            stop=threading.Event(),
        )
        return w, statuses, pools

    def test_a_round_measures_folds_and_saves_newest_first(self):
        store = FakeStore([job(3), job(2), job(1)])
        w, statuses, _ = self.make(store, config())
        self.assertEqual(w.tick(), 0.0)
        self.assertEqual([row[0] for row in store.saved], ['uid-3', 'uid-2', 'uid-1'])
        self.assertEqual({row[2] for row in store.saved}, {152.0})
        self.assertEqual(statuses, ['running'])
        self.assertEqual(w.progress.analyzed, 3)

    def test_a_round_syncs_the_effective_bpm_of_what_it_measured(self):
        """Issue #141: a new measurement reaches library_track_effective_bpm within the round."""
        store = FakeStore([job(3), job(2), job(1)])
        w, _, _ = self.make(store, config(bpm_reliable_confidence=80))
        w.tick()
        self.assertEqual(store.synced, [(None, 0.8), ([3, 2, 1], 0.8)])
        self.assertEqual(w.progress.effective_tracks, 5)

    def test_the_full_sync_runs_every_interval_even_while_paused(self):
        store = FakeStore([])
        now = [1000.0]
        w, _, _ = self.make(store, config(bpm_analysis_paused=True), clock=lambda: now[0])
        w.tick()
        w.tick()
        self.assertEqual(store.synced, [(None, 0.75)])
        now[0] += worker.EFFECTIVE_SYNC_SECONDS
        w.tick()
        self.assertEqual(store.synced, [(None, 0.75), (None, 0.75)])

    def test_a_failed_sync_neither_stops_the_round_nor_waits_the_full_interval(self):
        store = FakeStore([job(1)])
        store.sync_error = RuntimeError('database gone')
        now = [1000.0]
        w, _, _ = self.make(store, config(), clock=lambda: now[0])
        with self.assertLogs('music-manager.bpm', level='ERROR'):
            w.tick()
        self.assertEqual(len(store.saved), 1)
        store.sync_error = None
        now[0] += worker.IDLE_SECONDS
        w.tick()
        self.assertEqual(store.synced[-1], (None, 0.75))

    def test_failures_are_counted_and_stored(self):
        store = FakeStore([job(2), job(1)])
        w, _, _ = self.make(
            store,
            config(),
            analyze=lambda j, _e: {
                'track_id': j['track_id'],
                'ok': j['track_id'] == 2,
                'raw': 150.0,
                'confidence': 1.0,
                'error': 'x',
            },
        )
        w.tick()
        self.assertEqual((w.progress.analyzed, w.progress.failed), (1, 1))
        self.assertEqual([row[1] for row in store.saved], ['ok', 'failed'])

    def test_an_empty_queue_idles_and_counts_once(self):
        store = FakeStore([])
        w, statuses, _ = self.make(store, config())
        self.assertEqual(w.tick(), worker.IDLE_SECONDS)
        self.assertEqual((statuses, w.progress.remaining), (['idle'], 0))

    def test_paused_and_disabled_do_no_work_and_resume_where_they_stopped(self):
        store = FakeStore([job(2), job(1)])
        settings = config(bpm_analysis_paused=True)
        w, statuses, _ = self.make(store, settings)
        self.assertEqual(w.tick(), worker.OFF_SECONDS)
        settings['bpm_analysis_paused'] = False
        settings['bpm_analysis_enabled'] = False
        self.assertEqual(w.tick(), worker.OFF_SECONDS)
        self.assertEqual(store.saved, [])
        settings['bpm_analysis_enabled'] = True
        w.tick()
        self.assertEqual(len(store.saved), 2)
        self.assertEqual(statuses, ['paused', 'disabled', 'running'])

    def test_the_pool_follows_the_workers_setting(self):
        store = FakeStore([job(i) for i in range(10, 0, -1)])
        settings = config()
        w, _, pools = self.make(store, settings)
        store.due_tracks = lambda _c, _n, limit=2: store.jobs[:2]
        w.tick()
        settings['bpm_analysis_workers'] = 4
        w.tick()
        self.assertEqual([size for size, _ in pools], [2, 4])
        self.assertTrue(pools[0][1].shut)
        w.close()
        self.assertTrue(pools[1][1].shut)

    def test_fresh_priors_are_loaded_and_everything_refolded_once_a_day(self):
        store = FakeStore([])
        now = [1000.0]
        w, _, _ = self.make(store, config(bpm_analysis_paused=True), clock=lambda: now[0])
        w.tick()
        self.assertEqual((store.recomputes, store.refolds), (0, 1))
        now[0] += 60
        w.tick()
        self.assertEqual(store.refolds, 1)
        now[0] += worker.PRIORS_SECONDS
        w.tick()
        self.assertEqual(store.refolds, 2)

    def test_missing_or_day_old_priors_are_recomputed_first(self):
        for stamp in (None, datetime(2026, 9, 27, 12, 0, 0)):
            store = FakeStore([])
            store.priors_at = stamp
            w, _, _ = self.make(store, config(bpm_analysis_paused=True))
            w.tick()
            self.assertEqual((store.recomputes, store.refolds), (1, 1))

    def test_a_refold_that_changed_rows_brings_the_effective_table_along(self):
        for written, expect_full_sync in ((3, True), (0, False)):
            store = FakeStore([])
            store.refold_written = written
            w, _, _ = self.make(store, config(bpm_analysis_paused=True))
            w._next_full_sync = 10**9  # pylint: disable=protected-access  # the full sync is not due
            w.tick()
            self.assertEqual(any(ids is None for ids, _ in store.synced), expect_full_sync)

    def test_a_failed_refold_is_retried_after_the_idle_interval(self):
        store = FakeStore([])
        store.maintain_error = RuntimeError('database down')
        now = [1000.0]
        w, _, _ = self.make(store, config(bpm_analysis_paused=True), clock=lambda: now[0])
        w.tick()
        store.maintain_error = None
        now[0] += worker.IDLE_SECONDS - 1
        w.tick()
        self.assertEqual(store.refolds, 0)
        now[0] += 2
        w.tick()
        self.assertEqual(store.refolds, 1)

    def test_run_survives_a_failed_round_and_stops_on_request(self):
        store = FakeStore([])
        w, _, _ = self.make(store, config())
        calls = []

        def tick():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError('database down')
            w.stop.set()
            return 0.0

        w.tick = tick
        w.stop.wait = lambda delay: False  # no real sleeping
        w.run()
        self.assertEqual(len(calls), 2)


class StatusTest(unittest.TestCase):
    def test_the_status_file_round_trips_into_health(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'state' / 'status.json'
            progress = worker.Progress(started=900.0, analyzed=100, failed=2, remaining=5000, state='running')
            progress.window = [(1000.0 - 1800, 200), (1000.0 - 600, 100)]
            worker.write_status(progress, config(), path=path, now=1000.0)
            read = status.read_status(path, now=1010.0)
        self.assertEqual((read['state'], read['analyzed'], read['remaining']), ('running', 100, 5000))
        self.assertEqual(read['rate_per_hour'], 600.0)
        self.assertEqual(read['eta_hours'], 8.3)
        self.assertFalse(read['stale'])
        entry = status.heartbeat_entry(read)
        self.assertEqual((entry['alive'], entry['last_tick_age_seconds']), (True, 10.0))

    def test_an_old_status_is_stale_and_a_missing_one_is_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'status.json'
            self.assertIsNone(status.read_status(path))
            self.assertIsNone(status.heartbeat_entry(None))
            path.write_text(json.dumps({'heartbeat_at': 0}))
            self.assertTrue(status.read_status(path, now=status.STALE_AFTER_SECONDS + 1)['stale'])
            path.write_text('[1, 2]')
            self.assertIsNone(status.read_status(path))

    def test_an_unwritable_status_path_is_not_fatal(self):
        worker.write_status(worker.Progress(), config(), path=Path('/proc/nope/status.json'), now=1.0)


if __name__ == '__main__':
    unittest.main()
