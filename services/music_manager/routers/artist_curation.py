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
from services.common.Helpers.FilterTableHelper import resolve_redirect_chains
from services.common.Helpers.RescanInvalidator import invalidate_quietly
from services.music_manager import curation_rules
from services.music_manager.database import get_db_connection, require_connection, transaction
from services.music_manager.job_store import job_store
from services.music_manager.rbac import require_permission

router = APIRouter(tags=['artist-curation'])
logger = logging.getLogger('music-manager.artist-curation')

READ = Depends(require_permission('music.read'))
WRITE = Depends(require_permission('rules.manage'))

WHITE = 'white'
BLACK = 'black'
STATES = (WHITE, BLACK)
#: What the list endpoint filters on. `unknown` is the queue: names nobody decided.
#: `pending` is the part of the queue the tagger does not trust -- names the scanner
#: inserted after the queue was wired up (TrustedArtistHelper), as opposed to the
#: grandfathered ones that were in the library before and are still trusted.
PENDING = 'pending'
FILTERS = ('unknown', PENDING, WHITE, BLACK, 'all')
#: The registry key of the tagger's trusted-artist helper (Cache.databaseHelpers).
TRUSTED_ARTIST_HELPER = 'library_artists'
PROPOSAL_KINDS = ('keep', 'rewrite', 'split', 'reject', 'unknown')
#: `decided` puts the newest decision first -- how a curator reviews what the scheduled
#: evidence run approved last night.
SORTS = ('tracks', 'name', 'decided')

#: One list request never returns more than this. The queue is tens of thousands of
#: names; the page pages through it, and a bulk decision carries explicit names.
MAX_LIMIT = 500
#: Names one decide call may carry. Each one marks files for a retag, so this is a
#: ceiling on how much tagger work one click can queue.
MAX_DECISION_NAMES = 500
#: Who migrate_v26 recorded as the decider of the redirects that predate this page.
LEGACY_DECIDER = 'legacy-redirect'
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
    """A pooled connection; no pool at all is a 503 (database.require_connection)."""
    return require_connection(get_db_connection())


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
    (r.name IS NULL AND l.name IS NULL) AS pending,
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
    row['pending'] = bool(row.get('pending'))
    return row


@router.get('')
def list_artists(
    state: str = 'unknown',
    q: str | None = None,
    proposal: str | None = None,
    sort: str = 'tracks',
    limit: int = 200,
    offset: int = 0,
    decided_by: str | None = None,
    _auth: dict = READ,
):
    """Artists by curation state, the ones touching most tracks first.

    `state=unknown` is the queue; `state=pending` is the part of it the tagger does not
    trust yet (every row also carries `pending`). `proposal` narrows it to what the last analysis
    proposed (`reject`, `rewrite`, ...), which is how a curator works through a class
    of names at a time rather than the whole tail. Decided names that have since left
    `library_artists` (a rebuild, a retag that removed them) still list under their
    state: the decision is the durable thing. `decided_by` narrows a decided list to one
    decider -- `auto-external` is what the scheduled evidence run signs, so
    `state=white&decided_by=auto-external&sort=decided` is its review list.
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
            'LEFT JOIN rules_artist_proposals p ON p.name = r.name '
            'LEFT JOIN rules_artist_legacy_trust l ON l.name = r.name'
        )
        where = ['r.state = %s']
        params: list = [state]
    else:
        base = (
            f'FROM library_artists a LEFT JOIN rules_artists r ON r.name = a.name '
            f'LEFT JOIN ({TRACK_COUNTS}) tc ON tc.artist_id = a.id '
            'LEFT JOIN rules_artist_proposals p ON p.name = a.name '
            'LEFT JOIN rules_artist_legacy_trust l ON l.name = a.name'
        )
        if state == 'unknown':
            where = ['r.name IS NULL']
        elif state == PENDING:
            where = ['r.name IS NULL', 'l.name IS NULL']
        else:
            where = []
        params = []
    if q:
        where.append('COALESCE(a.name, r.name) LIKE %s')
        params.append(f'%{q}%')
    if proposal:
        where.append('p.kind = %s')
        params.append(proposal)
    if decided_by:
        where.append('r.decided_by = %s')
        params.append(decided_by.strip()[:64])
    where_sql = f" WHERE {' AND '.join(where)}" if where else ''
    order = {'tracks': 'track_count DESC, name', 'name': 'name', 'decided': 'r.decided_at DESC, name'}[sort]

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
                'SELECT COUNT(*) AS n FROM library_artists a LEFT JOIN rules_artists r ON r.name = a.name '
                'LEFT JOIN rules_artist_legacy_trust l ON l.name = a.name '
                'WHERE r.name IS NULL AND l.name IS NULL'
            )
            pending = cursor.fetchone()['n']
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
                PENDING: pending,
                WHITE: decided.get(WHITE, 0),
                BLACK: decided.get(BLACK, 0),
                'proposals': proposals,
                'analyzed_at': analyzed_at,
            }
    finally:
        conn.close()


#: The scheduled evidence run's ledger, newest first (artist_auto_approve_worker).
EVIDENCE_RUNS_SQL = """
    SELECT id, CAST(started_at AS CHAR) AS started_at, CAST(finished_at AS CHAR) AS finished_at,
           dry_run, new_names, backlog_names, approved, applied, unresolved, skipped, incomplete,
           requests, failed_requests, stopped_early
    FROM rules_artist_evidence_runs ORDER BY id DESC LIMIT %s
"""
#: What the last runs judged `approve`, whether or not it was applied (a dry run applies nothing).
EVIDENCE_APPROVALS_SQL = """
    SELECT e.name, e.rule, e.run_id, CAST(e.checked_at AS CHAR) AS checked_at,
           CAST(e.applied_at AS CHAR) AS applied_at, r.state, r.decided_by
    FROM rules_artist_evidence e LEFT JOIN rules_artists r ON r.name = e.name
    WHERE e.verdict = 'approve' AND e.run_id >= %s
    ORDER BY e.checked_at DESC, e.name LIMIT %s
"""


@router.get('/auto-approve/runs')
def evidence_runs(limit: int = 30, _auth: dict = READ):
    """The scheduled evidence run's recent rounds and what they judged approvable.

    `runs` is one row per round with its counts; `approvals` lists the names those rounds
    judged `approve`, with `applied_at` (NULL in a dry run) and the name's decision now --
    so a curator can see what was approved automatically and undo it on the page
    (`DELETE /api/rules/artists/{name}`), and in a dry run see what would have been.
    """
    limit = max(1, min(int(limit), 365))
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute(EVIDENCE_RUNS_SQL, (limit,))
            runs = list(cursor.fetchall())
            oldest = min((row['id'] for row in runs), default=0)
            cursor.execute(EVIDENCE_APPROVALS_SQL, (oldest, MAX_LIMIT))
            approvals = list(cursor.fetchall())
    finally:
        conn.close()
    for row in runs:
        row['dry_run'] = bool(row['dry_run'])
        row['stopped_early'] = bool(row['stopped_early'])
    return {'runs': runs, 'approvals': approvals}


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


def _redirect_dependents(cursor, target: str) -> list[str]:
    """Names whose correction points at `target`, from either table, case-insensitively.

    Both tables, because `rules_ignored_artists` also holds redirects typed on the
    Tagger tab (`/api/rules/artist-redirects`) that never had a curation decision.
    """
    cursor.execute(
        'SELECT name FROM rules_artists WHERE state = %s AND LOWER(canonical_name) = LOWER(%s) '
        'UNION SELECT name FROM rules_ignored_artists WHERE LOWER(corrected_name) = LOWER(%s)',
        (BLACK, target, target),
    )
    seen: dict[str, str] = {}
    for row in cursor.fetchall():
        name = row['name']
        if name.lower() != target.lower():
            seen.setdefault(name.lower(), name)
    return sorted(seen.values(), key=str.lower)


def _release_redirects_to(cursor, target: str, new_target: str | None) -> list[str]:
    """Keep no redirect pointing at a name that is no longer an approved artist.

    Called before `target` is rejected or its decision forgotten. Two cases, deliberately
    different:

    * `target` is rejected *with* a correction (`X -> Z`): every `Y -> X` becomes
      `Y -> Z`. The curator said Y is X and X is Z, so Y is Z; nothing is lost and no
      chain is left for the tagger to walk.
    * `target` is rejected without one, or undone: every `Y -> X` is forgotten and Y
      goes back to the queue. The premise of that redirect -- X is the artist -- has
      been withdrawn, and what Y should be instead is not something to guess. Turning
      Y into a plain rejection would strip a credit from every file that carries it on
      the next retag; the queue loses nothing and shows Y again with fresh advice.

    Returns the names that were touched, so the caller can say so.
    """
    dependents = _redirect_dependents(cursor, target)
    if not dependents:
        return []
    if new_target:
        cursor.execute(
            'UPDATE rules_artists SET canonical_name = %s '
            'WHERE state = %s AND LOWER(canonical_name) = LOWER(%s) AND LOWER(name) <> LOWER(%s)',
            (new_target, BLACK, target, new_target),
        )
        cursor.execute(
            'UPDATE rules_ignored_artists SET corrected_name = %s '
            'WHERE LOWER(corrected_name) = LOWER(%s) AND LOWER(name) <> LOWER(%s)',
            (new_target, target, new_target),
        )
    else:
        cursor.execute(
            'DELETE FROM rules_artists WHERE state = %s AND LOWER(canonical_name) = LOWER(%s)',
            (BLACK, target),
        )
        cursor.execute('DELETE FROM rules_ignored_artists WHERE LOWER(corrected_name) = LOWER(%s)', (target,))
    return dependents


def record_approvals(cursor, names: list[str], decided_by: str) -> None:
    """Approve `names` inside the caller's transaction, exactly as `decide` does for `state=white`.

    For the scheduled evidence run (artist_auto_approve_worker), which approves in batches
    without an HTTP round trip. An approval has no redirects to settle and no files to
    retag, so this is the whole of what `decide` writes for it; the caller refreshes the
    tagger's snapshots once afterwards with `refresh_artist_trust`.
    """
    for name in names:
        _upsert_decision(cursor, name, WHITE, None, decided_by)
        _mirror_to_tagger(cursor, name, WHITE, None)


def refresh_artist_trust() -> None:
    """Reload the running tagger's redirect and trusted-artist snapshots after a decision."""
    curation_rules.refresh(curation_rules.ARTIST_REDIRECT_HELPER)
    curation_rules.refresh(TRUSTED_ARTIST_HELPER)


@router.post('/decide')
def decide(request: DecisionRequest, auth: dict = WRITE):
    """Approve or reject names, optionally rewriting them to one approved spelling.

    Several names at once because the queue is worked in classes -- every `reject`
    proposal on a page, every variant of one artist. A correction implies the target
    is an artist: a `canonical_name` that has no decision yet is approved in the same
    call, so `Dr.Peacock -> Dr. Peacock` is one action rather than two. A black target
    is refused -- rewriting one problem into another is the thing this must not do.

    Rejecting a name that other redirects point at settles those first
    (`_release_redirects_to`): with a correction they follow it, without one they go
    back to the queue. Both lists are in the reply.
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
    repointed: list[str] = []
    requeued: list[str] = []
    target = None
    conn = _connect()
    try:
        if canonical:
            # Checked before the transaction opens: a refused request never starts one.
            with conn.cursor() as cursor:
                cursor.execute('SELECT state FROM rules_artists WHERE name = %s', (canonical,))
                target = cursor.fetchone()
            if target and target['state'] == BLACK:
                raise HTTPException(status_code=400, detail=f"'{canonical}' is rejected; pick an approved name")
        # One transaction: re-pointing the redirects that lead to a rejected name and
        # rejecting it land together, or a crash in between leaves a chain behind.
        with transaction(conn), conn.cursor() as cursor:
            if canonical and not target:
                _upsert_decision(cursor, canonical, WHITE, None, decided_by)
                _mirror_to_tagger(cursor, canonical, WHITE, None)
            if request.state == BLACK:
                deciding = {name.lower() for name in names}
                for name in names:
                    touched = _release_redirects_to(cursor, name, canonical)
                    # A dependent decided in this same call gets its own decision below, and
                    # one that two of the names lead to is listed once.
                    for other in touched:
                        if other.lower() not in deciding:
                            deciding.add(other.lower())
                            (repointed if canonical else requeued).append(other)
            for name in names:
                _upsert_decision(cursor, name, request.state, canonical, decided_by)
                _mirror_to_tagger(cursor, name, request.state, canonical)
    finally:
        conn.close()

    # The running tagger holds a preloaded copy of rules_ignored_artists; without this
    # it keeps writing the old name until a restart, retag included.
    curation_rules.refresh(curation_rules.ARTIST_REDIRECT_HELPER)
    # And its trusted-artist snapshot: an approval is what lets the artist rules match
    # a pending name, a rejection is what takes a name out of their dictionary.
    curation_rules.refresh(TRUSTED_ARTIST_HELPER)
    if request.state == BLACK:
        # Only a rejection changes what a file should carry; an approval leaves the
        # tag as it is, so there is nothing to retag for. Exact: the files that change
        # are the ones carrying the name today. The wide match the rule endpoints use
        # would turn a rejected '001' into a retag of every path with a catalogue number.
        for name in names:
            invalidate_quietly(name, 'artist_decision', exact=True)
    return {
        'status': 'ok',
        'decided': len(names),
        'canonical_name': canonical,
        'repointed': repointed,
        'returned_to_queue': requeued,
    }


@router.delete('/{name:path}')
def undo(name: str, _auth: dict = WRITE):
    """Forget a decision: the name goes back to the queue and the tagger stops acting on it.

    Redirects that pointed at the name go back to the queue with it
    (`_release_redirects_to`): they were decided on the premise that this name is the
    artist, and that premise is what an undo withdraws. They are listed in the reply.
    """
    name = (name or '').strip()
    if not name:
        raise HTTPException(status_code=400, detail='No name given')
    conn = _connect()
    try:
        with transaction(conn), conn.cursor() as cursor:
            cursor.execute('DELETE FROM rules_artists WHERE name = %s', (name,))
            if not cursor.rowcount:
                raise HTTPException(status_code=404, detail='No decision for that name')
            cursor.execute('DELETE FROM rules_ignored_artists WHERE LOWER(name) = LOWER(%s)', (name,))
            requeued = _release_redirects_to(cursor, name, None)
    finally:
        conn.close()
    # No retag for the requeued names, as for the undone one: the tagger now leaves
    # them alone, and a file that carries one keeps it either way.
    curation_rules.refresh(curation_rules.ARTIST_REDIRECT_HELPER)
    curation_rules.refresh(TRUSTED_ARTIST_HELPER)
    return {'status': 'ok', 'returned_to_queue': requeued}


@router.get('/redirects/issues')
def redirect_issues(_auth: dict = READ):
    """Read-only integrity check: redirects that end somewhere they should not, or loop.

    `decide` and `undo` keep new ones from appearing, but rows stored before that, or
    typed on the Tagger tab, can still point at a rejected or forgotten name. SQL
    cannot tell which way such a row should be repaired, so this only reports.
    """
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT name, corrected_name FROM rules_ignored_artists')
            redirects = [(row['name'], row['corrected_name']) for row in cursor.fetchall()]
            cursor.execute('SELECT name, state, canonical_name, decided_by FROM rules_artists')
            decisions = list(cursor.fetchall())
    finally:
        conn.close()
    return find_redirect_issues(redirects, decisions)


def find_redirect_issues(redirects: list, decisions: list) -> dict:
    """What `GET /redirects/issues` reports, from the rows of the two tables. Pure.

    * `dangling` -- a redirect whose final target is not an approved artist: the
      target is rejected in `rules_artists`, is a plain drop row in
      `rules_ignored_artists`, or (for a curation decision) has no decision at all any
      more. Each with the reason in words.
    * `cycles` -- redirect loops, as in `resolve_redirect_chains`.
    * `chains` -- redirects of more than one hop. The tagger follows these since bug
      080, so they are information rather than a fault; `count` leaves them out.

    @param redirects: `(name, corrected_name)` rows of `rules_ignored_artists`.
    @param decisions: `{name, state, canonical_name, decided_by}` rows of `rules_artists`.
    """
    corrections: dict[str, str] = {}
    dropped: set[str] = set()
    for name, corrected in redirects:
        name = (name or '').strip()
        corrected = (corrected or '').strip()
        if not name:
            continue
        if corrected:
            corrections[name] = corrected
        else:
            dropped.add(name.lower())
    state_of = {str(row['name']).lower(): row['state'] for row in decisions}
    mirrored = {name.lower() for name in corrections}
    # A curation redirect not (yet) mirrored is still a redirect the page shows.
    for row in decisions:
        canonical = (row.get('canonical_name') or '').strip()
        if row['state'] == BLACK and canonical and str(row['name']).lower() not in mirrored:
            corrections[str(row['name'])] = canonical
    # Redirects decided on the page, whose target was approved in the same call. The
    # rows migrate_v26 seeded (`legacy-redirect`) never had an approved target, so a
    # target without a decision says nothing about them.
    curated = {
        str(row['name']).lower()
        for row in decisions
        if row['state'] == BLACK and row.get('canonical_name') and row.get('decided_by') != LEGACY_DECIDER
    }

    resolved, paths, cycles = resolve_redirect_chains(corrections)
    looping = {member.lower() for cycle in cycles for member in cycle}
    dangling = []
    for name, target in sorted(resolved.items(), key=lambda item: item[0].lower()):
        key = target.lower()
        if name.lower() in looping or key == name.lower():
            continue
        reason = None
        if state_of.get(key) == BLACK:
            reason = 'target is rejected'
        elif key in dropped:
            reason = 'target is dropped by the tagger'
        elif name.lower() in curated and key not in state_of:
            reason = 'target has no decision (undone?)'
        if reason:
            dangling.append({'name': name, 'target': target, 'path': paths.get(name, [name, target]), 'reason': reason})
    chains = [
        {'name': name, 'path': path}
        for name, path in sorted(paths.items(), key=lambda item: item[0].lower())
        if name.lower() not in looping
    ]
    return {'count': len(dangling) + len(cycles), 'dangling': dangling, 'cycles': cycles, 'chains': chains}


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
    state = job_store.jobs.setdefault(job_id, {})
    state.update({'status': 'running', 'progress': 0, 'total': 0, 'current': None, 'failed': 0})
    conn = get_db_connection()
    if not conn:
        state.update({'status': 'failed', 'error': 'No database connection'})
        job_store.finish(job_id, state)
        return
    try:
        with transaction(conn), conn.cursor() as cursor:
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
        state['status'] = 'finished'
        state['summary'] = {kind: sum(1 for row in rows if row[1] == kind) for kind in PROPOSAL_KINDS}
    except Exception as e:  # pylint: disable=broad-except
        logger.exception('Artist analysis failed')
        state.update({'status': 'failed', 'error': str(e)})
    finally:
        conn.close()
        state['current'] = None
        job_store.finish(job_id, state)


@router.post('/analyze', status_code=202)
def analyze(background: BackgroundTasks, _auth: dict = WRITE):
    """Recompute every proposal. Cheap to repeat: nothing a human decided is read or written."""
    for existing_id, existing in list(job_store.jobs.items()):
        if existing_id.startswith('artist-analysis-') and existing.get('status') in ('queued', 'running'):
            return {'status': 'running', 'job_id': existing_id}
    job_id = f'artist-analysis-{uuid.uuid4()}'
    job_store.jobs[job_id] = {'status': 'queued', 'progress': 0, 'total': 0, 'current': None, 'failed': 0}
    background.add_task(_run_analysis, job_id)
    return {'status': 'queued', 'job_id': job_id}


@router.get('/analyze/{job_id}')
def analysis_status(job_id: str, _auth: dict = READ):
    """Where an analysis run is, or its result once finished."""
    state = job_store.state(job_id)
    if not state:
        raise HTTPException(status_code=404, detail='Unknown job')
    return state
