"""One Wrapped tab, put together: the period, the cards in display order and the coverage card.

The card order in `cards` is the display order; the page does not sort. The Library tab names
no listener: its cards count accounts and show tracks, artists and labels only.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from services.music_manager.library_paths import relative_path
from services.music_manager.routers.listening import ListeningScope
from services.music_manager.wrapped import collection_cards as cc
from services.music_manager.wrapped import listening_cards as lc
from services.music_manager.wrapped.cards import OK
from services.music_manager.wrapped.data import (
    load_festival_helper,
    load_period,
    load_podcast_helper,
    load_user_history,
)
from services.music_manager.wrapped.periods import Period

USER = 'user'
LIBRARY = 'library'

#: The version of the payload's shape. A stored snapshot of another version is recomputed.
#: 2: every track also has `library_path`, the path the page hands LMS to play it.
WRAPPED_FORMAT = 2


def _period_block(period: Period, zone: ZoneInfo, now: datetime) -> dict[str, Any]:
    end = period.end_utc(zone).replace(tzinfo=UTC)
    until = min(now, end)
    return {
        'key': period.key,
        'from': period.date_from.isoformat(),
        'to': period.date_to.isoformat(),
        'year': period.year,
        'running': now < end,
        'data_until': until.isoformat(),
    }


def _share(part: int, whole: int) -> float | None:
    return round(part / whole, 4) if whole else None


def _coverage(data, cards: list[dict]) -> dict[str, Any]:
    listens = data.listens
    linked = data.linked
    return {
        'listens': len(listens),
        'linked': len(linked),
        'unmatched': data.unmatched,
        'measured_share': _share(sum(1 for x in listens if x.played_secs is not None), len(listens)),
        'origin_known_share': _share(sum(1 for x in listens if lc.origin_of(x.source) != 'unknown'), len(listens)),
        'bpm_share': _share(sum(1 for x in linked if x.track_id in data.bpm), len(linked)),
        'release_year_share': _share(sum(1 for x in linked if x.release_year), len(linked)),
        'arrival_share': _share(sum(1 for x in linked if x.arrived_at is not None), len(linked)),
        'left_out': [
            {'id': card['id'], 'status': card['status'], 'reason': card['reason']}
            for card in cards
            if card['status'] != OK
        ],
    }


def _track_ids(value, found: set[int]) -> None:
    if isinstance(value, dict):
        if isinstance(value.get('track_id'), int):
            found.add(value['track_id'])
        for item in value.values():
            _track_ids(item, found)
    elif isinstance(value, list):
        for item in value:
            _track_ids(item, found)


def _set_paths(value, paths: dict[int, str]) -> None:
    if isinstance(value, dict):
        if isinstance(value.get('track_id'), int):
            path = paths.get(value['track_id'])
            value['file_path'] = path
            value['library_path'] = relative_path(path)
        for item in value.values():
            _set_paths(item, paths)
    elif isinstance(value, list):
        for item in value:
            _set_paths(item, paths)


def attach_paths(cursor, cards: list[dict]) -> None:
    """Give every track on a card the path of one of its files, which the page turns into a song.

    `file_path` is muma's own scan mount and names a file LMS does not have; `library_path` is
    the same path without the library root, which is what the page hands LMS's getSongsByPath
    (as the feeds do, `library_paths.relative_path`).
    """
    found: set[int] = set()
    _track_ids(cards, found)
    if not found:
        return
    ids = sorted(found)
    marks = ', '.join(['%s'] * len(ids))
    cursor.execute(
        f'SELECT track_id, MIN(file_path) AS file_path FROM library_media_files '
        f'WHERE track_id IN ({marks}) GROUP BY track_id',
        tuple(ids),
    )
    paths = {row['track_id']: row['file_path'] for row in cursor.fetchall() or []}
    _set_paths(cards, paths)


def _shared_cards(data, festivals, shows, facts) -> dict[str, Callable[[], dict]]:
    """The listening cards both tabs can show, by id."""
    builders = {
        'title': lambda: lc.card_title(data),
        'listening_time': lambda: lc.card_listening_time(data),
        'listeners': lambda: lc.card_listeners(data),
        'top_tracks': lambda: lc.card_top_tracks(data),
        'top_artists': lambda: lc.card_top_artists(data),
        'top_genres': lambda: lc.card_top_genres(data),
        'seasons': lambda: lc.card_seasons(data),
        'top_label': lambda: lc.card_top_label(data),
        'top_channel': lambda: lc.card_top_channel(data),
        'top_remixer': lambda: lc.card_top_remixer(data),
        'festival': lambda: lc.card_festival(data, festivals),
        'time_travel': lambda: lc.card_time_travel(data, festivals),
        'show': lambda: lc.card_show(data, shows),
        'forms': lambda: lc.card_forms(data),
        'bpm': lambda: lc.card_bpm(data),
        'bpm_extremes': lambda: lc.card_bpm_extremes(data),
        'taste_vs_shelf': lambda: lc.card_taste_vs_shelf(data, facts.shelf),
        'clock': lambda: lc.card_clock(data),
        'heatmap': lambda: lc.card_heatmap(data),
        'night_shift': lambda: lc.card_night_shift(data),
        'busiest_day': lambda: lc.card_busiest_day(data),
        'first_last': lambda: lc.card_first_last(data),
        'months': lambda: lc.card_months(data),
        'streak': lambda: lc.card_streak(data),
        'session': lambda: lc.card_session(data),
        'origins': lambda: lc.card_origins(data),
        'release_years': lambda: lc.card_release_years(data),
        'fresh_vs_stock': lambda: lc.card_fresh_vs_stock(data),
        'long_wait': lambda: lc.card_long_wait(data),
        'impulse': lambda: lc.card_impulse(data),
        'untouched': lambda: lc.card_untouched(data, facts.music),
        'word': lambda: lc.card_word(data),
        'unidentified': lambda: lc.card_unidentified(data),
        'most_shared': lambda: lc.card_most_shared(data),
    }
    return builders


USER_ORDER = (
    'title',
    'listening_time',
    'top_tracks',
    'top_artists',
    'top_genres',
    'seasons',
    'top_label',
    'top_channel',
    'top_remixer',
    'festival',
    'time_travel',
    'show',
    'forms',
    'bpm',
    'bpm_extremes',
    'taste_vs_shelf',
    'clock',
    'night_shift',
    'busiest_day',
    'first_last',
    'months',
    'streak',
    'session',
    'origins',
    'release_years',
    'fresh_vs_stock',
    'long_wait',
    'impulse',
    'untouched',
    'new_genres',
    'discovery',
    'loyal',
    'one_hit',
    'ratings',
    'contradiction',
    'word',
    'unidentified',
    'only_you',
)

LIBRARY_ORDER = (
    'title',
    'listeners',
    'top_tracks',
    'top_artists',
    'top_genres',
    'top_label',
    'most_shared',
    'heatmap',
    'origins',
    'forms',
    'festival',
    'festival_editions',
    'releases_of_year',
    'downloads',
    'growth',
    'shelf',
    'start_now',
    'unplayed',
    'system',
)


def build_payload(cursor, kind: str, username: str | None, period: Period, zone: ZoneInfo, now: datetime) -> dict:
    """Compute one tab. `username` is the reader for the User tab and None for the Library tab."""
    scope = ListeningScope(username if kind == USER else None, period.date_from, period.date_to, zone)
    data = load_period(cursor, scope, library_scope=kind == LIBRARY)
    festivals = load_festival_helper(cursor)
    shows = load_podcast_helper(cursor)
    facts = cc.collection_facts(cursor, now.date())
    builders = _shared_cards(data, festivals, shows, facts)
    if kind == USER:
        history = load_user_history(cursor, scope)
        builders.update(
            {
                'new_genres': lambda: lc.card_new_genres(data, history),
                'discovery': lambda: lc.card_discovery(data, history),
                'loyal': lambda: lc.card_loyal(data),
                'one_hit': lambda: lc.card_one_hit(data),
                'ratings': lambda: lc.card_ratings(data, history),
                'contradiction': lambda: lc.card_contradiction(data, history),
                'only_you': lambda: lc.card_only_you(data, history),
            }
        )
        order: tuple[str, ...] = USER_ORDER
    else:
        builders.update(
            {
                'festival_editions': lambda: cc.card_festival_editions(cursor, data, festivals),
                'releases_of_year': lambda: cc.card_releases_of_year(cursor, data),
                'downloads': lambda: cc.card_downloads(cursor, data),
                'growth': lambda: cc.card_growth(cursor, data, facts),
                'shelf': lambda: cc.card_shelf(facts),
                'start_now': lambda: cc.card_start_now(facts, now),
                'unplayed': lambda: cc.card_unplayed(data, facts),
                'system': lambda: cc.card_system(cursor, data),
            }
        )
        order = LIBRARY_ORDER
    cards = [builders[card_id]() for card_id in order]
    attach_paths(cursor, cards)
    return {
        'scope': kind,
        'format': WRAPPED_FORMAT,
        'tz': str(zone.key),
        'period': _period_block(period, zone, now),
        'generated_at': now.isoformat(),
        'coverage': _coverage(data, cards),
        'cards': cards,
    }
