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
"""

import argparse
import csv
import hashlib
import json
import logging
import os
import re
import sqlite3
import sys
import time
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

logger = logging.getLogger('artist-auto-approve')

#: Bump when a threshold or a normalisation rule changes: verdicts stored under an older
#: policy are recomputed from the cached responses, nothing is fetched again.
POLICY = 'v1'
DECIDED_BY = 'auto-external'
USER_AGENT = 'muma-artist-auto-approve/0.1 (https://gitlab.com/muma/music-management)'

DEEZER = 'deezer'
MUSICBRAINZ = 'musicbrainz'
ITUNES = 'itunes'
#: Asked in this order, cheapest first; a name stops at its first approval.
SOURCES = (DEEZER, ITUNES, MUSICBRAINZ)
#: Deezer and iTunes are fed by the same distributors, so an approval on one title needs
#: MusicBrainz -- separately curated -- plus one of these.
COMMERCIAL = {DEEZER, ITUNES}

APPROVE = 'approve'
UNRESOLVED = 'unresolved'
SKIPPED = 'skipped'
#: A source did not answer (quota, 503, network) so the evidence is partial; the next
#: run asks again instead of treating silence as "not found".
INCOMPLETE = 'incomplete'

#: Rules 1 and 2: this many different local titles found outside.
MIN_TITLES = 2
#: Rules 2 and 3 lean on one title, so it has to be a distinctive one -- `Free` on a
#: same-named artist is a coincidence waiting to happen, `Feel The Electricity` is not.
DISTINCTIVE_WORDS = 2
DISTINCTIVE_LETTERS = 10
#: A title shorter than this never counts at all; `180` matches too much.
MIN_TITLE_LETTERS = 4
#: MusicBrainz artist types that are an act. `Other` covers labels and event brands.
MUSICBRAINZ_ACT_TYPES = {'Person', 'Group', 'Orchestra', 'Choir', 'Character'}
#: How many exact-name candidates per source get their tracklist fetched. A short name
#: has many namesakes; the real one is rarely past the third.
MAX_CANDIDATES = 3

#: Names that are catalogued as artists by the stores but are labels, channels, event
#: brands or shows in this library. They have real recording credits (a compilation
#: series, a podcast), so evidence would approve them; keep them in the queue.
BRAND_BLOCKLIST = {
    'q-dance',
    'dj mag',
    'sick events',
    'the boom room',
    'various artists',
    'various',
    'monstercat',
    'defqon.1',
    'thunderdome',
    'masters of hardcore',
    'dominator',
    'hardtunes',
    'scantraxx',
    'art of dance',
    'b2s',
    'bkjn',
    'mixmash',
}

#: A name shaped like a brand rather than an act. The stores credit a festival with its
#: anthems and a label with its compilations, so evidence would approve `DediKted
#: Festival` (it did); such a name stays in the queue for a human.
BRAND_SHAPE = re.compile(
    r"\b(?:festival|events?|records|recordings|recordz|music|tv|radio|podcast|exclusives?|premieres?|presents|"
    r"sessions?|mag|magazine|official|channel|network|label|agency|bookings|promo(?:tions?)?|store|shop)\b|"
    r"\b(?:19|20)\d\d\b",
    re.IGNORECASE,
)

#: Per-source minimum interval between requests, seconds. MusicBrainz says one per
#: second and answers 503 above it; iTunes documents ~20 per minute; Deezer is
#: undocumented and answers `Quota limit exceeded` (HTTP 200) when pushed.
MIN_INTERVAL = {DEEZER: 0.25, MUSICBRAINZ: 1.1, ITUNES: 3.2}
TIMEOUT = 20
RETRIES = 5

DECIDE_BATCH = 100

# ----------------------------------------------------------------------------- normalisation

#: A bracket that ends in a mix-type word: `(Extended Mix)`, `(Hard Remix)`, `(Official
#: BKJN vs Partyraiser 2026 Anthem)`, `(Album Intro Edit)`. Ending, not containing: `(Free
#: Your Mind)` and `(Music Is Everything)` are the song.
_MIX_BRACKET = re.compile(
    r"\s*[\(\[]\s*[^()\[\]]*?\b(?:remix|rmx|mix|edit|bootleg|mashup|mash-up|rework|remake|refix|flip|vip|"
    r"version|instrumental|acapella|dub|cut|anthem|theme|extended|original|radio|reprise|explicit|clean)\s*[\)\]]",
    re.IGNORECASE,
)
#: A bracket that is packaging, wherever the word sits: `[OUT NOW ON OWSLA!]`, `(jeuj...
#: free download)`, `(Official Videoclip)`, `(HQ Preview)`.
_PROMO_BRACKET = re.compile(
    r"\s*[\(\[]\s*[^()\[\]]*\b(?:free\s*(?:\w+\s*)?(?:dl|download)|out now|official\s*(?:video|audio|videoclip|music video)?|"
    r"videoclip|preview|snippet|premiere|hq|hd|lyrics?|visualizer)\b[^()\[\]]*[\)\]]",
    re.IGNORECASE,
)
#: A catalogue id (`[TX023]`, `[ FR002 ]`, `(DEM050)`), a label (`[Silk Music]`, `(Napalm
#: Records)`) or a feature (`(feat. Layna)`).
_TAG_BRACKET = re.compile(
    r"\s*[\(\[]\s*(?:(?-i:[A-Z]{1,8}[\- ]?\d{1,4}[A-Z]{0,2})|[^()\[\]]*\b(?:records?|recordings|music)|"
    r"(?:feat\.?|ft\.?|featuring)\b[^()\[\]]*)\s*[\)\]]",
    re.IGNORECASE,
)
#: Packaging at the very end of the title, after brackets are gone: `... FREE DOWNLOAD`,
#: `... - Napalm Records`, `...hardtunes only`. Anchored, so `Dream Premiere Night` keeps
#: its name.
_TRAILING_NOISE = re.compile(
    r"\s*(?:[-|–]\s*)?(?:free\s*(?:dl|download)|out now|official\s*(?:video|audio|music video)|hq|hd|preview|"
    r"snippet|premiere|hardtunes only|[^-|–]*\brecords)\W*(?:[\(\[][^()\[\]]*[\)\]]\W*)*$",
    re.IGNORECASE,
)
_FEAT = re.compile(r"\s+(?:feat\.?|ft\.?|featuring)\s+.*$", re.IGNORECASE)
#: What a label or an event is credited with on the stores: sets, compilations, mixes.
#: Checked on the raw title, before `(Album Mix)` and `(Continuous Mix)` are stripped.
_COMPILATION_MARKERS = re.compile(
    r"\bbest of\b|\bvol(?:ume)?\.?\s*\d|\bchapter\s*\d|\bmegamix\b|\b(?:album|continuous|full|dj|live|yearmix|year)\s*mix\b|"
    r"\bmix\s*$",
    re.IGNORECASE,
)
#: What a set or a show is called, judged after the packaging is gone so that a year
#: in `(Official ... 2026 Anthem)` does not condemn the song.
_SET_MARKERS = re.compile(
    r"\|| @ |\blive (?:from|at|set)\b|\bdj[- ]?set\b|\bpodcast\b|\bepisode\b|\bwarm-?up\b|"
    r"\b(?:19|20)\d\d\b|\bpresents\b|\bpres\.",
    re.IGNORECASE,
)


def fold(value: str) -> str:
    """Case, accents, typographic quotes and punctuation folded away; words separated by one space."""
    value = unicodedata.normalize('NFKD', value or '')
    value = ''.join(ch for ch in value if not unicodedata.combining(ch))
    value = value.replace('&', ' and ')
    return re.sub(r'[^a-z0-9]+', ' ', value.casefold()).strip()


def normalise_artist(name: str) -> str:
    return fold(name)


def strip_packaging(title: str) -> str:
    """The song under the packaging: no mix suffix, catalogue id, label, promo tail or feature."""
    value = title or ''
    previous = None
    while previous != value:
        previous = value
        for pattern in (_MIX_BRACKET, _PROMO_BRACKET, _TAG_BRACKET, _TRAILING_NOISE):
            value = pattern.sub('', value)
    return _FEAT.sub('', value).strip()


def normalise_title(title: str) -> str:
    return fold(strip_packaging(title))


def looks_like_a_set(title: str) -> bool:
    """`Defqon.1 | ORANGE | Friday`, `Uncaged Vol. 8 (Album Mix)`: not a song, never matched.

    Sets, compilations and mixes are what a *label* is credited with on the stores, so
    they count on neither side -- Monstercat was approved on two of them.
    """
    return bool(_COMPILATION_MARKERS.search(title or '')) or bool(_SET_MARKERS.search(strip_packaging(title)))


def letters(value: str) -> int:
    return sum(ch.isalnum() for ch in value)


def is_distinctive(normalised_title: str) -> bool:
    return len(normalised_title.split()) >= DISTINCTIVE_WORDS and letters(normalised_title) >= DISTINCTIVE_LETTERS


def usable_titles(titles: list[str]) -> dict[str, str]:
    """Normalised title -> one raw example, for the titles worth asking about."""
    out: dict[str, str] = {}
    for raw in titles:
        if looks_like_a_set(raw):
            continue
        key = normalise_title(raw)
        if letters(key) < MIN_TITLE_LETTERS:
            continue
        out.setdefault(key, raw)
    return out


# ----------------------------------------------------------------------------- scoring


@dataclass
class ExternalArtist:
    source: str
    external_id: str
    name: str
    kind: str | None = None  # MusicBrainz type; None elsewhere
    titles: list[str] = field(default_factory=list)  # raw external recording titles
    detail: dict = field(default_factory=dict)  # fans, url -- evidence only


@dataclass
class Verdict:
    verdict: str
    rule: str | None
    evidence: dict


def match_titles(local: dict[str, str], external: ExternalArtist) -> dict[str, str]:
    """Local normalised titles found in the external tracklist, with the external raw title."""
    seen = {}
    for raw in external.titles:
        if looks_like_a_set(raw):
            continue
        key = normalise_title(raw)
        if key in local and key not in seen:
            seen[key] = raw
    return seen


def score_artist(name: str, titles: list[str], candidates: list[ExternalArtist]) -> Verdict:
    """The decision, from the local titles and whatever the sources said about the name.

    Candidates must already be exact-name matches; this does not re-check the name.
    """
    if normalise_artist(name) in {fold(brand) for brand in BRAND_BLOCKLIST}:
        return Verdict(SKIPPED, 'brand', {'reason': 'on the label/channel blocklist'})
    if BRAND_SHAPE.search(name):
        return Verdict(SKIPPED, 'brand-shape', {'reason': 'named like a label, channel or event'})
    local = usable_titles(titles)
    if not local:
        return Verdict(SKIPPED, 'no-titles', {'reason': 'no title survives normalisation'})

    per_candidate = []
    for candidate in candidates:
        matched = match_titles(local, candidate)
        if not matched:
            continue
        per_candidate.append(
            {
                'source': candidate.source,
                'id': candidate.external_id,
                'name': candidate.name,
                'type': candidate.kind,
                'matched': {key: {'local': local[key], 'external': raw} for key, raw in matched.items()},
                **candidate.detail,
            }
        )
    evidence = {'titles_queried': len(local), 'matches': per_candidate}
    if not per_candidate:
        return Verdict(UNRESOLVED, None, evidence)

    acts = [hit for hit in per_candidate if hit['source'] != MUSICBRAINZ or hit['type'] in MUSICBRAINZ_ACT_TYPES]

    # Rule 1: two titles on one external act.
    if any(len(hit['matched']) >= MIN_TITLES for hit in acts):
        return Verdict(APPROVE, 'two-titles-one-act', evidence)

    # Rule 2: two titles from two sources, one of them distinctive. Two namesakes on
    # one store with a title each are not two sources.
    by_source: dict[str, set[str]] = defaultdict(set)
    for hit in acts:
        by_source[hit['source']].update(hit['matched'])
    matched_keys = set().union(*by_source.values()) if by_source else set()
    if (
        len(by_source) >= 2
        and len(matched_keys) >= MIN_TITLES
        and any(len(matched_keys - keys) >= 1 for keys in by_source.values())
        and any(is_distinctive(key) for key in matched_keys)
    ):
        return Verdict(APPROVE, 'two-titles-two-sources', evidence)

    # Rule 3: one distinctive title on MusicBrainz (an act) and on a store.
    mb_ok = any(hit['source'] == MUSICBRAINZ and any(is_distinctive(key) for key in hit['matched']) for hit in acts)
    store_ok = any(hit['source'] in COMMERCIAL and any(is_distinctive(key) for key in hit['matched']) for hit in acts)
    if mb_ok and store_ok:
        return Verdict(APPROVE, 'distinctive-title-two-sources', evidence)
    return Verdict(UNRESOLVED, None, evidence)


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


def titles_hash(titles: list[str]) -> str:
    """Changes when the library's titles for a name change, which makes a verdict stale."""
    return hashlib.sha1(json.dumps(sorted(set(titles))).encode()).hexdigest()[:16]


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


def _deezer_error(body: str) -> bool:
    """Deezer reports its quota (and most other refusals) as a 200 with an error object."""
    try:
        return isinstance(json.loads(body), dict) and 'error' in json.loads(body)
    except ValueError:
        return True


def _q(value: str) -> str:
    from urllib.parse import quote

    return quote(value, safe='')


def _lucene(value: str) -> str:
    return re.sub(r'([+\-!(){}\[\]^"~*?:\\/&|])', r'\\\1', value)


def deezer_candidates(fetcher: Fetcher, name: str) -> list[ExternalArtist]:
    key = normalise_artist(name)
    found = fetcher.get(DEEZER, f'https://api.deezer.com/search/artist?q={_q(name)}&limit=10') or {}
    out = []
    for artist in (found.get('data') or [])[: MAX_CANDIDATES * 2]:
        if normalise_artist(artist.get('name', '')) != key:
            continue
        candidate = ExternalArtist(DEEZER, str(artist['id']), artist['name'], detail={'fans': artist.get('nb_fan')})
        top = fetcher.get(DEEZER, f"https://api.deezer.com/artist/{artist['id']}/top?limit=50") or {}
        candidate.titles = [track.get('title', '') for track in top.get('data') or []]
        out.append(candidate)
        if len(out) >= MAX_CANDIDATES:
            break
    # The top list is short for a small act; the plain search reaches the long tail and
    # tracks the name is only credited on, filtered back to the exact ids found above.
    if out:
        ids = {c.external_id: c for c in out}
        search = fetcher.get(DEEZER, f'https://api.deezer.com/search?q={_q(name)}&limit=100') or {}
        for track in search.get('data') or []:
            owner = ids.get(str((track.get('artist') or {}).get('id')))
            if owner is not None:
                owner.titles.append(track.get('title', ''))
    return out


def musicbrainz_candidates(fetcher: Fetcher, name: str) -> list[ExternalArtist]:
    key = normalise_artist(name)
    query = _q(f'artist:"{_lucene(name)}"')
    found = fetcher.get(MUSICBRAINZ, f'https://musicbrainz.org/ws/2/artist?query={query}&fmt=json&limit=10') or {}
    out = []
    for artist in found.get('artists') or []:
        names = [artist.get('name', '')] + [alias.get('name', '') for alias in artist.get('aliases') or []]
        if key not in {normalise_artist(n) for n in names}:
            continue
        candidate = ExternalArtist(MUSICBRAINZ, artist['id'], artist['name'], kind=artist.get('type'))
        recordings = (
            fetcher.get(MUSICBRAINZ, f"https://musicbrainz.org/ws/2/recording?artist={artist['id']}&fmt=json&limit=100")
            or {}
        )
        candidate.titles = [r.get('title', '') for r in recordings.get('recordings') or []]
        out.append(candidate)
        if len(out) >= MAX_CANDIDATES:
            break
    return out


def itunes_candidates(fetcher: Fetcher, name: str) -> list[ExternalArtist]:
    key = normalise_artist(name)
    found = (
        fetcher.get(ITUNES, f'https://itunes.apple.com/search?term={_q(name)}&entity=song&limit=200&country=NL') or {}
    )
    by_id: dict[str, ExternalArtist] = {}
    for track in found.get('results') or []:
        if normalise_artist(track.get('artistName', '')) != key:
            continue
        artist_id = str(track.get('artistId'))
        candidate = by_id.setdefault(artist_id, ExternalArtist(ITUNES, artist_id, track['artistName']))
        candidate.titles.append(track.get('trackName', ''))
    return list(by_id.values())[:MAX_CANDIDATES]


LOOKUPS = {DEEZER: deezer_candidates, MUSICBRAINZ: musicbrainz_candidates, ITUNES: itunes_candidates}


def resolve(fetcher: Fetcher, name: str, titles: list[str], sources: tuple[str, ...]) -> Verdict:
    """Cheapest source first; stop as soon as the evidence is enough."""
    candidates: list[ExternalArtist] = []
    verdict = score_artist(name, titles, candidates)
    if verdict.verdict == SKIPPED:
        return verdict
    failed_before = fetcher.failed
    for source in sources:
        candidates.extend(LOOKUPS[source](fetcher, name))
        verdict = score_artist(name, titles, candidates)
        if verdict.verdict == APPROVE:
            break
    if verdict.verdict != APPROVE and fetcher.failed > failed_before:
        verdict = Verdict(INCOMPLETE, None, dict(verdict.evidence, failed_requests=fetcher.failed - failed_before))
    verdict.evidence['sources'] = list(sources)
    return verdict


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
