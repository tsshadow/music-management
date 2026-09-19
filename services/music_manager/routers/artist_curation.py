"""Artist curation: which names in `library_artists` are artists at all.

The table fills itself -- the scanner inserts every artist string a tagger rule ever
produced -- so roughly one name in ten is a real artist and the rest is promo noise,
sentences, catalogue ids and misspellings. This is the genre curation model
(`/api/rules/genres` in management.py) applied to that table, with one difference in
storage: the tagger already has a decision table for artists, `rules_ignored_artists`
(a name without a correction is dropped from a tag, one with a correction is
rewritten), and ten tagger rules read it. So rather than teach them a new table, a
decision made here is *mirrored* into that one -- `rules_artists` is the record of the
decision (state, who, when), `rules_ignored_artists` is what the tagger acts on, and
`decide()` keeps the two in step.

Three things stay separate, as `docs/designs/artist-curation/` requires: the raw name
(`library_artists`), the derived proposal (`rules_artist_proposals`, rewritten by
every analysis run) and the human decision (`rules_artists`, which an analysis run
never touches). A proposal is only ever a suggestion the page shows next to the name;
nothing here applies one on its own.

The analysis is `ArtistNameAnalyzer` over every undecided name, with the *approved*
names as its dictionary -- not a bootstrap seeded from the data's own shape, which is
how the dry run came to propose `Rbr` -> `RBR ©`. Approving an artist is therefore
what makes the next run find its polluted variants. Two things the analyzer does not
do are added here: normalised-name collisions (`Dr. Peacock` / `Dr.Peacock`) resolve
to the spelling with the most tracks, and a rewrite that would point a name at a
spelling with fewer tracks than itself is downgraded to a queue entry, because that
direction is almost always the wrong one.
"""

import json
import logging
import re
import uuid
from collections import defaultdict

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from services.common.config_store import ConfigStore as Settings
from services.common.Helpers.ArtistNameAnalyzer import (
    REWRITE,
    UNKNOWN,
    AnalyzerConfig,
    ArtistNameAnalyzer,
    normalize,
)
from services.common.Helpers.RescanInvalidator import invalidate_quietly
from services.music_manager import curation_rules
from services.music_manager.database import get_db_connection
from services.music_manager.rbac import require_permission
from services.music_manager.routers.jobs import job_manager

router = APIRouter(tags=['artist-curation'])
logger = logging.getLogger('music-manager.artist-curation')

READ = Depends(require_permission('music.read'))
WRITE = Depends(require_permission('rules.manage'))

WHITE = 'white'
BLACK = 'black'
STATES = (WHITE, BLACK)
#: What the list endpoint filters on. `unknown` is the queue: names nobody decided.
FILTERS = ('unknown', WHITE, BLACK, 'all')
PROPOSAL_KINDS = ('keep', 'rewrite', 'split', 'reject', 'unknown')
SORTS = ('tracks', 'name')

#: One list request never returns more than this. The queue is tens of thousands of
#: names; the page pages through it, and a bulk decision carries explicit names.
MAX_LIMIT = 500
#: Names one decide call may carry. Each one marks files for a retag, so this is a
#: ceiling on how much tagger work one click can queue.
MAX_DECISION_NAMES = 500
#: The config key an admin can tune the analyzer with (Beheer -> Configuratie).
ANALYZER_CONFIG_KEY = 'artist_curation_analyzer'


class DecisionRequest(BaseModel):
    names: list[str]
    state: str
    canonical_name: str | None = None
    #: Who to record as the decider. Only honoured for the system key: a script that
    #: approves on external evidence (tools/artist_auto_approve.py) signs its rows so
    #: the page shows `auto-external` rather than `system`, and an undo can find them.
    decided_by: str | None = None


def _connect():
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='No database connection')
    return conn


def _decided_by(auth: dict, requested: str | None = None) -> str:
    user = auth.get('user')
    if isinstance(user, dict) and user.get('username'):
        return str(user['username'])[:64]
    if requested and auth.get('type') == 'system':
        return requested.strip()[:64]
    return str(auth.get('type', 'human'))[:64]


# ----------------------------------------------------------------------------- read


TRACK_COUNTS = 'SELECT artist_id, COUNT(DISTINCT track_id) AS track_count FROM library_track_artists GROUP BY artist_id'

ROW_COLUMNS = """
    a.id, COALESCE(a.name, r.name) AS name,
    COALESCE(tc.track_count, 0) AS track_count,
    r.state, r.canonical_name,
    CAST(r.decided_at AS CHAR) AS decided_at, r.decided_by,
    p.kind AS proposal_kind, p.target AS proposal_target,
    p.evidence AS proposal_evidence, p.confidence AS proposal_confidence
"""


def _parse_evidence(row: dict) -> dict:
    row = dict(row)
    raw = row.get('proposal_evidence')
    try:
        row['proposal_evidence'] = json.loads(raw) if raw else []
    except (TypeError, ValueError):
        row['proposal_evidence'] = [str(raw)]
    if not row.get('state'):
        row['state'] = 'unknown'
    return row


@router.get('')
def list_artists(
    state: str = 'unknown',
    q: str | None = None,
    proposal: str | None = None,
    sort: str = 'tracks',
    limit: int = 200,
    offset: int = 0,
    _auth: dict = READ,
):
    """Artists by curation state, the ones touching most tracks first.

    `state=unknown` is the queue. `proposal` narrows it to what the last analysis
    proposed (`reject`, `rewrite`, ...), which is how a curator works through a class
    of names at a time rather than the whole tail. Decided names that have since left
    `library_artists` (a rebuild, a retag that removed them) still list under their
    state: the decision is the durable thing.
    """
    if state not in FILTERS:
        raise HTTPException(status_code=400, detail=f"state must be one of {', '.join(FILTERS)}")
    if proposal is not None and proposal not in PROPOSAL_KINDS:
        raise HTTPException(status_code=400, detail=f"proposal must be one of {', '.join(PROPOSAL_KINDS)}")
    if sort not in SORTS:
        raise HTTPException(status_code=400, detail=f"sort must be one of {', '.join(SORTS)}")
    limit = max(1, min(int(limit), MAX_LIMIT))
    offset = max(0, int(offset))

    # Decided names are anchored on the decision table, undecided ones on the library:
    # a decision outlives the library row, and a library row without a decision is by
    # definition the queue.
    if state in STATES:
        base = (
            f'FROM rules_artists r LEFT JOIN library_artists a ON a.name = r.name '
            f'LEFT JOIN ({TRACK_COUNTS}) tc ON tc.artist_id = a.id '
            'LEFT JOIN rules_artist_proposals p ON p.name = r.name'
        )
        where = ['r.state = %s']
        params: list = [state]
    else:
        base = (
            f'FROM library_artists a LEFT JOIN rules_artists r ON r.name = a.name '
            f'LEFT JOIN ({TRACK_COUNTS}) tc ON tc.artist_id = a.id '
            'LEFT JOIN rules_artist_proposals p ON p.name = a.name'
        )
        where = ['r.name IS NULL'] if state == 'unknown' else []
        params = []
    if q:
        where.append('COALESCE(a.name, r.name) LIKE %s')
        params.append(f'%{q}%')
    if proposal:
        where.append('p.kind = %s')
        params.append(proposal)
    where_sql = f" WHERE {' AND '.join(where)}" if where else ''
    order = 'track_count DESC, name' if sort == 'tracks' else 'name'

    conn = _connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute(f'SELECT COUNT(*) AS total {base}{where_sql}', params)
            total = cursor.fetchone()['total']
            cursor.execute(
                f'SELECT {ROW_COLUMNS} {base}{where_sql} ORDER BY {order} LIMIT %s OFFSET %s',
                params + [limit, offset],
            )
            rows = [_parse_evidence(row) for row in cursor.fetchall()]
            return {'total': total, 'rows': rows, 'limit': limit, 'offset': offset}
    finally:
        conn.close()


@router.get('/summary')
def summary(_auth: dict = READ):
    """How big the job is: names per state, proposals per kind, and when the analysis ran."""
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) AS n FROM library_artists')
            in_library = cursor.fetchone()['n']
            cursor.execute('SELECT state, COUNT(*) AS n FROM rules_artists GROUP BY state')
            decided = {row['state']: row['n'] for row in cursor.fetchall()}
            cursor.execute(
                'SELECT COUNT(*) AS n FROM library_artists a LEFT JOIN rules_artists r ON r.name = a.name '
                'WHERE r.name IS NULL'
            )
            unknown = cursor.fetchone()['n']
            cursor.execute(
                'SELECT p.kind, COUNT(*) AS n FROM rules_artist_proposals p '
                'LEFT JOIN rules_artists r ON r.name = p.name WHERE r.name IS NULL GROUP BY p.kind'
            )
            proposals = {row['kind']: row['n'] for row in cursor.fetchall()}
            cursor.execute('SELECT CAST(MAX(analyzed_at) AS CHAR) AS analyzed_at FROM rules_artist_proposals')
            analyzed_at = (cursor.fetchone() or {}).get('analyzed_at')
            return {
                'in_library': in_library,
                'unknown': unknown,
                WHITE: decided.get(WHITE, 0),
                BLACK: decided.get(BLACK, 0),
                'proposals': proposals,
                'analyzed_at': analyzed_at,
            }
    finally:
        conn.close()


# ----------------------------------------------------------------------------- decide


def _upsert_decision(cursor, name: str, state: str, canonical: str | None, decided_by: str) -> None:
    cursor.execute(
        'INSERT INTO rules_artists (name, state, canonical_name, decided_at, decided_by) '
        'VALUES (%s, %s, %s, NOW(), %s) '
        'ON DUPLICATE KEY UPDATE state = VALUES(state), canonical_name = VALUES(canonical_name), '
        'decided_at = NOW(), decided_by = VALUES(decided_by)',
        (name, state, canonical, decided_by),
    )


def _mirror_to_tagger(cursor, name: str, state: str, canonical: str | None) -> None:
    """Keep `rules_ignored_artists` saying what the decision says.

    Black without a correction is "drop from the tag", black with one is "rewrite",
    and white is "leave alone" -- which for that table means no row at all. Matched
    case-insensitively because `FilterTableHelper` matches that way too, so a row
    left behind under another casing would still fire.
    """
    cursor.execute('SELECT id FROM rules_ignored_artists WHERE LOWER(name) = LOWER(%s)', (name,))
    existing = cursor.fetchone()
    if state == WHITE:
        if existing:
            cursor.execute('DELETE FROM rules_ignored_artists WHERE LOWER(name) = LOWER(%s)', (name,))
        return
    if existing:
        cursor.execute(
            'UPDATE rules_ignored_artists SET corrected_name = %s WHERE LOWER(name) = LOWER(%s)',
            (canonical, name),
        )
    else:
        cursor.execute('INSERT INTO rules_ignored_artists (name, corrected_name) VALUES (%s, %s)', (name, canonical))


@router.post('/decide')
def decide(request: DecisionRequest, auth: dict = WRITE):
    """Approve or reject names, optionally rewriting them to one approved spelling.

    Several names at once because the queue is worked in classes -- every `reject`
    proposal on a page, every variant of one artist. A correction implies the target
    is an artist: a `canonical_name` that has no decision yet is approved in the same
    call, so `Dr.Peacock -> Dr. Peacock` is one action rather than two. A black target
    is refused -- rewriting one problem into another is the thing this must not do.
    """
    if request.state not in STATES:
        raise HTTPException(status_code=400, detail=f'state must be {WHITE} or {BLACK}')
    names = []
    for raw in request.names:
        name = (raw or '').strip()
        if name and name not in names:
            names.append(name)
    if not names:
        raise HTTPException(status_code=400, detail='No names given')
    if len(names) > MAX_DECISION_NAMES:
        raise HTTPException(status_code=400, detail=f'At most {MAX_DECISION_NAMES} names per decision')
    canonical = (request.canonical_name or '').strip() or None
    if canonical and request.state == WHITE:
        raise HTTPException(status_code=400, detail='An approved name keeps its own spelling; a correction rejects it')
    if canonical and canonical.lower() in {name.lower() for name in names}:
        raise HTTPException(status_code=400, detail='A name cannot be its own correction')

    decided_by = _decided_by(auth, request.decided_by)
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            if canonical:
                cursor.execute('SELECT state FROM rules_artists WHERE name = %s', (canonical,))
                target = cursor.fetchone()
                if target and target['state'] == BLACK:
                    raise HTTPException(status_code=400, detail=f"'{canonical}' is rejected; pick an approved name")
                if not target:
                    _upsert_decision(cursor, canonical, WHITE, None, decided_by)
                    _mirror_to_tagger(cursor, canonical, WHITE, None)
            for name in names:
                _upsert_decision(cursor, name, request.state, canonical, decided_by)
                _mirror_to_tagger(cursor, name, request.state, canonical)
            conn.commit()
    finally:
        conn.close()

    # The running tagger holds a preloaded copy of rules_ignored_artists; without this
    # it keeps writing the old name until a restart, retag included.
    curation_rules.refresh(curation_rules.ARTIST_REDIRECT_HELPER)
    if request.state == BLACK:
        # Only a rejection changes what a file should carry; an approval leaves the
        # tag as it is, so there is nothing to retag for. Exact: the files that change
        # are the ones carrying the name today. The wide match the rule endpoints use
        # would turn a rejected '001' into a retag of every path with a catalogue number.
        for name in names:
            invalidate_quietly(name, 'artist_decision', exact=True)
    return {'status': 'ok', 'decided': len(names), 'canonical_name': canonical}


@router.delete('/{name:path}')
def undo(name: str, _auth: dict = WRITE):
    """Forget a decision: the name goes back to the queue and the tagger stops acting on it."""
    name = (name or '').strip()
    if not name:
        raise HTTPException(status_code=400, detail='No name given')
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute('DELETE FROM rules_artists WHERE name = %s', (name,))
            removed = cursor.rowcount
            cursor.execute('DELETE FROM rules_ignored_artists WHERE LOWER(name) = LOWER(%s)', (name,))
            conn.commit()
    finally:
        conn.close()
    if not removed:
        raise HTTPException(status_code=404, detail='No decision for that name')
    curation_rules.refresh(curation_rules.ARTIST_REDIRECT_HELPER)
    return {'status': 'ok'}


# ----------------------------------------------------------------------------- analyze


def _analyzer_config() -> AnalyzerConfig:
    """The configured thresholds, or the defaults when the setting is missing or not a dict."""
    value = Settings().get(ANALYZER_CONFIG_KEY, None)
    return AnalyzerConfig.from_dict(value if isinstance(value, dict) else None)


#: Honorifics a name is the same artist without. `DJ Angerfist` and `Angerfist` are one
#: act; so are `MC Tha Watcher` and `Tha Watcher`. Only a leading token, only these
#: two: `DJ Mag` stays what it is because nothing called `Mag` exists to merge into,
#: and the merge is advice with its reasoning shown, never a silent rewrite.
MERGE_PREFIXES = re.compile(r'^(dj|mc) ')
#: The same prefix on the raw spelling, for asking the analyzer about the bare name.
RAW_MERGE_PREFIXES = re.compile(r'^(dj|mc)[\s.\-]+', re.IGNORECASE)


def merge_key(name: str) -> str:
    """The key two spellings of one artist share: normalised, minus a leading DJ/MC."""
    return MERGE_PREFIXES.sub('', normalize(name))


def collision_targets(names_with_tracks: dict) -> dict:
    """Names that are the same artist ignoring case, accents, punctuation and a DJ/MC prefix.

    Returns `{variant: winner}` for every variant that is not the winner of its group.
    The winner is the spelling with the most tracks; on a tie the shortest, then the
    alphabetically first, so the answer is stable between runs.

    @param names_with_tracks: `{name: track_count}` over the names to group.
    """
    groups: dict = defaultdict(list)
    for name, tracks in names_with_tracks.items():
        key = merge_key(name)
        if key:
            groups[key].append((name, tracks))
    targets = {}
    for members in groups.values():
        if len(members) < 2:
            continue
        winner = sorted(members, key=lambda item: (-item[1], len(item[0]), item[0]))[0][0]
        for name, _tracks in members:
            if name != winner:
                targets[name] = winner
    return targets


def propose_all(
    undecided: dict, approved: list, counts: dict | None = None, config: AnalyzerConfig | None = None
) -> dict:
    """Every undecided name's proposal, as `{name: Proposal}`.

    Pure: no database. The collision pass runs first because it needs no dictionary,
    and the most-tracks-wins guard runs last because the analyzer cannot know track
    counts. Kept separate from the job so it can be tested on a dict.

    @param undecided: `{name: track_count}` for the names to propose on.
    @param approved: the dictionary -- names a human approved.
    @param counts: track counts for names outside `undecided` (the approved ones),
        so the guard can compare against a rewrite target; defaults to `undecided`.
    """
    analyzer = ArtistNameAnalyzer(approved, config)
    collisions = collision_targets(undecided)
    tracks_of = {**(counts or {}), **undecided}
    proposals = {}
    for name, tracks in undecided.items():
        proposal = analyzer.propose(name)
        if proposal.kind == UNKNOWN and merge_key(name) != normalize(name):
            # `DJ Angerfist` against an approved `Angerfist`: the analyzer's fuzzy match
            # does not reach a two-letter prefix on a short name, so ask it about the
            # bare name and keep its answer when that is a match.
            bare = analyzer.propose(RAW_MERGE_PREFIXES.sub('', name.strip(), count=1))
            if bare.kind in (REWRITE, 'keep') and bare.values:
                proposal = bare
                proposal.kind = REWRITE
                proposal.evidence = [f"'{bare.values[0]}' without the DJ/MC prefix is approved"]
        if name in collisions:
            winner = collisions[name]
            same_spelling = normalize(name) == normalize(winner)
            proposal.kind = REWRITE
            proposal.values = [winner]
            proposal.confidence = 90 if same_spelling else 80
            proposal.evidence = [
                (
                    f"same name as '{winner}' ignoring case, accents and punctuation"
                    if same_spelling
                    else f"same name as '{winner}' without the DJ/MC prefix"
                )
                + f' ({undecided[winner]} tracks against {tracks})'
            ]
        elif proposal.kind == REWRITE and proposal.values:
            # Only when the target's size is known: an approved name the library does
            # not hold (typed as a correction target) has no count to lose against.
            target = proposal.values[0]
            target_tracks = tracks_of.get(target)
            if target_tracks is not None and target_tracks < tracks:
                proposal.kind = UNKNOWN
                proposal.values = [name]
                proposal.evidence = proposal.evidence + [
                    f"not rewritten: '{target}' has fewer tracks ({target_tracks}) than this name ({tracks})"
                ]
        proposals[name] = proposal
    return proposals


def _run_analysis(job_id: str) -> None:
    """Rewrite `rules_artist_proposals` for every undecided name. Never touches a decision."""
    state = job_manager.jobs.setdefault(job_id, {})
    state.update({'status': 'running', 'progress': 0, 'total': 0, 'current': None, 'failed': 0})
    conn = get_db_connection()
    if not conn:
        state.update({'status': 'failed', 'error': 'No database connection'})
        job_manager.results[job_id] = dict(state)
        return
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT name FROM rules_artists WHERE state = %s', (WHITE,))
            approved = [row['name'] for row in cursor.fetchall()]
            cursor.execute(
                f'SELECT a.name, COALESCE(tc.track_count, 0) AS track_count '
                f'FROM library_artists a LEFT JOIN ({TRACK_COUNTS}) tc ON tc.artist_id = a.id '
                'LEFT JOIN rules_artists r ON r.name = a.name WHERE r.name IS NULL'
            )
            undecided = {row['name']: int(row['track_count']) for row in cursor.fetchall()}
            # Track counts of approved names too, for the most-tracks-wins guard.
            if approved:
                placeholders = ', '.join(['%s'] * len(approved))
                cursor.execute(
                    f'SELECT a.name, COALESCE(tc.track_count, 0) AS track_count '
                    f'FROM library_artists a LEFT JOIN ({TRACK_COUNTS}) tc ON tc.artist_id = a.id '
                    f'WHERE a.name IN ({placeholders})',
                    approved,
                )
                counts = {row['name']: int(row['track_count']) for row in cursor.fetchall()}
            else:
                counts = {}
            state['total'] = len(undecided)

            proposals = propose_all(undecided, approved, counts, _analyzer_config())
            rows = [
                (
                    name,
                    proposal.kind,
                    ' + '.join(proposal.values) if proposal.kind != UNKNOWN else None,
                    json.dumps(proposal.evidence),
                    int(proposal.confidence),
                    int(proposal.junk_score),
                )
                for name, proposal in proposals.items()
            ]
            cursor.execute('DELETE FROM rules_artist_proposals')
            for start in range(0, len(rows), 1000):
                cursor.executemany(
                    'INSERT INTO rules_artist_proposals '
                    '(name, kind, target, evidence, confidence, junk_score, analyzed_at) '
                    'VALUES (%s, %s, %s, %s, %s, %s, NOW())',
                    rows[start : start + 1000],
                )
                state['progress'] = min(len(rows), start + 1000)
            conn.commit()
        state['status'] = 'finished'
        state['summary'] = {kind: sum(1 for row in rows if row[1] == kind) for kind in PROPOSAL_KINDS}
    except Exception as e:  # pylint: disable=broad-except
        logger.exception('Artist analysis failed')
        state.update({'status': 'failed', 'error': str(e)})
    finally:
        conn.close()
        state['current'] = None
        job_manager.results[job_id] = dict(state)
        if job_id not in job_manager.history:
            job_manager.history.appendleft(job_id)


@router.post('/analyze', status_code=202)
def analyze(background: BackgroundTasks, _auth: dict = WRITE):
    """Recompute every proposal. Cheap to repeat: nothing a human decided is read or written."""
    for existing_id, existing in job_manager.jobs.items():
        if existing_id.startswith('artist-analysis-') and existing.get('status') in ('queued', 'running'):
            return {'status': 'running', 'job_id': existing_id}
    job_id = f'artist-analysis-{uuid.uuid4()}'
    job_manager.jobs[job_id] = {'status': 'queued', 'progress': 0, 'total': 0, 'current': None, 'failed': 0}
    background.add_task(_run_analysis, job_id)
    return {'status': 'queued', 'job_id': job_id}


@router.get('/analyze/{job_id}')
def analysis_status(job_id: str, _auth: dict = READ):
    """Where an analysis run is, or its result once finished."""
    state = job_manager.jobs.get(job_id) or job_manager.results.get(job_id)
    if not state:
        raise HTTPException(status_code=404, detail='Unknown job')
    return state
