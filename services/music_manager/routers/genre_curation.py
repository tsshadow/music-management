"""Genre curation advice: what the analyzer proposes for every genre in the queue.

The queue itself (`GET /api/rules/genres`) and the decision
(`POST /api/rules/genres/{id}/decide`) live in management.py; this router adds
the advice next to them, the way `/api/rules/artists` carries advice for artist
names. Three things stay separate: the raw genre (`rules_genres`, state
`unknown`), the proposal (`rules_genre_proposals`, rewritten whole on every run)
and the human decision (state `white`/`black` plus `rules_genre_expansions`,
which an analysis run never touches). A proposal is only ever a suggestion the
page shows next to the name; nothing here applies one on its own.

The dictionary is the curator's own past work: the approved genres, every
correction already made (`Upterror` -> `Uptempo Hardcore` + `Terror` teaches the
analyzer what a blend looks like), the names rejected without a correction, and
the artist and label links from the tagger page -- `Dr Peacock` in the genre
field is an artist linked to Frenchcore, so that is the advice.
"""

import json
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from services.common.config_store import ConfigStore as Settings
from services.common.Helpers.GenreNameAnalyzer import (
    KINDS,
    GenreAnalyzerConfig,
    GenreNameAnalyzer,
    build_dictionary,
)
from services.music_manager.database import get_db_connection
from services.music_manager.job_store import job_store
from services.music_manager.rbac import require_permission

router = APIRouter(tags=['genre-curation'])
logger = logging.getLogger('music-manager.genre-curation')

READ = Depends(require_permission('music.read'))
WRITE = Depends(require_permission('rules.manage'))

PROPOSAL_KINDS = KINDS
#: The config key an admin can tune the analyzer with (Beheer -> Configuratie).
ANALYZER_CONFIG_KEY = 'genre_curation_analyzer'
#: An artist below this many tracks is not evidence of anything: `library_artists`
#: holds every string a tagger rule ever produced, and a genre string colliding
#: with one of those would be called "an artist" for no reason.
MIN_ARTIST_TRACKS = 3

APPROVED_SQL = """
    SELECT g.id, g.name, COUNT(tg.track_id) AS tracks
    FROM rules_genres g
    LEFT JOIN library_track_genres tg ON tg.genre_id = g.id
    WHERE g.state = 'white'
    GROUP BY g.id, g.name
"""
EXPANSIONS_SQL = """
    SELECT g.name, t.name AS target
    FROM rules_genre_expansions e
    JOIN rules_genres g ON g.id = e.genre_id
    JOIN rules_genres t ON t.id = e.target_id
    ORDER BY e.genre_id, e.position, t.name
"""
REJECTED_SQL = """
    SELECT g.name
    FROM rules_genres g
    LEFT JOIN rules_genre_expansions e ON e.genre_id = g.id
    WHERE g.state = 'black' AND e.genre_id IS NULL
"""
QUEUE_SQL = "SELECT id, name FROM rules_genres WHERE state = 'unknown'"
ARTISTS_SQL = """
    SELECT a.name, g.name AS genre
    FROM library_artists a
    LEFT JOIN (SELECT artist_id, COUNT(DISTINCT track_id) AS track_count
               FROM library_track_artists GROUP BY artist_id) tc ON tc.artist_id = a.id
    LEFT JOIN rules_artist_genres r ON r.artist_name = a.name
    LEFT JOIN rules_genres g ON g.id = r.genre_id
    WHERE COALESCE(tc.track_count, 0) >= %s OR r.id IS NOT NULL
"""
LABELS_SQL = """
    SELECT l.name, g.name AS genre
    FROM library_labels l
    LEFT JOIN rules_label_genres r ON r.label_name = l.name
    LEFT JOIN rules_genres g ON g.id = r.genre_id
"""


def _connect():
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='No database connection')
    return conn


def _analyzer_config() -> GenreAnalyzerConfig:
    """The configured thresholds, or the defaults when the setting is missing or not a dict."""
    value = Settings().get(ANALYZER_CONFIG_KEY, None)
    return GenreAnalyzerConfig.from_dict(value if isinstance(value, dict) else None)


def load_dictionary(cursor) -> tuple:
    """The dictionary from the database, plus `{approved name: id}` for storing targets."""
    cursor.execute(APPROVED_SQL)
    approved_rows = cursor.fetchall()
    cursor.execute(EXPANSIONS_SQL)
    expansions = [(row['name'], row['target']) for row in cursor.fetchall()]
    cursor.execute(REJECTED_SQL)
    rejected = [row['name'] for row in cursor.fetchall()]
    cursor.execute(ARTISTS_SQL, (MIN_ARTIST_TRACKS,))
    artists = [(row['name'], row['genre']) for row in cursor.fetchall()]
    cursor.execute(LABELS_SQL)
    labels = [(row['name'], row['genre']) for row in cursor.fetchall()]
    dictionary = build_dictionary(
        [(row['name'], row['tracks']) for row in approved_rows], expansions, rejected, artists, labels
    )
    ids = {row['name']: int(row['id']) for row in approved_rows}
    return dictionary, ids


def propose_all(queue: dict, dictionary, config: GenreAnalyzerConfig | None = None) -> dict:
    """Every queued genre's proposal, as `{genre_id: Proposal}`. Pure: no database.

    @param queue: `{genre_id: name}` for the genres awaiting a decision.
    """
    analyzer = GenreNameAnalyzer(dictionary, config)
    return {genre_id: analyzer.propose(name) for genre_id, name in queue.items()}


def _run_analysis(job_id: str) -> None:
    """Rewrite `rules_genre_proposals` for every queued genre. Never touches a decision."""
    state = job_store.jobs.setdefault(job_id, {})
    state.update({'status': 'running', 'progress': 0, 'total': 0, 'current': None, 'failed': 0})
    conn = get_db_connection()
    if not conn:
        state.update({'status': 'failed', 'error': 'No database connection'})
        job_store.finish(job_id, state)
        return
    try:
        with conn.cursor() as cursor:
            dictionary, ids = load_dictionary(cursor)
            cursor.execute(QUEUE_SQL)
            queue = {int(row['id']): row['name'] for row in cursor.fetchall()}
            state['total'] = len(queue)

            proposals = propose_all(queue, dictionary, _analyzer_config())
            rows = []
            for genre_id, proposal in proposals.items():
                # Targets are stored with their id so the page can post the decision
                # straight away; a name whose id is unknown (should not happen: the
                # dictionary was built from the same rows) is left out rather than guessed.
                targets = [{'id': ids[name], 'name': name} for name in proposal.values if name in ids]
                rows.append(
                    (
                        genre_id,
                        proposal.kind,
                        json.dumps(targets),
                        json.dumps(proposal.evidence),
                        int(proposal.confidence),
                    )
                )
            cursor.execute('DELETE FROM rules_genre_proposals')
            for start in range(0, len(rows), 1000):
                cursor.executemany(
                    'INSERT INTO rules_genre_proposals (genre_id, kind, targets, evidence, confidence, analyzed_at) '
                    'VALUES (%s, %s, %s, %s, %s, NOW())',
                    rows[start : start + 1000],
                )
                state['progress'] = min(len(rows), start + 1000)
            conn.commit()
        state['status'] = 'finished'
        state['summary'] = {kind: sum(1 for row in rows if row[1] == kind) for kind in PROPOSAL_KINDS}
    except Exception as e:  # pylint: disable=broad-except
        logger.exception('Genre analysis failed')
        state.update({'status': 'failed', 'error': str(e)})
    finally:
        conn.close()
        state['current'] = None
        job_store.finish(job_id, state)


@router.get('/summary')
def summary(_auth: dict = READ):
    """How big the job is: genres per state, proposals per kind, and when the analysis ran."""
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT state, COUNT(*) AS n FROM rules_genres GROUP BY state')
            states = {row['state']: int(row['n']) for row in cursor.fetchall()}
            cursor.execute(
                'SELECT p.kind, COUNT(*) AS n FROM rules_genre_proposals p '
                "JOIN rules_genres g ON g.id = p.genre_id WHERE g.state = 'unknown' GROUP BY p.kind"
            )
            proposals = {row['kind']: int(row['n']) for row in cursor.fetchall()}
            cursor.execute('SELECT CAST(MAX(analyzed_at) AS CHAR) AS analyzed_at FROM rules_genre_proposals')
            analyzed_at = (cursor.fetchone() or {}).get('analyzed_at')
            return {
                'unknown': states.get('unknown', 0),
                'white': states.get('white', 0),
                'black': states.get('black', 0),
                'proposals': proposals,
                'analyzed_at': analyzed_at,
            }
    finally:
        conn.close()


@router.post('/analyze', status_code=202)
def analyze(background: BackgroundTasks, _auth: dict = WRITE):
    """Recompute every proposal. Cheap to repeat: nothing a human decided is read or written."""
    for existing_id, existing in list(job_store.jobs.items()):
        if existing_id.startswith('genre-analysis-') and existing.get('status') in ('queued', 'running'):
            return {'status': 'running', 'job_id': existing_id}
    job_id = f'genre-analysis-{uuid.uuid4()}'
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
