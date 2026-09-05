"""Covers scripts/feeds_dryrun.py.

The script is what lets the feed policy numbers (the seven-day radar window, the thirty places,
the ten-minute song ceiling) be chosen from a real funnel instead of guessed -- see
docs/designs/feeds/technical.md. It must not touch a database at import time, loaded here the same
way BackfillReleaseDatesTest.py loads its script: by path, as a plain module.
"""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'feeds_dryrun.py'
spec = importlib.util.spec_from_file_location('feeds_dryrun', SCRIPT)
dryrun = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dryrun)


def test_window_override_reaches_the_policy():
    policy = dryrun.policy_for('release-radar', window=30, size=None, max_seconds=None)
    assert policy.release_window_days == 30
    assert policy.size == 30


def test_an_unknown_slug_is_refused():
    try:
        dryrun.policy_for('nope', window=None, size=None, max_seconds=None)
    except SystemExit:
        return
    raise AssertionError('unknown slug should exit')


def test_the_funnel_is_printed_in_order(capsys):
    dryrun.print_report(
        shares={'uptempo': 0.6, '__tail__': 0.4},
        funnel={'candidates': 120, 'bucketed': 118, 'allocated': 30, 'capped': 28, 'emitted': 28},
        tracks=[
            {
                'id': 1,
                'title': 'X',
                'artist': 'Y',
                'bucket': 'uptempo',
                'reason': 'genre',
                'release_date': '2026-09-01',
            }
        ],
    )
    out = capsys.readouterr().out
    assert out.index('candidates') < out.index('emitted')
    assert 'uptempo' in out


def test_a_smaller_limit_truncates_the_tracks():
    tracks = [{'id': 1}, {'id': 2}, {'id': 3}]
    assert dryrun._limited(tracks, 2) == [{'id': 1}, {'id': 2}]


def test_no_limit_returns_every_track():
    tracks = [{'id': 1}, {'id': 2}, {'id': 3}]
    assert dryrun._limited(tracks, None) == tracks


def test_a_limit_of_zero_returns_nothing():
    """The bug this guards: `0 if limit else tracks` reads a limit of zero as falsy and returns
    every track -- the opposite of what `--limit 0` says. Only `is not None` tells "not given"
    apart from "given as zero"."""
    tracks = [{'id': 1}, {'id': 2}, {'id': 3}]
    assert dryrun._limited(tracks, 0) == []
