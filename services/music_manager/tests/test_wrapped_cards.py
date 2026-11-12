"""The Wrapped listening cards, over hand-built periods (docs/designs/wrapped-page/technical.md)."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from services.common.Helpers.FestivalHelper import Festival, FestivalHelper
from services.common.Helpers.PodcastHelper import PodcastHelper, Show
from services.music_manager.routers.listening import ListeningScope
from services.music_manager.wrapped import listening_cards as lc
from services.music_manager.wrapped.data import Listen, PeriodData, UserHistory, to_local

UTC_ZONE = ZoneInfo('UTC')
AMS = ZoneInfo('Europe/Amsterdam')


def scope(zone=UTC_ZONE, username='teun', start=date(2026, 1, 1), end=date(2026, 12, 31)):
    return ListeningScope(username, start, end, zone)


def listen(at, track_id=None, s=None, **fields):
    s = s or scope()
    fields.setdefault('username', 'teun')
    fields.setdefault('source', 'frontend')
    fields.setdefault('played_secs', None)
    if track_id is not None:
        fields.setdefault('title', f'Track {track_id}')
        fields.setdefault('artist', f'Artist {track_id}')
        fields.setdefault('artist_id', track_id)
        fields.setdefault('duration_secs', 200.0)
        fields.setdefault('form', 'track')
        fields.setdefault('track_uid', f'uid{track_id}')
    return Listen(at=at, local=to_local(at, s), track_id=track_id, **fields)


def period(listens, s=None, **extra):
    s = s or scope()
    return PeriodData(scope=s, listens=sorted(listens, key=lambda listen: listen.at), **extra)


T0 = datetime(2026, 3, 2, 12, 0)


def spread(track_ids, start=T0, step=timedelta(hours=1), **fields):
    return [listen(start + i * step, t, **fields) for i, t in enumerate(track_ids)]


class TotalsTest:
    def test_title_counts_both_kinds_and_estimates_the_time(self):
        data = period([listen(T0, 1, played_secs=100.0), listen(T0, 2), listen(T0, None, title='x')])
        card = lc.card_title(data)
        assert card['status'] == 'ok'
        assert card['data'] == {
            'listens': 3,
            'linked': 2,
            'unmatched': 1,
            'distinct_tracks': 2,
            'estimated_secs': 300,
        }

    def test_title_is_empty_without_listens(self):
        assert lc.card_title(period([]))['status'] == 'empty'

    def test_listening_time_keeps_measured_and_imputed_apart(self):
        data = period([listen(T0, 1, played_secs=60.0), listen(T0, 2), listen(T0, None, played_secs=30.0)])
        card = lc.card_listening_time(data)['data']
        assert card == {'measured_secs': 90, 'imputed_secs': 200, 'estimated_secs': 290, 'measured_share': 0.6667}

    def test_listeners_counts_deleted_accounts_as_former_and_names_nobody(self):
        data = period(
            [listen(T0, 1, username='teun'), listen(T0, 1, username='Teun'), listen(T0, 2, username='deleted-7')]
        )
        assert lc.card_listeners(data)['data'] == {'active': 1, 'former': 1}


class RankingsTest:
    def test_top_tracks_ranks_by_plays_then_title_and_discloses_unmatched(self):
        data = period([*spread([1, 1, 1, 2, 2, 3, 4]), listen(T0, None, title='raw')])
        card = lc.card_top_tracks(data)
        assert [t['track_id'] for t in card['data']['tracks']] == [1, 2, 3, 4]
        assert card['data']['unmatched'] == 1
        assert card['basis'] == {'counted': 7, 'of': 8, 'unit': 'listens'}

    def test_top_tracks_needs_three_tracks(self):
        assert lc.card_top_tracks(period(spread([1, 2])))['status'] == 'below_minimum'

    def test_top_artists_counts_primary_artists(self):
        data = period(spread([1, 1, 2, 3]))
        artists = lc.card_top_artists(data)['data']['artists']
        assert artists[0] == {'artist_id': 1, 'artist': 'Artist 1', 'listens': 2}

    def test_top_genres_counts_a_listen_in_each_genre_and_reports_untagged(self):
        data = period(spread([1, 2, 3, 4]), genres={1: ['A', 'B'], 2: ['A'], 3: ['C']})
        card = lc.card_top_genres(data)['data']
        assert card['genres'][0] == {'genre': 'A', 'listens': 2}
        assert card['untagged'] == 1

    def test_seasons_needs_two_seasons_with_twenty_tagged_listens(self):
        winter = spread([1] * 20, start=datetime(2026, 1, 5))
        summer = spread([2] * 20, start=datetime(2026, 7, 5))
        data = period([*winter, *summer], genres={1: ['Hardstyle'], 2: ['Hardcore']})
        card = lc.card_seasons(data)
        assert [s['season'] for s in card['data']['seasons']] == ['winter', 'summer']
        assert lc.card_seasons(period(winter, genres={1: ['X']}))['status'] == 'below_minimum'

    def test_top_label_counts_a_listen_once_per_label(self):
        data = period(spread([1] * 12 + [2]), labels={1: [(9, 'Scantraxx'), (9, 'Scantraxx')], 2: [(8, 'Dirty')]})
        card = lc.card_top_label(data)['data']
        assert card['top'] == {'name': 'Scantraxx', 'tracks': 1, 'label_id': 9, 'listens': 12}
        assert card['runners_up'][0]['label_id'] == 8

    def test_top_label_needs_ten_listens(self):
        assert lc.card_top_label(period(spread([1] * 3), labels={1: [(9, 'L')]}))['status'] == 'below_minimum'

    def test_top_channel_reports_the_linked_label(self):
        chan = {'channel_id': 5, 'platform': 'soundcloud', 'name': 'Q-dance', 'label': 'Q-dance', 'artist': None}
        card = lc.card_top_channel(period(spread([1] * 10), channels={1: [chan]}))['data']
        assert card['top']['name'] == 'Q-dance' and card['top']['listens'] == 10

    def test_top_remixer_is_blocked_without_credits(self):
        card = lc.card_top_remixer(period(spread([1])))
        assert card == {
            'id': 'top_remixer',
            'status': 'blocked',
            'reason': 'no_remixer_credits',
            'basis': None,
            'data': None,
        }

    def test_top_remixer_counts_credits(self):
        data = period(spread([1] * 5), remixer_credits=True, remixers={1: ['Sub Zero Project']})
        assert lc.card_top_remixer(data)['data']['top']['remixer'] == 'Sub Zero Project'


def festivals():
    helper = FestivalHelper(preload=False)
    helper.set_festivals([Festival('Qlimax'), Festival('Defqon.1')])
    return helper


class FestivalsAndShowsTest:
    def test_festival_counts_sets_with_hours_and_editions(self):
        rows = [
            listen(
                T0, 1, form='liveset', title='Qlimax 2024 Warm Up', performance_date='2024-11-23', played_secs=3600.0
            ),
            listen(T0, 2, form='set', title='Qlimax 2019 Mix'),
            listen(T0, 3, form='track', title='Qlimax Anthem'),
        ]
        card = lc.card_festival(period(rows), festivals())['data']['top']
        assert card['festival'] == 'Qlimax'
        assert card['listens'] == 2
        assert card['editions'] == [2019, 2024]
        assert card['secs'] == 3800 and card['estimated'] is True

    def test_time_travel_names_the_oldest_and_newest_edition(self):
        rows = [
            listen(T0, 1, form='liveset', title='Defqon.1 2010', performance_date=None),
            listen(T0, 2, form='liveset', title='Qlimax 2024'),
        ]
        card = lc.card_time_travel(period(rows), festivals())['data']
        assert card['oldest'] == {'festival': 'Defqon.1', 'year': 2010}
        assert card['newest'] == {'festival': 'Qlimax', 'year': 2024}

    def test_time_travel_needs_two_editions(self):
        rows = [listen(T0, 1, form='liveset', title='Qlimax 2024')]
        assert lc.card_time_travel(period(rows), festivals())['status'] == 'below_minimum'

    def test_show_matches_approved_shows(self):
        shows = PodcastHelper(preload=False)
        shows.set_shows([Show('Hardstyle Sessions', ['Hardstyle Sessions'])])
        rows = spread([1, 2], form='podcast', title='Hardstyle Sessions #200')
        assert lc.card_show(period(rows), shows)['data']['top']['show'] == 'Hardstyle Sessions'

    def test_forms_add_up_to_the_linked_count(self):
        rows = spread([1] * 6, form='track') + spread([2] * 2, form='set') + spread([3], form='interview')
        rows += spread([4], form=None)
        card = lc.card_forms(period(rows))['data']
        assert sum(f['listens'] for f in card['forms']) == 10
        assert [f['form'] for f in card['forms']] == ['track', 'set', 'other', 'unknown']


class TempoTest:
    def test_bpm_averages_per_listen_and_per_month(self):
        rows = spread([1] * 10, start=datetime(2026, 1, 1)) + spread([2] * 10, start=datetime(2026, 2, 1))
        data = period(rows, bpm={1: (150.0, 'high'), 2: (170.0, 'medium')})
        card = lc.card_bpm(data)['data']
        assert card['average'] == 160.0
        assert card['months'] == [{'month': '2026-01', 'average': 150.0}, {'month': '2026-02', 'average': 170.0}]

    def test_bpm_needs_twenty_listens_with_a_tempo(self):
        assert lc.card_bpm(period(spread([1] * 5), bpm={1: (150.0, 'high')}))['status'] == 'below_minimum'

    def test_extremes_use_high_confidence_only(self):
        rows = spread([1] * 10 + [2] * 10 + [3])
        data = period(rows, bpm={1: (120.0, 'high'), 2: (200.0, 'high'), 3: (300.0, 'medium')})
        card = lc.card_bpm_extremes(data)['data']
        assert card['fastest']['bpm'] == 200.0 and card['slowest']['bpm'] == 120.0

    def test_taste_vs_shelf_gives_shares(self):
        data = period(spread([1] * 50), bpm={1: (151.0, 'high')})
        card = lc.card_taste_vs_shelf(data, {150: 1, 100: 3})['data']
        assert card['buckets'] == [
            {'bpm': 100, 'listens_share': 0.0, 'shelf_share': 0.75},
            {'bpm': 150, 'listens_share': 1.0, 'shelf_share': 0.25},
        ]


class TimeTest:
    def test_a_new_years_eve_listen_counts_in_the_readers_zone(self):
        at = datetime(2025, 12, 31, 23, 30)
        ams = scope(AMS)
        assert to_local(at, ams).year == 2026
        assert to_local(at, scope()).year == 2025

    def test_clock_heatmap_and_night_shift(self):
        rows = [listen(datetime(2026, 3, 2, 2, 0), 1)] * 10 + [listen(datetime(2026, 3, 3, 14, 0), 1)] * 50
        data = period(rows)
        assert lc.card_clock(data)['data']['hours'][2] == 10
        assert lc.card_heatmap(data)['data']['matrix'][0][2] == 10
        assert lc.card_night_shift(data)['data'] == {'listens': 10, 'share': 0.1667}

    def test_busiest_day_and_first_last(self):
        rows = [listen(datetime(2026, 3, 2, 10), 1), *[listen(datetime(2026, 3, 3, h), 2) for h in range(5)]]
        data = period(rows)
        assert lc.card_busiest_day(data)['data'] == {'date': '2026-03-03', 'listens': 5}
        first_last = lc.card_first_last(data)['data']
        assert first_last['first']['track_id'] == 1 and first_last['last']['track_id'] == 2

    def test_months_split_linked_and_unmatched(self):
        data = period([listen(datetime(2026, 1, 5), 1), listen(datetime(2026, 1, 6), None, title='x')])
        assert lc.card_months(data)['data']['months'] == [{'month': '2026-01', 'linked': 1, 'unmatched': 1}]

    def test_streak_across_a_daylight_saving_change_counts_the_day_once(self):
        ams = scope(AMS)
        # 29 March 2026 is the day the clocks go forward in Amsterdam.
        rows = [listen(datetime(2026, 3, d, 10), 1, s=ams) for d in (28, 29, 30)]
        rows.append(listen(datetime(2026, 3, 29, 0, 30), 1, s=ams))
        card = lc.card_streak(period(rows, s=ams))['data']
        assert card == {'days': 3, 'first': '2026-03-28', 'last': '2026-03-30'}

    def test_streak_needs_two_days(self):
        assert lc.card_streak(period([listen(T0, 1)]))['status'] == 'below_minimum'

    def test_session_joins_at_played_plus_fifteen_minutes_and_splits_a_second_later(self):
        gap = 100 + 15 * 60
        joined = [listen(T0, 1, played_secs=100.0), listen(T0 + timedelta(seconds=gap), 2, played_secs=100.0)]
        split = [listen(T0, 1, played_secs=100.0), listen(T0 + timedelta(seconds=gap + 1), 2, played_secs=100.0)]
        assert len(lc.sessions(joined)) == 1
        assert len(lc.sessions(split)) == 2

    def test_session_card_reports_the_longest(self):
        rows = [listen(T0 + timedelta(minutes=4 * i), 1) for i in range(4)]
        card = lc.card_session(period(rows))['data']
        assert card['listens'] == 4 and card['duration_secs'] == 12 * 60 + 200


class OriginsTest:
    def test_origin_mapping(self):
        assert [lc.origin_of(s) for s in ('frontend', 'mobile', 'auto', 'lms-web', 'listenbrainz_import')] == [
            'web',
            'phone',
            'car',
            'legacy_web',
            'imported',
        ]
        assert lc.origin_of('lms-history-import-lms') == 'imported'
        assert lc.origin_of(None) == lc.origin_of('lms') == 'unknown'

    def test_origins_report_car_hours(self):
        rows = spread([1] * 9, source='mobile') + [listen(T0, 1, source='auto', played_secs=600.0)]
        card = lc.card_origins(period(rows))
        assert card['data']['car_secs'] == 600
        assert card['basis']['counted'] == 10

    def test_release_years(self):
        rows = spread([1] * 5, release_year=1999) + spread([2] * 5, release_year=2024) + spread([3])
        card = lc.card_release_years(period(rows))['data']
        assert card['oldest']['year'] == 1999 and card['newest']['year'] == 2024
        assert card['decades'] == [{'decade': 1990, 'listens': 5}, {'decade': 2020, 'listens': 5}]
        assert card['unknown'] == 1


class ArrivalTest:
    def test_cards_are_blocked_without_any_arrival_date(self):
        data = period(spread([1, 2, 3]))
        for fn in (lc.card_fresh_vs_stock, lc.card_long_wait, lc.card_impulse):
            assert fn(data)['reason'] == 'no_arrival_date'

    def test_fresh_long_wait_and_impulse(self):
        rows = [
            listen(T0 + timedelta(days=i), i, arrived_at=T0 + timedelta(days=i) - timedelta(hours=i + 1))
            for i in range(1, 11)
        ]
        rows.append(listen(T0, 50, arrived_at=datetime(2024, 1, 1)))
        data = period(rows)
        assert lc.card_fresh_vs_stock(data)['data'] == {'fresh': 10, 'known': 11, 'share': 0.9091}
        assert lc.card_long_wait(data)['data']['track_id'] == 50
        assert lc.card_impulse(data)['data']['median_secs'] == 6.5 * 3600

    def test_untouched(self):
        card = lc.card_untouched(period(spread([1, 2])), 1000)['data']
        assert card['played'] == 2 and card['share'] == 0.002


class UserCardsTest:
    def test_new_genres_skip_genres_heard_before(self):
        data = period(spread([1, 2]), genres={1: ['Old'], 2: ['New']})
        card = lc.card_new_genres(data, UserHistory(prior_genres={'Old'}))['data']
        assert card['genres'] == [{'genre': 'New', 'listens': 1}]

    def test_discovery_is_a_new_artist_with_three_plays(self):
        data = period(spread([1, 1, 1, 2, 2, 2, 2]))
        card = lc.card_discovery(data, UserHistory(prior_artists={2}))['data']
        assert card['artist_id'] == 1 and card['listens'] == 3

    def test_loyal_is_left_out_when_it_is_the_top_artist(self):
        rows = [listen(datetime(2026, m, 1), 1) for m in (1, 2, 3)]
        card = lc.card_loyal(period(rows))
        assert card['status'] == 'below_minimum' and card['reason'] == 'same_as_top_artist'

    def test_loyal_differs_from_the_top_artist(self):
        rows = [listen(datetime(2026, m, 1), 1) for m in (1, 2, 3)] + spread([2] * 5)
        assert lc.card_loyal(period(rows))['data']['artist_id'] == 1

    def test_one_hit_needs_five_plays_on_one_day(self):
        rows = spread([1] * 5, step=timedelta(minutes=5)) + [listen(T0, 2), listen(T0 + timedelta(days=2), 2)]
        assert lc.card_one_hit(period(rows))['data'] == {
            'artist_id': 1,
            'artist': 'Artist 1',
            'date': '2026-03-02',
            'listens': 5,
        }

    def test_ratings_and_contradiction(self):
        ratings = [{'entity_id': f'uid{i}', 'rating': 5, 'updated_at': datetime(2026, 8, i)} for i in range(1, 5)]
        ratings.append({'entity_id': 'uid9', 'rating': 1, 'updated_at': datetime(2026, 8, 9)})
        history = UserHistory(ratings=ratings)
        data = period(spread([1, 1, 9, 9, 9]))
        card = lc.card_ratings(data, history)['data']
        assert card['given'] == 5
        assert card['stars'][4] == {'stars': 5, 'count': 4}
        assert card['five_star_play_share'] == 0.4
        assert card['rebuilt_before_period'] is True
        assert lc.card_contradiction(data, history)['data']['listens'] == 3

    def test_only_you_counts_and_never_names(self):
        data = period(spread([1, 1, 2, 3]))
        card = lc.card_only_you(data, UserHistory(others_tracks={2}))['data']
        assert card['track']['track_id'] == 1
        assert card['shared_tracks'] == 1 and card['only_you'] == 2
        assert 'username' not in str(card)


class WordsAndIdsTest:
    def test_word_of_the_year_skips_stop_words(self):
        rows = spread([1] * 20, title='The Anthem (Original Mix)')
        assert lc.card_word(period(rows))['data']['word'] == 'anthem'

    def test_unidentified(self):
        rows = [listen(T0, None, title='ID', artist='ID'), listen(T0, 2, title=' id ')]
        assert lc.card_unidentified(period(rows))['data'] == {'listens': 2, 'distinct': 2}

    def test_most_shared_counts_accounts(self):
        rows = [listen(T0, 1, username='a'), listen(T0, 1, username='b'), listen(T0, 2, username='a')]
        card = lc.card_most_shared(period(rows))['data']
        assert card['listeners'] == 2 and card['track_id'] == 1
