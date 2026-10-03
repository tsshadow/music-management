"""Coverage for build_feed: the one module that touches a connection.

Every other feeds module is pure Python over plain rows; this is the seam that
opens cursors, runs the Task 9 queries, and hands the rows to profile.py,
buckets.py, quota.py and scoring.py. The fixtures below are shaped like the
Task 9 queries' own SELECT lists (see feeds/queries.py) -- not like the pure
modules' own unit tests, which use post-processed shapes (lists, not the raw
comma-joined strings a real cursor returns).
"""

import dataclasses
import unittest
from collections import Counter
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from services.music_manager.feeds import build
from services.music_manager.feeds.build import build_feed, describe_feed, resolve_profile
from services.music_manager.feeds.policy import POLICIES
from services.music_manager.feeds.profile import TAIL
from services.music_manager.feeds.queries import listens_query
from services.music_manager.tests.scripted_cursor import ScriptedCursor

# daily-mix (an alias of daily-mix-mid, see policy.py) now carries a hardness_band,
# which excludes any candidate whose hardness cannot be resolved -- exactly what
# every fixture below leaves unset, since they predate the hardness statistic
# entirely. Tests in this file that only want the plain daily_sample ordering
# behaviour, independent of hardness banding, use this instead.
PLAIN_DAILY_SAMPLE = dataclasses.replace(POLICIES['daily-mix-mid'], slug='daily-sample-test', hardness_band=None)

NOW = datetime(2026, 9, 5, 12, 0, 0)

# listens_query is called twice per build_feed run: once for this listener and
# once for the server profile. The two are told apart by the WHERE clause that
# actually differs between them -- the server variant has no username filter at
# all -- and never by how many parameters they carry. A parameter count is not
# a property of the question being asked: adding one parameter to listens_query
# would silently reroute the user's query to the server fixture, and every test
# here would stay green while testing the wrong thing. These fragments cannot
# drift that way; if the query's shape changes, no rule matches, the fixtures
# come back empty and the tests fail loudly.
_LISTENS_FRAGMENT = 'JOIN library_tracks t ON t.id = s.track_id'
_USER_LISTENS_FRAGMENT = 'WHERE s.username = %s AND s.listened_at >= %s'
_SERVER_LISTENS_FRAGMENT = 'WHERE s.listened_at >= %s'
# Both candidates_query and the dominant-genre queries start `FROM
# library_tracks t`, so the candidates fragment has to name something only
# the candidate query selects.
_CANDIDATES_FRAGMENT = 'library_media_files mf'
_CANONICAL_ROWS_FRAGMENT = 'AND t.id IN ('
# rotation_counts_query also carries the media-file EXISTS, so it is told apart by
# the per-window count columns only it selects.
_ROTATION_COUNTS_FRAGMENT = 'AS songs_0'
# The split daily mixes (bug report 131): split_sample_query also carries the media-file
# EXISTS and candidate_rows_query the canonical fragment, so both are told apart by the
# half they name. last_listened_query by the column only it selects.
_RECENT_SAMPLE_FRAGMENT = 'AS recent_id'
_OLDER_SAMPLE_FRAGMENT = 'AS older_id'
_RECENT_ROWS_FRAGMENT = "'recent' AS pool"
_OLDER_ROWS_FRAGMENT = "'older' AS pool"
_LAST_LISTENED_FRAGMENT = 'AS last_listened_at'
_HIERARCHY_FRAGMENT = 'FROM rules_subgenre_hierarchy'
_EXCLUSIONS_FRAGMENT = 'FROM feeds_profile_exclusions'
_LABEL_DOMINANT_FRAGMENT = 'GROUP BY l.name, rg.name'
_ARTIST_DOMINANT_FRAGMENT = 'GROUP BY a.name, rg.name'
# genre_hardness_query, and the label/artist variants of entity_hardness_query --
# told apart from the dominant-genre fragments above (which also join
# library_track_genres/rules_genres) by the aggregate they actually select.
_GENRE_HARDNESS_FRAGMENT = 'AS weighted_sum'
_LABEL_HARDNESS_FRAGMENT = 'JOIN library_track_labels tl ON tl.label_id = l.id'
_ARTIST_HARDNESS_FRAGMENT = 'JOIN library_tracks t ON t.primary_artist_id = a.id'


def scripted(
    listens=(),
    server_listens=(),
    candidates=(),
    hierarchy=(),
    exclusions=(),
    label_dominant=(),
    artist_dominant=(),
    genre_hardness=(),
    label_hardness=(),
    artist_hardness=(),
    canonicals=(),
    rotation_counts=(),
    older=(),
    last_listened=(),
    recent=None,
):
    """A connection whose cursor answers build_feed's queries from fixed rows.

    `recent` is a split daily mix's recent half, `candidates` unless given -- the rows a
    daily mix drew from before the split, so a test written before it still feeds them.
    """
    recent = list(candidates if recent is None else recent)
    rules = (
        (_ROTATION_COUNTS_FRAGMENT, None, list(rotation_counts)),
        (_RECENT_SAMPLE_FRAGMENT, None, [{'recent_id': row['id']} for row in recent]),
        (_OLDER_SAMPLE_FRAGMENT, None, [{'older_id': row['id']} for row in older]),
        (_RECENT_ROWS_FRAGMENT, None, recent),
        (_OLDER_ROWS_FRAGMENT, None, list(older)),
        (_LAST_LISTENED_FRAGMENT, None, list(last_listened)),
        # canonical_rows_query shares candidates_query's SELECT, so it has to be matched
        # first, on the one thing only it has.
        (_CANONICAL_ROWS_FRAGMENT, None, list(canonicals)),
        (_USER_LISTENS_FRAGMENT, None, list(listens)),
        (_SERVER_LISTENS_FRAGMENT, None, list(server_listens)),
        (_CANDIDATES_FRAGMENT, None, list(candidates)),
        (_HIERARCHY_FRAGMENT, None, list(hierarchy)),
        (_EXCLUSIONS_FRAGMENT, None, list(exclusions)),
        (_LABEL_DOMINANT_FRAGMENT, None, list(label_dominant)),
        (_ARTIST_DOMINANT_FRAGMENT, None, list(artist_dominant)),
        (_GENRE_HARDNESS_FRAGMENT, None, list(genre_hardness)),
        (_LABEL_HARDNESS_FRAGMENT, None, list(label_hardness)),
        (_ARTIST_HARDNESS_FRAGMENT, None, list(artist_hardness)),
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
    id_, artist, genre, label=None, heard=False, rating=None, is_soundcloud=False, release_date='2026-09-01', bpm=180
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
        'bpm': bpm,
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

# More than max_per_artist (3) tracks with no artist at all -- a mix of None
# and '', since both reach the same "no name" branch in _cap_per_artist. None
# of these share a real artist with any other, so the cap must never treat
# them as one bucket the way it would a flood from a single named artist.
NO_ARTIST_FLOOD = [
    _candidate('noartist0', None, 'Uptempo'),
    _candidate('noartist1', None, 'Uptempo'),
    _candidate('noartist2', '', 'Uptempo'),
    _candidate('noartist3', '', 'Uptempo'),
    _candidate('noartist4', None, 'Uptempo'),
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

    def test_untagged_artists_are_not_capped_as_one_shared_bucket(self):
        """The cap partitions each artist-less track on its own id (technical.md,

        step 8) -- a `key = artist or '__untagged__'` regression would collapse
        every one of these into a single shared key and silently cap the whole
        group at max_per_artist, which `test_no_artist_takes_more_than_three_places`
        cannot catch because it only ever floods one *named* artist.
        """
        conn = scripted(listens=MANY_LISTENS, candidates=NO_ARTIST_FLOOD)
        feed = build_feed(conn, 'user', POLICIES['release-radar'], NOW)
        self.assertEqual(len(feed.tracks), len(NO_ARTIST_FLOOD))

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
        first = build_feed(scripted(listens=MANY_LISTENS, candidates=MIXED_CANDIDATES), 'user', PLAIN_DAILY_SAMPLE, NOW)
        second = build_feed(
            scripted(listens=MANY_LISTENS, candidates=MIXED_CANDIDATES), 'user', PLAIN_DAILY_SAMPLE, NOW
        )
        self.assertEqual([t['id'] for t in first.tracks], [t['id'] for t in second.tracks])

    def test_the_two_listens_fixtures_cannot_answer_each_other_s_query(self):
        """The fixtures route on the WHERE clause that genuinely differs between

        the two calls, not on a parameter count. Neither fragment appears in the
        other's statement, so neither rule can ever swallow the other's query --
        which a count-based rule silently would the day listens_query gains a
        parameter.
        """
        user_sql = ' '.join(listens_query('user', 90, NOW)[0].split())
        server_sql = ' '.join(listens_query(None, 90, NOW)[0].split())
        self.assertIn(_USER_LISTENS_FRAGMENT, user_sql)
        self.assertNotIn(_SERVER_LISTENS_FRAGMENT, user_sql)
        self.assertIn(_SERVER_LISTENS_FRAGMENT, server_sql)
        self.assertNotIn(_USER_LISTENS_FRAGMENT, server_sql)

    def test_a_full_profile_never_queries_the_server(self):
        """MANY_LISTENS alone is already above the blend ramp, so blend() would

        discard a server profile unread -- build_feed should not even ask for
        one. The scripted cursor's own executed-statement log is the proof.
        """
        conn = scripted(listens=MANY_LISTENS, candidates=MIXED_CANDIDATES)
        build_feed(conn, 'user', POLICIES['release-radar'], NOW)
        cursor = conn.cursor.return_value
        self.assertEqual(len(cursor.statements_matching(_LISTENS_FRAGMENT)), 1)

    def test_the_dominant_genre_queries_only_ask_about_the_names_in_play(self):
        """Unbounded, these are two full-library group-bys on every request.

        The parameters are the distinct labels and artists the candidates
        themselves carry -- nothing wider.
        """
        candidates = [
            _candidate('a', 'Angerfist', 'Uptempo', label='Masters of Hardcore'),
            _candidate('b', 'Angerfist', 'Uptempo', label='Masters of Hardcore'),
            _candidate('c', 'Radical Redemption', 'Uptempo', label='Minus Is More'),
        ]
        conn = scripted(listens=MANY_LISTENS, candidates=candidates)
        build_feed(conn, 'user', POLICIES['release-radar'], NOW)
        cursor = conn.cursor.return_value
        _, label_params = cursor.statements_matching(_LABEL_DOMINANT_FRAGMENT)[0]
        _, artist_params = cursor.statements_matching(_ARTIST_DOMINANT_FRAGMENT)[0]
        self.assertEqual(label_params, ['Masters of Hardcore', 'Minus Is More'])
        self.assertEqual(artist_params, ['Angerfist', 'Radical Redemption'])

    def test_candidates_without_a_label_ask_no_label_question_at_all(self):
        """An empty name set must skip the query, not send `IN ()`."""
        conn = scripted(listens=MANY_LISTENS, candidates=NO_ARTIST_FLOOD)
        build_feed(conn, 'user', POLICIES['release-radar'], NOW)
        cursor = conn.cursor.return_value
        self.assertEqual(cursor.statements_matching(_LABEL_DOMINANT_FRAGMENT), [])
        self.assertEqual(cursor.statements_matching(_ARTIST_DOMINANT_FRAGMENT), [])

    def test_a_server_with_no_history_falls_back_to_configured_genres(self):
        conn = scripted(listens=[], server_listens=[], candidates=MIXED_CANDIDATES)
        feed = build_feed(conn, 'newcomer', POLICIES['release-radar'], NOW, starting_genres=['Uptempo', 'Raw'])
        self.assertEqual(feed.scope, 'configured')

    def test_without_starting_genres_the_fallback_is_still_not_enough_data(self):
        conn = scripted(listens=[], server_listens=[], candidates=MIXED_CANDIDATES)
        feed = build_feed(conn, 'newcomer', POLICIES['release-radar'], NOW)
        self.assertEqual(feed.state, 'not_enough_data')


WINDOW = POLICIES['release-radar'].profile_window_days


class ResolveProfileTest(unittest.TestCase):
    """Steps 1-3 on their own -- the one copy build_feed, the router and the dry run share.

    They each carried their own before, and the copies had already drifted: the dry run's
    never applied `starting_genres`, so the configured-fallback path was invisible to the
    tool built to measure it. These tests exercise the function directly, so a fourth caller
    inherits behaviour that is pinned rather than re-derived.
    """

    def test_a_listener_with_a_profile_of_their_own_owns_the_shares(self):
        resolution = resolve_profile(scripted(listens=UPTEMPO_HEAVY_LISTENS), 'user', WINDOW, NOW)
        self.assertEqual(resolution.scope, 'user')
        self.assertEqual(resolution.profile.scope, 'user')
        self.assertGreater(resolution.shares['uptempo'], resolution.shares['raw'])
        self.assertAlmostEqual(sum(resolution.shares.values()), 1.0)

    def test_a_newcomer_borrows_the_server(self):
        resolution = resolve_profile(scripted(listens=[], server_listens=MANY_LISTENS), 'newcomer', WINDOW, NOW)
        self.assertEqual(resolution.scope, 'server')

    def test_nothing_anywhere_and_no_configured_fallback_is_empty(self):
        """`empty` is what build_feed turns into `not_enough_data`; resolve_profile

        reports the scope and leaves the verdict to its caller, because
        /api/feeds/profile renders the same state as `scope: empty` rather than
        as an error.
        """
        resolution = resolve_profile(scripted(listens=[], server_listens=[]), 'newcomer', WINDOW, NOW)
        self.assertEqual(resolution.scope, 'empty')
        self.assertEqual(resolution.shares, {TAIL: 1.0})

    def test_the_configured_fallback_is_applied_here_and_becomes_the_shares(self):
        """The step the dry run's own copy of this logic never had."""
        resolution = resolve_profile(
            scripted(listens=[], server_listens=[]), 'newcomer', WINDOW, NOW, starting_genres=['Uptempo', 'Raw']
        )
        self.assertEqual(resolution.scope, 'configured')
        self.assertEqual(resolution.profile.genres, {'uptempo': 1.0, 'raw': 1.0})
        self.assertAlmostEqual(resolution.shares['uptempo'], 0.5)
        self.assertAlmostEqual(resolution.shares['raw'], 0.5)

    def test_a_configured_fallback_never_overrules_a_real_profile(self):
        resolution = resolve_profile(
            scripted(listens=MANY_LISTENS), 'user', WINDOW, NOW, starting_genres=['Hardtechno']
        )
        self.assertEqual(resolution.scope, 'user')
        self.assertNotIn('hardtechno', resolution.shares)

    def test_an_exclusion_is_applied_before_the_shares_are_taken(self):
        conn = scripted(listens=UPTEMPO_HEAVY_LISTENS, exclusions=[{'entity_type': 'genre', 'entity_name': 'uptempo'}])
        resolution = resolve_profile(conn, 'user', WINDOW, NOW)
        self.assertNotIn('uptempo', resolution.profile.genres)
        self.assertNotIn('uptempo', resolution.shares)

    def test_the_subgenre_graph_comes_back_with_the_shares(self):
        """build_feed buckets candidates against exactly the graph the shares were

        rolled up with; handing back one and re-reading the other is how those two
        drift apart.
        """
        conn = scripted(listens=MANY_LISTENS, hierarchy=[{'subgenre': 'Uptempo', 'genre': 'Hardcore'}])
        resolution = resolve_profile(conn, 'user', WINDOW, NOW)
        self.assertEqual(resolution.parents, {'uptempo': {'hardcore'}})

    def test_the_listens_come_back_with_the_profile(self):
        """The band mixes' hardness percentiles are measured over the listener's own
        listens; carrying them on the resolution is what lets that happen without a
        second read of scrobble_listens."""
        resolution = resolve_profile(scripted(listens=MANY_LISTENS), 'user', WINDOW, NOW)
        self.assertEqual(len(resolution.listens), len(MANY_LISTENS))
        self.assertEqual(resolution.listens[0]['genres'], ['Uptempo'])


class DescribeOnceTest(unittest.TestCase):
    """docs/designs/feeds/home-load.md, step 2: one resolution serves every describe.

    `GET /api/feeds` used to resolve the profile once per policy -- seven reads of the
    same 90-day history, plus one more per band mix for its percentiles. Eleven of
    the fourteen listens queries behind one Home load were this.
    """

    def _listens_queries(self, conn):
        return conn.cursor.return_value.statements_matching(_LISTENS_FRAGMENT)

    def test_describing_every_policy_off_one_resolution_reads_the_listens_once(self):
        conn = scripted(listens=MANY_LISTENS)
        resolution = resolve_profile(conn, 'user', WINDOW, NOW)
        for policy in POLICIES.values():
            describe_feed(conn, 'user', policy, NOW, resolution=resolution)
        self.assertEqual(len(self._listens_queries(conn)), 1)

    def test_describing_without_a_resolution_still_resolves_on_its_own(self):
        """The single-policy callers keep working unchanged."""
        conn = scripted(listens=MANY_LISTENS)
        info = describe_feed(conn, 'user', POLICIES['daily-mix-mid'], NOW)
        self.assertEqual(info['title'], 'Middenin')
        self.assertEqual(len(self._listens_queries(conn)), 1)

    def test_the_hardness_stats_are_measured_once_and_shared_by_the_three_bands(self):
        conn = scripted(listens=MANY_LISTENS)
        resolution = resolve_profile(conn, 'user', WINDOW, NOW)
        cursor = conn.cursor.return_value
        for slug in ('daily-mix-soft', 'daily-mix-mid', 'daily-mix-hard'):
            describe_feed(conn, 'user', POLICIES[slug], NOW, resolution=resolution)
        # The fixture listens carry artists and no labels or track ids, so the one
        # hardness lookup that actually runs is the artist mean -- once, for the first
        # band; the other two read the memo.
        self.assertEqual(len(cursor.statements_matching(_ARTIST_HARDNESS_FRAGMENT)), 1)
        self.assertIn('hardness_stats', resolution.memo)

    def test_the_shared_rows_are_not_mutated_by_the_hardness_pass(self):
        """`_listener_hardness_stats` rewrites `label` and adds `hardness` on the rows it
        works on; the resolution's own rows must stay what build_profile saw."""
        conn = scripted(listens=MANY_LISTENS)
        resolution = resolve_profile(conn, 'user', WINDOW, NOW)
        describe_feed(conn, 'user', POLICIES['daily-mix-mid'], NOW, resolution=resolution)
        self.assertNotIn('hardness', resolution.listens[0])
        self.assertNotIn('label', resolution.listens[0])


# Three candidates, one per band, resolved through the tempo fallback alone: no
# genre_hardness or entity_hardness fixture is provided, so every candidate falls
# all the way through track_hardness's chain to its bpm. 130 -> 20 (soft), 165 ->
# 65 (mid), 205 -> 95 (hard) -- see test_feeds_hardness.py's TempoHardnessTest for
# the interpolation these numbers come from.
SOFT_CANDIDATE = _candidate('soft1', None, 'Uptempo', bpm=130)
MID_CANDIDATE = _candidate('mid1', None, 'Uptempo', bpm=165)
HARD_CANDIDATE = _candidate('hard1', None, 'Uptempo', bpm=205)
SPECTRUM_CANDIDATES = [SOFT_CANDIDATE, MID_CANDIDATE, HARD_CANDIDATE]

# A band mix without the recent/older split (bug report 131): the one shape the
# 90 -> 365 -> none relaxation ladder still runs for (the dry run's --window).
LADDER_MID = dataclasses.replace(POLICIES['daily-mix-mid'], release_window_days=90, recent_share=None)


class HardnessBandBuildTest(unittest.TestCase):
    """The band edges are fixed at (50, 75) (`hardness.DEFAULT_BAND_EDGES`) by

    default, regardless of this listener's own history -- MANY_LISTENS resolves
    no hardness at all (its fixture rows carry no `track_id`, so
    `_annotate_hardness` never even queries for one), which is exactly the point:
    nothing about this listener's profile is what decides the edges any more.
    """

    def test_the_mid_band_keeps_only_the_middle_candidate(self):
        conn = scripted(listens=MANY_LISTENS, candidates=SPECTRUM_CANDIDATES)
        feed = build_feed(conn, 'user', POLICIES['daily-mix-mid'], NOW)
        self.assertEqual([t['id'] for t in feed.tracks], ['mid1'])
        self.assertEqual(feed.hardness_band, (50.0, 75.0))
        self.assertEqual(feed.hardness_edges_source, 'default')

    def test_a_configured_setting_overrides_the_default_edges(self):
        conn = scripted(listens=MANY_LISTENS, candidates=SPECTRUM_CANDIDATES)
        feed = build_feed(
            conn, 'user', POLICIES['daily-mix-mid'], NOW, hardness_edges=(30.0, 60.0), hardness_edges_source='setting'
        )
        # 65 (MID_CANDIDATE's tempo hardness) is now >= the hard edge, so it
        # reclassifies out of 'mid' under the overridden edges.
        self.assertEqual(feed.hardness_band, (30.0, 60.0))
        self.assertEqual(feed.hardness_edges_source, 'setting')

    def test_the_soft_band_keeps_only_the_soft_candidate(self):
        conn = scripted(listens=MANY_LISTENS, candidates=SPECTRUM_CANDIDATES)
        feed = build_feed(conn, 'user', POLICIES['daily-mix-soft'], NOW)
        self.assertEqual([t['id'] for t in feed.tracks], ['soft1'])

    def test_the_hard_band_keeps_only_the_hard_candidate(self):
        conn = scripted(listens=MANY_LISTENS, candidates=SPECTRUM_CANDIDATES)
        feed = build_feed(conn, 'user', POLICIES['daily-mix-hard'], NOW)
        self.assertEqual([t['id'] for t in feed.tracks], ['hard1'])

    def test_daily_mix_is_the_classic_unrestricted_policy_not_a_band_alias(self):
        """Design correction after MR !798's first pipeline: 'daily-mix' is its

        own, unbanded policy again -- all three candidates come back regardless
        of their hardness, because 'daily-mix' never filters on it at all. The
        car and the phone must never lose a track to a missing hardness value on
        this slug.
        """
        conn = scripted(listens=MANY_LISTENS, candidates=SPECTRUM_CANDIDATES)
        feed = build_feed(conn, 'user', POLICIES['daily-mix'], NOW)
        self.assertEqual(sorted(t['id'] for t in feed.tracks), ['hard1', 'mid1', 'soft1'])
        self.assertIsNone(feed.hardness_band)
        self.assertIsNone(feed.filled_from_unknown)

    def test_unknown_hardness_never_enters_the_band_directly(self):
        """A candidate with no resolvable hardness is not bucketed into any

        genre share -- the band-matching step (`bucketed`) never sees it.
        """
        no_tempo = _candidate('no-tempo', None, 'Uptempo', bpm=None)
        conn = scripted(listens=MANY_LISTENS, candidates=[no_tempo])
        feed = build_feed(conn, 'user', POLICIES['daily-mix-mid'], NOW)
        self.assertEqual(feed.funnel['bucketed'], 0)

    def test_unknown_hardness_is_still_offered_as_a_last_resort_filler(self):
        """Design correction after MR !798's first pipeline: excluding an

        unknown-hardness track from the band is not the same as excluding it
        from the mix -- a thin library must still get a full mix rather than
        an honestly empty one.
        """
        no_tempo = _candidate('no-tempo', None, 'Uptempo', bpm=None)
        conn = scripted(listens=MANY_LISTENS, candidates=[no_tempo])
        feed = build_feed(conn, 'user', POLICIES['daily-mix-mid'], NOW)
        self.assertEqual(feed.state, 'ok')
        self.assertEqual([t['id'] for t in feed.tracks], ['no-tempo'])
        self.assertEqual(feed.tracks[0]['bucket'], '__unknown__')
        self.assertEqual(feed.tracks[0]['reason'], 'unknown_hardness')
        self.assertEqual(feed.filled_from_unknown, 1)

    def test_a_full_band_never_reaches_for_unknown_hardness_filler(self):
        plenty = [_candidate(f'mid{i}', None, 'Uptempo', bpm=165) for i in range(POLICIES['daily-mix-mid'].size)]
        unknowns = [_candidate(f'unk{i}', None, 'Uptempo', bpm=None) for i in range(5)]
        conn = scripted(listens=MANY_LISTENS, candidates=plenty + unknowns)
        feed = build_feed(conn, 'user', POLICIES['daily-mix-mid'], NOW)
        self.assertEqual(feed.filled_from_unknown, 0)
        self.assertTrue(all(track['reason'] != 'unknown_hardness' for track in feed.tracks))

    def test_a_thin_split_band_backfills_from_unknown_without_relaxing(self):
        """Bug report 131: a band with a recent/older split has no ladder -- a short
        half fills from the other, and only then does the unknown-hardness filler run."""
        thin_mid = [_candidate(f'mid{i}', None, 'Uptempo', bpm=165) for i in range(5)]
        unknowns = [_candidate(f'unk{i}', None, 'Uptempo', bpm=None) for i in range(10)]
        conn = scripted(listens=MANY_LISTENS, candidates=thin_mid + unknowns)
        feed = build_feed(conn, 'user', POLICIES['daily-mix-mid'], NOW)
        self.assertIsNone(feed.relaxed_to)
        self.assertEqual(feed.filled_from_unknown, 10)
        self.assertEqual(len(feed.tracks), 15)
        self.assertEqual(feed.pool_counts, {'recent': 5, 'older': 0})

    def test_a_thin_band_relaxes_then_backfills_from_unknown_to_reach_size(self):
        """Both correction pieces at once: the relaxation ladder runs out

        first (never enough 'mid' candidates at any window), and only then are
        the remaining places filled from unknown-hardness candidates.
        """
        thin_mid = [_candidate(f'mid{i}', None, 'Uptempo', bpm=165) for i in range(5)]
        unknowns = [_candidate(f'unk{i}', None, 'Uptempo', bpm=None) for i in range(10)]
        conn = scripted(listens=MANY_LISTENS, candidates=thin_mid + unknowns)
        feed = build_feed(conn, 'user', LADDER_MID, NOW)
        self.assertEqual(feed.relaxed_to, 'none')
        self.assertEqual(feed.filled_from_unknown, 10)
        self.assertEqual(len(feed.tracks), 15)

    def test_a_short_band_relaxes_the_window_all_the_way_and_says_so(self):
        """Only one candidate ever qualifies for 'mid' here -- nowhere near

        MIN_BAND_CANDIDATES -- so every relaxation step runs out and the last
        window tried is "no window at all", reported as the literal string
        'none' rather than a bare None (which already means something else:
        no relaxation happened at all).
        """
        conn = scripted(listens=MANY_LISTENS, candidates=SPECTRUM_CANDIDATES)
        feed = build_feed(conn, 'user', LADDER_MID, NOW)
        self.assertEqual(feed.relaxed_to, 'none')

    def test_enough_candidates_in_the_band_needs_no_relaxation(self):
        plenty = [_candidate(f'mid{i}', None, 'Uptempo', bpm=165) for i in range(15)]
        conn = scripted(listens=MANY_LISTENS, candidates=plenty)
        feed = build_feed(conn, 'user', LADDER_MID, NOW)
        self.assertIsNone(feed.relaxed_to)
        self.assertEqual(feed.funnel['candidates'], 15)

    def test_the_source_tally_reports_no_resolvable_listens_here(self):
        """Every listen in MANY_LISTENS carries a genre with no known hardness and

        no track id to look one up by -- 'none' is the honest tally, not a crash
        or a silently empty dict.
        """
        conn = scripted(listens=MANY_LISTENS, candidates=SPECTRUM_CANDIDATES)
        feed = build_feed(conn, 'user', POLICIES['daily-mix-mid'], NOW)
        self.assertEqual(feed.hardness_source_counts, {'none': len(MANY_LISTENS)})
        self.assertIsNone(feed.hardness_percentiles)


def _entity_listen(uid, artist, label, genres, days=1):
    return {**_listen(uid, artist, genres, days=days), 'labels': label}


# 30 distinct tracks, all by the same artist on the same label -- enough to clear
# both the blend ramp (scope='user') and MIN_TRACKS_PER_ENTITY, and few enough
# names that the profile's top 10 has exactly one entry apiece. Which name
# pick_daily_entity lands on is then not a matter of the hash at all (see
# PickDailyEntityTest.test_a_single_name_always_wins).
SINGLE_ENTITY_LISTENS = [_entity_listen(f'single-{i}', 'Angerfist', 'Neophyte Records', ['Uptempo']) for i in range(30)]


def _songs(name, *counts):
    """One rotation_counts_query row: `counts` per window, 90 / 365 / no window."""
    return {'name': name, **{f'songs_{index}': count for index, count in enumerate(counts)}}


# Enough at the policy's own 90-day window, so nothing is relaxed.
ANGERFIST_PLAYABLE = [_songs('Angerfist', 15, 15, 15)]
NEOPHYTE_PLAYABLE = [_songs('Neophyte Records', 15, 15, 15)]


class RotatingMixBuildTest(unittest.TestCase):
    def test_the_artist_mix_is_titled_and_filtered_by_the_only_top_artist(self):
        conn = scripted(listens=SINGLE_ENTITY_LISTENS, candidates=MIXED_CANDIDATES, rotation_counts=ANGERFIST_PLAYABLE)
        feed = build_feed(conn, 'user', POLICIES['daily-mix-artist'], NOW)
        self.assertEqual(feed.title, 'angerfist')
        cursor = conn.cursor.return_value
        _, params = cursor.statements_matching(_CANDIDATES_FRAGMENT)[0]
        self.assertEqual(params[-1], 'angerfist')

    def test_the_label_mix_is_titled_and_filtered_by_the_only_top_label(self):
        conn = scripted(listens=SINGLE_ENTITY_LISTENS, candidates=MIXED_CANDIDATES, rotation_counts=NEOPHYTE_PLAYABLE)
        feed = build_feed(conn, 'user', POLICIES['daily-mix-label'], NOW)
        self.assertEqual(feed.title, 'neophyte records')
        cursor = conn.cursor.return_value
        _, params = cursor.statements_matching(_CANDIDATES_FRAGMENT)[0]
        self.assertEqual(params[-1], 'neophyte records')

    def test_a_profile_with_no_artist_affinities_has_nothing_to_rotate_through(self):
        # MANY_LISTENS carries artists, but every one of them supports only a
        # single distinct track, which build_profile drops (MIN_TRACKS_PER_ENTITY).
        conn = scripted(listens=MANY_LISTENS, candidates=MIXED_CANDIDATES)
        feed = build_feed(conn, 'user', POLICIES['daily-mix-artist'], NOW)
        self.assertEqual(feed.state, 'not_enough_data')
        # No name to count for, so the count query is never sent either.
        self.assertEqual(conn.cursor.return_value.statements_matching(_ROTATION_COUNTS_FRAGMENT), [])


# Two artists in the top ten: Angerfist with 20 distinct tracks, Unproven with 10.
# Which of the two the day's hash lands on is deliberately not assumed by the tests
# below -- each makes only one of them playable, so the answer is the same either way.
TWO_ARTIST_LISTENS = [_entity_listen(f'ang-{i}', 'Angerfist', 'Neophyte Records', ['Uptempo']) for i in range(20)] + [
    _entity_listen(f'unp-{i}', 'Unproven', 'Masters Of Hardcore', ['Uptempo']) for i in range(10)
]
ANGERFIST_FLOOD = [_candidate(f'ang{i}', 'Angerfist', 'Uptempo') for i in range(20)]


class RotatingMixPlayableArtistTest(unittest.TestCase):
    """Bug report 110: a rotating mix only ever draws a name it can fill."""

    def _build(self, counts, slug='daily-mix-artist', candidates=ANGERFIST_FLOOD):
        conn = scripted(listens=TWO_ARTIST_LISTENS, candidates=candidates, rotation_counts=counts)
        return conn, build_feed(conn, 'user', POLICIES[slug], NOW)

    def _candidate_params(self, conn):
        statements = conn.cursor.return_value.statements_matching(_CANDIDATES_FRAGMENT)
        return [params for sql, params in statements if _ROTATION_COUNTS_FRAGMENT not in sql]

    def test_an_artist_with_no_playable_tracks_is_skipped(self):
        # Unproven has no row at all: not one song with a file survives the pool.
        conn, feed = self._build([_songs('Angerfist', 20, 20, 20)])
        self.assertEqual(feed.title, 'angerfist')
        self.assertEqual(feed.state, 'ok')
        self.assertEqual(self._candidate_params(conn)[0][-1], 'angerfist')

    def test_the_other_way_round_the_other_artist_is_taken(self):
        conn, feed = self._build([_songs('Unproven', 20, 20, 20)])
        self.assertEqual(feed.title, 'unproven')
        self.assertEqual(self._candidate_params(conn)[0][-1], 'unproven')

    def test_an_artist_below_the_minimum_at_every_window_is_skipped(self):
        below = build.MIN_ROTATION_CANDIDATES - 1
        _conn, feed = self._build([_songs('Unproven', below, below, below), _songs('Angerfist', 20, 20, 20)])
        self.assertEqual(feed.title, 'angerfist')

    def test_the_whole_top_ten_is_counted_in_one_query(self):
        conn, _ = self._build([_songs('Angerfist', 20, 20, 20)])
        counts = conn.cursor.return_value.statements_matching(_ROTATION_COUNTS_FRAGMENT)
        self.assertEqual(len(counts), 1)
        self.assertEqual(sorted(counts[0][1][-2:]), ['angerfist', 'unproven'])

    def test_the_window_is_widened_to_the_narrowest_one_that_fills_the_mix(self):
        conn, feed = self._build([_songs('Angerfist', 2, 20, 40)])
        self.assertEqual(feed.relaxed_to, 365)
        params = self._candidate_params(conn)[0]
        self.assertIn((NOW.date() - timedelta(days=365)).isoformat(), params)

    def test_a_name_that_only_fills_with_no_window_is_built_without_one(self):
        conn, feed = self._build([_songs('Angerfist', 0, 4, 119)])
        self.assertEqual(feed.relaxed_to, 'none')
        sql = [
            s for s, _ in conn.cursor.return_value.statements_matching(_CANDIDATES_FRAGMENT) if 'AS songs_0' not in s
        ]
        self.assertNotIn('LENGTH(', sql[0])

    def test_no_relaxation_is_reported_when_the_policy_s_own_window_suffices(self):
        _, feed = self._build([_songs('Angerfist', 20, 20, 20)])
        self.assertIsNone(feed.relaxed_to)

    def test_when_no_artist_qualifies_the_mix_is_empty_not_near_empty(self):
        conn, feed = self._build([_songs('Angerfist', 3, 5, 9), _songs('Unproven', 0, 2, 2)])
        self.assertEqual(feed.state, 'no_matches')
        self.assertEqual(feed.tracks, [])
        self.assertEqual(feed.title, 'Artiestmix')
        self.assertIsNone(feed.subtitle)
        # Nothing was drawn, so no candidate query ran for anyone.
        self.assertEqual(self._candidate_params(conn), [])

    def test_the_listing_describes_the_same_artist_the_build_uses(self):
        conn = scripted(listens=TWO_ARTIST_LISTENS, rotation_counts=[_songs('Unproven', 20, 20, 20)])
        info = describe_feed(conn, 'user', POLICIES['daily-mix-artist'], NOW)
        self.assertEqual(info['title'], 'unproven')

    def test_the_artist_mix_is_not_cut_to_three_tracks_by_the_per_artist_cap(self):
        _, feed = self._build([_songs('Angerfist', 20, 20, 20)])
        self.assertEqual(len(feed.tracks), 20)

    def test_the_label_mix_still_caps_each_artist(self):
        conn = scripted(
            listens=TWO_ARTIST_LISTENS,
            candidates=ANGERFIST_FLOOD,
            rotation_counts=[_songs('Neophyte Records', 20, 20, 20)],
        )
        feed = build_feed(conn, 'user', POLICIES['daily-mix-label'], NOW)
        self.assertEqual(feed.title, 'neophyte records')
        self.assertEqual(len(feed.tracks), POLICIES['daily-mix-label'].max_per_artist)


def _version(id_, work_id, canonical_id, **overrides):
    """A candidate that is one version of a work, as candidates_query returns it."""
    file_path = overrides.pop('file_path', None)
    row = _candidate(id_, overrides.pop('artist', 'Deadly Guns'), overrides.pop('genre', 'Uptempo'), **overrides)
    row.update(work_id=work_id, canonical_track_id=canonical_id)
    if file_path:
        row['file_path'] = file_path
    return row


class CollapseToSongsTest(unittest.TestCase):
    """Bug report 096: one entry per song in every feed, and it is the canonical."""

    def test_two_versions_of_one_song_take_one_place(self):
        # KOPPEN ROLLEN on Teun's radar, 2026-09-26: a YouTube and a SoundCloud rip of one work.
        youtube = _version(9655173, 394638, 9655173, label='Neophyte Records')
        soundcloud = _version(9652563, 394638, 9655173, is_soundcloud=True)
        conn = scripted(listens=MANY_LISTENS, candidates=[soundcloud, youtube])
        feed = build_feed(conn, 'user', POLICIES['release-radar'], NOW)
        self.assertEqual([track['id'] for track in feed.tracks], [9655173])
        self.assertEqual(feed.funnel['candidates'], 1)

    def test_the_canonical_is_emitted_even_when_only_a_rip_qualified(self):
        """ERABREAK - Elevate: the rip was in the window, the official version was not a
        candidate; the feed must still play the official version."""
        rip = _version(20, 5, 10, is_soundcloud=True, file_path='/music/rip.mp3')
        official = _version(10, 5, 10, label='Scantraxx', release_date='2025-01-01', file_path='/music/official.flac')
        conn = scripted(listens=MANY_LISTENS, candidates=[rip], canonicals=[official])
        feed = build_feed(conn, 'user', POLICIES['release-radar'], NOW)
        self.assertEqual(len(feed.tracks), 1)
        track = feed.tracks[0]
        self.assertEqual(track['file_path'], '/music/official.flac')
        self.assertTrue(track['has_label'])
        # The date is the qualifying version's, not the canonical's own older tag.
        self.assertEqual(track['release_date'], '2026-09-01')
        _, params = conn.cursor.return_value.statements_matching(_CANONICAL_ROWS_FRAGMENT)[0]
        self.assertEqual(params[-1], 10)

    def test_the_song_gets_the_newest_date_of_its_versions(self):
        older = _version(1, 5, 1, release_date='2026-08-01')
        newer = _version(2, 5, 1, release_date='2026-09-03')
        collapsed = build._collapse_to_songs(scripted(), 'user', [older, newer])
        self.assertEqual(len(collapsed), 1)
        self.assertEqual(collapsed[0]['id'], 1)
        self.assertEqual(collapsed[0]['release_date'], '2026-09-03')

    def test_a_canonical_without_a_file_leaves_the_qualifying_version(self):
        rip_b = _version(31, 5, 99)
        rip_a = _version(30, 5, 99)
        collapsed = build._collapse_to_songs(scripted(canonicals=[]), 'user', [rip_b, rip_a])
        self.assertEqual([row['id'] for row in collapsed], [30])

    def test_ungrouped_tracks_pass_through_untouched(self):
        loose = [_candidate(1, 'A', 'Uptempo'), _candidate(2, 'A', 'Uptempo')]
        conn = scripted()
        collapsed = build._collapse_to_songs(conn, 'user', loose)
        self.assertEqual([row['id'] for row in collapsed], [1, 2])
        # Nothing to look up: no second query.
        self.assertEqual(conn.cursor.return_value.statements_matching(_CANONICAL_ROWS_FRAGMENT), [])

    def test_heard_is_the_song_s_so_a_rip_of_a_heard_song_ranks_as_heard(self):
        """The query answers `heard` per song, so both versions carry True; the collapsed
        entry must keep it, and rank below an equal unheard song."""
        heard_rip = _version(40, 7, 41, heard=True, release_date='2026-09-04')
        heard_official = _version(41, 7, 41, heard=True, release_date='2026-09-04')
        unheard = _candidate(50, 'Other Artist', 'Uptempo', release_date='2026-09-02')
        conn = scripted(listens=MANY_LISTENS, candidates=[heard_rip, heard_official, unheard])
        feed = build_feed(conn, 'user', POLICIES['release-radar'], NOW)
        self.assertEqual([track['id'] for track in feed.tracks], [50, 41])
        self.assertTrue(feed.tracks[1]['heard'])


def _recent(count, prefix='new', **overrides):
    """`count` candidates released inside the recent window, one artist each."""
    return [_candidate(f'{prefix}{i}', f'{prefix} Artist {i}', 'Uptempo', **overrides) for i in range(count)]


def _older(count, prefix='old', **overrides):
    """`count` candidates as older_candidates_query returns them: released years ago."""
    overrides.setdefault('release_date', '2019-03-01')
    return [_candidate(f'{prefix}{i}', f'{prefix} Artist {i}', 'Uptempo', **overrides) for i in range(count)]


CLASSIC_20 = build.replace(POLICIES['daily-mix'], size=20)


class RecentOlderSplitTest(unittest.TestCase):
    """Bug report 131: a daily mix is half last year, half older, and a short half fills
    from the other so the size holds."""

    def _build(self, recent, older, policy=CLASSIC_20, **kwargs):
        conn = scripted(listens=MANY_LISTENS, candidates=recent, older=older, **kwargs)
        return conn, build_feed(conn, 'user', policy, NOW)

    def test_the_default_share_is_half_and_half(self):
        _, feed = self._build(_recent(40), _older(40))
        self.assertEqual(len(feed.tracks), 20)
        self.assertEqual(feed.pool_counts, {'recent': 10, 'older': 10})
        years = Counter(track['release_date'][:4] for track in feed.tracks)
        self.assertEqual(years, Counter({'2026': 10, '2019': 10}))

    def test_the_share_is_a_policy_value(self):
        _, feed = self._build(_recent(40), _older(40), policy=build.replace(CLASSIC_20, recent_share=0.3))
        self.assertEqual(feed.pool_counts, {'recent': 6, 'older': 14})

    def test_a_short_older_half_is_filled_from_the_recent_one(self):
        _, feed = self._build(_recent(40), _older(3))
        self.assertEqual(len(feed.tracks), 20)
        self.assertEqual(feed.pool_counts, {'recent': 17, 'older': 3})

    def test_a_short_recent_half_is_filled_from_the_older_one(self):
        _, feed = self._build(_recent(4), _older(40))
        self.assertEqual(len(feed.tracks), 20)
        self.assertEqual(feed.pool_counts, {'recent': 4, 'older': 16})

    def test_both_halves_short_is_everything_there_is(self):
        _, feed = self._build(_recent(4), _older(5))
        self.assertEqual(feed.pool_counts, {'recent': 4, 'older': 5})

    def test_a_song_in_both_halves_is_only_recent(self):
        recent = [_version('r1', 7, 'r1', release_date='2026-09-01')]
        older = [_version('o1', 7, 'r1', release_date='2012-01-01'), *_older(3)]
        _, feed = self._build(recent, older)
        self.assertEqual(sorted(t['id'] for t in feed.tracks), ['old0', 'old1', 'old2', 'r1'])

    def test_the_older_query_is_matched_on_the_profile_and_seeded_per_day(self):
        conn, _ = self._build(_recent(4), _older(4))
        ((_, params),) = conn.cursor.return_value.statements_matching(_OLDER_SAMPLE_FRAGMENT)
        self.assertIn('uptempo', params)
        self.assertEqual(params[-2:], ['user|2026-09-05|older', CLASSIC_20.older_pool_limit])

    def test_only_heard_older_songs_are_looked_up_for_rediscovery(self):
        older = [
            *_older(1, prefix='fresh'),
            *_older(1, prefix='recentlyplayed', heard=True),
            *_older(1, prefix='longago', heard=True),
        ]
        last = [
            {'work_id': None, 'track_id': 'recentlyplayed0', 'last_listened_at': NOW - timedelta(days=2)},
            {'work_id': None, 'track_id': 'longago0', 'last_listened_at': NOW - timedelta(days=400)},
        ]
        conn = scripted(listens=MANY_LISTENS, older=older, last_listened=last)
        candidates = build._load_split_candidates(
            conn, 'user', CLASSIC_20, NOW, {'entity_filter': None, 'band_edges': None}, build.TasteProfile()
        )
        factors = {c['id']: c['rediscovery'] for c in candidates}
        self.assertEqual(factors['fresh0'], 1.0)
        self.assertEqual(factors['longago0'], 1.0)
        self.assertLess(factors['recentlyplayed0'], 0.25)
        ((_, params),) = conn.cursor.return_value.statements_matching(_LAST_LISTENED_FRAGMENT)
        self.assertEqual(params, ['user', 'longago0', 'recentlyplayed0'])

    def test_a_recently_played_older_song_is_drawn_later(self):
        order_key = build._order_key_fn(CLASSIC_20, build.TasteProfile(), 'user', NOW.date())
        song = _older(1)[0]
        self.assertGreater(order_key({**song, 'rediscovery': 0.2}), order_key({**song, 'rediscovery': 1.0}))

    def test_a_band_mix_filters_both_halves_on_its_band(self):
        recent = [_candidate(f'rmid{i}', f'RM {i}', 'Uptempo', bpm=165) for i in range(3)] + [SOFT_CANDIDATE]
        older = [_candidate(f'omid{i}', f'OM {i}', 'Uptempo', bpm=165, release_date='2015-05-05') for i in range(3)]
        older.append(_candidate('ohard', 'OH', 'Uptempo', bpm=205, release_date='2015-05-05'))
        _, feed = self._build(recent, older, policy=build.replace(POLICIES['daily-mix-mid'], size=6))
        self.assertEqual(sorted(t['id'] for t in feed.tracks), ['omid0', 'omid1', 'omid2', 'rmid0', 'rmid1', 'rmid2'])
        self.assertEqual(feed.pool_counts, {'recent': 3, 'older': 3})
        self.assertIsNone(feed.relaxed_to)

    def test_the_label_mix_restricts_its_older_half_to_the_label(self):
        conn = scripted(
            listens=SINGLE_ENTITY_LISTENS,
            candidates=MIXED_CANDIDATES,
            older=_older(5),
            rotation_counts=[_songs('Neophyte Records', 15)],
        )
        feed = build_feed(conn, 'user', POLICIES['daily-mix-label'], NOW)
        self.assertEqual(feed.title, 'neophyte records')
        ((sql, params),) = conn.cursor.return_value.statements_matching(_OLDER_SAMPLE_FRAGMENT)
        self.assertIn('el.name = %s', sql)
        self.assertIn('neophyte records', params)
        self.assertNotIn('a.name IN', sql)

    def test_release_radar_and_the_artist_mix_never_sample_older_songs(self):
        for slug, counts in (('release-radar', ()), ('daily-mix-artist', ANGERFIST_PLAYABLE)):
            with self.subTest(slug=slug):
                conn = scripted(
                    listens=SINGLE_ENTITY_LISTENS, candidates=MIXED_CANDIDATES, older=_older(5), rotation_counts=counts
                )
                feed = build_feed(conn, 'user', POLICIES[slug], NOW)
                self.assertEqual(conn.cursor.return_value.statements_matching(_OLDER_SAMPLE_FRAGMENT), [])
                self.assertIsNone(feed.pool_counts)


class ReserveTest(unittest.TestCase):
    """Issue #137: the continuation's tracks come out of the same build, for no extra query."""

    def _build(self, reserve_size=None, policy=CLASSIC_20):
        conn = scripted(listens=MANY_LISTENS, candidates=_recent(40), older=_older(40))
        return conn, build_feed(conn, 'user', policy, NOW, reserve_size=reserve_size)

    def test_the_reserve_is_the_longer_build_without_the_head(self):
        _, feed = self._build(reserve_size=60)
        _, longer = self._build(policy=build.resize(CLASSIC_20, 60))
        head = {build.song_key(track) for track in feed.tracks}
        self.assertEqual(len(feed.tracks), 20)
        self.assertEqual(
            [track['id'] for track in feed.reserve],
            [track['id'] for track in longer.tracks if build.song_key(track) not in head],
        )
        self.assertFalse(head & {build.song_key(track) for track in feed.reserve})

    def test_the_reserve_costs_no_query(self):
        plain_conn, plain = self._build()
        build.clear_sample_memo()  # both builds must run their own samples to be compared
        reserve_conn, _ = self._build(reserve_size=60)
        self.assertEqual(len(plain_conn.cursor.return_value.executed), len(reserve_conn.cursor.return_value.executed))
        self.assertIsNone(plain.reserve)

    def test_the_head_is_the_same_with_or_without_a_reserve(self):
        _, plain = self._build()
        _, with_reserve = self._build(reserve_size=60)
        self.assertEqual([t['id'] for t in plain.tracks], [t['id'] for t in with_reserve.tracks])


# Issue #138: the four hardness-family mixes share one pair of samples. A spread of bpm puts
# tracks in every band, so each of the four builds has something of its own to emit.
_SPREAD_BPMS = (150, 160, 170, 180, 190, 200, 210)
SHARED_RECENT = [
    _candidate(f'sr{i}', f'SR Artist {i}', 'Uptempo', bpm=_SPREAD_BPMS[i % len(_SPREAD_BPMS)]) for i in range(35)
]
SHARED_OLDER = [
    _candidate(f'so{i}', f'SO Artist {i}', 'Raw', bpm=_SPREAD_BPMS[i % len(_SPREAD_BPMS)], release_date='2016-04-04')
    for i in range(35)
]
HARDNESS_FAMILY = ('daily-mix', 'daily-mix-soft', 'daily-mix-mid', 'daily-mix-hard')


def _sample_statements(conn) -> int:
    cursor = conn.cursor.return_value
    return len(cursor.statements_matching(_RECENT_SAMPLE_FRAGMENT)) + len(
        cursor.statements_matching(_OLDER_SAMPLE_FRAGMENT)
    )


class SharedSampleTest(unittest.TestCase):
    """Issue #138: Klassiek, Zachter, Middenin and Harder ask the same two sample
    questions; the library is sampled once per listener and day, not four times."""

    def _conn(self, **kwargs):
        kwargs.setdefault('candidates', SHARED_RECENT)
        kwargs.setdefault('older', SHARED_OLDER)
        return scripted(listens=MANY_LISTENS, **kwargs)

    def _build(self, slug, now=NOW, conn=None):
        conn = conn or self._conn()
        return conn, build_feed(conn, 'user', build.replace(POLICIES[slug], size=20), now, reserve_size=60)

    def test_sharing_changes_nothing_in_any_of_the_four_builds(self):
        unshared = {}
        for slug in HARDNESS_FAMILY:
            build.clear_sample_memo()
            conn, feed = self._build(slug)
            self.assertEqual(_sample_statements(conn), 2, slug)
            unshared[slug] = dataclasses.asdict(feed)
        build.clear_sample_memo()
        shared, statements = {}, 0
        for slug in HARDNESS_FAMILY:
            conn, feed = self._build(slug)
            statements += _sample_statements(conn)
            shared[slug] = dataclasses.asdict(feed)
        self.assertEqual(statements, 2)
        for slug in HARDNESS_FAMILY:
            with self.subTest(slug=slug):
                self.assertTrue(shared[slug]['tracks'], 'every mix must emit something to compare')
                self.assertEqual(shared[slug], unshared[slug])

    def test_one_connection_for_the_whole_refresh_samples_once(self):
        conn = self._conn()
        for slug in HARDNESS_FAMILY:
            self._build(slug, conn=conn)
        cursor = conn.cursor.return_value
        self.assertEqual(len(cursor.statements_matching(_RECENT_SAMPLE_FRAGMENT)), 1)
        self.assertEqual(len(cursor.statements_matching(_OLDER_SAMPLE_FRAGMENT)), 1)

    def test_the_label_mix_keeps_its_own_samples(self):
        self._build('daily-mix', conn=scripted(listens=SINGLE_ENTITY_LISTENS, candidates=SHARED_RECENT))
        conn = scripted(
            listens=SINGLE_ENTITY_LISTENS,
            candidates=SHARED_RECENT,
            older=SHARED_OLDER,
            rotation_counts=[_songs('Neophyte Records', 15)],
        )
        feed = build_feed(conn, 'user', POLICIES['daily-mix-label'], NOW)
        self.assertEqual(feed.title, 'neophyte records')
        self.assertEqual(_sample_statements(conn), 2)

    def test_another_day_is_a_new_sample(self):
        self._build('daily-mix')
        conn, _ = self._build('daily-mix-soft', now=NOW + timedelta(days=1))
        self.assertEqual(_sample_statements(conn), 2)

    def test_another_listener_is_a_new_sample(self):
        self._build('daily-mix')
        conn = self._conn()
        build_feed(conn, 'someone-else', POLICIES['daily-mix-soft'], NOW)
        self.assertEqual(_sample_statements(conn), 2)

    def test_a_sample_expires_after_the_ttl(self):
        clock = [1000.0]
        original = build._memo_clock
        build._memo_clock = lambda: clock[0]
        try:
            self._build('daily-mix')
            clock[0] += build.SAMPLE_MEMO_TTL_SECONDS - 1
            conn, _ = self._build('daily-mix-soft')
            self.assertEqual(_sample_statements(conn), 0)
            clock[0] += 2
            conn, _ = self._build('daily-mix-mid')
            self.assertEqual(_sample_statements(conn), 2)
        finally:
            build._memo_clock = original

    def test_the_memo_is_bounded_and_holds_ids_only(self):
        conn = self._conn()
        for i in range(build.SAMPLE_MEMO_MAX_ENTRIES + 5):
            build._sample_ids(conn, 'SELECT 1 AS recent_id', [f'seed-{i}'], 'recent')
        self.assertEqual(len(build._sample_memo), build.SAMPLE_MEMO_MAX_ENTRIES)
        self.assertNotIn(('SELECT 1 AS recent_id', ('seed-0',)), build._sample_memo)
        _, ids = next(iter(build._sample_memo.values()))
        self.assertEqual(ids, tuple(row['id'] for row in SHARED_RECENT))

    def test_a_reused_sample_is_a_copy(self):
        conn = self._conn()
        first = build._sample_ids(conn, 'SELECT t.id AS recent_id', ['x'], 'recent')
        first.clear()
        self.assertEqual(
            build._sample_ids(conn, 'SELECT t.id AS recent_id', ['x'], 'recent'),
            [row['id'] for row in SHARED_RECENT],
        )
