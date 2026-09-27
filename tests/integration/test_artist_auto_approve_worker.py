"""The scheduled artist evidence run's SQL (`EvidenceStore`) against a real MariaDB.

The unit tests (services/music_manager/tests/test_artist_auto_approve_worker.py) replace the
store; this proves the queries it replaces: which names a round picks (new before backlog,
never a decided, tagger-ruled, trackless or undone name), that a verdict is stored and
replaced, that applying approves exactly like the curation page and never over a decision
taken meanwhile, and the ledger. See docs/designs/artist-curation/technical.md,
"Scheduled evidence run".
"""

import pytest

from services.common.Helpers.ArtistEvidence import APPROVE, UNRESOLVED, Verdict
from services.music_manager import artist_auto_approve_worker as worker
from tests.integration.conftest import _connect, run_sql

pytestmark = pytest.mark.integration


@pytest.fixture(name='store')
def store_fixture(db):
    """An EvidenceStore on the test database, plus helpers to arrange the library."""
    return worker.EvidenceStore(connect=_connect)


def add_artist(db, name, titles=('Some Song',), legacy=False):
    """A library artist with one track per title; `legacy` grandfathers it."""
    with db.cursor() as cursor:
        cursor.execute('INSERT INTO library_artists (name) VALUES (%s)', (name,))
        artist_id = cursor.lastrowid
        for title in titles:
            cursor.execute('INSERT INTO library_tracks (title) VALUES (%s)', (title,))
            cursor.execute(
                'INSERT INTO library_track_artists (track_id, artist_id) VALUES (%s, %s)', (cursor.lastrowid, artist_id)
            )
        if legacy:
            cursor.execute('INSERT INTO rules_artist_legacy_trust (name) VALUES (%s)', (name,))
    return artist_id


def names(candidates):
    return [(c.name, c.new) for c in candidates]


def test_new_names_come_first_newest_first_then_the_backlog_by_tracks(db, store):
    add_artist(db, 'Old Small', legacy=True)
    add_artist(db, 'Old Big', titles=('A', 'B', 'C'), legacy=True)
    add_artist(db, 'New One')
    add_artist(db, 'New Two')
    found = store.candidates(max_names=10, backlog_slice=10, recheck_days=90)
    assert names(found) == [('New Two', True), ('New One', True), ('Old Big', False), ('Old Small', False)]
    assert names(store.candidates(max_names=3, backlog_slice=10, recheck_days=90))[-1] == ('Old Big', False)
    assert names(store.candidates(max_names=10, backlog_slice=0, recheck_days=90)) == [
        ('New Two', True),
        ('New One', True),
    ]


def test_decided_trackless_and_tagger_ruled_names_are_never_candidates(db, store):
    add_artist(db, 'Approved')
    add_artist(db, 'Ruled')
    add_artist(db, 'Trackless', titles=())
    add_artist(db, 'Open')
    run_sql(db, "INSERT INTO rules_artists (name, state, decided_by) VALUES ('Approved', 'white', 'user')")
    run_sql(db, "INSERT INTO rules_ignored_artists (name, corrected_name) VALUES ('ruled', 'Someone')")
    assert names(store.candidates(10, 10, 90)) == [('Open', True)]
    assert store.remaining(90) == 1


def test_a_current_verdict_takes_a_name_out_until_it_is_stale_or_incomplete(db, store):
    add_artist(db, 'Judged')
    add_artist(db, 'Flaky')
    round_id = store.start_round(dry_run=True)
    store.record_verdict('Judged', 'h1', Verdict(UNRESOLVED, None, {'matches': []}), round_id)
    store.record_verdict('Flaky', 'h2', Verdict('incomplete', None, {}), round_id)
    assert names(store.candidates(10, 10, 90)) == [('Flaky', True)]
    # An unresolved verdict older than the recheck window counts as no verdict.
    run_sql(db, "UPDATE rules_artist_evidence SET checked_at = NOW() - INTERVAL 100 DAY WHERE name = 'Judged'")
    assert {c.name for c in store.candidates(10, 10, 90)} == {'Judged', 'Flaky'}
    # Replacing a verdict keeps one row per name.
    store.record_verdict('Flaky', 'h2', Verdict(UNRESOLVED, None, {}), round_id)
    rows = run_sql(db, 'SELECT name, verdict, run_id FROM rules_artist_evidence ORDER BY name')
    assert [(r['name'], r['verdict']) for r in rows] == [('Flaky', 'unresolved'), ('Judged', 'unresolved')]


def test_titles_are_read_per_artist(db, store):
    first = add_artist(db, 'Angerfist', titles=('Raise Your Fist', 'Dance With The Wolves'))
    second = add_artist(db, 'Ran-D', titles=('Zombie',))
    titles = store.titles([first, second])
    assert sorted(titles[first]) == ['Dance With The Wolves', 'Raise Your Fist']
    assert titles[second] == ['Zombie']


def test_applying_approves_like_the_page_and_never_over_a_decision(db, store):
    add_artist(db, 'Angerfist')
    add_artist(db, 'Decided Meanwhile')
    run_sql(db, "INSERT INTO rules_ignored_artists (name, corrected_name) VALUES ('angerfist', NULL)")
    round_id = store.start_round(dry_run=False)
    for name in ('Angerfist', 'Decided Meanwhile'):
        store.record_verdict(name, 'h', Verdict(APPROVE, 'two-titles-one-act', {}), round_id)
    assert store.pending_approvals(10) == ['Angerfist', 'Decided Meanwhile']
    run_sql(db, "INSERT INTO rules_artists (name, state, decided_by) VALUES ('Decided Meanwhile', 'black', 'user')")

    assert store.apply_approvals(['Angerfist', 'Decided Meanwhile']) == ['Angerfist']

    decisions = {r['name']: r for r in run_sql(db, 'SELECT name, state, decided_by FROM rules_artists')}
    assert (decisions['Angerfist']['state'], decisions['Angerfist']['decided_by']) == ('white', 'auto-external')
    assert (decisions['Decided Meanwhile']['state'], decisions['Decided Meanwhile']['decided_by']) == ('black', 'user')
    # White is "no row" in the table the tagger acts on.
    assert not run_sql(db, "SELECT * FROM rules_ignored_artists WHERE name = 'angerfist'")
    assert store.pending_approvals(10) == []


def test_an_undone_approval_is_never_looked_up_or_applied_again(db, store):
    add_artist(db, 'Undone Act')
    round_id = store.start_round(dry_run=False)
    store.record_verdict('Undone Act', 'h', Verdict(APPROVE, 'two-titles-one-act', {}), round_id)
    store.apply_approvals(['Undone Act'])
    run_sql(db, "DELETE FROM rules_artists WHERE name = 'Undone Act'")  # the curator's undo
    run_sql(db, "UPDATE rules_artist_evidence SET policy = 'v0', checked_at = NOW() - INTERVAL 400 DAY")
    assert store.candidates(10, 10, 90) == []
    assert store.pending_approvals(10) == []


def test_the_ledger_records_a_round(db, store):
    assert store.seconds_since_last_round() is None
    round_id = store.start_round(dry_run=True)
    result = worker.RoundResult(dry_run=True, new_names=2, backlog_names=5, requests=30, failed_requests=1)
    result.verdicts[APPROVE] = 3
    store.finish_round(round_id, result)
    row = run_sql(db, 'SELECT * FROM rules_artist_evidence_runs')[0]
    assert (row['dry_run'], row['new_names'], row['backlog_names'], row['approved'], row['requests']) == (
        1,
        2,
        5,
        3,
        30,
    )
    assert row['finished_at'] is not None
    assert 0 <= store.seconds_since_last_round() < 60
