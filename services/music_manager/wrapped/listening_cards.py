"""The cards that count listens, for both tabs. Pure functions over a `PeriodData`.

Each function returns one card (see cards.py). The definitions and minimums are the tables in
docs/designs/wrapped-page/technical.md; a ranking breaks ties on name, then id, so two requests
give the same order. A card that counts linked listens only carries `unmatched` in its data,
the listens it could not count (decision 1).
"""

from __future__ import annotations

import re
import statistics
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from services.music_manager.wrapped.cards import (
    NO_ARRIVAL_DATE,
    NO_REMIXER_CREDITS,
    SAME_AS_TOP_ARTIST,
    basis,
    below,
    blocked,
    empty,
    gated,
    ok,
)
from services.music_manager.wrapped.data import Listen, PeriodData, UserHistory, utc_bounds
from services.music_manager.wrapped.words import title_words

TOP_N = 5
RUNNERS_UP = 4

# A session goes on while the next listen starts within the previous one's length plus this.
SESSION_GAP_SECS = 15 * 60

SEASONS = ('winter', 'spring', 'summer', 'autumn')
_SEASON_OF_MONTH = {12: 'winter', 1: 'winter', 2: 'winter', 3: 'spring', 4: 'spring', 5: 'spring'}
_SEASON_OF_MONTH.update({6: 'summer', 7: 'summer', 8: 'summer', 9: 'autumn', 10: 'autumn', 11: 'autumn'})

FESTIVAL_FORMS = ('set', 'liveset')
FORM_GROUPS = ('track', 'set', 'liveset', 'podcast')

# The ratings table was rebuilt on this day, so a rating's date before it is not when it was given.
RATINGS_REBUILT = date(2026, 7, 4)

_ID_TITLE = re.compile(r'^\s*id\s*$', re.IGNORECASE)


def _iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment is not None else None


def _ranked(counts: Counter, names: dict, limit: int) -> list:
    """The keys of `counts`, most first, ties by name, then key."""
    return sorted(counts, key=lambda key: (-counts[key], str(names.get(key) or ''), str(key)))[:limit]


def _linked_basis(data: PeriodData, counted: int | None = None) -> dict:
    linked = len(data.linked)
    return basis(linked if counted is None else counted, len(data.listens))


def _track_ref(listen: Listen) -> dict:
    return {'track_id': listen.track_id, 'title': listen.title, 'artist': listen.artist}


def _first_per_track(listens: list[Listen]) -> dict[int, Listen]:
    out: dict[int, Listen] = {}
    for listen in listens:
        if listen.track_id is not None and listen.track_id not in out:
            out[listen.track_id] = listen
    return out


# -- totals ------------------------------------------------------------------------------


def card_title(data: PeriodData) -> dict:
    """The headline: listens, linked and not, distinct tracks, estimated time."""
    linked = data.linked
    estimated = sum(listen.length or 0 for listen in data.listens)
    payload = {
        'listens': len(data.listens),
        'linked': len(linked),
        'unmatched': data.unmatched,
        'distinct_tracks': len({listen.track_id for listen in linked}),
        'estimated_secs': round(estimated),
    }
    if data.library_scope:
        payload['listeners'] = len({listen.username.lower() for listen in data.listens})
    return gated('title', len(data.listens), 1, lambda: payload)


def card_listening_time(data: PeriodData) -> dict:
    """Measured, imputed and estimated listening time, kept apart (as /api/listening/summary)."""
    measured = [listen for listen in data.listens if listen.played_secs is not None]
    measured_secs = sum(listen.played_secs or 0 for listen in measured)
    imputed_secs = sum(
        listen.duration_secs or 0
        for listen in data.listens
        if listen.linked and listen.played_secs is None and listen.duration_secs is not None
    )
    total = len(data.listens)
    return gated(
        'listening_time',
        total,
        1,
        lambda: {
            'measured_secs': round(measured_secs),
            'imputed_secs': round(imputed_secs),
            'estimated_secs': round(measured_secs + imputed_secs),
            'measured_share': round(len(measured) / total, 4),
        },
        basis(len(measured), total),
    )


def card_listeners(data: PeriodData) -> dict:
    """Accounts that listened, and how many of them are deleted (`deleted-<id>`, decision 10)."""
    names = {listen.username.lower() for listen in data.listens}
    former = sum(1 for name in names if name.startswith('deleted-'))
    return gated('listeners', len(names), 1, lambda: {'active': len(names) - former, 'former': former})


# -- rankings ----------------------------------------------------------------------------


def card_top_tracks(data: PeriodData) -> dict:
    """The five most played tracks."""
    linked = data.linked
    counts = Counter(listen.track_id for listen in linked)
    refs = _first_per_track(linked)
    names = {track_id: ref.title for track_id, ref in refs.items()}

    def build():
        items = [{**_track_ref(refs[t]), 'listens': counts[t]} for t in _ranked(counts, names, TOP_N)]
        return {'tracks': items, 'unmatched': data.unmatched}

    return gated('top_tracks', len(counts), 3, build, _linked_basis(data))


def card_top_artists(data: PeriodData) -> dict:
    """The five most played primary artists."""
    counts: Counter = Counter()
    names: dict = {}
    for listen in data.linked:
        if listen.artist_id is not None:
            counts[listen.artist_id] += 1
            names.setdefault(listen.artist_id, listen.artist)

    def build():
        items = [{'artist_id': a, 'artist': names[a], 'listens': counts[a]} for a in _ranked(counts, names, TOP_N)]
        return {'artists': items, 'unmatched': data.unmatched}

    return gated('top_artists', len(counts), 3, build, _linked_basis(data, sum(counts.values())))


def top_artist_id(data: PeriodData) -> int | None:
    """The id of the most played primary artist, ranked as on the top artists card, or None."""
    counts: Counter = Counter()
    names: dict = {}
    for listen in data.linked:
        if listen.artist_id is not None:
            counts[listen.artist_id] += 1
            names.setdefault(listen.artist_id, listen.artist)
    ranked = _ranked(counts, names, 1)
    return ranked[0] if ranked else None


def card_top_genres(data: PeriodData) -> dict:
    """The five most played genres. A listen counts once in each genre of its track, so they overlap."""
    counts: Counter = Counter()
    untagged = 0
    for listen in data.linked:
        genres = data.genres.get(listen.tid) or []
        if not genres:
            untagged += 1
        for genre in set(genres):
            counts[genre] += 1

    def build():
        items = [{'genre': g, 'listens': counts[g]} for g in _ranked(counts, {g: g for g in counts}, TOP_N)]
        return {'genres': items, 'untagged': untagged, 'unmatched': data.unmatched}

    tagged = len(data.linked) - untagged
    return gated('top_genres', len(counts), 3, build, _linked_basis(data, tagged))


def card_seasons(data: PeriodData) -> dict:
    """The leading genre of each season with at least 20 tagged listens."""
    per_season: dict[str, Counter] = defaultdict(Counter)
    tagged: Counter = Counter()
    for listen in data.linked:
        genres = set(data.genres.get(listen.tid) or [])
        if not genres:
            continue
        season = _SEASON_OF_MONTH[listen.local.month]
        tagged[season] += 1
        for genre in genres:
            per_season[season][genre] += 1
    seasons = []
    for season in SEASONS:
        if tagged[season] < 20:
            continue
        counts = per_season[season]
        genre = _ranked(counts, {g: g for g in counts}, 1)[0]
        seasons.append({'season': season, 'genre': genre, 'listens': counts[genre], 'tagged': tagged[season]})
    if not tagged:
        return empty('seasons')
    if len(seasons) < 2:
        return below('seasons', _linked_basis(data, sum(tagged.values())))
    return ok('seasons', {'seasons': seasons, 'unmatched': data.unmatched}, _linked_basis(data, sum(tagged.values())))


def _ranking_card(card_id: str, counts: Counter, info: dict, minimum: int, data: PeriodData, key: str) -> dict:
    """A "top one, four runners-up" card over `counts`, where `info[k]` describes key k."""
    if not counts:
        return empty(card_id)
    order = _ranked(counts, {k: info[k].get('name') for k in counts}, 1 + RUNNERS_UP)
    top = order[0]
    if counts[top] < minimum:
        return below(card_id, _linked_basis(data))
    items = [{**info[k], key: k, 'listens': counts[k]} for k in order]
    return ok(
        card_id,
        {'top': items[0], 'runners_up': items[1:], 'unmatched': data.unmatched},
        _linked_basis(data, sum(counts.values())),
    )


def card_top_label(data: PeriodData) -> dict:
    """The real label played most: label links plus the label of a linked channel."""
    counts: Counter = Counter()
    tracks: dict = defaultdict(set)
    info: dict = {}
    for listen in data.linked:
        for label_id, name in dict(data.labels.get(listen.tid) or []).items():
            counts[label_id] += 1
            tracks[label_id].add(listen.track_id)
            info[label_id] = {'name': name}
    for label_id, entry in info.items():
        entry['tracks'] = len(tracks[label_id])
    return _ranking_card('top_label', counts, info, 10, data, 'label_id')


def card_top_channel(data: PeriodData) -> dict:
    """The SoundCloud or YouTube channel whose uploads were played most."""
    counts: Counter = Counter()
    info: dict = {}
    for listen in data.linked:
        seen = set()
        for channel in data.channels.get(listen.tid) or []:
            if channel['channel_id'] in seen:
                continue
            seen.add(channel['channel_id'])
            counts[channel['channel_id']] += 1
            info[channel['channel_id']] = {k: v for k, v in channel.items() if k != 'channel_id'}
    return _ranking_card('top_channel', counts, info, 10, data, 'channel_id')


def card_top_remixer(data: PeriodData) -> dict:
    """The remixer credited on most plays. Blocked while no track carries a remixer credit (decision 12)."""
    if not data.remixer_credits:
        return blocked('top_remixer', NO_REMIXER_CREDITS)
    counts: Counter = Counter()
    for listen in data.linked:
        for name in set(data.remixers.get(listen.tid) or []):
            counts[name] += 1
    return _ranking_card('top_remixer', counts, {n: {'name': n} for n in counts}, 5, data, 'remixer')


# -- festivals and shows -----------------------------------------------------------------


def _festival_hits(data: PeriodData, festivals) -> list[tuple[Listen, str, int | None]]:
    """(listen, festival, edition year) for every set or live set whose title names a festival."""
    cache: dict = {}
    hits = []
    for listen in data.linked:
        if listen.form not in FESTIVAL_FORMS:
            continue
        if listen.track_id not in cache:
            cache[listen.track_id] = festivals.get_all(listen.title or '')
        for match in cache[listen.track_id]:
            year = None
            if listen.performance_date and listen.performance_date[:4].isdigit():
                year = int(listen.performance_date[:4])
            elif match.get('year'):
                year = int(match['year'])
            hits.append((listen, match['festival'], year))
    return hits


def card_festival(data: PeriodData, festivals) -> dict:
    """The festival whose sets were played most, with hours and the editions played."""
    hits = _festival_hits(data, festivals)
    counts: Counter = Counter()
    info: dict = {}
    for listen, festival, year in hits:
        counts[festival] += 1
        entry = info.setdefault(festival, {'name': festival, 'secs': 0.0, 'estimated': False, 'editions': set()})
        entry['secs'] += listen.length or 0
        entry['estimated'] = entry['estimated'] or listen.played_secs is None
        if year:
            entry['editions'].add(year)
    for entry in info.values():
        entry['secs'] = round(entry['secs'])
        entry['editions'] = sorted(entry['editions'])
    return _ranking_card('festival', counts, info, 2, data, 'festival')


def card_time_travel(data: PeriodData, festivals) -> dict:
    """The oldest and the newest festival edition played."""
    editions = {(year, festival) for _listen, festival, year in _festival_hits(data, festivals) if year}
    if not editions:
        return empty('time_travel')
    if len(editions) < 2:
        return below('time_travel', basis(len(editions), len(editions), 'editions'))
    oldest, newest = min(editions), max(editions)
    return ok(
        'time_travel',
        {
            'oldest': {'festival': oldest[1], 'year': oldest[0]},
            'newest': {'festival': newest[1], 'year': newest[0]},
            'editions': len(editions),
            'unmatched': data.unmatched,
        },
    )


def card_show(data: PeriodData, shows) -> dict:
    """The podcast or radio show played most, by the approved shows the form pass knows."""
    counts: Counter = Counter()
    info: dict = {}
    cache: dict = {}
    for listen in data.linked:
        if listen.form != 'podcast':
            continue
        if listen.track_id not in cache:
            match = shows.get(listen.title or '')
            cache[listen.track_id] = match['podcast'] if match else None
        name = cache[listen.track_id]
        if not name:
            continue
        counts[name] += 1
        entry = info.setdefault(name, {'name': name, 'secs': 0.0})
        entry['secs'] += listen.length or 0
    for entry in info.values():
        entry['secs'] = round(entry['secs'])
    return _ranking_card('show', counts, info, 2, data, 'show')


def card_forms(data: PeriodData) -> dict:
    """How plays and time split between tracks, sets, live sets, podcasts and the rest."""
    groups: dict[str, dict] = {}
    for listen in data.linked:
        form = listen.form if listen.form in FORM_GROUPS else ('unknown' if listen.form is None else 'other')
        entry = groups.setdefault(form, {'form': form, 'listens': 0, 'measured_secs': 0.0, 'estimated_secs': 0.0})
        entry['listens'] += 1
        entry['measured_secs'] += listen.played_secs or 0
        entry['estimated_secs'] += listen.length or 0
    order = [*FORM_GROUPS, 'other', 'unknown']
    items = [groups[f] for f in order if f in groups]
    for entry in items:
        entry['measured_secs'] = round(entry['measured_secs'])
        entry['estimated_secs'] = round(entry['estimated_secs'])
    return gated(
        'forms', len(data.linked), 10, lambda: {'forms': items, 'unmatched': data.unmatched}, _linked_basis(data)
    )


# -- tempo -------------------------------------------------------------------------------


def _with_bpm(data: PeriodData, confidence: str | None = None) -> list[tuple[Listen, float]]:
    out = []
    for listen in data.linked:
        value = data.bpm.get(listen.tid)
        if value and (confidence is None or value[1] == confidence):
            out.append((listen, value[0]))
    return out


def card_bpm(data: PeriodData) -> dict:
    """The average tempo per listen, and per month."""
    rows = _with_bpm(data)
    months: dict[str, list[float]] = defaultdict(list)
    for listen, bpm in rows:
        months[listen.local.strftime('%Y-%m')].append(bpm)

    def build():
        return {
            'average': round(statistics.fmean(bpm for _l, bpm in rows), 1),
            'months': [{'month': m, 'average': round(statistics.fmean(v), 1)} for m, v in sorted(months.items())],
            'unmatched': data.unmatched,
        }

    return gated('bpm', len(rows), 20, build, _linked_basis(data, len(rows)))


def card_bpm_extremes(data: PeriodData) -> dict:
    """The fastest and the slowest track played, on high-confidence tempos only."""
    rows = _with_bpm(data, 'high')

    def build():
        by_track = {listen.track_id: (listen, bpm) for listen, bpm in rows}
        ordered = sorted(by_track.values(), key=lambda pair: (pair[1], pair[0].title or '', pair[0].track_id))
        slowest, fastest = ordered[0], ordered[-1]
        return {
            'fastest': {**_track_ref(fastest[0]), 'bpm': fastest[1]},
            'slowest': {**_track_ref(slowest[0]), 'bpm': slowest[1]},
            'unmatched': data.unmatched,
        }

    return gated('bpm_extremes', len(rows), 20, build, _linked_basis(data, len(rows)))


def bpm_bucket(bpm: float) -> int:
    """The 5-BPM bucket a tempo falls in: 147.3 is 145."""
    return int(bpm // 5) * 5


def card_taste_vs_shelf(data: PeriodData, shelf: dict[int, int]) -> dict:
    """The tempo of the listening next to the tempo of the whole collection, both as shares."""
    rows = _with_bpm(data)
    played = Counter(bpm_bucket(bpm) for _l, bpm in rows)
    shelf_total = sum(shelf.values())

    def build():
        buckets = sorted(set(played) | set(shelf))
        return {
            'buckets': [
                {
                    'bpm': b,
                    'listens_share': round(played[b] / len(rows), 4),
                    'shelf_share': round(shelf.get(b, 0) / shelf_total, 4) if shelf_total else 0,
                }
                for b in buckets
            ],
            'unmatched': data.unmatched,
        }

    return gated('taste_vs_shelf', len(rows), 50, build, _linked_basis(data, len(rows)))


# -- time --------------------------------------------------------------------------------


def card_clock(data: PeriodData) -> dict:
    """Listens per local hour and per weekday (Monday first)."""
    hours = [0] * 24
    weekdays = [0] * 7
    for listen in data.listens:
        hours[listen.local.hour] += 1
        weekdays[listen.local.weekday()] += 1
    return gated('clock', len(data.listens), 20, lambda: {'hours': hours, 'weekdays': weekdays})


def card_heatmap(data: PeriodData) -> dict:
    """A weekday by hour matrix of all listening (Monday first)."""
    matrix = [[0] * 24 for _ in range(7)]
    for listen in data.listens:
        matrix[listen.local.weekday()][listen.local.hour] += 1
    return gated('heatmap', len(data.listens), 50, lambda: {'matrix': matrix})


def card_night_shift(data: PeriodData) -> dict:
    """The share of listens between 00:00 and 04:59 local time."""
    night = sum(1 for listen in data.listens if listen.local.hour < 5)
    total = len(data.listens)
    return gated('night_shift', total, 20, lambda: {'listens': night, 'share': round(night / total, 4)})


def card_busiest_day(data: PeriodData) -> dict:
    """The local date with the most listens; the earlier date wins a tie."""
    days = Counter(listen.local.date() for listen in data.listens)

    def build():
        day = min(days, key=lambda d: (-days[d], d))
        return {'date': day.isoformat(), 'listens': days[day]}

    return gated('busiest_day', len(data.listens), 5, build)


def _listen_ref(listen: Listen) -> dict:
    return {'at': _iso(listen.local), 'linked': listen.linked, **_track_ref(listen)}


def card_first_last(data: PeriodData) -> dict:
    """The first and the last listen of the period, linked or not."""
    return gated(
        'first_last',
        len(data.listens),
        1,
        lambda: {'first': _listen_ref(data.listens[0]), 'last': _listen_ref(data.listens[-1])},
    )


def card_months(data: PeriodData) -> dict:
    """Listens per local month, linked and not."""
    months: dict[str, dict] = {}
    for listen in data.listens:
        key = listen.local.strftime('%Y-%m')
        entry = months.setdefault(key, {'month': key, 'linked': 0, 'unmatched': 0})
        entry['linked' if listen.linked else 'unmatched'] += 1
    return gated('months', len(data.listens), 1, lambda: {'months': [months[k] for k in sorted(months)]})


def longest_streak(days: set[date]) -> tuple[int, date | None, date | None]:
    """The longest run of consecutive dates: (length, first, last)."""
    best: tuple[int, date | None, date | None] = (0, None, None)
    for day in sorted(days):
        if day - timedelta(days=1) in days:
            continue
        end = day
        while end + timedelta(days=1) in days:
            end += timedelta(days=1)
        length = (end - day).days + 1
        if length > best[0]:
            best = (length, day, end)
    return best


def card_streak(data: PeriodData) -> dict:
    """The most local days in a row with at least one listen."""
    length, first, last = longest_streak({listen.local.date() for listen in data.listens})
    if not data.listens:
        return empty('streak')
    if length < 2 or first is None or last is None:
        return below('streak')
    return ok('streak', {'days': length, 'first': first.isoformat(), 'last': last.isoformat()})


def sessions(listens: list[Listen]) -> list[list[Listen]]:
    """Listens in time order, cut where the gap passes the previous length plus 15 minutes."""
    out: list[list[Listen]] = []
    for listen in listens:
        if out:
            prev = out[-1][-1]
            gap = (listen.at - prev.at).total_seconds()
            if gap <= (prev.length or 0) + SESSION_GAP_SECS:
                out[-1].append(listen)
                continue
        out.append([listen])
    return out


def _session_secs(session: list[Listen]) -> float:
    return (session[-1].at - session[0].at).total_seconds() + (session[-1].length or 0)


def card_session(data: PeriodData) -> dict:
    """The longest unbroken listening session."""
    if not data.listens:
        return empty('session')
    longest = max(sessions(data.listens), key=lambda s: (_session_secs(s), len(s)))
    if len(longest) < 3:
        return below('session')
    return ok(
        'session',
        {
            'start': _iso(longest[0].local),
            'end': _iso(longest[-1].local),
            'listens': len(longest),
            'duration_secs': round(_session_secs(longest)),
        },
    )


def origin_of(source: str | None) -> str:
    """Where a listen came from, by its `source`: web, phone, car, legacy web, imported, unknown."""
    value = (source or '').lower()
    if value == 'frontend':
        return 'web'
    if value == 'mobile':
        return 'phone'
    if value == 'auto':
        return 'car'
    if value == 'lms-web':
        return 'legacy_web'
    if value.startswith(('listenbrainz', 'lms-history-import')):
        return 'imported'
    return 'unknown'


def card_origins(data: PeriodData) -> dict:
    """Listens and measured time per origin, and the measured hours in the car."""
    groups: dict[str, dict] = {}
    for listen in data.listens:
        origin = origin_of(listen.source)
        entry = groups.setdefault(origin, {'origin': origin, 'listens': 0, 'measured_secs': 0.0})
        entry['listens'] += 1
        entry['measured_secs'] += listen.played_secs or 0
    items = sorted(groups.values(), key=lambda e: (-e['listens'], e['origin']))
    for entry in items:
        entry['measured_secs'] = round(entry['measured_secs'])
    car = groups.get('car', {}).get('measured_secs', 0)
    known = sum(e['listens'] for e in items if e['origin'] != 'unknown')
    return gated(
        'origins',
        len(data.listens),
        10,
        lambda: {'origins': items, 'car_secs': car},
        basis(known, len(data.listens)),
    )


def card_release_years(data: PeriodData) -> dict:
    """The oldest and newest release played, and plays per decade."""
    rows = [listen for listen in data.linked if listen.release_year]
    unknown = len(data.linked) - len(rows)

    def build():
        oldest = min(rows, key=lambda r: (r.release_year, r.title or '', r.track_id))
        newest = max(rows, key=lambda r: (r.release_year, r.title or '', -(r.track_id or 0)))
        decades = Counter(listen.release_year // 10 * 10 for listen in rows)
        return {
            'oldest': {**_track_ref(oldest), 'year': oldest.release_year},
            'newest': {**_track_ref(newest), 'year': newest.release_year},
            'decades': [{'decade': d, 'listens': decades[d]} for d in sorted(decades)],
            'unknown': unknown,
            'unmatched': data.unmatched,
        }

    return gated('release_years', len(rows), 10, build, _linked_basis(data, len(rows)))


# -- arrival (decision 3) ----------------------------------------------------------------


def _arrivals(data: PeriodData) -> list[Listen]:
    return [listen for listen in data.linked if listen.arrived_at is not None]


def card_fresh_vs_stock(data: PeriodData) -> dict:
    """The share of plays, of tracks with a known arrival, that arrived in the period."""
    known = _arrivals(data)
    if not known:
        return blocked('fresh_vs_stock', NO_ARRIVAL_DATE)
    start, end = utc_bounds(data.scope)
    fresh = sum(1 for listen in known if listen.arrived_at is not None and start <= listen.arrived_at < end)
    return gated(
        'fresh_vs_stock',
        len(known),
        10,
        lambda: {'fresh': fresh, 'known': len(known), 'share': round(fresh / len(known), 4)},
        _linked_basis(data, len(known)),
    )


def _waits(data: PeriodData) -> list[tuple[Listen, float]]:
    """(first play in the period, seconds since arrival) per track with a known arrival before it."""
    out = []
    for listen in _first_per_track(_arrivals(data)).values():
        if listen.arrived_at is None:
            continue
        wait = (listen.at - listen.arrived_at).total_seconds()
        if wait >= 0:
            out.append((listen, wait))
    return out


def card_long_wait(data: PeriodData) -> dict:
    """The track that waited longest between arriving and its first play in the period."""
    if not _arrivals(data):
        return blocked('long_wait', NO_ARRIVAL_DATE)
    waits = _waits(data)

    def build():
        listen, wait = max(waits, key=lambda pair: (pair[1], -(pair[0].track_id or 0)))
        return {
            **_track_ref(listen),
            'arrived_at': _iso(listen.arrived_at),
            'first_play': _iso(listen.local),
            'wait_secs': round(wait),
        }

    return gated('long_wait', len(waits), 10, build, basis(len(waits), len(waits), 'tracks'))


def card_impulse(data: PeriodData) -> dict:
    """The median time from arrival to first play, over tracks that arrived in the period."""
    if not _arrivals(data):
        return blocked('impulse', NO_ARRIVAL_DATE)
    start, end = utc_bounds(data.scope)
    waits = [
        wait for listen, wait in _waits(data) if listen.arrived_at is not None and start <= listen.arrived_at < end
    ]
    return gated(
        'impulse',
        len(waits),
        10,
        lambda: {'median_secs': round(statistics.median(waits)), 'tracks': len(waits)},
        basis(len(waits), len(waits), 'tracks'),
    )


def card_untouched(data: PeriodData, library_size: int) -> dict:
    """How many of the library's tracks were played, and the share that was not."""
    played = len({listen.track_id for listen in data.linked})
    return gated(
        'untouched',
        played,
        1,
        lambda: {
            'played': played,
            'library': library_size,
            'share': round(played / library_size, 6) if library_size else None,
            'unmatched': data.unmatched,
        },
        _linked_basis(data),
    )


# -- User tab only -----------------------------------------------------------------------


def card_new_genres(data: PeriodData, history: UserHistory) -> dict:
    """Genres played for the first time ever."""
    counts: Counter = Counter()
    for listen in data.linked:
        for genre in set(data.genres.get(listen.tid) or []):
            if genre not in history.prior_genres:
                counts[genre] += 1

    def build():
        order = _ranked(counts, {g: g for g in counts}, 10)
        return {'genres': [{'genre': g, 'listens': counts[g]} for g in order], 'count': len(counts)}

    return gated('new_genres', len(counts), 1, build, _linked_basis(data))


def card_discovery(data: PeriodData, history: UserHistory) -> dict:
    """The artist first heard in the period with the most plays in it."""
    counts: Counter = Counter()
    first: dict = {}
    names: dict = {}
    for listen in data.linked:
        if listen.artist_id is None or listen.artist_id in history.prior_artists:
            continue
        counts[listen.artist_id] += 1
        first.setdefault(listen.artist_id, listen)
        names[listen.artist_id] = listen.artist
    if not counts:
        return empty('discovery')
    top = _ranked(counts, names, 1)[0]
    if counts[top] < 3:
        return below('discovery', _linked_basis(data))
    return ok(
        'discovery',
        {
            'artist_id': top,
            'artist': names[top],
            'listens': counts[top],
            'first_listen': _iso(first[top].local),
            'unmatched': data.unmatched,
        },
        _linked_basis(data),
    )


def card_loyal(data: PeriodData) -> dict:
    """The artist played in the most different months; left out when it is the top artist."""
    months: dict = defaultdict(set)
    counts: Counter = Counter()
    names: dict = {}
    for listen in data.linked:
        if listen.artist_id is None:
            continue
        months[listen.artist_id].add(listen.local.strftime('%Y-%m'))
        counts[listen.artist_id] += 1
        names[listen.artist_id] = listen.artist
    if not months:
        return empty('loyal')
    top = min(months, key=lambda a: (-len(months[a]), -counts[a], str(names[a] or ''), a))
    if len(months[top]) < 3:
        return below('loyal', _linked_basis(data))
    if top == top_artist_id(data):
        return below('loyal', _linked_basis(data), SAME_AS_TOP_ARTIST)
    return ok(
        'loyal',
        {'artist_id': top, 'artist': names[top], 'months': len(months[top]), 'listens': counts[top]},
        _linked_basis(data),
    )


def card_one_hit(data: PeriodData) -> dict:
    """An artist whose plays all fall on one local day, at least five of them."""
    days: dict = defaultdict(set)
    counts: Counter = Counter()
    names: dict = {}
    for listen in data.linked:
        if listen.artist_id is None:
            continue
        days[listen.artist_id].add(listen.local.date())
        counts[listen.artist_id] += 1
        names[listen.artist_id] = listen.artist
    single = Counter({a: counts[a] for a in counts if len(days[a]) == 1})
    if not single:
        return empty('one_hit')
    top = _ranked(single, names, 1)[0]
    if single[top] < 5:
        return below('one_hit', _linked_basis(data))
    day = next(iter(days[top]))
    return ok(
        'one_hit',
        {'artist_id': top, 'artist': names[top], 'date': day.isoformat(), 'listens': single[top]},
        _linked_basis(data),
    )


def card_ratings(data: PeriodData, history: UserHistory) -> dict:
    """Ratings given in the period, per star, and the share of plays that were five-star tracks."""
    start, end = utc_bounds(data.scope)
    given = [r for r in history.ratings if r.get('updated_at') and start <= r['updated_at'] < end]
    stars = Counter(int(r['rating']) for r in given)
    five = {r['entity_id'] for r in history.ratings if int(r['rating']) == 5}
    linked = data.linked
    five_plays = sum(1 for listen in linked if listen.track_uid in five)

    def build():
        return {
            'given': len(given),
            'stars': [{'stars': s, 'count': stars.get(s, 0)} for s in range(1, 6)],
            'five_star_play_share': round(five_plays / len(linked), 4) if linked else None,
            'rebuilt_before_period': data.date_from < RATINGS_REBUILT,
        }

    return gated('ratings', len(given), 5, build, basis(len(given), len(given), 'ratings'))


def card_contradiction(data: PeriodData, history: UserHistory) -> dict:
    """A track rated one or two stars and still played often."""
    low = {r['entity_id']: int(r['rating']) for r in history.ratings if int(r['rating']) <= 2}
    counts: Counter = Counter()
    refs: dict = {}
    for listen in data.linked:
        if listen.track_uid in low:
            counts[listen.track_id] += 1
            refs.setdefault(listen.track_id, listen)
    if not counts:
        return empty('contradiction')
    top = _ranked(counts, {t: ref.title for t, ref in refs.items()}, 1)[0]
    if counts[top] < 3:
        return below('contradiction', _linked_basis(data))
    listen = refs[top]
    return ok(
        'contradiction',
        {**_track_ref(listen), 'rating': low[listen.track_uid], 'listens': counts[top]},
        _linked_basis(data),
    )


def card_only_you(data: PeriodData, history: UserHistory) -> dict:
    """The most played track nobody else played, and how many of your tracks others also played.

    Counts only: the card never names another listener (decision 7).
    """
    linked = data.linked
    counts = Counter(listen.tid for listen in linked)
    refs = _first_per_track(linked)
    if not counts:
        return empty('only_you')
    if len(counts) < 3:
        return below('only_you', _linked_basis(data))
    shared = sum(1 for track_id in counts if track_id in history.others_tracks)
    alone = Counter({t: n for t, n in counts.items() if t not in history.others_tracks})
    track = None
    if alone:
        top = _ranked(alone, {t: refs[t].title for t in alone}, 1)[0]
        track = {**_track_ref(refs[top]), 'listens': alone[top]}
    return ok(
        'only_you',
        {'track': track, 'only_you': len(alone), 'shared_tracks': shared, 'tracks': len(counts)},
        _linked_basis(data),
    )


# -- words and IDs -----------------------------------------------------------------------


def card_word(data: PeriodData) -> dict:
    """The most frequent word in the titles played, counted per listen."""
    counts: Counter = Counter()
    titled = 0
    for listen in data.listens:
        words = set(title_words(listen.title))
        if listen.title:
            titled += 1
        for word in words:
            counts[word] += 1

    def build():
        order = _ranked(counts, {w: w for w in counts}, 1 + RUNNERS_UP)
        return {
            'word': order[0],
            'count': counts[order[0]],
            'runners_up': [{'word': w, 'count': counts[w]} for w in order[1:]],
        }

    if not counts:
        return empty('word')
    return gated('word', titled, 20, build, basis(titled, len(data.listens)))


def is_unidentified(listen: Listen) -> bool:
    """An "ID - ID" track: a title that is only "ID"."""
    return bool(_ID_TITLE.match(listen.title or ''))


def card_unidentified(data: PeriodData) -> dict:
    """Plays of unreleased "ID" tracks."""
    rows = [listen for listen in data.listens if is_unidentified(listen)]
    distinct = {(listen.track_id, (listen.artist or '').lower()) for listen in rows}
    return gated('unidentified', len(rows), 1, lambda: {'listens': len(rows), 'distinct': len(distinct)})


# -- Library tab only --------------------------------------------------------------------


def card_most_shared(data: PeriodData) -> dict:
    """The track played by the most different accounts. Counts accounts, never names one."""
    listeners: dict = defaultdict(set)
    for listen in data.linked:
        listeners[listen.track_id].add(listen.username.lower())
    if not listeners:
        return empty('most_shared')
    refs = _first_per_track(data.linked)
    counts = Counter({t: len(names) for t, names in listeners.items()})
    top = _ranked(counts, {t: ref.title for t, ref in refs.items()}, 1)[0]
    if counts[top] < 2:
        return below('most_shared', _linked_basis(data))
    return ok('most_shared', {**_track_ref(refs[top]), 'listeners': counts[top]}, _linked_basis(data))
