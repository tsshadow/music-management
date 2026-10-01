"""False merges: one work holding a whole series of different songs (bug report 098).

The fixture mirrors production's `q dance:::next` (a misparsed upload series, every file
its own length) and two genuine works: a song with a radio and an extended cut, and a
song collected many times in a handful of lengths.
"""

from services.music_manager import song_work_audit as audit

# 20 different songs, 117 to 241 seconds apart -- production's work 290529 in miniature.
SERIES = [
    {
        'work_id': 1,
        'work_key': 'q dance:::next',
        'duration_secs': 117 + 6.5 * index,
        'release_date': f'{2020 + index % 6}-01-01',
    }
    for index in range(20)
]
# One song, two cuts: radio 205 s, extended 330 s -- a ratio above 1.5 that must not trip.
RADIO_AND_EXTENDED = [
    {'work_id': 2, 'work_key': 'mandy:::stay in love', 'duration_secs': 205.0, 'release_date': '2023-05-01'},
    {'work_id': 2, 'work_key': 'mandy:::stay in love', 'duration_secs': 205.4, 'release_date': '2023-05-01'},
    {'work_id': 2, 'work_key': 'mandy:::stay in love', 'duration_secs': 330.0, 'release_date': '2023-05-01'},
]
# A classic ripped fourteen times: many files, few lengths.
POPULAR = [
    {'work_id': 3, 'work_key': 'art of fighters:::fuck you', 'duration_secs': length, 'release_date': '2004-01-01'}
    for length in (201, 201, 202, 240, 240, 241, 199, 200, 300, 301, 300, 240, 202, 201)
]


def test_distinct_lengths_chain_neighbours():
    assert audit.distinct_lengths([184, 185, 186, 240, 241]) == 2
    assert audit.distinct_lengths([100, 110, 120]) == 3
    assert audit.distinct_lengths([None, 0, -1]) == 0


def test_a_series_of_different_songs_is_split():
    verdict = audit.assess_work(SERIES)
    assert verdict['verdict'] == 'split'
    assert verdict['lengths'] == 20


def test_a_radio_and_extended_pair_is_not_flagged():
    assert audit.assess_work(RADIO_AND_EXTENDED) is None


def test_a_popular_song_with_few_lengths_is_only_flagged_for_its_size():
    # More than MANY_MEMBERS members is always worth a look (bug report 142), never a split.
    verdict = audit.assess_work(POPULAR)
    assert verdict['verdict'] == 'suspicious'
    assert verdict['reasons'] == ['14 members']


def test_ten_members_is_not_flagged_eleven_is():
    members = [{'duration_secs': 200, 'release_date': None} for _ in range(10)]
    assert audit.assess_work(members) is None
    members.append({'duration_secs': 200, 'release_date': None})
    assert audit.assess_work(members)['reasons'] == ['11 members']


def test_a_wide_spread_below_the_split_is_only_suspicious():
    members = [{'duration_secs': length, 'release_date': None} for length in (100, 150, 200, 250)]
    verdict = audit.assess_work(members)
    assert verdict['verdict'] == 'suspicious'
    assert 'longest is 2.5x the shortest' in verdict['reasons']


def test_many_versions_over_many_years_are_suspicious():
    members = [{'duration_secs': 200 + (index % 2), 'release_date': f'{2010 + index}-01-01'} for index in range(13)]
    verdict = audit.assess_work(members)
    assert verdict['verdict'] == 'suspicious'
    assert verdict['reasons'] == ['13 versions from 13 different years', '13 members']


def test_exactly_twelve_lengths_is_not_enough_to_split():
    members = [{'duration_secs': 100 + 10 * index, 'release_date': None} for index in range(12)]
    assert audit.assess_work(members)['verdict'] == 'suspicious'
    members.append({'duration_secs': 400, 'release_date': None})
    assert audit.assess_work(members)['verdict'] == 'split'


def test_the_report_lists_the_false_merge_and_the_large_work_worst_first():
    found = audit.suspicious_works(RADIO_AND_EXTENDED + POPULAR + SERIES)
    assert [(work['work_id'], work['work_key'], work['verdict']) for work in found] == [
        (1, 'q dance:::next', 'split'),
        (3, 'art of fighters:::fuck you', 'suspicious'),
    ]
