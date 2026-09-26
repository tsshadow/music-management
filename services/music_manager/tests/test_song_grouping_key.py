"""The grouping key after bug report 098: which spellings meet, and which must stay apart.

Kept apart from test_song_versions.py so the key's table can grow without touching the
ranking tests. Every row is a pair of (artist, title) that production spells differently;
the first table must share a key, the second must not.
"""

import pytest

from services.music_manager.song_versions import grouping_artist, version_free_title, work_key

SAME_SONG = [
    # dash suffixes, the Release Radar misses of 2026-09-26
    (('Dj Test', 'Lost On You'), ('Dj Test', 'Lost On You - Official Hardcore Visualizer')),
    (('Dj Test', 'Honor The Fight'), ('Dj Test', 'Honor The Fight - Official Hardstyle Visualizer')),
    (('Dj Test', 'Bailalo'), ('Dj Test', 'Báilalo - Official Video')),
    (('Dj Test', 'Hurricane'), ('Dj Test', 'Hurricane † - Official Preview [OUT NOW]')),
    (('Dj Test', 'Lekkah'), ('Dj Test', 'Lekkah - Official Preview  † [OUT NOW]')),
    (('Dj Test', 'Lost On You'), ('Dj Test', 'Lost On You | Official Visualizer')),
    (('Dj Test', 'Lost On You'), ('Dj Test', 'Lost On You – Radio Edit')),
    # words that were missing from the list
    (('Dj Test', 'Never'), ('Dj Test', 'Never (Official Music Video)')),
    (('Dj Test', 'Never'), ('Dj Test', 'Never (official Audio)')),
    (('Dj Test', 'Never'), ('Dj Test', 'Never (Official Video)')),
    (('Dj Test', 'Feel The Sun'), ('Dj Test', 'Feel The Sun (Pro Mix)')),
    (('Dj Test', 'Feel The Sun'), ('Dj Test', 'Feel The Sun (Pro Edit)')),
    (('Dj Test', 'Feel The Sun'), ('Dj Test', 'Feel The Sun (Visualizer)')),
    (('Dj Test', 'Feel The Sun'), ('Dj Test', 'Feel The Sun (Official Lyric Video)')),
    (('Dj Test', 'Feel The Sun'), ('Dj Test', 'Feel The Sun [Official Uptempo Visualizer]')),
    # decoration after the marker, and an unbracketed "official" tail
    (('Dj Test', 'Anaboa'), ('Dj Test', 'Anaboa (Official video) 🐆🐍🦅')),
    (('Dj Test', 'Shum (Billx remix)'), ('Dj Test', 'Shum (Billx remix) official video')),
    # stacked markers
    (('Dj Test', 'Lost On You'), ('Dj Test', 'Lost On You (Extended Mix) - Official Audio')),
    # first artist of a collaboration, on an exactly equal title
    (('Cheeva', 'Hardcore Hooligans'), ('CHEEVA & D-sire', 'Hardcore Hooligans')),
    (('Sickmode', 'Make You Freak'), ('Sickmode x Fraw', 'Make You Freak')),
    (('Marnage', 'Queen Of The Night'), ('Marnage, Nanoviola & Anna Timofei', 'Queen Of The Night')),
    (('Angerfist', 'Raise Your Fist'), ('Angerfist feat. MC Nolz', 'Raise Your Fist (Radio Edit)')),
    # a kind phrase in the artist field is no artist at all
    ((None, 'King Hiss'), ('Official Preview', 'King Hiss (Original Mix)')),
]

DIFFERENT_SONGS = [
    (('Dj Test', 'Lost On You'), ('Dj Test', 'Lost On You (Remix)')),
    (('Dj Test', 'Lost On You'), ('Dj Test', 'Lost On You - Wildstylez Remix')),
    (('Dj Test', 'Lost On You'), ('Dj Test', 'Lost On You (VIP)')),
    (('Dj Test', 'Lost On You'), ('Dj Test', 'Lost On You - VIP Mix')),
    (('Dj Test', 'Lost On You'), ('Dj Test', 'Lost On You (Bootleg)')),
    (('Dj Test', 'Lost On You'), ('Dj Test', 'Lost On You (Wildstylez Edit)')),
    (('Dj Test', 'Lost On You'), ('Dj Test', 'Lost On You (Hardcore Mix)')),
    (('Dj Test', 'Lost On You'), ('Dj Test', 'Lost On You (Hardstyle Edit)')),
    (('Dj Test', 'Lost On You'), ('Dj Test', 'Lost On You - Official Defqon.1 2013 Anthem')),
    (('Dj Test', 'Lost On You'), ('Dj Test', 'Lost On You (Official Hardcore Anthem)')),
    (('Dj Test', 'Speakers'), ('Dj Test', 'Speakers (Streiks & Kratchs Remix) † - Official Preview')),
    # different lead artists never meet, whatever the title
    (('Angerfist', 'Raise Your Fist'), ('Radical Redemption', 'Raise Your Fist')),
    (('Code:Red', 'Everyone Is Dead'), ('RED', 'Everyone Is Dead')),
    (('MANDY', 'Supersaw (Dj Furax Remix)'), ('Dj Furax', 'Supersaw (Dj Furax Remix)')),
    (('D-sire & Cheeva', 'Hardcore Hooligans'), ('Cheeva', 'Hardcore Hooligans')),
    # the collaboration rule needs the title to match
    (('Cheeva', 'Hardcore Hooligans'), ('CHEEVA & D-sire', 'Hardcore Hooligans 2')),
    # the dash rule never splits a hyphenated word, nor an artist-in-title
    (('Dj Test', 'Man'), ('Dj Test', 'Man-At-Arms (Original Mix)')),
    ((None, 'The Elite - Royals'), ((None, 'The Elite - Other Song'))),
]


def _key(pair, track_id):
    artist, title = pair
    return work_key(artist, title, track_id, 200.0)


@pytest.mark.parametrize(('left', 'right'), SAME_SONG, ids=[right[1] for _left, right in SAME_SONG])
def test_versions_of_one_song_share_a_key(left, right):
    assert _key(left, 1) == _key(right, 2)


@pytest.mark.parametrize(('left', 'right'), DIFFERENT_SONGS, ids=[right[1] for _left, right in DIFFERENT_SONGS])
def test_different_songs_keep_different_keys(left, right):
    assert _key(left, 1) != _key(right, 2)


def test_a_title_made_only_of_markers_is_not_stripped_to_nothing():
    # "Official Visualizer" as the whole title is what a misparse leaves behind; stripping
    # it would hand the track an empty title and so a key of its own, hiding the misparse.
    assert version_free_title('Official Visualizer') == 'official visualizer'
    assert version_free_title('Radio') == 'radio'


def test_a_dash_suffix_needs_every_word_known():
    assert version_free_title('Lost On You - Official Anthem') == 'lost on you official anthem'
    assert version_free_title('Lost On You - Official Video') == 'lost on you'


def test_genre_words_count_only_inside_an_official_upload_marker():
    assert version_free_title('X (Official Hardcore Video)') == 'x'
    assert version_free_title('X (Hardcore Video)') == 'x hardcore video'
    assert version_free_title('X (Official Hardcore)') == 'x official hardcore'


def test_grouping_artist():
    assert grouping_artist('CHEEVA & D-sire') == 'cheeva'
    assert grouping_artist('Malcolm X') == 'malcolm x'
    assert grouping_artist('Code:Red') == 'code red'
    assert grouping_artist('Official Preview') == ''
    assert grouping_artist('Official Hardcore Visualizer') == ''
    # a lone modifier word is still a name -- only an "official" phrase is a parse accident
    assert grouping_artist('Original') == 'original'
    assert grouping_artist(None) == ''
    assert grouping_artist('') == ''
