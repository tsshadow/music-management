"""When a remembered credit is written to the file, and when it is thrown away.

The pairing this covers: `InferArtistFromTitleRule` offers a credit early, and the rules
between it and this one can still change who is on the track. A credit that no longer
names them all is worse than none -- the web player prefers `display_artist` over the
artist list, so a stale credit hides an artist rather than merely failing to name one.
"""

import unittest
from unittest.mock import MagicMock

from services.tagger.constants import ORIGINAL_ARTIST
from services.tagger.Song.rules.CaptureDisplayArtistRule import CaptureDisplayArtistRule


class CaptureDisplayArtistRuleTest(unittest.TestCase):
    def song(self, candidate, artists, already_has=False):
        song = MagicMock()
        song.display_artist_candidate = candidate
        song.tag_collection.has_item.return_value = already_has
        song.tag_collection.get_item_as_array.return_value = list(artists)
        return song

    def written(self, song):
        CaptureDisplayArtistRule().apply(song)
        calls = [
            call.args[1]
            for call in song.tag_collection.set_item.call_args_list
            if call.args and call.args[0] == ORIGINAL_ARTIST
        ]
        return calls[0] if calls else None

    def test_a_credit_that_still_names_the_artists_is_written(self):
        song = self.song('Angerfist & Miss K8', ['Angerfist', 'Miss K8'])
        self.assertEqual('Angerfist & Miss K8', self.written(song))

    def test_a_featured_artist_added_afterwards_discards_the_credit(self):
        """`Angerfist & Miss K8 - Track (feat. Albino)`.

        InferFeatureFromTitleRule appends Albino to the artist tag after the credit was
        offered. Writing it anyway would leave the track showing two of its three
        artists; leaving it unwritten makes every consumer fall back to the full list.
        """
        song = self.song('Angerfist & Miss K8', ['Angerfist', 'Miss K8', 'Albino'])
        self.assertIsNone(self.written(song))

    def test_a_renamed_artist_does_not_lose_the_credit_to_reordering(self):
        """CheckArtistRule replaces a name by appending the canonical one and removing
        the old, so the tag comes back in a different order with the same people on it."""
        song = self.song('Miss K8 & Angerfist', ['Angerfist', 'Miss K8'])
        self.assertEqual('Miss K8 & Angerfist', self.written(song))

    def test_a_value_the_file_already_carries_is_left_alone(self):
        song = self.song('Angerfist & Miss K8', ['Angerfist', 'Miss K8'], already_has=True)
        self.assertIsNone(self.written(song))

    def test_a_song_that_was_offered_nothing_writes_nothing(self):
        self.assertIsNone(self.written(self.song(None, ['Angerfist'])))

    def test_an_artist_tag_emptied_by_a_later_rule_writes_nothing(self):
        """CheckArtistRule removes an artist that is on the ignore list without a
        correction, and can take the last one with it."""
        self.assertIsNone(self.written(self.song('Angerfist & Miss K8', [])))


if __name__ == '__main__':
    unittest.main()
