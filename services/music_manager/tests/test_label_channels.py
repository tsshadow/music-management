"""A label or artist page's channels: GET /api/channel-links/by-label (issue #122), /by-artist (#126)."""

import unittest
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.mock_base('mutagen', 'markdown', 'pymysql', 'dbutils', 'DatabaseConnector')


import services.music_manager.routers.users as users_router
from services.music_manager.api_key import resolve_system_api_key

users_router.run_lms_db_sync = lambda only_sources=None: None

from fastapi.testclient import TestClient

from services.music_manager import channel_links as links
from services.music_manager.main import app
from services.music_manager.routers import channel_links as router_module
from services.music_manager.tests.scripted_cursor import normalize

API_KEY = resolve_system_api_key()


class ChannelAlbumTest(unittest.TestCase):
    """The album the tagger files a channel's tracks under."""

    def test_the_album_is_the_publisher_and_the_channel(self):
        self.assertEqual('Soundcloud (Traxtorm)', links.channel_album('soundcloud', 'Traxtorm'))
        self.assertEqual('Youtube (Traxtorm)', links.channel_album('youtube', 'Traxtorm'))
        self.assertEqual('Telegram (Hard)', links.channel_album('telegram', 'Hard'))

    def test_an_unknown_platform_or_an_empty_name_has_no_album(self):
        self.assertIsNone(links.channel_album('bandcamp', 'Traxtorm'))
        self.assertIsNone(links.channel_album('soundcloud', ''))


class SourceUrlTest(unittest.TestCase):
    """The followed account a channel is named after, when exactly one is."""

    def test_the_key_keeps_letters_and_digits_only(self):
        self.assertEqual('traxtormrecords', links.account_key('@Traxtorm-Records'))
        self.assertEqual('traxtormrecords', links.account_key('TRAXTORM RECORDS'))
        self.assertEqual('', links.account_key(None))

    def test_one_matching_account_gives_its_page(self):
        soundcloud = links.account_index(['brainimpact', 'other'])
        youtube = links.account_index(['@traxtormrecords', 'UC123abc'])
        self.assertEqual(
            'https://soundcloud.com/brainimpact', links.source_url('soundcloud', 'BRAIN IMPACT', soundcloud)
        )
        self.assertEqual(
            'https://www.youtube.com/@traxtormrecords', links.source_url('youtube', 'Traxtorm Records', youtube)
        )
        self.assertEqual('https://www.youtube.com/channel/UC123abc', links.source_url('youtube', 'UC123ABC', youtube))

    def test_no_match_two_matches_or_telegram_give_nothing(self):
        index = links.account_index(['brain-impact', 'brainimpact', 'hysta'])
        self.assertIsNone(links.source_url('soundcloud', 'Brain Impact', index))
        self.assertIsNone(links.source_url('soundcloud', 'Hysta Official', index))
        self.assertIsNone(links.source_url('telegram', 'hysta', index))

    def test_the_index_holds_each_name_once_and_skips_empty_keys(self):
        self.assertEqual({'hysta': ['hysta']}, links.account_index(['hysta', 'hysta', '---', '']))


class ChannelsCall:
    """Calls one of the two list endpoints against a scripted cursor; mixed into both test cases."""

    path = ''

    def setUp(self):
        self.client = TestClient(app)
        self.headers = {'x-api-key': API_KEY}

    def call(self, name, answers):
        cursor = MagicMock()
        executed = []

        def execute(sql, params=()):
            executed.append((normalize(sql), params))
            answer = answers.get(normalize(sql), [])
            if isinstance(answer, Exception):
                raise answer
            cursor.fetchall.return_value = answer

        cursor.execute.side_effect = execute
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cursor
        with patch.object(router_module, 'get_db_connection', return_value=conn):
            response = self.client.get(self.path, params={'name': name}, headers=self.headers)
        return response, executed


class LabelChannelsEndpointTest(ChannelsCall, unittest.TestCase):
    """The endpoint: one indexed read for the channels, the accounts only when there are channels."""

    path = '/api/channel-links/by-label'

    def test_a_label_lists_its_channels_with_counts_album_and_source(self):
        rows = [
            {
                'id': 3,
                'platform': 'soundcloud',
                'name': 'Traxtorm Records',
                'artist_id': None,
                'artist_name': None,
                'track_count': 812,
            },
            {'id': 4, 'platform': 'youtube', 'name': 'Traxtorm', 'artist_id': 9, 'artist_name': 'X', 'track_count': 0},
        ]
        response, executed = self.call(
            'Traxtorm Records',
            {
                normalize(router_module.LABEL_CHANNELS_QUERY): rows,
                normalize(router_module.ACCOUNTS_QUERY['soundcloud']): [{'name': 'traxtormrecords'}],
                normalize(router_module.ACCOUNTS_QUERY['youtube']): [{'name': '@other'}],
            },
        )
        self.assertEqual(200, response.status_code)
        self.assertEqual(
            [
                {
                    'id': 3,
                    'platform': 'soundcloud',
                    'name': 'Traxtorm Records',
                    'track_count': 812,
                    'artist': None,
                    'album': 'Soundcloud (Traxtorm Records)',
                    'source_url': 'https://soundcloud.com/traxtormrecords',
                },
                {
                    'id': 4,
                    'platform': 'youtube',
                    'name': 'Traxtorm',
                    'track_count': 0,
                    'artist': {'id': 9, 'name': 'X'},
                    'album': 'Youtube (Traxtorm)',
                    'source_url': None,
                },
            ],
            response.json(),
        )
        self.assertEqual(('Traxtorm Records',), executed[0][1])

    def test_a_label_without_channels_asks_nothing_more(self):
        response, executed = self.call('Nobody', {})
        self.assertEqual([], response.json())
        self.assertEqual([normalize(router_module.LABEL_CHANNELS_QUERY)], [sql for sql, _ in executed])

    def test_only_the_platforms_present_have_their_accounts_read(self):
        row = {'id': 1, 'platform': 'youtube', 'name': 'A', 'artist_id': None, 'artist_name': None, 'track_count': 1}
        _response, executed = self.call('L', {normalize(router_module.LABEL_CHANNELS_QUERY): [row]})
        self.assertNotIn(normalize(router_module.ACCOUNTS_QUERY['soundcloud']), [sql for sql, _ in executed])
        self.assertIn(normalize(router_module.ACCOUNTS_QUERY['youtube']), [sql for sql, _ in executed])

    def test_an_unreadable_accounts_table_costs_the_link_not_the_list(self):
        row = {'id': 1, 'platform': 'soundcloud', 'name': 'A', 'artist_id': None, 'artist_name': None, 'track_count': 1}
        response, _ = self.call(
            'L',
            {
                normalize(router_module.LABEL_CHANNELS_QUERY): [row],
                normalize(router_module.ACCOUNTS_QUERY['soundcloud']): RuntimeError('no table'),
            },
        )
        self.assertEqual(200, response.status_code)
        self.assertIsNone(response.json()[0]['source_url'])

    def test_a_blank_name_asks_nothing(self):
        response, executed = self.call('  ', {})
        self.assertEqual([], response.json())
        self.assertEqual([], executed)

    def test_the_list_needs_an_api_key(self):
        self.assertEqual(401, self.client.get('/api/channel-links/by-label?name=x').status_code)


class ArtistChannelsEndpointTest(ChannelsCall, unittest.TestCase):
    """The mirror on the artist page: keyed on the artist's name, each channel with its label."""

    path = '/api/channel-links/by-artist'

    def test_an_artist_lists_its_channels_with_their_labels(self):
        rows = [
            {
                'id': 5,
                'platform': 'soundcloud',
                'name': 'D-Sturb',
                'label_id': 2,
                'label_name': 'Traxtorm',
                'track_count': 40,
            },
            {'id': 6, 'platform': 'telegram', 'name': 'dsturb', 'label_id': None, 'label_name': None, 'track_count': 0},
        ]
        response, executed = self.call(
            ' D-Sturb ',
            {
                normalize(router_module.ARTIST_CHANNELS_QUERY): rows,
                normalize(router_module.ACCOUNTS_QUERY['soundcloud']): [{'name': 'dsturb'}],
            },
        )
        self.assertEqual(200, response.status_code)
        self.assertEqual(
            [
                {
                    'id': 5,
                    'platform': 'soundcloud',
                    'name': 'D-Sturb',
                    'track_count': 40,
                    'label': {'id': 2, 'name': 'Traxtorm'},
                    'album': 'Soundcloud (D-Sturb)',
                    'source_url': 'https://soundcloud.com/dsturb',
                },
                {
                    'id': 6,
                    'platform': 'telegram',
                    'name': 'dsturb',
                    'track_count': 0,
                    'label': None,
                    'album': 'Telegram (dsturb)',
                    'source_url': None,
                },
            ],
            response.json(),
        )
        self.assertEqual((normalize(router_module.ARTIST_CHANNELS_QUERY), ('D-Sturb',)), executed[0])

    def test_an_artist_without_channels_asks_nothing_more(self):
        response, executed = self.call('Nobody', {})
        self.assertEqual([], response.json())
        self.assertEqual([normalize(router_module.ARTIST_CHANNELS_QUERY)], [sql for sql, _ in executed])

    def test_only_the_platforms_present_have_their_accounts_read(self):
        row = {'id': 1, 'platform': 'youtube', 'name': 'A', 'label_id': None, 'label_name': None, 'track_count': 1}
        _response, executed = self.call('A', {normalize(router_module.ARTIST_CHANNELS_QUERY): [row]})
        self.assertNotIn(normalize(router_module.ACCOUNTS_QUERY['soundcloud']), [sql for sql, _ in executed])
        self.assertIn(normalize(router_module.ACCOUNTS_QUERY['youtube']), [sql for sql, _ in executed])

    def test_an_unreadable_accounts_table_costs_the_link_not_the_list(self):
        row = {'id': 1, 'platform': 'soundcloud', 'name': 'A', 'label_id': None, 'label_name': None, 'track_count': 1}
        response, _ = self.call(
            'A',
            {
                normalize(router_module.ARTIST_CHANNELS_QUERY): [row],
                normalize(router_module.ACCOUNTS_QUERY['soundcloud']): RuntimeError('no table'),
            },
        )
        self.assertEqual(200, response.status_code)
        self.assertIsNone(response.json()[0]['source_url'])

    def test_the_list_needs_an_api_key(self):
        self.assertEqual(401, self.client.get('/api/channel-links/by-artist?name=x').status_code)


if __name__ == '__main__':
    unittest.main()
