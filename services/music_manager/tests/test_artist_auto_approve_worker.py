"""The scheduled artist evidence run (`artist-auto-approve`): bounds, rate limits, stop, dry run.

The database is replaced by `FakeStore`, which records what a round writes, and the network
by `FakeSession`. The judgement itself is not faked: where a verdict matters the real
`ArtistEvidence.resolve` runs over canned catalogue answers. tests/integration/
test_artist_auto_approve_worker.py runs the SQL of `EvidenceStore` against MariaDB.
"""

import json
import logging
import threading
import unittest

import pytest

pytestmark = pytest.mark.mock_base('DatabaseConnector')

from services.common.Helpers import ArtistEvidence  # noqa: E402
from services.common.Helpers.ArtistEvidence import (  # noqa: E402
    APPROVE,
    DEEZER,
    INCOMPLETE,
    ITUNES,
    MUSICBRAINZ,
    SKIPPED,
    UNRESOLVED,
    Verdict,
)
from services.music_manager import artist_auto_approve_worker as worker  # noqa: E402
from services.music_manager import thread_registry  # noqa: E402

LOGGER = 'music-manager.artist-auto-approve'


def config(**overrides):
    """A validated settings snapshot, as `settings_snapshot` returns it."""
    base = worker.settings_snapshot({})
    base.update(overrides)
    return base


class FakeClock:
    """A monotonic clock that only moves when someone waits on it, or the test advances it."""

    def __init__(self, start=1000.0):
        self.now = start
        self.waits = []

    def __call__(self):
        return self.now

    def wait(self, seconds):
        self.waits.append(round(seconds, 3))
        self.now += seconds
        return False


class FakeResponse:
    """What `requests` returns: a status, a body and headers."""

    def __init__(self, status=200, body=None, headers=None):
        self.status_code = status
        self.text = body if isinstance(body, str) else json.dumps(body if body is not None else {})
        self.headers = headers or {}


class FakeSession:
    """Answers GETs from a list of responses per URL fragment, and records every URL asked."""

    def __init__(self, routes=None, default=None):
        self.routes = routes or {}
        self.default = default if default is not None else FakeResponse(200, {})
        self.urls = []

    def get(self, url, timeout=None):
        self.urls.append(url)
        for fragment, answers in self.routes.items():
            if fragment in url:
                # A sequence is answered in order; its last answer repeats.
                answer = answers if not isinstance(answers, list) else self._next(answers)
                if isinstance(answer, Exception):
                    raise answer
                return answer
        return self.default

    @staticmethod
    def _next(answers):
        return answers.pop(0) if len(answers) > 1 else answers[0]


class FakeStore:
    """Records what a round reads and writes, instead of MariaDB."""

    def __init__(self, candidates=(), titles=None, approvals=None, ignored=(), age=None):
        self._candidates = list(candidates)
        self._titles = titles or {}
        self._approvals = approvals
        self._ignored = set(ignored)
        self.age = age
        self.rounds = []
        self.finished = {}
        self.verdicts = {}
        self.applied = []
        self.candidate_args = None

    def seconds_since_last_round(self):
        return self.age

    def start_round(self, dry_run):
        self.rounds.append(dry_run)
        return len(self.rounds)

    def finish_round(self, round_id, result):
        self.finished[round_id] = result

    def candidates(self, max_names, backlog_slice, recheck_days):
        self.candidate_args = (max_names, backlog_slice, recheck_days)
        return self._candidates

    def remaining(self, recheck_days):
        return 42

    def titles(self, artist_ids):
        return {artist_id: self._titles.get(artist_id, []) for artist_id in artist_ids}

    def ignored_keys(self):
        return self._ignored

    def record_verdict(self, name, hashed, verdict, round_id):
        self.verdicts[name] = verdict

    def pending_approvals(self, limit):
        if self._approvals is not None:
            return list(self._approvals)[:limit]
        return [name for name, verdict in self.verdicts.items() if verdict.verdict == APPROVE][:limit]

    def apply_approvals(self, names):
        self.applied.extend(names)
        return list(names)


def deezer_act(name, titles, artist_id=7):
    """Canned Deezer routes for one exact-name act credited with `titles`."""
    return {
        'api.deezer.com/search/artist': FakeResponse(200, {'data': [{'id': artist_id, 'name': name, 'nb_fan': 10}]}),
        f'api.deezer.com/artist/{artist_id}/top': FakeResponse(200, {'data': [{'title': t} for t in titles]}),
        'api.deezer.com/search?': FakeResponse(200, {'data': []}),
    }


class SettingsTest(unittest.TestCase):
    def test_defaults_are_on_with_dry_run_and_a_bounded_daily_round(self):
        snapshot = worker.settings_snapshot({})
        self.assertEqual(
            snapshot,
            {
                'enabled': True,
                'dry_run': True,
                'interval_seconds': 24 * 3600,
                'backlog_slice': 300,
                'max_names': 1000,
                'max_seconds': 180 * 60,
                'recheck_days': 90,
            },
        )

    def test_nonsense_falls_back_and_strings_read_as_booleans(self):
        snapshot = worker.settings_snapshot(
            {
                'artist_auto_approve_dry_run': 'off',
                'artist_auto_approve_enabled': 'yes',
                'artist_auto_approve_max_names': 'lots',
                'artist_auto_approve_backlog_slice': 0,
                'artist_auto_approve_interval_hours': -3,
            }
        )
        self.assertFalse(snapshot['dry_run'])
        self.assertTrue(snapshot['enabled'])
        self.assertEqual(snapshot['max_names'], 1000)
        self.assertEqual(snapshot['backlog_slice'], 0, 'zero is a valid slice: new names only')
        self.assertEqual(snapshot['interval_seconds'], 24 * 3600)

    def test_the_schema_declares_every_setting_in_one_group(self):
        # The unit suite replaces services.common.config_store with a mock (mock_base), so the
        # real schema is loaded from its file under another name.
        import importlib.util
        import sys
        from pathlib import Path
        from unittest.mock import patch

        path = Path(__file__).resolve().parents[2] / 'common' / 'config_store.py'
        spec = importlib.util.spec_from_file_location('real_config_store_aa', path)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'real_config_store_aa': module}):
            spec.loader.exec_module(module)
        fields = {f.key: f for f in module._config_fields() if f.key.startswith('artist_auto_approve_')}
        self.assertEqual(
            {key.removeprefix('artist_auto_approve_'): f.default for key, f in fields.items()},
            dict(worker.DEFAULTS),
        )
        self.assertEqual({f.group for f in fields.values()}, {'Artist curation'})


class RateLimitedFetcherTest(unittest.TestCase):
    def test_requests_to_one_source_are_spaced_by_its_interval(self):
        clock = FakeClock()
        session = FakeSession(default=FakeResponse(200, {'ok': 1}))
        fetcher = worker.RateLimitedFetcher(session, clock=clock, wait=clock.wait)
        fetcher.get(MUSICBRAINZ, 'https://musicbrainz.org/a')
        fetcher.get(MUSICBRAINZ, 'https://musicbrainz.org/b')
        fetcher.get(ITUNES, 'https://itunes.apple.com/c')
        fetcher.get(ITUNES, 'https://itunes.apple.com/d')
        # The first request to a source never waits; the second waits its full interval,
        # because the fake clock only moves while waiting.
        self.assertEqual(clock.waits, [ArtistEvidence.MIN_INTERVAL[MUSICBRAINZ], ArtistEvidence.MIN_INTERVAL[ITUNES]])
        self.assertEqual(fetcher.requests, 4)

    def test_time_already_spent_elsewhere_counts_towards_the_interval(self):
        clock = FakeClock()
        fetcher = worker.RateLimitedFetcher(FakeSession(default=FakeResponse(200, {})), clock=clock, wait=clock.wait)
        fetcher.get(MUSICBRAINZ, 'https://musicbrainz.org/a')
        clock.now += 0.6
        fetcher.get(MUSICBRAINZ, 'https://musicbrainz.org/b')
        self.assertEqual(clock.waits, [0.5])

    def test_an_answer_is_asked_once_per_round(self):
        clock = FakeClock()
        session = FakeSession(default=FakeResponse(200, {'x': 1}))
        fetcher = worker.RateLimitedFetcher(session, clock=clock, wait=clock.wait)
        self.assertEqual(fetcher.get(DEEZER, 'https://api.deezer.com/q'), {'x': 1})
        self.assertEqual(fetcher.get(DEEZER, 'https://api.deezer.com/q'), {'x': 1})
        self.assertEqual(len(session.urls), 1)

    def test_a_503_backs_off_and_is_retried(self):
        clock = FakeClock()
        session = FakeSession(
            {'musicbrainz': [FakeResponse(503, 'busy', {'Retry-After': '4'}), FakeResponse(200, {'fine': True})]}
        )
        fetcher = worker.RateLimitedFetcher(session, clock=clock, wait=clock.wait)
        self.assertEqual(fetcher.get(MUSICBRAINZ, 'https://musicbrainz.org/x'), {'fine': True})
        self.assertIn(4.0, clock.waits)
        self.assertEqual(fetcher.requests, 2)

    def test_a_deezer_quota_error_is_not_an_answer(self):
        clock = FakeClock()
        session = FakeSession(default=FakeResponse(200, {'error': {'message': 'Quota limit exceeded'}}))
        fetcher = worker.RateLimitedFetcher(session, clock=clock, wait=clock.wait, retries=2)
        self.assertIsNone(fetcher.get(DEEZER, 'https://api.deezer.com/q'))
        self.assertEqual(fetcher.failed, 1)
        self.assertEqual(fetcher.cache, {})

    def test_a_stop_during_a_pause_ends_the_fetch_without_a_request(self):
        stop = threading.Event()
        clock = FakeClock()

        def wait(seconds):
            stop.set()
            return True

        session = FakeSession(default=FakeResponse(200, {}))
        fetcher = worker.RateLimitedFetcher(session, clock=clock, wait=wait)
        fetcher.get(MUSICBRAINZ, 'https://musicbrainz.org/a')
        self.assertIsNone(fetcher.get(MUSICBRAINZ, 'https://musicbrainz.org/b'))
        self.assertTrue(fetcher.stopped)
        self.assertEqual(len(session.urls), 1)
        # Once stopped, nothing more goes out.
        self.assertIsNone(fetcher.get(DEEZER, 'https://api.deezer.com/q'))
        self.assertEqual(len(session.urls), 1)


class RoundTest(unittest.TestCase):
    def fetcher(self, routes=None):
        clock = FakeClock()
        return worker.RateLimitedFetcher(FakeSession(routes or {}), clock=clock, wait=clock.wait), clock

    def test_the_decision_rules_are_the_tools_own(self):
        from tools import artist_auto_approve as tool

        self.assertIs(tool.resolve, ArtistEvidence.resolve)
        self.assertIs(tool.score_artist, ArtistEvidence.score_artist)
        self.assertIs(run_round_default('resolver'), ArtistEvidence.resolve)

    def test_two_titles_on_one_act_is_an_approval_through_the_real_rules(self):
        titles = ['Feel The Electricity (Original Mix)', 'Raise Your Fist (Extended Mix)']
        fetcher, clock = self.fetcher(deezer_act('Angerfist', ['Feel The Electricity', 'Raise Your Fist']))
        store = FakeStore([worker.Candidate(1, 'Angerfist', True)], titles={1: titles})
        refreshed = []
        result = worker.run_round(
            config(dry_run=False), store=store, fetcher=fetcher, clock=clock, refresh=lambda: refreshed.append(1)
        )
        self.assertEqual(store.verdicts['Angerfist'].verdict, APPROVE)
        self.assertEqual(store.verdicts['Angerfist'].rule, 'two-titles-one-act')
        self.assertEqual(store.applied, ['Angerfist'])
        self.assertEqual(refreshed, [1])
        self.assertEqual((result.new_names, result.applied), (1, 1))

    def test_one_title_on_one_store_is_not_enough(self):
        fetcher, clock = self.fetcher(deezer_act('Holly', ['Feel The Electricity']))
        store = FakeStore([worker.Candidate(1, 'Holly', False)], titles={1: ['Feel The Electricity', 'Other Song']})
        worker.run_round(config(dry_run=False), store=store, fetcher=fetcher, clock=clock, refresh=lambda: None)
        self.assertEqual(store.verdicts['Holly'].verdict, UNRESOLVED)
        self.assertEqual(store.applied, [])

    def test_a_brand_shaped_name_is_skipped_without_a_request(self):
        fetcher, clock = self.fetcher()
        store = FakeStore([worker.Candidate(1, 'DediKted Festival', True)], titles={1: ['Anthem One', 'Anthem Two']})
        worker.run_round(config(dry_run=False), store=store, fetcher=fetcher, clock=clock, refresh=lambda: None)
        self.assertEqual(store.verdicts['DediKted Festival'].verdict, SKIPPED)
        self.assertEqual(fetcher.session.urls, [])

    def test_a_name_the_tagger_already_rewrites_is_skipped_without_a_request(self):
        fetcher, clock = self.fetcher()
        store = FakeStore([worker.Candidate(1, 'Dr.Peacock', True)], titles={1: ['A Song']}, ignored={'dr peacock'})
        worker.run_round(config(dry_run=False), store=store, fetcher=fetcher, clock=clock, refresh=lambda: None)
        self.assertEqual(store.verdicts['Dr.Peacock'].rule, worker.TAGGER_RULE)
        self.assertEqual(fetcher.session.urls, [])

    def test_dry_run_stores_verdicts_but_approves_nothing(self):
        fetcher, clock = self.fetcher()
        store = FakeStore(
            [worker.Candidate(1, 'Angerfist', True)], titles={1: ['A', 'B']}, approvals=['Angerfist', 'Earlier Act']
        )
        refreshed = []
        with self.assertLogs(LOGGER, level='INFO') as logs:
            result = worker.run_round(
                config(dry_run=True),
                store=store,
                fetcher=fetcher,
                clock=clock,
                resolver=lambda *a: Verdict(APPROVE, 'two-titles-one-act', {}),
                refresh=lambda: refreshed.append(1),
            )
        self.assertEqual(store.applied, [])
        self.assertEqual(refreshed, [])
        self.assertEqual(result.approvable, 2)
        self.assertEqual(store.rounds, [True])
        self.assertEqual(len([r for r in logs.records if r.levelno == logging.INFO]), 1, 'one summary per round')
        self.assertIn('dry run, 2 approvable', logs.output[0])

    def test_turning_dry_run_off_applies_what_earlier_dry_runs_judged(self):
        fetcher, clock = self.fetcher()
        store = FakeStore([], approvals=['Earlier Act', 'Other Act'], ignored={'other act'})
        result = worker.run_round(
            config(dry_run=False), store=store, fetcher=fetcher, clock=clock, refresh=lambda: None
        )
        self.assertEqual(store.applied, ['Earlier Act'], 'a name that got a tagger rule since stays out')
        self.assertEqual(result.applied, 1)

    def test_the_round_stops_at_its_time_bound_and_says_so(self):
        fetcher, clock = self.fetcher()
        names = [worker.Candidate(i, f'Name {i}', False) for i in range(10)]
        store = FakeStore(names)

        def slow_resolver(*_args):
            clock.now += 60
            return Verdict(UNRESOLVED, None, {})

        with self.assertLogs(LOGGER, level='INFO') as logs:
            result = worker.run_round(
                config(max_seconds=150), store=store, fetcher=fetcher, clock=clock, resolver=slow_resolver
            )
        self.assertEqual(len(store.verdicts), 3)
        self.assertTrue(result.stopped_early)
        self.assertTrue(store.finished[1].stopped_early)
        self.assertIn('stopped at its bound', logs.output[0])

    def test_the_round_passes_its_bounds_to_the_candidate_query(self):
        fetcher, clock = self.fetcher()
        store = FakeStore([])
        worker.run_round(
            config(max_names=50, backlog_slice=20, recheck_days=7), store=store, fetcher=fetcher, clock=clock
        )
        self.assertEqual(store.candidate_args, (50, 20, 7))

    def test_a_stop_mid_name_stores_nothing_for_it(self):
        stop = threading.Event()
        clock = FakeClock()

        def wait(_seconds):
            stop.set()
            return True

        session = FakeSession(default=FakeResponse(200, {'data': []}))
        fetcher = worker.RateLimitedFetcher(session, clock=clock, wait=wait)
        store = FakeStore(
            [worker.Candidate(1, 'First Act', True), worker.Candidate(2, 'Second Act', True)],
            titles={1: ['Some Long Title'], 2: ['Another Long Title']},
        )
        result = worker.run_round(config(), store=store, fetcher=fetcher, clock=clock, stop=stop)
        # The first name asks each source once, which never waits; the second name's first
        # request has to wait its interval, and that wait is where the stop arrives.
        self.assertEqual(list(store.verdicts), ['First Act'])
        self.assertTrue(result.stopped_early)

    def test_a_failing_lookup_skips_the_name_not_the_round(self):
        fetcher, clock = self.fetcher()
        store = FakeStore([worker.Candidate(1, 'Broken', True), worker.Candidate(2, 'Fine', True)])

        def resolver(_fetcher, name, *_rest):
            if name == 'Broken':
                raise ValueError('bad json')
            return Verdict(INCOMPLETE, None, {})

        worker.run_round(config(), store=store, fetcher=fetcher, clock=clock, resolver=resolver)
        self.assertEqual(list(store.verdicts), ['Fine'])


def run_round_default(name):
    """The default of one of run_round's keyword arguments."""
    import inspect

    return inspect.signature(worker.run_round).parameters[name].default


class CandidatesBoundTest(unittest.TestCase):
    """`EvidenceStore.candidates` fills the round with new names first and the backlog after, never past max."""

    def store(self, new_count, backlog_count):
        store = worker.EvidenceStore(connect=lambda: None)
        calls = []

        def rows(sql, params=()):
            calls.append((sql, params))
            limit = params[-1]
            count = new_count if sql is worker.NEW_NAMES_SQL else backlog_count
            return [{'id': i, 'name': f'n{i}'} for i in range(min(count, limit))]

        store._rows = rows  # type: ignore[method-assign]
        return store, calls

    def test_new_names_first_then_the_slice(self):
        store, calls = self.store(new_count=3, backlog_count=1000)
        found = store.candidates(max_names=1000, backlog_slice=300, recheck_days=90)
        self.assertEqual(sum(c.new for c in found), 3)
        self.assertEqual(sum(not c.new for c in found), 300)
        self.assertEqual(calls[1][1][-1], 300)

    def test_the_slice_shrinks_to_what_max_leaves(self):
        store, calls = self.store(new_count=990, backlog_count=1000)
        found = store.candidates(max_names=1000, backlog_slice=300, recheck_days=90)
        self.assertEqual(len(found), 1000)
        self.assertEqual(calls[1][1][-1], 10)

    def test_a_burst_of_new_names_leaves_no_room_for_the_backlog(self):
        store, calls = self.store(new_count=5000, backlog_count=1000)
        found = store.candidates(max_names=1000, backlog_slice=300, recheck_days=90)
        self.assertEqual(len(found), 1000)
        self.assertTrue(all(c.new for c in found))
        self.assertEqual(len(calls), 1, 'no backlog query at all')


class TickTest(unittest.TestCase):
    def test_switched_off_does_nothing(self):
        store = FakeStore(age=None)
        ran = []
        delay = worker.auto_approve_tick(
            {'artist_auto_approve_enabled': False}, store=store, round_runner=lambda *a, **k: ran.append(1)
        )
        self.assertEqual(ran, [])
        self.assertEqual(delay, worker.CHECK_EVERY_SECONDS)

    def test_a_round_is_due_on_the_first_check_and_after_the_interval(self):
        ran = []
        for age in (None, 24 * 3600, 30 * 3600):
            worker.auto_approve_tick(
                {}, store=FakeStore(age=age), round_runner=lambda *a, _age=age, **k: ran.append(_age)
            )
        self.assertEqual(ran, [None, 24 * 3600, 30 * 3600])

    def test_not_due_waits_until_it_is_but_checks_at_least_hourly(self):
        ran = []
        runner = lambda *a, **k: ran.append(1)  # noqa: E731
        self.assertEqual(worker.auto_approve_tick({}, store=FakeStore(age=24 * 3600 - 600), round_runner=runner), 600)
        self.assertEqual(worker.auto_approve_tick({}, store=FakeStore(age=60), round_runner=runner), 3600)
        self.assertEqual(ran, [])


class LoopTest(unittest.TestCase):
    def setUp(self):
        thread_registry.reset()

    def tearDown(self):
        thread_registry.reset()

    def test_the_loop_ends_when_its_stop_event_is_set(self):
        stop = threading.Event()
        ticks = []

        def tick():
            ticks.append(1)
            stop.set()
            return 0

        original = worker.auto_approve_tick
        worker.auto_approve_tick = tick
        try:
            worker.run_artist_auto_approve(stop)
        finally:
            worker.auto_approve_tick = original
        self.assertEqual(ticks, [1])

    def test_it_registers_a_daily_heartbeat_window_for_health(self):
        stop = threading.Event()
        stop.set()
        worker.run_artist_auto_approve(stop)
        beat = thread_registry._heartbeats[worker.THREAD_NAME]
        self.assertEqual(beat.stale_after, 72 * 3600)
