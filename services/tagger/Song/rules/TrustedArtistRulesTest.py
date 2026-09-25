"""The artist rules against the trusted-artist dictionary: a guess cannot approve itself.

Each test builds a real TrustedArtistHelper whose database answers with the *trusted*
names only -- the query itself is pinned against MariaDB in
tests/integration/test_artist_curation_wired.py. `library_artists` in these scenarios
also holds the pending name (the scanner recorded it from an earlier guess), and the
point is that no rule gets to see it.
"""

import unittest
from unittest.mock import MagicMock, patch

from services.common.Helpers.TrustedArtistHelper import TrustedArtistHelper
from services.tagger.constants import ARTIST, ORIGINAL_TITLE, REMIXER, TITLE
from services.tagger.Song.rules.CheckArtistRule import CheckArtistRule
from services.tagger.Song.rules.InferArtistFromTitleRule import InferArtistFromTitleRule
from services.tagger.Song.rules.InferRemixerFromTitleRule import InferRemixerFromTitleRule


def trusted_helper(names):
    """A TrustedArtistHelper whose trusted query returns `names`."""
    with patch('services.common.Helpers.TableHelper.DatabaseConnector') as connector_cls:
        cursor = MagicMock()
        cursor.fetchall.return_value = [(name, 0) for name in names]
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        connector_cls.return_value.connect.return_value = connection
        return TrustedArtistHelper()


def ignored(names=(), corrections=None):
    helper = MagicMock()
    corrections = corrections or {}
    helper.get_all.return_value = list(names) + list(corrections)
    helper.get_corrected.side_effect = lambda name: corrections.get(name, '')
    helper.exists.side_effect = lambda name: name in names or name in corrections
    return helper


class InferArtistOnlyTrustsApprovedNamesTest(unittest.TestCase):
    """The Premiere loop (bug of 9.188 tracks), closed for every new name, not one at a time."""

    def apply(self, title, trusted):
        song = MagicMock()
        song.path = lambda: '/music/Soundcloud/Kerbela/track.mp3'
        song.tag_collection.has_item.return_value = False
        song.tag_collection.get_item_as_string.side_effect = lambda key: {
            ARTIST: '',
            TITLE: title,
            ORIGINAL_TITLE: title,
        }[key]
        song.tag_collection.get_item = MagicMock(return_value=title)
        genres = MagicMock()
        genres.get_all.return_value = ['Hardstyle']
        rule = InferArtistFromTitleRule(artist_db=trusted_helper(trusted), genre_db=genres, ignored_db=ignored())
        rule.apply(song)
        return [c.args[1] for c in song.tag_collection.set_item.call_args_list if c.args[0] == ARTIST]

    def test_a_trusted_marker_would_win_the_title(self):
        """The control: while the marker is trusted it beats the real artist."""
        self.assertIn('Premiere', self.apply('PREMIERE ｜ TARS - Rumble', ['Premiere', 'TARS']))

    def test_a_pending_marker_does_not(self):
        """Same title, the marker only recorded by the scanner: the approved name wins."""
        written = self.apply('PREMIERE ｜ TARS - Rumble', ['TARS'])
        self.assertIn('TARS', written)
        self.assertNotIn('Premiere', written)


class InferRemixerOnlyTrustsApprovedNamesTest(unittest.TestCase):
    def test_only_a_trusted_remixer_is_credited(self):
        items = {ARTIST: MagicMock(), REMIXER: MagicMock()}
        for item in items.values():
            item.to_array.return_value = []
        song = MagicMock()
        song.tag_collection.get_item_as_string.return_value = 'Rumble (Angerfist Remix) (Tagger Guess Edit)'
        song.tag_collection.get_item.side_effect = items.__getitem__
        rule = InferRemixerFromTitleRule(artist_db=trusted_helper(['Angerfist']), ignored_db=ignored())
        rule.apply(song)
        credited = [c.args[0] for c in items[REMIXER].add.call_args_list]
        self.assertEqual(credited, ['Angerfist'])


class CheckArtistAppliesRejectionsTest(unittest.TestCase):
    """A rejected name is never trusted, so its correction finally reaches the file.

    Before, CheckArtistRule asked library_artists first -- and the scanner had inserted the
    rejected name there, so `exists` answered yes and the correction branch never ran.
    """

    def test_a_rejected_name_with_a_correction_is_rewritten(self):
        tag = MagicMock()
        song = MagicMock()
        song.library_artists.return_value = ['Angerfst']
        song.tag_collection.get_item.return_value = tag
        rule = CheckArtistRule(
            artist_db=trusted_helper(['Angerfist']), ignored_db=ignored(corrections={'Angerfst': 'Angerfist'})
        )
        rule.apply(song)
        tag.replace.assert_called_once_with('Angerfst', 'Angerfist')

    def test_a_pending_name_is_left_as_it_is(self):
        tag = MagicMock()
        song = MagicMock()
        song.library_artists.return_value = ['Tagger Guess']
        song.tag_collection.get_item.return_value = tag
        CheckArtistRule(artist_db=trusted_helper(['Angerfist']), ignored_db=ignored()).apply(song)
        tag.replace.assert_not_called()
        tag.remove.assert_not_called()


if __name__ == '__main__':
    unittest.main()
