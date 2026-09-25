"""Coverage for /api/curation: the artist, label and genre edit pages.

Two things these tests exist to pin down, beyond the ordinary CRUD:

* every write refreshes the preloaded lookup helpers, because `Cache.databaseHelpers`
  is built once at import and a rule that is not reloaded is invisible to the running
  tagger until the process restarts;
* the difference between 400 and 403. A target that cannot be used (a genre curation
  has not accepted) is a bad request against a legitimate page. A subject that may not
  be edited at all (a rejected genre) is a page that should not exist.
"""

import sys
import unittest
from unittest.mock import MagicMock, patch

for _mod_name in ('dbutils', 'dbutils.pooled_db', 'pymysql', 'mutagen', 'mutagen.easyid3', 'markdown'):
    sys.modules.setdefault(_mod_name, MagicMock())

import services.music_manager.routers.users as users_router
from services.music_manager.api_key import resolve_system_api_key

users_router.run_lms_db_sync = lambda: None

from fastapi.testclient import TestClient

from services.common.Helpers import Cache
from services.music_manager.main import app
from services.music_manager.routers import curation as curation_router
from services.music_manager.tests.scripted_cursor import (
    ScriptedCursor,
    assert_atomic,
    assert_rolled_back,
    transaction_log,
)

API_KEY = resolve_system_api_key()

ARTIST_ROW = {'id': 7, 'name': 'Angerfist', 'sort_name': 'Angerfist', 'mbid': None}
LABEL_ROW = {'id': 3, 'name': 'Masters of Hardcore', 'mbid': None, 'parent_label_id': None}
WHITE_GENRE = {'id': 12, 'name': 'Hardcore', 'state': 'white'}
BLACK_GENRE = {'id': 99, 'name': 'Arts', 'state': 'black'}


class CurationTestCase(unittest.TestCase):
    """Wires a scripted cursor under the router and hands out an admin client."""

    rules = ()

    def setUp(self):
        self.client = TestClient(app)
        self.headers = {'x-api-key': API_KEY}
        self.cursor = ScriptedCursor(self.rules)
        self.conn = MagicMock()
        self.conn.cursor.return_value = self.cursor
        patcher = patch.object(curation_router, 'get_db_connection', return_value=self.conn)
        patcher.start()
        self.addCleanup(patcher.stop)
        Cache.reload.reset_mock()

    def reloaded_helpers(self):
        return [call.args[0] if call.args else None for call in Cache.reload.call_args_list]

    def statements(self, fragment):
        return self.cursor.statements_matching(fragment)


class ArtistReadTest(CurationTestCase):
    rules = (
        ('FROM library_artists', None, ARTIST_ROW),
        (
            'FROM artist_external_ids',
            None,
            [{'source': 'spotify', 'external_id': 'abc', 'external_url': None, 'verified': 0}],
        ),
        ('FROM library_artist_aliases', None, [{'alias': 'DJ Angerfist'}]),
        ('FROM rules_artist_genres', None, [{'genre_id': 12, 'name': 'Hardcore', 'created_by': 'user'}]),
        ('COUNT(DISTINCT', None, {'affected': 143}),
    )

    def test_returns_identity_rules_and_track_count_in_one_call(self):
        response = self.client.get('/api/curation/artists/Angerfist', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['name'], 'Angerfist')
        self.assertEqual(body['aliases'], ['DJ Angerfist'])
        self.assertEqual(body['genre_rules'], [{'genre_id': 12, 'name': 'Hardcore', 'created_by': 'user'}])
        self.assertEqual(body['external_ids'][0]['source'], 'spotify')
        self.assertEqual(body['track_count'], 143)

    def test_reading_does_not_reload_the_tagger_caches(self):
        self.client.get('/api/curation/artists/Angerfist', headers=self.headers)
        self.assertEqual(self.reloaded_helpers(), [])


class LabelListTest(CurationTestCase):
    rules = (
        ('SELECT COUNT(*) AS total FROM library_labels', None, {'total': 1}),
        (
            'FROM library_labels l',
            None,
            [
                {
                    'id': 3,
                    'name': 'Masters of Hardcore',
                    'mbid': None,
                    'parent_name': None,
                    'track_count': 812,
                    'catid_count': 2,
                    'genre_count': 1,
                }
            ],
        ),
    )

    def test_lists_labels_with_what_the_tagger_knows_about_them(self):
        response = self.client.get('/api/curation/labels?q=hardcore', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['total'], 1)
        self.assertEqual(body['rows'][0]['name'], 'Masters of Hardcore')
        self.assertEqual(body['rows'][0]['catid_count'], 2)
        _sql, params = self.statements('FROM library_labels l')[-1]
        self.assertEqual(params[0], '%hardcore%')

    def test_the_page_size_is_capped(self):
        self.client.get('/api/curation/labels?limit=99999', headers=self.headers)
        _sql, params = self.statements('LIMIT %s OFFSET %s')[-1]
        self.assertEqual(params[-2], curation_router.LABEL_PAGE_MAX)


class UnknownArtistTest(CurationTestCase):
    rules = (('COUNT(DISTINCT', None, {'affected': 0}),)

    def test_a_name_the_library_has_never_seen_is_not_a_404(self):
        """A rule may legitimately be written before the first matching file arrives."""
        response = self.client.get('/api/curation/artists/Nobody', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['name'], 'Nobody')
        self.assertIsNone(body['artist_id'])
        self.assertIsNone(body['mbid'])
        self.assertEqual(body['aliases'], [])
        self.assertEqual(body['track_count'], 0)


class ArtistGenreRuleTest(CurationTestCase):
    rules = (
        ('FROM rules_genres WHERE id', None, WHITE_GENRE),
        ('COUNT(DISTINCT', None, {'affected': 143}),
    )

    def test_adding_a_rule_writes_it_and_reports_what_it_touches(self):
        response = self.client.post(
            '/api/curation/artists/Angerfist/genres', json={'genre_id': 12}, headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['affected_tracks'], 143)
        inserts = self.statements('INSERT INTO rules_artist_genres')
        self.assertEqual(len(inserts), 1)
        self.assertEqual(inserts[0][1][:2], ('Angerfist', 12))

    def test_adding_a_rule_records_who_wrote_it(self):
        self.client.post('/api/curation/artists/Angerfist/genres', json={'genre_id': 12}, headers=self.headers)
        params = self.statements('INSERT INTO rules_artist_genres')[0][1]
        self.assertEqual(params[2], 'system')

    def test_adding_a_rule_refreshes_the_artist_genre_helper(self):
        self.client.post('/api/curation/artists/Angerfist/genres', json={'genre_id': 12}, headers=self.headers)
        self.assertEqual(self.reloaded_helpers(), ['artistGenreHelper'])

    def test_removing_a_rule_refreshes_the_artist_genre_helper(self):
        response = self.client.delete('/api/curation/artists/Angerfist/genres/12', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.reloaded_helpers(), ['artistGenreHelper'])
        deletes = self.statements('DELETE FROM rules_artist_genres')
        self.assertEqual(deletes[0][1], ('Angerfist', 12))

    def test_adding_a_rule_marks_its_files_for_a_retag(self):
        """Refreshing the helper is not enough: without this the tagger has no reason to
        walk back to those files, and the rule sits unapplied behind the whole queue."""
        with patch('services.music_manager.routers.curation.invalidate_quietly', return_value=143) as invalidate:
            response = self.client.post(
                '/api/curation/artists/Angerfist/genres', json={'genre_id': 12}, headers=self.headers
            )
        invalidate.assert_called_once_with('Angerfist', 'artist_genre_rule')
        self.assertEqual(response.json()['marked_for_retag'], 143)

    def test_removing_a_rule_marks_its_files_for_a_retag(self):
        with patch('services.music_manager.routers.curation.invalidate_quietly', return_value=7) as invalidate:
            response = self.client.delete('/api/curation/artists/Angerfist/genres/12', headers=self.headers)
        invalidate.assert_called_once_with('Angerfist', 'artist_genre_rule')
        self.assertEqual(response.json()['marked_for_retag'], 7)

    def test_a_rule_still_saves_when_marking_the_files_fails(self):
        """The rule is already committed by then; refusing to answer would lose it."""
        with patch(
            'services.common.Helpers.RescanInvalidator.rescan_invalidator.invalidate_by_term',
            side_effect=RuntimeError('database gone'),
        ):
            response = self.client.post(
                '/api/curation/artists/Angerfist/genres', json={'genre_id': 12}, headers=self.headers
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['marked_for_retag'], 0)


class RejectedGenreTargetTest(CurationTestCase):
    rules = (('FROM rules_genres WHERE id', None, BLACK_GENRE),)

    def test_a_rule_cannot_point_at_a_genre_curation_rejected(self):
        response = self.client.post(
            '/api/curation/artists/Angerfist/genres', json={'genre_id': 99}, headers=self.headers
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.statements('INSERT INTO rules_artist_genres'), [])
        self.assertEqual(self.reloaded_helpers(), [])


class UnknownGenreTargetTest(CurationTestCase):
    rules = ()

    def test_a_rule_cannot_point_at_a_genre_that_does_not_exist(self):
        response = self.client.post(
            '/api/curation/artists/Angerfist/genres', json={'genre_id': 4242}, headers=self.headers
        )
        self.assertEqual(response.status_code, 400)


class ArtistMbidTest(CurationTestCase):
    rules = (('FROM library_artists', None, ARTIST_ROW),)

    def test_a_valid_mbid_is_stored_on_the_artist(self):
        mbid = '5b11f4ce-a62d-471e-81fc-a69a8278c7da'
        response = self.client.put('/api/curation/artists/Angerfist/mbid', json={'mbid': mbid}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        updates = self.statements('UPDATE library_artists SET mbid')
        self.assertEqual(updates[0][1], (mbid, 7))

    def test_setting_an_mbid_also_records_it_as_a_verified_external_id(self):
        """The two places an MBID can live must not be able to disagree."""
        mbid = '5b11f4ce-a62d-471e-81fc-a69a8278c7da'
        self.client.put('/api/curation/artists/Angerfist/mbid', json={'mbid': mbid}, headers=self.headers)
        inserts = self.statements('INSERT INTO artist_external_ids')
        self.assertEqual(len(inserts), 1)
        self.assertIn('musicbrainz', inserts[0][1])

    def test_a_malformed_mbid_is_rejected(self):
        response = self.client.put(
            '/api/curation/artists/Angerfist/mbid', json={'mbid': 'not-a-uuid'}, headers=self.headers
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.statements('UPDATE library_artists SET mbid'), [])

    def test_an_mbid_can_be_cleared(self):
        response = self.client.put('/api/curation/artists/Angerfist/mbid', json={'mbid': None}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.statements('UPDATE library_artists SET mbid')[0][1], (None, 7))

    def test_an_artist_the_library_does_not_know_cannot_be_given_an_mbid(self):
        self.cursor.rules = []
        response = self.client.put(
            '/api/curation/artists/Nobody/mbid',
            json={'mbid': '5b11f4ce-a62d-471e-81fc-a69a8278c7da'},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 404)


class ArtistAliasTest(CurationTestCase):
    rules = (('FROM library_artists', None, ARTIST_ROW),)

    def test_an_alias_is_added_for_the_artist(self):
        response = self.client.post(
            '/api/curation/artists/Angerfist/aliases', json={'alias': 'DJ Angerfist'}, headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.statements('INSERT INTO library_artist_aliases')[0][1], (7, 'DJ Angerfist'))

    def test_an_alias_identical_to_the_artist_name_is_rejected(self):
        response = self.client.post(
            '/api/curation/artists/Angerfist/aliases', json={'alias': ' angerfist '}, headers=self.headers
        )
        self.assertEqual(response.status_code, 400)

    def test_an_empty_alias_is_rejected(self):
        response = self.client.post(
            '/api/curation/artists/Angerfist/aliases', json={'alias': '   '}, headers=self.headers
        )
        self.assertEqual(response.status_code, 400)

    def test_an_alias_can_be_removed(self):
        response = self.client.delete('/api/curation/artists/Angerfist/aliases/DJ%20Angerfist', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.statements('DELETE FROM library_artist_aliases')[0][1], (7, 'DJ Angerfist'))


class LabelReadTest(CurationTestCase):
    rules = (
        ('FROM library_labels', None, LABEL_ROW),
        ('FROM label_external_ids', None, []),
        ('FROM rules_label_genres', None, [{'genre_id': 12, 'name': 'Hardcore', 'created_by': None}]),
        ('FROM rules_catid_label', None, [{'catid': 'MOH'}]),
        ('COUNT(DISTINCT', None, {'affected': 88}),
    )

    def test_returns_rules_catids_and_track_count(self):
        response = self.client.get('/api/curation/labels/Masters%20of%20Hardcore', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['name'], 'Masters of Hardcore')
        self.assertEqual(body['catids'], ['MOH'])
        self.assertEqual(body['genre_rules'][0]['name'], 'Hardcore')
        self.assertEqual(body['track_count'], 88)


class LabelCatalogTest(CurationTestCase):
    """The two queries behind the catalogue, merged by path.

    The label link is what the scanner wrote and lags the disk (half of the EPs tree
    has no link after a skipped rescan), so the label folder is also read by path.
    The join still contributes files whose folder is named differently -- and files
    outside the EPs tree, which the builder skips.
    """

    LINKED = [
        {'file_path': '/mnt/music/EPs/Masters of Hardcore/MOH001 First/01.mp3'},
        {'file_path': '/mnt/music/EPs/Masters of Hardcore/MOH001 First/02.mp3'},
        {'file_path': '/mnt/music/Soundcloud/Masters of Hardcore/some-set.mp3'},
    ]
    BY_PATH = [
        {'file_path': '/mnt/music/EPs/Masters of Hardcore/MOH001 First/01.mp3'},
        {'file_path': '/mnt/music/EPs/Masters of Hardcore/MOH003 Third/01.mp3'},
        {'file_path': '/mnt/music/EPs/Masters of Hardcore/MOHFREE Giveaway/01.mp3'},
    ]
    rules = (
        ('FROM library_labels', None, LABEL_ROW),
        ('FROM library_track_labels tl JOIN library_media_files mf', None, LINKED),
        ('FROM library_media_files mf WHERE mf.file_path LIKE', None, BY_PATH),
    )

    def setUp(self):
        super().setUp()
        patcher = patch.object(curation_router, 'Settings')
        settings = patcher.start()
        self.addCleanup(patcher.stop)
        settings.return_value.eps_folder_path = '/mnt/music/EPs'
        settings.return_value.delimiter = '/'

    def _catalog(self):
        return self.client.get('/api/curation/labels/Masters%20of%20Hardcore/catalog', headers=self.headers)

    def test_a_file_with_no_label_link_yet_is_still_counted_from_its_path(self):
        response = self._catalog()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['name'], 'Masters of Hardcore')
        moh = body['series'][0]
        # MOH003 only exists in the path query; MOH001 is in both and counts once.
        self.assertEqual((moh['prefix'], moh['min'], moh['max'], moh['present'], moh['absent']), ('MOH', 1, 3, 2, [2]))
        self.assertEqual(moh['releases'], 2)
        self.assertEqual(body['other'], [{'catid': 'MOHFREE', 'release_folder': 'MOHFREE Giveaway'}])

    def test_the_two_queries_are_merged_by_path_and_files_outside_the_root_are_reported(self):
        body = self._catalog().json()
        # 2 + 3 rows, one shared path: five distinct files, one of them under Soundcloud/.
        self.assertEqual((body['files_considered'], body['files_outside_root']), (5, 1))

    def test_the_path_query_is_anchored_on_the_label_folder_with_wildcards_escaped(self):
        self._catalog()
        _sql, params = self.statements('FROM library_media_files mf WHERE mf.file_path LIKE')[-1]
        self.assertEqual(params, ('/mnt/music/EPs/Masters of Hardcore/%',))
        _sql, params = self.statements('FROM library_track_labels tl')[-1]
        self.assertEqual(params, (3,))

    def test_reading_the_catalogue_does_not_reload_the_tagger_caches(self):
        self._catalog()
        self.assertEqual(self.reloaded_helpers(), [])


class LabelCatalogLikeEscapingTest(unittest.TestCase):
    def test_underscores_and_percents_in_a_label_name_do_not_widen_the_match(self):
        # `__Free&None` is a real label folder; a bare `_` in LIKE would also match
        # `/mnt/music/EPs/xxFree&None/`.
        self.assertEqual(
            curation_router._like_prefix('/mnt/music/EPs/__Free&None/'), '/mnt/music/EPs/\\_\\_Free&None/%'
        )
        self.assertEqual(curation_router._like_prefix('/x/50% off/'), '/x/50\\% off/%')


class LabelCatalogWithoutRootTest(CurationTestCase):
    rules = (
        ('FROM library_labels', None, LABEL_ROW),
        (
            'FROM library_track_labels tl JOIN library_media_files mf',
            None,
            [{'file_path': '/somewhere/Masters of Hardcore/MOH001 First/01.mp3'}],
        ),
    )

    def test_without_an_eps_root_only_the_label_link_is_read(self):
        with patch.object(curation_router, 'Settings') as settings:
            settings.return_value.eps_folder_path = ''
            settings.return_value.delimiter = '/'
            response = self.client.get('/api/curation/labels/Masters%20of%20Hardcore/catalog', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.statements('WHERE mf.file_path LIKE'), [])
        self.assertEqual(response.json()['series'][0]['prefix'], 'MOH')


class LabelCatalogUnknownLabelTest(CurationTestCase):
    rules = ()

    def test_a_label_the_library_does_not_hold_is_a_404(self):
        # Unlike GET /labels/{name}, which answers for a label that only exists in the
        # rule tables: a catalogue can only be read off files, and there are none.
        response = self.client.get('/api/curation/labels/Nobody/catalog', headers=self.headers)
        self.assertEqual(response.status_code, 404)


class LabelCatalogWithoutFilesTest(CurationTestCase):
    rules = (('FROM library_labels', None, LABEL_ROW),)

    def test_a_label_without_files_is_an_empty_catalogue_not_an_error(self):
        with patch.object(curation_router, 'Settings') as settings:
            settings.return_value.eps_folder_path = '/mnt/music/EPs'
            settings.return_value.delimiter = '/'
            response = self.client.get('/api/curation/labels/Masters%20of%20Hardcore/catalog', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['series'], [])
        self.assertEqual(response.json()['files_considered'], 0)


class LabelGenreRuleTest(CurationTestCase):
    rules = (
        ('FROM rules_genres WHERE id', None, WHITE_GENRE),
        ('COUNT(DISTINCT', None, {'affected': 88}),
    )

    def test_adding_a_rule_refreshes_the_label_genre_helper(self):
        response = self.client.post(
            '/api/curation/labels/Masters%20of%20Hardcore/genres', json={'genre_id': 12}, headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.reloaded_helpers(), ['labelGenreHelper'])


class LabelParentTest(CurationTestCase):
    rules = (('FROM library_labels', None, LABEL_ROW),)

    def test_a_label_cannot_be_its_own_parent(self):
        response = self.client.put(
            '/api/curation/labels/Masters%20of%20Hardcore/parent', json={'parent_label_id': 3}, headers=self.headers
        )
        self.assertEqual(response.status_code, 400)

    def test_a_parent_can_be_cleared(self):
        response = self.client.put(
            '/api/curation/labels/Masters%20of%20Hardcore/parent', json={'parent_label_id': None}, headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.statements('UPDATE library_labels SET parent_label_id')[0][1], (None, 3))


class LabelCatidTest(CurationTestCase):
    rules = (('FROM library_labels', None, LABEL_ROW),)

    def test_a_catalogue_prefix_is_stored_uppercase(self):
        response = self.client.post(
            '/api/curation/labels/Masters%20of%20Hardcore/catids', json={'catid': 'moh'}, headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.statements('INSERT INTO rules_catid_label')[0][1], ('MOH', 'Masters of Hardcore'))


class GenreListTest(CurationTestCase):
    rules = (
        ('SELECT COUNT(*) AS total FROM rules_genres g', None, {'total': 1}),
        (
            'FROM rules_genres g LEFT JOIN',
            None,
            [
                {
                    'id': 90,
                    'name': 'Industrial Hardcore',
                    'hardness': 80,
                    'occurrences': 0,
                    'track_count': 1514,
                    'artist_rule_count': 3,
                    'label_rule_count': 1,
                    'parents': 'Hardcore;Industrial',
                }
            ],
        ),
    )

    def test_lists_approved_genres_with_what_the_tagger_knows_about_them(self):
        response = self.client.get('/api/curation/genres?q=indus', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['total'], 1)
        row = body['rows'][0]
        self.assertEqual(row['name'], 'Industrial Hardcore')
        self.assertEqual(row['parents'], ['Hardcore', 'Industrial'])
        self.assertEqual(row['artist_rule_count'], 3)
        sql, params = self.statements('FROM rules_genres g LEFT JOIN')[-1]
        self.assertIn("g.state = 'white'", sql)
        self.assertEqual(params[0], '%indus%')

    def test_the_page_size_is_capped_and_a_genre_without_parents_has_an_empty_list(self):
        self.cursor.rules = [
            ('SELECT COUNT(*) AS total FROM rules_genres g', None, {'total': 1}),
            ('FROM rules_genres g LEFT JOIN', None, [{'id': 1, 'name': 'Hardcore', 'parents': None}]),
        ]
        body = self.client.get('/api/curation/genres?limit=99999', headers=self.headers).json()
        self.assertEqual(body['rows'][0]['parents'], [])
        _sql, params = self.statements('LIMIT %s OFFSET %s')[-1]
        self.assertEqual(params[-2], curation_router.GENRE_PAGE_MAX)


class GenreReadTest(CurationTestCase):
    rules = (
        ('FROM rules_genres WHERE normalized_name', None, WHITE_GENRE),
        ("FROM rules_subgenre_hierarchy WHERE LOWER(subgenre)", None, [{'genre': 'Hardcore'}]),
        ("FROM rules_subgenre_hierarchy WHERE LOWER(genre)", None, [{'subgenre': 'Industrial Hardcore'}]),
    )

    def test_returns_parents_and_children(self):
        response = self.client.get('/api/curation/genres/Industrial%20Hardcore', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['parents'], ['Hardcore'])
        self.assertEqual(body['children'], ['Industrial Hardcore'])


def white(genre_id, name):
    """A curated genre row, answered only for its own normalized name."""
    return (
        'FROM rules_genres WHERE normalized_name',
        (name.lower(),),
        {'id': genre_id, 'name': name, 'state': 'white'},
    )


GENRE_ROWS = (
    white(12, 'Hardcore'),
    white(13, 'Industrial Hardcore'),
    white(14, 'Uptempo'),
    white(15, 'Upterror'),
    white(16, 'Terror'),
)


class GenreHierarchyTest(CurationTestCase):
    rules = GENRE_ROWS

    def test_parents_replace_the_previous_set_rather_than_merging(self):
        response = self.client.put(
            '/api/curation/genres/Industrial%20Hardcore/parents', json={'parents': ['Hardcore']}, headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.statements('DELETE FROM rules_subgenre_hierarchy')), 1)
        self.assertEqual(len(self.statements('INSERT INTO rules_subgenre_hierarchy')), 1)

    def test_setting_parents_refreshes_the_subgenre_helper(self):
        self.client.put(
            '/api/curation/genres/Industrial%20Hardcore/parents', json={'parents': ['Hardcore']}, headers=self.headers
        )
        self.assertEqual(self.reloaded_helpers(), ['subgenreHelper'])

    def test_an_empty_list_clears_the_hierarchy(self):
        response = self.client.put(
            '/api/curation/genres/Industrial%20Hardcore/parents', json={'parents': []}, headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.statements('DELETE FROM rules_subgenre_hierarchy')), 1)
        self.assertEqual(self.statements('INSERT INTO rules_subgenre_hierarchy'), [])

    def test_a_genre_cannot_be_its_own_parent(self):
        response = self.client.put(
            '/api/curation/genres/Hardcore/parents', json={'parents': ['hardcore']}, headers=self.headers
        )
        self.assertEqual(response.status_code, 400)


class GenreCycleTest(CurationTestCase):
    """Filing a genre under one of its own descendants would close a cycle: 409."""

    # Upterror -> Uptempo -> Hardcore, and Upterror -> Terror -> Hardcore.
    rules = GENRE_ROWS + (
        (
            'SELECT subgenre, genre FROM rules_subgenre_hierarchy',
            None,
            [
                {'subgenre': 'Uptempo', 'genre': 'Hardcore'},
                {'subgenre': 'Upterror', 'genre': 'Uptempo'},
                {'subgenre': 'Upterror', 'genre': 'Terror'},
                {'subgenre': 'Terror', 'genre': 'Hardcore'},
            ],
        ),
    )

    def put(self, name, parents):
        return self.client.put(f'/api/curation/genres/{name}/parents', json={'parents': parents}, headers=self.headers)

    def test_a_direct_cycle_is_refused(self):
        response = self.put('Hardcore', ['Uptempo'])
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['detail'], 'Hardcore is already an ancestor of Uptempo')
        self.assertEqual(self.statements('DELETE FROM rules_subgenre_hierarchy'), [])
        self.assertEqual(self.statements('INSERT INTO rules_subgenre_hierarchy'), [])

    def test_an_indirect_cycle_is_refused(self):
        response = self.put('Hardcore', ['Upterror'])
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['detail'], 'Hardcore is already an ancestor of Upterror')

    def test_one_bad_parent_refuses_the_whole_list(self):
        response = self.put('Uptempo', ['Terror', 'Upterror'])
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.statements('INSERT INTO rules_subgenre_hierarchy'), [])

    def test_a_self_parent_is_refused_before_the_graph_is_read(self):
        response = self.put('Uptempo', ['uptempo'])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.statements('SELECT subgenre, genre FROM rules_subgenre_hierarchy'), [])

    def test_a_valid_reparent_is_still_stored(self):
        # Uptempo moves from Hardcore to Terror: no cycle, Uptempo is not above Terror.
        response = self.put('Uptempo', ['Terror'])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['parents'], ['Terror'])
        self.assertEqual(
            self.statements('INSERT INTO rules_subgenre_hierarchy'),
            [('INSERT INTO rules_subgenre_hierarchy (subgenre, genre) VALUES (%s, %s)', ('Uptempo', 'Terror'))],
        )

    def test_the_genre_page_lists_every_descendant(self):
        response = self.client.get('/api/curation/genres/Hardcore', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['descendants'], ['Terror', 'Uptempo', 'Upterror'])


class PreexistingCycleTest(CurationTestCase):
    """A cycle stored before the check existed must neither hang a write nor hide."""

    rules = GENRE_ROWS + (
        (
            'SELECT subgenre, genre FROM rules_subgenre_hierarchy',
            None,
            [
                {'subgenre': 'Uptempo', 'genre': 'Terror'},
                {'subgenre': 'Terror', 'genre': 'Uptempo'},
                {'subgenre': 'Upterror', 'genre': 'Upterror'},
            ],
        ),
    )

    def test_a_write_elsewhere_terminates(self):
        response = self.client.put(
            '/api/curation/genres/Hardcore/parents', json={'parents': ['Uptempo']}, headers=self.headers
        )
        self.assertEqual(response.status_code, 200)

    def test_the_check_endpoint_reports_every_cycle(self):
        response = self.client.get('/api/curation/genre-hierarchy/cycles', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'count': 2, 'cycles': [['Terror', 'Uptempo'], ['Upterror']]})


class AcyclicHierarchyCheckTest(CurationTestCase):
    rules = (
        ('SELECT subgenre, genre FROM rules_subgenre_hierarchy', None, [{'subgenre': 'Uptempo', 'genre': 'Hardcore'}]),
    )

    def test_a_clean_hierarchy_reports_nothing(self):
        response = self.client.get('/api/curation/genre-hierarchy/cycles', headers=self.headers)
        self.assertEqual(response.json(), {'count': 0, 'cycles': []})


class GenreHardnessTest(CurationTestCase):
    rules = (('FROM rules_genres WHERE normalized_name', None, WHITE_GENRE),)

    def test_the_read_side_reports_it(self):
        response = self.client.get('/api/curation/genres/Hardcore', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        # WHITE_GENRE carries no 'hardness' key at all -- the read side must fall
        # back to None rather than raising a KeyError on a genre the seed has not
        # reached yet.
        self.assertIsNone(response.json()['hardness'])

    def test_a_value_in_range_is_stored(self):
        response = self.client.put(
            '/api/curation/genres/Hardcore/hardness', json={'hardness': 70}, headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok', 'hardness': 70})
        self.assertEqual(self.statements('UPDATE rules_genres SET hardness')[0][1], (70, 12))

    def test_null_clears_it_back_to_the_seeded_default(self):
        response = self.client.put(
            '/api/curation/genres/Hardcore/hardness', json={'hardness': None}, headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.statements('UPDATE rules_genres SET hardness')[0][1], (None, 12))

    def test_out_of_range_is_refused(self):
        response = self.client.put(
            '/api/curation/genres/Hardcore/hardness', json={'hardness': 101}, headers=self.headers
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.statements('UPDATE rules_genres SET hardness'), [])

    def test_negative_is_refused(self):
        response = self.client.put(
            '/api/curation/genres/Hardcore/hardness', json={'hardness': -1}, headers=self.headers
        )
        self.assertEqual(response.status_code, 400)


class RejectedGenreHardnessTest(CurationTestCase):
    rules = (('FROM rules_genres WHERE normalized_name', None, BLACK_GENRE),)

    def test_a_rejected_genre_has_no_hardness_to_edit(self):
        response = self.client.put('/api/curation/genres/Arts/hardness', json={'hardness': 50}, headers=self.headers)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.statements('UPDATE rules_genres SET hardness'), [])


class RejectedGenreSubjectTest(CurationTestCase):
    rules = (('FROM rules_genres WHERE normalized_name', None, BLACK_GENRE),)

    def test_a_rejected_genre_has_no_hierarchy_to_edit(self):
        """Curation decides whether a genre exists. A rejected one is not in the library."""
        response = self.client.put(
            '/api/curation/genres/Arts/parents', json={'parents': ['Hardcore']}, headers=self.headers
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.statements('INSERT INTO rules_subgenre_hierarchy'), [])

    def test_a_rejected_genre_still_reads_back_so_the_page_can_explain_itself(self):
        response = self.client.get('/api/curation/genres/Arts', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['state'], 'black')
        self.assertFalse(response.json()['editable'])


class PermissionTest(unittest.TestCase):
    """A user without rules.manage may read these pages and change nothing on them."""

    def setUp(self):
        self.conn = MagicMock()
        self.conn.cursor.return_value = ScriptedCursor((('COUNT(DISTINCT', None, {'affected': 0}),))
        patcher = patch.object(curation_router, 'get_db_connection', return_value=self.conn)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _as_plain_user(self):
        return patch.object(
            users_router,
            'verify_token',
            return_value={
                'status': 'ok',
                'type': 'user',
                'user': {'username': 'user', 'role_name': 'user', 'permissions': ['music.read']},
            },
        )

    def test_a_plain_user_may_read_an_artist(self):
        with self._as_plain_user():
            response = TestClient(app).get('/api/curation/artists/Angerfist', headers={'x-api-key': 'user-key'})
        self.assertEqual(response.status_code, 200)

    def test_a_plain_user_may_not_write_a_rule(self):
        with self._as_plain_user():
            response = TestClient(app).post(
                '/api/curation/artists/Angerfist/genres', json={'genre_id': 12}, headers={'x-api-key': 'user-key'}
            )
        self.assertEqual(response.status_code, 403)

    def test_a_plain_user_may_not_set_an_mbid(self):
        with self._as_plain_user():
            response = TestClient(app).put(
                '/api/curation/artists/Angerfist/mbid', json={'mbid': None}, headers={'x-api-key': 'user-key'}
            )
        self.assertEqual(response.status_code, 403)

    def test_a_request_without_a_key_is_unauthorized(self):
        self.assertEqual(TestClient(app).get('/api/curation/artists/Angerfist').status_code, 401)


class RetagTest(CurationTestCase):
    """Applying a rule to the files it matches, rather than waiting for the next pass."""

    rules = (
        (
            'SELECT DISTINCT mf.file_path FROM library_track_artists',
            None,
            [{'file_path': '/mnt/music/a.mp3'}, {'file_path': '/mnt/music/b.mp3'}],
        ),
        ('COUNT(DISTINCT', None, {'affected': 2}),
    )

    def setUp(self):
        super().setUp()
        self.tagger = MagicMock()
        patcher = patch.object(curation_router, 'tagger_manager', self.tagger)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_queues_the_files_the_rule_matches(self):
        response = self.client.post(
            '/api/curation/retag', json={'scope': 'artist', 'name': 'Angerfist'}, headers=self.headers
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()['files'], 2)
        self.assertTrue(response.json()['job_id'])

    def test_every_matched_file_is_actually_retagged(self):
        self.client.post('/api/curation/retag', json={'scope': 'artist', 'name': 'Angerfist'}, headers=self.headers)
        tagged = [call.args[0] for call in self.tagger.tag_single.call_args_list]
        self.assertEqual(tagged, ['/mnt/music/a.mp3', '/mnt/music/b.mp3'])

    def test_one_unreadable_file_does_not_abandon_the_rest(self):
        self.tagger.tag_single.side_effect = [OSError('permission denied'), None]
        self.client.post('/api/curation/retag', json={'scope': 'artist', 'name': 'Angerfist'}, headers=self.headers)
        self.assertEqual(self.tagger.tag_single.call_count, 2)

    def test_a_scope_that_is_not_artist_or_label_is_rejected(self):
        response = self.client.post(
            '/api/curation/retag', json={'scope': 'playlist', 'name': 'x'}, headers=self.headers
        )
        self.assertEqual(response.status_code, 422)


class RetagCeilingTest(CurationTestCase):
    rules = (
        (
            'SELECT DISTINCT mf.file_path FROM library_track_artists',
            None,
            [{'file_path': f'/mnt/music/{n}.mp3'} for n in range(curation_router.MAX_RETAG_FILES_DEFAULT + 1)],
        ),
    )

    def setUp(self):
        super().setUp()
        patcher = patch.object(curation_router, 'tagger_manager', MagicMock())
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_too_large_a_retag_is_refused_rather_than_started(self):
        """A rule on a prolific artist would hold the tagger lock for hours."""
        response = self.client.post(
            '/api/curation/retag', json={'scope': 'artist', 'name': 'Angerfist'}, headers=self.headers
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('full tagger run', response.json()['detail'])


class RetagPermissionTest(unittest.TestCase):
    def test_a_plain_user_may_not_start_a_retag(self):
        conn = MagicMock()
        conn.cursor.return_value = ScriptedCursor(())
        with (
            patch.object(curation_router, 'get_db_connection', return_value=conn),
            patch.object(
                users_router,
                'verify_token',
                return_value={
                    'status': 'ok',
                    'type': 'user',
                    'user': {'username': 'user', 'role_name': 'user', 'permissions': ['music.read']},
                },
            ),
        ):
            response = TestClient(app).post(
                '/api/curation/retag', json={'scope': 'artist', 'name': 'Angerfist'}, headers={'x-api-key': 'user-key'}
            )
        self.assertEqual(response.status_code, 403)


class RetagConfigurableCeilingTest(CurationTestCase):
    """The ceiling comes from the configuration, so it can be tuned without a deploy."""

    rules = (
        (
            'SELECT DISTINCT mf.file_path FROM library_track_artists',
            None,
            [{'file_path': f'/mnt/music/{n}.mp3'} for n in range(3)],
        ),
        ('COUNT(DISTINCT', None, {'affected': 3}),
    )

    def setUp(self):
        super().setUp()
        patcher = patch.object(curation_router, 'tagger_manager', MagicMock())
        patcher.start()
        self.addCleanup(patcher.stop)

    def _retag(self):
        return self.client.post(
            '/api/curation/retag', json={'scope': 'artist', 'name': 'Angerfist'}, headers=self.headers
        )

    def test_three_files_are_accepted_under_the_default_ceiling(self):
        self.assertEqual(self._retag().status_code, 202)

    def test_a_lowered_ceiling_refuses_the_same_three_files(self):
        with patch.object(curation_router, '_max_retag_files', return_value=2):
            response = self._retag()
        self.assertEqual(response.status_code, 400)
        self.assertIn('2', response.json()['detail'])

    def test_an_unreadable_setting_falls_back_to_the_default(self):
        """A broken config value must not take the endpoint down with it."""
        with patch.object(curation_router, 'Settings') as settings:
            settings.return_value.get.return_value = 'not a number'
            self.assertEqual(curation_router._max_retag_files(), curation_router.MAX_RETAG_FILES_DEFAULT)


class AtomicReplaceTest(CurationTestCase):
    """Every delete-then-insert on the curation pages runs in one transaction."""

    rules = (
        ('FROM library_artists', None, ARTIST_ROW),
        ('FROM library_labels', None, LABEL_ROW),
        white(13, 'Industrial Hardcore'),
        ('FROM rules_genres WHERE normalized_name', None, WHITE_GENRE),
    )
    MBID = '5b11f4ce-a62d-471e-81fc-a69a8278c7da'

    def test_an_artist_mbid_and_its_external_id_are_one_transaction(self):
        log = transaction_log(self.conn, self.cursor)
        response = self.client.put(
            '/api/curation/artists/Angerfist/mbid', json={'mbid': self.MBID}, headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        assert_atomic(
            self,
            log,
            'UPDATE library_artists SET mbid',
            'DELETE FROM artist_external_ids',
            'INSERT INTO artist_external_ids',
        )

    def test_an_artist_external_id_is_replaced_in_one_transaction(self):
        log = transaction_log(self.conn, self.cursor)
        response = self.client.put(
            '/api/curation/artists/Angerfist/external-ids',
            json={'source': 'spotify', 'external_id': 'abc'},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        assert_atomic(self, log, 'DELETE FROM artist_external_ids', 'INSERT INTO artist_external_ids')

    def test_a_failing_external_id_insert_keeps_the_old_one(self):
        log = transaction_log(self.conn, self.cursor, fail_on='INSERT INTO artist_external_ids')
        with self.assertRaises(RuntimeError):
            self.client.put(
                '/api/curation/artists/Angerfist/external-ids',
                json={'source': 'spotify', 'external_id': 'abc'},
                headers=self.headers,
            )
        assert_rolled_back(self, log)

    def test_a_label_mbid_and_its_external_id_are_one_transaction(self):
        log = transaction_log(self.conn, self.cursor)
        response = self.client.put(
            '/api/curation/labels/Masters%20of%20Hardcore/mbid', json={'mbid': self.MBID}, headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        assert_atomic(
            self,
            log,
            'UPDATE library_labels SET mbid',
            'DELETE FROM label_external_ids',
            'INSERT INTO label_external_ids',
        )

    def test_a_label_external_id_is_replaced_in_one_transaction(self):
        log = transaction_log(self.conn, self.cursor)
        response = self.client.put(
            '/api/curation/labels/Masters%20of%20Hardcore/external-ids',
            json={'source': 'discogs', 'external_id': '123'},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        assert_atomic(self, log, 'DELETE FROM label_external_ids', 'INSERT INTO label_external_ids')

    def test_genre_parents_are_replaced_in_one_transaction(self):
        log = transaction_log(self.conn, self.cursor)
        response = self.client.put(
            '/api/curation/genres/Industrial%20Hardcore/parents', json={'parents': ['Hardcore']}, headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        assert_atomic(self, log, 'DELETE FROM rules_subgenre_hierarchy', 'INSERT INTO rules_subgenre_hierarchy')

    def test_a_failing_parent_insert_keeps_the_old_hierarchy(self):
        log = transaction_log(self.conn, self.cursor, fail_on='INSERT INTO rules_subgenre_hierarchy')
        with self.assertRaises(RuntimeError):
            self.client.put(
                '/api/curation/genres/Industrial%20Hardcore/parents',
                json={'parents': ['Hardcore']},
                headers=self.headers,
            )
        assert_rolled_back(self, log)
        self.assertEqual(self.reloaded_helpers(), [])

    def test_a_cycle_is_refused_before_a_transaction_opens(self):
        log = transaction_log(self.conn, self.cursor)
        self.cursor.rules.insert(
            0,
            (
                'SELECT subgenre, genre FROM rules_subgenre_hierarchy',
                None,
                [{'subgenre': 'Hardcore', 'genre': 'Industrial Hardcore'}],
            ),
        )
        response = self.client.put(
            '/api/curation/genres/Industrial%20Hardcore/parents', json={'parents': ['Hardcore']}, headers=self.headers
        )
        self.assertEqual(response.status_code, 409)
        self.assertNotIn('BEGIN', log)
        self.assertFalse([entry for entry in log if entry.startswith(('DELETE', 'INSERT'))])
