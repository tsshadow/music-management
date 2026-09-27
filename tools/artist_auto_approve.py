#!/usr/bin/env python3
"""Approve artist names on external evidence, so the curation queue shrinks to the doubtful.

The artist curation queue (Beheer -> Curatie -> Artiestcuratie) holds every name in
`library_artists` nobody decided on: ~55.000 on prod, of which roughly one in ten is a
real artist. No internal signal separates the real ones from the noise -- that was
measured and closed -- so this asks the outside world instead. A name is approved
when a recording *credited to that name* on an external catalogue carries a title
the library also has under that name. Existence of the name alone proves nothing
(`Otis`, `Nero` and `Holly` exist everywhere as somebody); the title match is what
ties the external artist to the local one.

Sources are the ones that need no key -- Deezer, MusicBrainz, iTunes Search -- and
the lookup is per *artist*, not per track: one artist search, one tracklist, compared
against every local title of the name. Two or three requests per name per source
instead of one per track, and a name with two tracks gets the same treatment as one
with two hundred.

Approve when one of
  (1) two different local titles match recordings of one external act,
  (2) two different local titles match across sources, one of them distinctive
      (two words, ten letters), or
  (3) one distinctive title matches on MusicBrainz, where the artist is a Person or
      Group, *and* on Deezer or iTunes.
Deezer and iTunes together do not count as two sources for one title: their metadata
comes from the same distributors. Titles that are sets, compilations or mixes count on
neither side, and a name shaped like a brand (`... Festival`, `... Records`, a year)
is never approved: the stores credit a festival with its anthems and a label with its
compilations. Nothing is ever rejected automatically -- absence from a catalogue is
not evidence of noise in a SoundCloud-heavy hardcore library.

Four steps, each resumable through one sqlite file:

    tools/artist_auto_approve.py snapshot --state run.sqlite      # queue + titles from the DB
    tools/artist_auto_approve.py run      --state run.sqlite      # external lookups, cached
    tools/artist_auto_approve.py report   --state run.sqlite -o report.csv
    tools/artist_auto_approve.py apply    --state run.sqlite --base-url ... --api-key ...

`snapshot` reads the database the way the other tools do (`DB_HOST`, `DB_PORT`,
`DB_USER`, `DB_PASS`, `DB_DB`); a read-only account is enough. `run` can be stopped
at any time: every response is cached, every verdict stored, and a restart skips what
is done -- except names a source failed to answer for, which are asked again. `apply`
posts approvals through `POST /api/rules/artists/decide` in batches signed
`auto-external`, skipping anything a human decided since the snapshot; `undo`
reverses the names this file applied that are still signed that way.

music-manager runs the same judgement once a day on its own (thread `artist-auto-approve`,
services/music_manager/artist_auto_approve_worker.py; dry run by default). This tool stays for
a deliberate one-off run over a large slice, and for its CSV report.
"""

import argparse
import csv
import json
import logging
import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

logger = logging.getLogger('artist-auto-approve')

# The judgement lives in services/common so the scheduled run inside music-manager applies the
# very same rules; several names are re-exported for tools/test_artist_auto_approve.py.
from services.common.Helpers.ArtistEvidence import (  # noqa: E402,F401
    APPROVE,
    DECIDE_BATCH,
    DECIDED_BY,
    DEEZER,
    INCOMPLETE,
    ITUNES,
    MIN_INTERVAL,
    MUSICBRAINZ,
    POLICY,
    RETRIES,
    SKIPPED,
    SOURCES,
    TIMEOUT,
    UNRESOLVED,
    USER_AGENT,
    ExternalArtist,
    Verdict,
    _deezer_error,
    _q,
    fold,
    looks_like_a_set,
    normalise_artist,
    normalise_title,
    resolve,
    score_artist,
    titles_hash,
    usable_titles,
)

# ----------------------------------------------------------------------------- state


SCHEMA = """
CREATE TABLE IF NOT EXISTS candidates (
    name TEXT PRIMARY KEY, track_count INTEGER NOT NULL, titles TEXT NOT NULL, titles_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS responses (
    source TEXT NOT NULL, url TEXT NOT NULL, status INTEGER, body TEXT, fetched_at REAL NOT NULL,
    PRIMARY KEY (source, url)
);
CREATE TABLE IF NOT EXISTS verdicts (
    name TEXT PRIMARY KEY, policy TEXT NOT NULL, titles_hash TEXT NOT NULL, verdict TEXT NOT NULL, rule TEXT,
    evidence TEXT NOT NULL, decided_at REAL NOT NULL
);
-- Written *before* the POST: a batch the server took but the reply for which never
-- arrived is still here for undo. confirmed_at is the reply.
CREATE TABLE IF NOT EXISTS applied (
    name TEXT PRIMARY KEY, applied_at REAL NOT NULL, confirmed_at REAL, undone_at REAL
);
"""


def open_state(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


# ----------------------------------------------------------------------------- snapshot

SNAPSHOT_SQL = """
    SELECT a.name, t.title
    FROM library_artists a
    JOIN library_track_artists la ON la.artist_id = a.id
    JOIN library_tracks t ON t.id = la.track_id
    LEFT JOIN rules_artists r ON r.name = a.name
    WHERE r.name IS NULL
"""
#: A name the tagger already rewrites or drops stays out: approving it would delete
#: that rule (white mirrors as "no row"), which is a curation decision, not evidence.
LEGACY_RULES_SQL = 'SELECT name FROM rules_ignored_artists'


def snapshot(conn: sqlite3.Connection) -> int:
    from services.common.Helpers.DatabaseConnector import DatabaseConnector

    db = DatabaseConnector().connect()
    try:
        with db.cursor() as cursor:
            cursor.execute(LEGACY_RULES_SQL)
            legacy = {fold(row[0]) for row in cursor.fetchall()}
            cursor.execute(SNAPSHOT_SQL)
            titles: dict[str, list[str]] = {}
            for name, title in cursor.fetchall():
                titles.setdefault(name, []).append(title or '')
    finally:
        db.close()
    rows = [(name, len(ts), json.dumps(ts), titles_hash(ts)) for name, ts in titles.items() if fold(name) not in legacy]
    conn.execute('DELETE FROM candidates')
    conn.executemany('INSERT INTO candidates (name, track_count, titles, titles_hash) VALUES (?, ?, ?, ?)', rows)
    conn.commit()
    return len(rows)


# ----------------------------------------------------------------------------- fetching


class Fetcher:
    """Cached, rate-limited GET. A response is fetched once per state file, ever."""

    def __init__(self, conn: sqlite3.Connection, offline: bool = False):
        import requests

        self.conn = conn
        self.offline = offline
        self.session = requests.Session()
        self.session.headers['User-Agent'] = USER_AGENT
        self.last_call = dict.fromkeys(SOURCES, 0.0)
        self.fetched = 0
        self.failed = 0

    def get(self, source: str, url: str) -> dict | None:
        """The parsed body, or None when the source did not answer (counted in `failed`)."""
        row = self.conn.execute(
            'SELECT status, body FROM responses WHERE source = ? AND url = ?', (source, url)
        ).fetchone()
        if row is not None and row['status'] == 200:
            return json.loads(row['body'])
        if self.offline:
            self.failed += 1
            return None
        status, body = self._fetch(source, url)
        parsed = None
        if status == 200:
            try:
                parsed = json.loads(body)
            except ValueError:
                status = 0  # a 200 that is not JSON is not an answer; do not cache it as one
        if status == 200 and isinstance(parsed, dict):
            self.conn.execute(
                'INSERT OR REPLACE INTO responses (source, url, status, body, fetched_at) VALUES (?, ?, ?, ?, ?)',
                (source, url, status, body, time.time()),
            )
            self.conn.commit()
            self.fetched += 1
            return parsed
        self.failed += 1
        return None

    def _fetch(self, source: str, url: str) -> tuple[int, str]:
        for attempt in range(RETRIES):
            wait = MIN_INTERVAL[source] - (time.monotonic() - self.last_call[source])
            if wait > 0:
                time.sleep(wait)
            self.last_call[source] = time.monotonic()
            try:
                response = self.session.get(url, timeout=TIMEOUT)
            except Exception as error:  # noqa: BLE001 - network; retried
                logger.warning('%s: %s (%s)', source, error, url)
                time.sleep(2**attempt)
                continue
            status, body = response.status_code, response.text
            if source == DEEZER and status == 200 and _deezer_error(body):
                status = 429
            if status in (429, 503):
                retry_after = response.headers.get('Retry-After', '')
                time.sleep(float(retry_after) if retry_after.isdigit() else 2 ** (attempt + 1))
                continue
            return status, body
        return 0, ''


def run(conn: sqlite3.Connection, args) -> None:
    fetcher = Fetcher(conn, offline=args.offline)
    where = 'WHERE c.track_count BETWEEN ? AND ?'
    params: list = [args.min_tracks, args.max_tracks]
    if not args.recompute:
        where += ' AND (v.name IS NULL OR v.policy != ? OR v.titles_hash != c.titles_hash OR v.verdict = ?)'
        params += [POLICY, INCOMPLETE]
    rows = conn.execute(
        f'SELECT c.name, c.titles, c.titles_hash FROM candidates c LEFT JOIN verdicts v ON v.name = c.name {where} '
        'ORDER BY c.track_count DESC, c.name LIMIT ?',
        params + [args.limit],
    ).fetchall()
    logger.info('%d names to resolve', len(rows))
    started = time.monotonic()
    counts = {APPROVE: 0, UNRESOLVED: 0, SKIPPED: 0, INCOMPLETE: 0}
    for index, row in enumerate(rows, 1):
        titles = json.loads(row['titles'])
        try:
            verdict = resolve(fetcher, row['name'], titles, tuple(args.sources))
        except KeyboardInterrupt:
            raise
        except Exception:  # noqa: BLE001 - one name must not end the run
            logger.exception('%s: lookup failed', row['name'])
            continue
        counts[verdict.verdict] += 1
        conn.execute(
            'INSERT OR REPLACE INTO verdicts (name, policy, titles_hash, verdict, rule, evidence, decided_at) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            (
                row['name'],
                POLICY,
                row['titles_hash'],
                verdict.verdict,
                verdict.rule,
                json.dumps(verdict.evidence),
                time.time(),
            ),
        )
        conn.commit()
        if index % 25 == 0 or index == len(rows):
            rate = index / max(time.monotonic() - started, 1e-9)
            logger.info(
                '%d/%d  approve=%d unresolved=%d skipped=%d  %.1f names/min  %d requests',
                index,
                len(rows),
                counts[APPROVE],
                counts[UNRESOLVED],
                counts[SKIPPED],
                rate * 60,
                fetcher.fetched,
            )


# ----------------------------------------------------------------------------- report / apply


def report(conn: sqlite3.Connection, out) -> None:
    writer = csv.writer(out)
    writer.writerow(['name', 'track_count', 'verdict', 'rule', 'sources', 'matched_titles', 'evidence'])
    rows = conn.execute(
        'SELECT c.name, c.track_count, v.verdict, v.rule, v.evidence FROM verdicts v '
        'JOIN candidates c ON c.name = v.name ORDER BY v.verdict, c.track_count DESC'
    )
    for row in rows:
        evidence = json.loads(row['evidence'])
        matches = evidence.get('matches', [])
        sources = sorted({hit['source'] for hit in matches})
        matched = sorted({m['local'] for hit in matches for m in hit['matched'].values()})
        writer.writerow(
            [
                row['name'],
                row['track_count'],
                row['verdict'],
                row['rule'] or '',
                ' '.join(sources),
                ' | '.join(matched),
                json.dumps(evidence, ensure_ascii=False),
            ]
        )


def summary(conn: sqlite3.Connection) -> dict:
    out = {'candidates': conn.execute('SELECT COUNT(*) FROM candidates').fetchone()[0]}
    for row in conn.execute('SELECT verdict, COUNT(*) AS n FROM verdicts GROUP BY verdict'):
        out[row['verdict']] = row['n']
    out['applied'] = conn.execute('SELECT COUNT(*) FROM applied WHERE undone_at IS NULL').fetchone()[0]
    out['unconfirmed'] = conn.execute(
        'SELECT COUNT(*) FROM applied WHERE confirmed_at IS NULL AND undone_at IS NULL'
    ).fetchone()[0]
    return out


def decided_on_server(base_url: str, headers: dict) -> dict[str, dict]:
    """Every decided name on the server, so a human's decision made since the snapshot wins."""
    import requests

    decided: dict[str, dict] = {}
    for state in ('white', 'black'):
        offset = 0
        while True:
            response = requests.get(
                f'{base_url}/api/rules/artists',
                params={'state': state, 'limit': 500, 'offset': offset},
                headers=headers,
                timeout=60,
            )
            response.raise_for_status()
            page = response.json()
            for row in page['rows']:
                decided[row['name']] = row
            offset += len(page['rows'])
            if not page['rows'] or offset >= page['total']:
                break
    return decided


def apply(conn: sqlite3.Connection, args) -> int:
    import requests

    base_url = args.base_url.rstrip('/')
    headers = {'X-API-Key': args.api_key}
    # Only names in the *current* snapshot: a refreshed snapshot drops names that were
    # decided or rebuilt away, and their old verdict must not be applied.
    names = [
        row['name']
        for row in conn.execute(
            'SELECT v.name FROM verdicts v JOIN candidates c ON c.name = v.name AND c.titles_hash = v.titles_hash '
            'LEFT JOIN applied a ON a.name = v.name '
            'WHERE v.verdict = ? AND v.policy = ? AND (a.name IS NULL OR a.undone_at IS NOT NULL) ORDER BY v.name',
            (APPROVE, POLICY),
        )
    ]
    if args.limit:
        names = names[: args.limit]
    decided = decided_on_server(base_url, headers)
    already = [name for name in names if name in decided]
    names = [name for name in names if name not in decided]
    logger.info('%d approvals to apply (%d already decided on the server, left alone)', len(names), len(already))
    if not args.yes:
        logger.info('dry run: pass --yes to post them')
        return 0
    for start in range(0, len(names), DECIDE_BATCH):
        batch = names[start : start + DECIDE_BATCH]
        now = time.time()
        conn.executemany(
            'INSERT OR REPLACE INTO applied (name, applied_at, confirmed_at, undone_at) VALUES (?, ?, NULL, NULL)',
            [(n, now) for n in batch],
        )
        conn.commit()
        try:
            response = requests.post(
                f'{base_url}/api/rules/artists/decide',
                json={'names': batch, 'state': 'white', 'decided_by': DECIDED_BY},
                headers=headers,
                timeout=120,
            )
        except requests.RequestException as error:
            logger.error('batch at %d: no reply (%s); it stays journalled as unconfirmed for undo', start, error)
            return 1
        if response.status_code != 200:
            logger.error('batch at %d refused: %s %s', start, response.status_code, response.text[:200])
            conn.execute('DELETE FROM applied WHERE applied_at = ? AND confirmed_at IS NULL', (now,))
            conn.commit()
            return 1
        conn.execute('UPDATE applied SET confirmed_at = ? WHERE applied_at = ?', (time.time(), now))
        conn.commit()
        logger.info('applied %d/%d', min(start + DECIDE_BATCH, len(names)), len(names))
    return 0


def undo(conn: sqlite3.Connection, args) -> int:
    """Forget the approvals this file made -- and only those still signed `auto-external`.

    A name a human has since re-decided keeps that decision; an unconfirmed batch is
    checked against the server rather than assumed either way.
    """
    import requests

    base_url = args.base_url.rstrip('/')
    headers = {'X-API-Key': args.api_key}
    journalled = [row['name'] for row in conn.execute('SELECT name FROM applied WHERE undone_at IS NULL ORDER BY name')]
    decided = decided_on_server(base_url, headers)
    ours = [n for n in journalled if n in decided and decided[n].get('decided_by') == DECIDED_BY]
    logger.info('%d journalled, %d still ours on the server', len(journalled), len(ours))
    if not args.yes:
        logger.info('dry run: pass --yes to delete them')
        return 0
    failures = 0
    for name in ours:
        response = requests.delete(f'{base_url}/api/rules/artists/{_q(name)}', headers=headers, timeout=30)
        if response.status_code not in (200, 404):
            logger.error('%s: %s %s', name, response.status_code, response.text[:200])
            failures += 1
            continue
        conn.execute('UPDATE applied SET undone_at = ? WHERE name = ?', (time.time(), name))
        conn.commit()
    gone = [n for n in journalled if n not in decided]
    if gone:
        conn.executemany('UPDATE applied SET undone_at = ? WHERE name = ?', [(time.time(), n) for n in gone])
        conn.commit()
    return 1 if failures else 0


# ----------------------------------------------------------------------------- cli


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--state', required=True, help='sqlite file holding the snapshot, cache and verdicts')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('snapshot', help='read the queue and its titles from the database')
    p_run = sub.add_parser('run', help='look every name up and store a verdict')
    p_run.add_argument('--min-tracks', type=int, default=1)
    p_run.add_argument('--max-tracks', type=int, default=10**9)
    p_run.add_argument('--limit', type=int, default=10**9)
    p_run.add_argument('--sources', nargs='+', choices=SOURCES, default=list(SOURCES))
    p_run.add_argument('--offline', action='store_true', help='only the cache; no requests')
    p_run.add_argument('--recompute', action='store_true', help='re-score names that already have a verdict')
    p_rep = sub.add_parser('report', help='CSV of every verdict with its evidence')
    p_rep.add_argument('-o', '--output', default='-')
    for name in ('apply', 'undo'):
        p = sub.add_parser(name)
        p.add_argument('--base-url', default=os.getenv('MUMA_URL', 'http://localhost:8000'))
        p.add_argument('--api-key', default=os.getenv('MUMA_API_KEY') or os.getenv('API_KEY'))
        p.add_argument('--yes', action='store_true', help='actually post; without it only counts')
        if name == 'apply':
            p.add_argument('--limit', type=int, default=0)
    sub.add_parser('summary')
    return parser


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    args = build_parser().parse_args(argv)
    conn = open_state(args.state)
    if args.command == 'snapshot':
        logger.info('%d names with tracks and no decision', snapshot(conn))
    elif args.command == 'run':
        run(conn, args)
    elif args.command == 'report':
        if args.output == '-':
            report(conn, sys.stdout)
        else:
            with open(args.output, 'w', newline='', encoding='utf-8') as handle:
                report(conn, handle)
    elif args.command == 'summary':
        print(json.dumps(summary(conn), indent=2))
    elif args.command in ('apply', 'undo'):
        if not args.api_key:
            logger.error('no API key: pass --api-key or set MUMA_API_KEY')
            return 2
        return (apply if args.command == 'apply' else undo)(conn, args)
    return 0


if __name__ == '__main__':
    sys.exit(main())
