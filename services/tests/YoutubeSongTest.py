import unittest

import pytest

from services.tests.mock_base import reset_database_helpers

pytestmark = pytest.mark.mock_base('mutagen', 'Cache')

from services.tagger.constants import ARTIST, ORIGINAL_ARTIST, PUBLISHER, TITLE
from services.tagger.Song.YoutubeSong import YoutubeSong

# What a YouTube download looks like by the time the tagger sees it: yt-dlp's
# FFmpegMetadataPP has already written the tags, and its artist falls back to the
# channel name because the YouTube extractor rarely supplies a real one.
CHANNEL = 'Masters of Hardcore'
RAW_TITLE = 'Deadly Guns & The Dark Horror - In The Pit (Official Videoclip)'


class YoutubeSongTest(unittest.TestCase):
    def setUp(self):
        reset_database_helpers()
        from services.common.Helpers.Cache import databaseHelpers

        self.mock_artists = ['Deadly Guns', 'The Dark Horror', 'Angerfist', 'Miss K8']
        databaseHelpers['library_artists'].get_all_values.return_value = self.mock_artists
        databaseHelpers['library_artists'].exists.side_effect = lambda x: x in self.mock_artists

    @staticmethod
    def _downloaded(channel=CHANNEL, title=RAW_TITLE, artist=None):
        """A song as it lands on disk, tagged by yt-dlp and nothing else."""
        song = YoutubeSong(f'/tmp/youtube/{channel}/track.m4a', {'uploader': channel})
        song.tag_collection.set_item(TITLE, title)
        song.tag_collection.set_item(ARTIST, artist or channel)
        return song

    def test_album_set_to_youtube_channel(self):
        song = self._downloaded(channel='Q-dance')
        song.parse()
        self.assertEqual(song.album(), 'Youtube (Q-dance)')
        self.assertEqual(song.tag_collection.get_item_as_string(PUBLISHER), 'Youtube')

    def test_label_channel_splits_artists_out_of_title(self):
        """The channel is a label, so the artists only exist in the title."""
        song = self._downloaded()
        song.parse()
        self.assertEqual(song.artist(), 'Deadly Guns;The Dark Horror')
        self.assertEqual(song.title(), 'In The Pit (Official Videoclip)')

    def test_title_is_split_even_when_youtube_supplied_an_artist(self):
        """The case that reaches the library with the artists still in the title.

        YouTube's music-credit panel makes yt-dlp set `artists`, which ffmpeg
        writes to the artist tag ahead of its uploader fallback. The old
        `update_song` only split the title while the artist tag still equalled
        the channel folder, so the moment YouTube supplied anything of its own
        the split silently stopped happening.
        """
        song = self._downloaded(channel='Deadly Guns', artist='Deadly Guns, The Dark Horror')
        song.parse()
        self.assertEqual(song.title(), 'In The Pit (Official Videoclip)')
        self.assertEqual(song.artist(), 'Deadly Guns;The Dark Horror')

    def test_channel_name_is_not_kept_alongside_the_real_artist(self):
        """`update_song` added to the artist tag, so the channel stayed behind."""
        song = self._downloaded()
        song.parse()
        self.assertNotIn(CHANNEL, song.library_artists())

    def test_album_artist_still_records_the_channel(self):
        song = self._downloaded()
        song.parse()
        self.assertEqual(song.album_artist(), CHANNEL)

    def test_artist_channel_still_splits_its_own_titles(self):
        """The one case the old rule did handle must keep working."""
        song = self._downloaded(channel='Angerfist', title='Angerfist - Raise Your Fist')
        song.parse()
        self.assertEqual(song.artist(), 'Angerfist')
        self.assertEqual(song.title(), 'Raise Your Fist')

    def test_featured_artist_is_lifted_out_of_the_title(self):
        song = self._downloaded(title='Angerfist - Raise Your Fist (feat. Miss K8)')
        song.parse()
        self.assertEqual(song.artist(), 'Angerfist;Miss K8')

    def test_set_title_moves_the_artist_out_of_the_at_form(self):
        song = self._downloaded(title='Angerfist @ Defqon.1 2025')
        song.parse()
        self.assertEqual(song.artist(), 'Angerfist')
        self.assertEqual(song.title(), 'Defqon.1 2025')

    def test_the_artist_line_as_the_title_wrote_it_is_kept_as_the_display_artist(self):
        """The half of the display artist that a download never reached.

        CleanTagsRule captures this when a file's own artist tag still needs splitting.
        A download's artists come out of the title instead, and arrive at that rule
        already split, so its "did the split change anything" test never fired and every
        SoundCloud and YouTube track lost its "Deadly Guns & The Dark Horror". 8 of
        344757 tracks on production carried a display artist.
        """
        song = self._downloaded()
        song.parse()
        self.assertEqual(song.original_artist(), 'Deadly Guns & The Dark Horror')

    def test_a_single_artist_is_not_given_a_second_copy_of_its_own_name(self):
        """Nothing was lost in the split, so there is nothing worth showing instead."""
        song = self._downloaded(channel='Angerfist', title='Angerfist - Raise Your Fist')
        song.parse()
        self.assertIsNone(song.original_artist())

    def test_a_featured_artist_lifted_out_of_the_title_leaves_no_partial_credit(self):
        """The whole chain, because the two halves of this sit in different rules.

        InferArtistFromTitleRule offers "Deadly Guns & The Dark Horror" as the credit and
        InferFeatureFromTitleRule then adds Miss K8 to the artist tag. A credit naming two
        of the three would be shown *instead of* the artist list by the web player, so no
        credit at all is the right outcome here.
        """
        song = self._downloaded(title='Deadly Guns & The Dark Horror - In The Pit (feat. Miss K8)')
        song.parse()
        self.assertEqual(song.artist(), 'Deadly Guns;The Dark Horror;Miss K8')
        self.assertIsNone(song.original_artist())

    def test_a_display_artist_the_file_already_carries_survives_a_retag(self):
        """A later round re-derives the artists from the same title.

        Letting it rewrite the value would replace what the file arrived with by
        whatever the current rules make of it, and the first pass is the one that saw
        the file as it was published.
        """
        song = self._downloaded()
        song.tag_collection.set_item(ORIGINAL_ARTIST, 'Deadly Guns vs The Dark Horror')
        song.parse()
        self.assertEqual(song.original_artist(), 'Deadly Guns vs The Dark Horror')


if __name__ == '__main__':
    unittest.main()
