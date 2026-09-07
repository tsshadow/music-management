"""One imported release, walked through every field the label chain is supposed to fill.

test_importer_genre_rules.py already covers the genre resolver a rule at a time. This
file is the other half: the whole chain over a single release, asserting the fields a
reader of the library actually sees -- publisher, catalogue number, the artists, the
artist string as it was written, the genres and the release date.

It exists because the chain had a hole that no per-rule test could show. Every rule in
`services/tagger/Song/rules/` had a test of its own and passed it, and one of them --
InferGenreFromLabelRule -- was in no song type's rule list at all. `rules_label_genre`
held 49 curated rows on production that nothing read. A test that asks a rule what it
does cannot notice that nobody asks it; only a test of the chain can.

The paths are real directories because InferReleaseDateFromNfoRule reads the NFO off
disk. The audio files are not: mutagen is mocked for this suite (services/conftest.py),
so a Song can be constructed for a path with no bytes behind it.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from services.tests.mock_base import reset_database_helpers, setup_mocks

setup_mocks()
from services.common.Helpers.GenreRulesHelper import WHITE, GenreRow  # noqa: E402
from services.tagger.constants import ARTIST, DATE  # noqa: E402
from services.tagger.Song import LabelSong as label_song_module  # noqa: E402
from services.tagger.Song.LabelSong import LabelSong  # noqa: E402

LABEL = 'Texcore'
RELEASE = 'TEX001 - Lil_Texas_and_Albino_-_Gabber_Cowboy-WEB-2026-SRG'
# As the file arrives from the scene rip: one artist tag holding two names, and a year.
ARTIST_AS_WRITTEN = 'Lil Texas & Albino'
NFO = b'    Street Date ......: 10-09-2026\n    Rip Date .........: 08-09-2026\n'


class LabelSongChainTest(unittest.TestCase):
    def setUp(self):
        reset_database_helpers()
        from services.common.Helpers.Cache import databaseHelpers

        self.helpers = databaseHelpers
        self.helpers['library_artists'].get_all_values.return_value = ['Lil Texas', 'Albino']
        self.helpers['library_artists'].exists.side_effect = lambda name: name in ('Lil Texas', 'Albino')
        self.helpers['genre_rules'].set_rows(
            [
                GenreRow(1, 'Uptempo Hardcore', 'uptempo hardcore', WHITE, None),
                GenreRow(2, 'Hardcore', 'hardcore', WHITE, None),
            ]
        )

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.eps = Path(tmp.name)
        self.release_dir = self.eps / LABEL / RELEASE
        self.release_dir.mkdir(parents=True)
        (self.release_dir / '00-release.nfo').write_bytes(NFO)

        # LabelSong reads the EPs root to decide which path component is the label, so
        # it has to point at the tree built above rather than at the deployment's.
        settings = MagicMock(eps_folder_path=str(self.eps), delimiter='/')
        patcher = patch.object(label_song_module, 's', settings)
        patcher.start()
        self.addCleanup(patcher.stop)

    def song(self, artist=ARTIST_AS_WRITTEN, genre=None):
        """A release file as the importer hands it over: tagged by whoever ripped it."""
        song = LabelSong(str(self.release_dir / '01-gabber_cowboy.mp3'))
        song.tag_collection.set_item(ARTIST, artist)
        song.tag_collection.set_item(DATE, '2026')
        if genre:
            song.tag_collection.set_item('genre', genre)
        return song

    def parsed(self, **kwargs):
        song = self.song(**kwargs)
        song.parse()
        return song

    def test_the_publisher_and_catalogue_number_come_from_the_path(self):
        """`<eps root>/<label>/<cat id - release>/` is the only place either is stated."""
        song = self.parsed()
        self.assertEqual('Texcore', song.publisher())
        self.assertEqual('TEX001', song.catalog_number())

    def test_the_artist_tag_is_split_into_one_name_per_artist(self):
        song = self.parsed()
        self.assertEqual(['Lil Texas', 'Albino'], song.library_artists())

    def test_the_artist_string_as_written_is_kept_as_the_display_artist(self):
        """Splitting is what the library indexes on; this is what a reader wants shown."""
        song = self.parsed()
        self.assertEqual(ARTIST_AS_WRITTEN, song.original_artist())

    def test_an_artists_genre_reaches_the_file(self):
        self.helpers['artistGenreHelper'].get.side_effect = lambda name: (
            ['Uptempo Hardcore'] if name == 'Lil Texas' else []
        )
        self.assertIn('Uptempo Hardcore', self.parsed().rules_genres())

    def test_the_labels_genre_reaches_the_file(self):
        """The rule that ran nowhere.

        `rules_label_genre` is curated by hand and had 49 rows on production; no song
        type appended InferGenreFromLabelRule, so every one of them was inert.
        """
        self.helpers['labelGenreHelper'].get.side_effect = lambda label: (
            ['Uptempo Hardcore'] if label == 'Texcore' else []
        )
        self.assertIn('Uptempo Hardcore', self.parsed().rules_genres())

    def test_a_release_whose_artists_say_nothing_still_gets_the_labels_genre(self):
        """The case that was silently losing the genre altogether.

        A single-genre label releasing a track by artists that carry no genre rule of
        their own came out genre-less, and looked like a release nobody had curated
        rather than like a rule that was never wired up.
        """
        self.helpers['artistGenreHelper'].get.return_value = []
        self.helpers['labelGenreHelper'].get.side_effect = lambda label: (
            ['Uptempo Hardcore'] if label == 'Texcore' else []
        )
        self.assertEqual(['Uptempo Hardcore'], self.parsed().rules_genres())

    def test_a_subgenre_brings_its_parent_genre_with_it_and_both_are_kept(self):
        """Uptempo Hardcore is a Hardcore record; the file says so twice, on purpose.

        The broader genre is what a browse groups on and the subgenre is what the
        record is, so replacing one with the other would lose a question somebody asks.
        """
        self.helpers['labelGenreHelper'].get.return_value = ['Uptempo Hardcore']
        self.helpers['subgenreHelper'].get.side_effect = lambda genre: (
            ['Hardcore'] if genre == 'Uptempo Hardcore' else []
        )
        self.assertEqual(['Hardcore', 'Uptempo Hardcore'], self.parsed().rules_genres())

    def test_the_release_date_comes_from_the_nfo_rather_than_the_year_in_the_tag(self):
        """A scene rip is tagged with a year; the NFO next to it states the day."""
        song = self.parsed()
        self.assertEqual('2026-09-10', song.original_date())
        self.assertEqual('2026-09-10', song.release_date())

    def test_the_year_the_file_arrived_with_is_not_overwritten(self):
        """Two dates, two meanings: DATE is this edition, ORIGINALDATE is the release."""
        self.assertEqual('2026', self.parsed().date())

    def test_the_copyright_names_the_label_and_the_year(self):
        self.assertEqual('Texcore (2026)', self.parsed().copyright())


if __name__ == '__main__':
    unittest.main()
