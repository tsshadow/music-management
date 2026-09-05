"""Coverage for build_feed: the one module that touches a connection.

Every other feeds module is pure Python over plain rows; this is the seam that
opens cursors, runs the Task 9 queries, and hands the rows to profile.py,
buckets.py, quota.py and scoring.py. The fixtures below are shaped like the
Task 9 queries' own SELECT lists (see feeds/queries.py) -- not like the pure
modules' own unit tests, which use post-processed shapes (lists, not the raw
comma-joined strings a real cursor returns).
"""

import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from services.music_manager.feeds.build import build_feed
from services.music_manager.feeds.policy import POLICIES
from services.music_manager.tests.scripted_cursor import ScriptedCursor

NOW = datetime(2026, 9, 5, 12, 0, 0)

# listens_query is called twice per build_feed run: once for this listener (2
# params -- username, then the window cutoff) and once for the server profile
# (1 param -- username is None, so its WHERE clause and placeholder drop out).
# Both calls share the same SQL text, so the fake cursor tells them apart by
# how many parameters they carry rather than by the statement itself.
_LISTENS_FRAGMENT = 'JOIN library_tracks t ON t.id = s.track_id'
# Both candidates_query and the dominant-genre queries start `FROM
# library_tracks t`, so the candidates fragment has to name something only
# the candidate query selects.
_CANDIDATES_FRAGMENT = 'library_media_files mf'
_HIERARCHY_FRAGMENT = 'FROM rules_subgenre_hierarchy'
_EXCLUSIONS_FRAGMENT = 'FROM feeds_profile_exclusions'
_LABEL_DOMINANT_FRAGMENT = 'GROUP BY l.name, rg.name'
_ARTIST_DOMINANT_FRAGMENT = 'GROUP BY a.name, rg.name'


class _ParamCount:
    """Matches any params list of a fixed length, without pinning the values.

    build_feed's own username is not known to the fixtures below (they are
    built once and reused across tests for 'user' and 'newcomer' alike), so
    the two listens_query calls are distinguished by shape -- 2 params for a
    named listener, 1 for the server -- rather than by exact value.
    """

    def __init__(self, length):
        self.length = length

    def __eq__(self, other):
        return isinstance(other, list) and len(other) == self.length

    def __repr__(self):
        return f'_ParamCount({self.length})'


def scripted(
    listens=(),
    server_listens=(),
    candidates=(),
    hierarchy=(),
    exclusions=(),
    label_dominant=(),
    artist_dominant=(),
):
    """A connection whose cursor answers build_feed's queries from fixed rows."""
    rules = (
        (_LISTENS_FRAGMENT, _ParamCount(2), list(listens)),
        (_LISTENS_FRAGMENT, _ParamCount(1), list(server_listens)),
        (_CANDIDATES_FRAGMENT, None, list(candidates)),
        (_HIERARCHY_FRAGMENT, None, list(hierarchy)),
        (_EXCLUSIONS_FRAGMENT, None, list(exclusions)),
        (_LABEL_DOMINANT_FRAGMENT, None, list(label_dominant)),
        (_ARTIST_DOMINANT_FRAGMENT, None, list(artist_dominant)),
    )
    cursor = ScriptedCursor(rules)
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn


def _listen(uid, artist, genres, days=1):
    return {
        'track_uid': uid,
        'listened_at': NOW - timedelta(days=days),
        'match_method': 'exact',
        'played_secs': None,
        'artist': artist,
        'labels': None,
        'genres': ','.join(genres),
    }


# 30 distinct uptempo tracks plus 5 distinct raw tracks: comfortably above the
# blend ramp (30 distinct tracks), so scope stays 'user' without leaning on the
# (absent) server profile at all.
MANY_LISTENS = [_listen(f'many-uptempo-{i}', f'Uptempo Artist {i}', ['Uptempo']) for i in range(30)] + [
    _listen(f'many-raw-{i}', f'Raw Artist {i}', ['Raw']) for i in range(5)
]

# Same shape, but with a third, smaller genre so its share survives
# genre_shares' rollup and gets at least one place of its own.
UPTEMPO_HEAVY_LISTENS = (
    [_listen(f'heavy-uptempo-{i}', f'Uptempo Artist {i}', ['Uptempo']) for i in range(30)]
    + [_listen(f'heavy-raw-{i}', f'Raw Artist {i}', ['Raw']) for i in range(4)]
    + [_listen(f'heavy-hardtechno-{i}', f'Hardtechno Artist {i}', ['Hardtechno']) for i in range(4)]
)


def _candidate(
    id_, artist, genre, label=None, heard=False, rating=None, is_soundcloud=False, release_date='2026-09-01'
):
    return {
        'id': id_,
        'title': f'Track {id_}',
        'track_uid': f'uid-{id_}',
        'artist': artist,
        'duration_secs': 300,
        'label': label,
        'has_label': bool(label),
        'genres': genre,
        'file_path': f'/music/{id_}.flac',
        'bpm': 180,
        'release_year': 2026,
        'release_date': release_date,
        'is_soundcloud': is_soundcloud,
        'rating': rating,
        'heard': heard,
    }


# 42 rows spread over uptempo, raw and hardtechno -- enough for the quota to
# have something to divide across three shares at once.
MIXED_CANDIDATES = (
    [_candidate(f'up{i}', f'Uptempo Artist {i}', 'Uptempo') for i in range(20)]
    + [_candidate(f'raw{i}', f'Raw Artist {i}', 'Raw') for i in range(12)]
    + [_candidate(f'hard{i}', f'Hardtechno Artist {i}', 'Hardtechno') for i in range(10)]
)

SOME_CANDIDATES = MIXED_CANDIDATES

# 15 tracks, one artist: enough to overflow the max_per_artist=3 cap by a wide
# margin if the cap were not applied at all.
ONE_ARTIST_FLOOD = [_candidate(f'flood{i}', 'Angerfist', 'Uptempo') for i in range(15)]

# Identical in every score-relevant way except heard -- the only thing that
# should decide which of the two comes out first.
HEARD_AND_UNHEARD = [
    _candidate('heard1', 'Angerfist', 'Uptempo', heard=True),
    _candidate('unheard1', 'Angerfist', 'Uptempo', heard=False),
]


class BuildFeedTest(unittest.TestCase):
    """Drives build_feed with a scripted cursor: see scripted_cursor.py for the shape."""

    def test_an_empty_window_is_stated_rather_than_widened(self):
        conn = scripted(listens=MANY_LISTENS, candidates=[])
        feed = build_feed(conn, 'user', POLICIES['release-radar'], NOW)
        self.assertEqual(feed.state, 'no_matches')
        self.assertEqual(feed.tracks, [])

    def test_a_listener_without_history_falls_back_to_the_server(self):
        conn = scripted(listens=[], server_listens=MANY_LISTENS, candidates=SOME_CANDIDATES)
        feed = build_feed(conn, 'newcomer', POLICIES['release-radar'], NOW)
        self.assertEqual(feed.scope, 'server')

    def test_nobody_has_listened_to_anything_at_all(self):
        conn = scripted(listens=[], server_listens=[], candidates=SOME_CANDIDATES)
        feed = build_feed(conn, 'newcomer', POLICIES['release-radar'], NOW)
        self.assertEqual(feed.state, 'not_enough_data')

    def test_the_shares_are_respected(self):
        conn = scripted(listens=UPTEMPO_HEAVY_LISTENS, candidates=MIXED_CANDIDATES)
        feed = build_feed(conn, 'user', POLICIES['release-radar'], NOW)
        buckets = [track['bucket'] for track in feed.tracks]
        self.assertGreater(buckets.count('uptempo'), buckets.count('hardtechno'))
        self.assertGreaterEqual(buckets.count('hardtechno'), 1)

    def test_no_artist_takes_more_than_three_places(self):
        conn = scripted(listens=MANY_LISTENS, candidates=ONE_ARTIST_FLOOD)
        feed = build_feed(conn, 'user', POLICIES['release-radar'], NOW)
        artists = [track['artist'] for track in feed.tracks]
        self.assertLessEqual(max(artists.count(a) for a in set(artists)), 3)

    def test_the_funnel_never_grows(self):
        conn = scripted(listens=MANY_LISTENS, candidates=MIXED_CANDIDATES)
        feed = build_feed(conn, 'user', POLICIES['release-radar'], NOW)
        counts = list(feed.funnel.values())
        self.assertEqual(counts, sorted(counts, reverse=True))

    def test_an_unheard_track_outranks_an_equal_one_already_played(self):
        conn = scripted(listens=MANY_LISTENS, candidates=HEARD_AND_UNHEARD)
        feed = build_feed(conn, 'user', POLICIES['release-radar'], NOW)
        self.assertFalse(feed.tracks[0]['heard'])

    def test_the_daily_mix_returns_the_same_order_twice(self):
        first = build_feed(
            scripted(listens=MANY_LISTENS, candidates=MIXED_CANDIDATES), 'user', POLICIES['daily-mix'], NOW
        )
        second = build_feed(
            scripted(listens=MANY_LISTENS, candidates=MIXED_CANDIDATES), 'user', POLICIES['daily-mix'], NOW
        )
        self.assertEqual([t['id'] for t in first.tracks], [t['id'] for t in second.tracks])
