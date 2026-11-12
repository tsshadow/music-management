"""Wrapped's loading, collection cards, payload, snapshots and periods, against a scripted cursor."""

import json
import threading
import time
from datetime import UTC, date, datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

pytestmark = pytest.mark.mock_base('DatabaseConnector')

from services.common import arrival  # noqa: E402
from services.music_manager.routers.listening import ListeningScope  # noqa: E402
from services.music_manager.tests.scripted_cursor import ScriptedCursor  # noqa: E402
from services.music_manager.wrapped import collection_cards as cc  # noqa: E402
from services.music_manager.wrapped import data as wd  # noqa: E402
from services.music_manager.wrapped import payload as wp  # noqa: E402
from services.music_manager.wrapped import snapshots  # noqa: E402
from services.music_manager.wrapped.periods import PeriodError, parse_key, parse_period, parse_zone  # noqa: E402

UTC_ZONE = ZoneInfo('UTC')
NOW = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)
YEAR = parse_period(2026, None, None)


def scope(username='teun'):
    return ListeningScope(username, date(2026, 1, 1), date(2026, 12, 31), UTC_ZONE)


LINKED_ROW = {
    'listened_at': datetime(2026, 3, 1, 10),
    'username': 'teun',
    'source': 'mobile',
    'played_secs': 120,
    'track_id': 7,
    'title': 'Qlimax 2024 Liveset',
    'artist': 'Sub Zero Project',
    'artist_id': 3,
    'duration_secs': 3600.0,
    'form': 'liveset',
    'performance_date': '2024-11-23',
    'track_uid': 'u7',
    'arrived_at': None,
    'release_year': 2024,
}
UNMATCHED_ROW = {
    'listened_at': datetime(2026, 2, 1, 10),
    'username': 'teun',
    'source': 'listenbrainz_import',
    'played_secs': None,
    'artist_name': 'ID',
    'track_title': 'ID',
}


COLLECTION_RULES = [
    ('SELECT rg.name, COUNT(*) AS tracks', None, [{'name': 'Hardstyle', 'tracks': 50}]),
    ('COUNT(arrived_at) AS arrived', None, {'tracks': 100, 'music': 90, 'secs': 1000.0, 'arrived': 0}),
    ('FLOOR(bpm / 5) * 5 AS bucket', None, [{'bucket': 150, 'n': 10}]),
]


def period_rules():
    return [
        *COLLECTION_RULES,
        ('FROM scrobble_listens l JOIN library_tracks t', None, [LINKED_ROW]),
        ('FROM scrobble_unmatched_listens', None, [UNMATCHED_ROW]),
        ('FROM library_track_genres tg', None, [{'track_id': 7, 'name': 'Hardstyle'}]),
        ('FROM library_track_labels tl', None, [{'track_id': 7, 'label_id': 2, 'name': 'Q-dance'}]),
        (
            'FROM library_track_channels tc JOIN channels c ON c.id = tc.channel_id LEFT JOIN',
            None,
            [
                {
                    'track_id': 7,
                    'channel_id': 4,
                    'platform': 'youtube',
                    'name': 'Q-dance',
                    'label_name': 'Q-dance',
                    'artist_name': None,
                }
            ],
        ),
        ('FROM library_track_effective_bpm b', None, [{'track_id': 7, 'bpm': 150, 'confidence': 'high'}]),
        ("SELECT EXISTS (SELECT 1 FROM library_track_artists WHERE role = 'remixer')", None, {'present': 0}),
        ('FROM rules_festivals', None, [{'id': 1, 'name': 'Qlimax'}]),
        ('FROM rules_festival_aliases', None, [{'festival_id': 1, 'alias': 'Qlimax'}]),
        ('FROM rules_festival_editions', None, [{'festival_id': 1, 'year': 2024, 'date': '2024-11-23'}]),
        ('FROM rules_podcasts p', None, [{'id': 1, 'name': 'Hardstyle Sessions', 'alias': 'HS'}]),
        ('FROM library_media_files', None, [{'track_id': 7, 'file_path': '/music/Youtube/Q/q.m4a'}]),
    ]


class LoadPeriodTest:
    def test_reads_both_tables_in_time_order_with_the_track_facts(self):
        data = wd.load_period(ScriptedCursor(period_rules()), scope())
        assert [listen.linked for listen in data.listens] == [False, True]
        assert data.genres == {7: ['Hardstyle']}
        assert data.labels == {7: [(2, 'Q-dance')]}
        assert data.channels[7][0]['label'] == 'Q-dance'
        assert data.bpm == {7: (150.0, 'high')}
        assert data.remixer_credits is False

    def test_the_label_query_passes_the_scope_twice(self):
        cursor = ScriptedCursor(period_rules())
        wd.load_period(cursor, scope())
        ((_sql, params),) = cursor.statements_matching('FROM library_track_labels tl')
        assert params.count('teun') == 2

    def test_skips_the_track_queries_without_linked_listens(self):
        cursor = ScriptedCursor([('FROM scrobble_unmatched_listens', None, [UNMATCHED_ROW])])
        wd.load_period(cursor, scope())
        assert not cursor.statements_matching('library_track_genres')

    def test_user_history_reads_before_the_period_and_others_in_it(self):
        cursor = ScriptedCursor(
            [
                ('SELECT DISTINCT rg.name', None, [{'name': 'Hardcore'}]),
                ('SELECT DISTINCT t.primary_artist_id', None, [{'artist_id': 3}]),
                ('SELECT DISTINCT track_id', None, [{'track_id': 9}]),
                ('FROM rating_tracks', None, [{'entity_id': 'u7', 'rating': 5, 'updated_at': datetime(2026, 8, 1)}]),
            ]
        )
        history = wd.load_user_history(cursor, scope())
        assert history.prior_genres == {'Hardcore'} and history.prior_artists == {3}
        assert history.others_tracks == {9} and len(history.ratings) == 1
        ((_sql, params),) = cursor.statements_matching('SELECT DISTINCT track_id')
        assert params == (datetime(2026, 1, 1), datetime(2027, 1, 1), 'teun')


class PayloadTest:
    def test_user_tab_has_every_card_in_order_and_paths(self):
        cc._facts_cache.clear()
        payload = wp.build_payload(ScriptedCursor(period_rules()), wp.USER, 'teun', YEAR, UTC_ZONE, NOW)
        assert [c['id'] for c in payload['cards']] == list(wp.USER_ORDER)
        assert payload['period']['running'] is True
        assert payload['period']['data_until'] == NOW.isoformat()
        festival = next(c for c in payload['cards'] if c['id'] == 'festival')
        assert festival['status'] == 'below_minimum'
        first_last = next(c for c in payload['cards'] if c['id'] == 'first_last')
        assert first_last['data']['last']['file_path'] == '/music/Youtube/Q/q.m4a'
        assert payload['coverage']['bpm_share'] == 1.0
        assert {'id': 'top_remixer', 'status': 'blocked', 'reason': 'no_remixer_credits'} in payload['coverage'][
            'left_out'
        ]

    def test_library_tab_names_no_listener(self):
        cc._facts_cache.clear()
        payload = wp.build_payload(ScriptedCursor(period_rules()), wp.LIBRARY, None, YEAR, UTC_ZONE, NOW)
        assert [c['id'] for c in payload['cards']] == list(wp.LIBRARY_ORDER)
        assert 'teun' not in json.dumps(payload)
        growth = next(c for c in payload['cards'] if c['id'] == 'growth')
        assert growth['reason'] == 'no_arrival_date'

    def test_a_closed_year_is_not_running(self):
        block = wp._period_block(parse_period(2025, None, None), UTC_ZONE, NOW)
        assert block['running'] is False
        assert block['data_until'] == '2026-01-01T00:00:00+00:00'


class CollectionCardsTest:
    def data(self, start=date(2026, 1, 1), end=date(2026, 12, 31)):
        return wd.PeriodData(scope=ListeningScope(None, start, end, UTC_ZONE), listens=[], library_scope=True)

    def test_releases_by_year_or_by_day(self):
        assert 'LEFT(t.release_date, 4)' in cc.release_condition(self.data())[0]
        cond, params = cc.release_condition(self.data(date(2026, 3, 1), date(2026, 6, 30)))
        assert 'CHAR_LENGTH' in cond and params == ['2026-03-01', '2026-06-30']

    def test_releases_of_year(self):
        cursor = ScriptedCursor(
            [
                ('SELECT COUNT(*) AS tracks FROM library_tracks t', None, {'tracks': 27020}),
                ('COUNT(DISTINCT x.track_id)', None, [{'label_id': 1, 'name': 'Scantraxx', 'tracks': 300}]),
            ]
        )
        card = cc.card_releases_of_year(cursor, self.data())
        assert card['data'] == {'tracks': 27020, 'labels': [{'label_id': 1, 'label': 'Scantraxx', 'tracks': 300}]}

    def test_downloads_per_month_with_the_undated_in_the_basis(self):
        cursor = ScriptedCursor(
            [
                ('GROUP BY platform, slot', None, [{'platform': 'youtube', 'slot': '2026-01-31 23', 'n': 4}]),
                ('ORDER BY n DESC, account', None, {'platform': 'youtube', 'account': 'Q-dance', 'n': 4}),
                ('AS undated', None, {'undated': 6}),
            ]
        )
        card = cc.card_downloads(cursor, self.data())
        assert card['data']['months'] == [{'month': '2026-01', 'soundcloud': 0, 'youtube': 4}]
        assert card['basis'] == {'counted': 4, 'of': 10, 'unit': 'downloads'}

    def test_growth_by_source(self):
        cursor = ScriptedCursor([('GROUP BY source', None, [{'source': 'soundcloud', 'n': 5}])])
        facts = cc.CollectionFacts(tracks=10, music=10, arrived=6)
        card = cc.card_growth(cursor, self.data(), facts)
        assert card['data'] == {'tracks': 5, 'sources': [{'source': 'soundcloud', 'tracks': 5}], 'unknown_arrival': 4}

    def test_shelf_start_now_unplayed_and_system(self):
        facts = cc.CollectionFacts(shelf={150: 3}, tracks=10, music=8, secs=86400.0, genres=[])
        assert cc.card_shelf(facts)['data']['buckets'] == [{'bpm': 150, 'tracks': 3}]
        assert cc.card_start_now(facts, NOW)['data'] == {'total_secs': 86400, 'finish': '2026-11-13'}
        assert cc.card_unplayed(self.data(), facts)['data']['unplayed'] == 8
        cursor = ScriptedCursor(
            [('AS bpm_measured', None, {'bpm_measured': 5, 'bulletins': 1, 'ratings': 0, 'criticals': 2})]
        )
        assert cc.card_system(cursor, self.data())['data']['criticals'] == 2

    def test_festival_editions(self):
        festivals = wd.load_festival_helper(ScriptedCursor(period_rules()))
        cursor = ScriptedCursor(
            [('WHERE form = \'liveset\'', None, [{'title': 'Qlimax 2026', 'performance_date': '2026-11-21'}])]
        )
        card = cc.card_festival_editions(cursor, self.data(), festivals)
        assert card['data'] == {'sets': 1, 'festivals': [{'festival': 'Qlimax', 'sets': 1}]}

    def test_collection_facts_are_read_once_a_day(self):
        cc._facts_cache.clear()
        cursor = ScriptedCursor(COLLECTION_RULES)
        cc.collection_facts(cursor, date(2026, 11, 12))
        facts = cc.collection_facts(cursor, date(2026, 11, 12))
        assert facts.genres == [{'genre': 'Hardstyle', 'tracks': 50}]
        assert len(cursor.statements_matching('COUNT(arrived_at)')) == 1


class PeriodsTest:
    def test_year_and_range(self):
        assert parse_period(2026, None, None).key == '2026'
        assert parse_period(None, date(2026, 3, 1), date(2026, 6, 30)).key == '2026-03-01_2026-06-30'
        assert parse_key('2026-03-01_2026-06-30').date_to == date(2026, 6, 30)
        assert parse_key('2025').year == 2025

    @pytest.mark.parametrize(
        'args',
        [
            (2026, date(2026, 1, 1), None),
            (None, None, None),
            (None, date(2026, 2, 1), date(2026, 1, 1)),
            (None, date(2020, 1, 1), date(2024, 1, 1)),
            (None, date(2026, 1, 1), None),
        ],
    )
    def test_bad_periods(self, args):
        with pytest.raises(PeriodError):
            parse_period(*args)

    def test_bad_zone(self):
        with pytest.raises(PeriodError):
            parse_zone('Mars/Olympus')


def snapshot_row(payload, generated, closed=0, fmt=wp.WRAPPED_FORMAT):
    return {'payload': json.dumps(payload), 'closed': closed, 'generated_at': generated, 'format': fmt}


class SnapshotsTest:
    def test_freshness(self):
        assert snapshots.is_fresh(snapshot_row({}, datetime(2026, 11, 12, 1)), NOW)
        assert not snapshots.is_fresh(snapshot_row({}, datetime(2026, 11, 11, 11)), NOW)
        assert snapshots.is_fresh(snapshot_row({}, datetime(2020, 1, 1), closed=1), NOW)
        assert not snapshots.is_fresh(snapshot_row({}, datetime(2020, 1, 1), closed=1, fmt=0), NOW)
        assert not snapshots.is_fresh(None, NOW)

    def test_a_fresh_row_is_not_recomputed(self, monkeypatch):
        build = MagicMock()
        monkeypatch.setattr(snapshots, 'build_payload', build)
        cursor = ScriptedCursor([('FROM wrapped_snapshots', None, snapshot_row({'x': 1}, datetime(2026, 11, 12, 6)))])
        conn = MagicMock()
        conn.cursor.return_value = cursor
        assert snapshots.get_or_compute(lambda: conn, 'user', 'teun', YEAR, UTC_ZONE, NOW) == {'x': 1}
        build.assert_not_called()

    def test_a_missing_row_is_computed_and_stored_closed_when_the_period_ended(self, monkeypatch):
        monkeypatch.setattr(snapshots, 'build_payload', lambda *a: {'cards': []})
        cursor = ScriptedCursor()
        conn = MagicMock()
        conn.cursor.return_value = cursor
        snapshots.get_or_compute(lambda: conn, 'library', 'ignored', parse_period(2025, None, None), UTC_ZONE, NOW)
        ((_sql, params),) = cursor.statements_matching('INSERT INTO wrapped_snapshots')
        assert params[:4] == ('library', '', '2025', 'UTC')
        assert params[5] == 1

    def test_two_concurrent_requests_compute_once(self, monkeypatch):
        store: dict = {}
        calls = []

        def build(*_args):
            calls.append(1)
            time.sleep(0.2)
            return {'n': len(calls)}

        class Cursor(ScriptedCursor):
            def execute(self, sql, params=None):
                super().execute(sql, params)
                if 'INSERT INTO wrapped_snapshots' in sql:
                    store['row'] = snapshot_row(json.loads(params[8]), NOW.replace(tzinfo=None))
                elif 'FROM wrapped_snapshots' in sql:
                    self._result = store.get('row')

        def connect():
            conn = MagicMock()
            conn.cursor.return_value = Cursor()
            return conn

        monkeypatch.setattr(snapshots, 'build_payload', build)
        results = []
        threads = [
            threading.Thread(
                target=lambda: results.append(snapshots.get_or_compute(connect, 'user', 'a', YEAR, UTC_ZONE, NOW))
            )
            for _ in range(2)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(calls) == 1
        assert results == [{'n': 1}, {'n': 1}]

    def test_drop_and_prune(self):
        cursor = ScriptedCursor(
            [
                (
                    'SELECT scope, username, period_key, tz',
                    None,
                    [{'scope': 'user', 'username': 'a', 'period_key': '2026', 'tz': 'UTC'}],
                )
            ]
        )
        keys = snapshots.drop(cursor, 'user', YEAR, 'A')
        assert keys == [('user', 'a', '2026', 'UTC')]
        assert cursor.statements_matching('DELETE FROM wrapped_snapshots')
        conn = MagicMock()
        prune_cursor = ScriptedCursor(rowcount=3)
        conn.cursor.return_value = prune_cursor
        assert snapshots.prune(conn, NOW) == 3
        ((_sql, params),) = prune_cursor.statements_matching('DELETE FROM wrapped_snapshots')
        assert params == (datetime(2026, 10, 13, 12, 0),)


class ArrivalTest:
    def test_source_from_the_top_folder(self):
        root = '/mnt/music'
        assert arrival.arrival_source('/mnt/music/Soundcloud/a/b.m4a', root) == 'soundcloud'
        assert arrival.arrival_source('/mnt/music/EPs/Label/x.flac', root) == 'label'
        assert arrival.arrival_source('/mnt/music/Lidarr/x/y.flac', root) == 'import'
        assert arrival.arrival_source('/elsewhere/x.flac', root) == 'unknown'

    def test_merged_arrival_takes_the_earlier_and_unknown_wins(self):
        early = {'arrived_at': datetime(2026, 1, 1), 'arrived_source': 'soundcloud'}
        late = {'arrived_at': datetime(2026, 5, 1), 'arrived_source': 'import'}
        assert arrival.merged_arrival(late, early) == (datetime(2026, 1, 1), 'soundcloud')
        assert arrival.merged_arrival({'arrived_at': None}, early) == (None, None)

    def test_carry_arrival_updates_the_new_row(self):
        cursor = ScriptedCursor(
            [
                (
                    'SELECT id, arrived_at, arrived_source FROM library_tracks',
                    None,
                    [
                        {'id': 1, 'arrived_at': datetime(2026, 1, 1), 'arrived_source': 'youtube'},
                        {'id': 2, 'arrived_at': datetime(2026, 11, 1), 'arrived_source': 'youtube'},
                    ],
                )
            ]
        )
        arrival.carry_arrival(cursor, 1, 2)
        ((_sql, params),) = cursor.statements_matching('UPDATE library_tracks SET arrived_at')
        assert params == (datetime(2026, 1, 1), 'youtube', 2)


def test_utc_bounds_follow_the_zone():
    s = ListeningScope(None, date(2026, 1, 1), date(2026, 12, 31), ZoneInfo('Europe/Amsterdam'))
    assert wd.utc_bounds(s) == (datetime(2025, 12, 31, 23), datetime(2026, 12, 31, 23))
    assert wd.to_local(datetime(2025, 12, 31, 23, 30), s).year == 2026
