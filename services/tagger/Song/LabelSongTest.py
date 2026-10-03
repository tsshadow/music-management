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

import pytest

from services.tests.mock_base import reset_database_helpers

pytestmark = pytest.mark.mock_base('mutagen', 'Cache')

from services.common.Helpers.GenreRulesHelper import WHITE, GenreRow  # noqa: E402
from services.tagger.constants import ARTIST, CATALOG_NUMBER, DATE  # noqa: E402
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


class NoLabelFolderTest(unittest.TestCase):
    """Bug report 146: a release filed where no label is named gets no publisher from the path.

    The importer's Mover files a `FREE ...` release into `<eps root>/__Free&None/` (production's
    `rules_catid_label` maps the catalogue id `FREE` there) and runs LabelSong over it directly,
    without asking whether that folder is a label. 231 releases carried `__Free&None` as their
    label in LMS on 2026-10-02.
    """

    def setUp(self):
        reset_database_helpers()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.eps = Path(tmp.name)
        settings = MagicMock(eps_folder_path=str(self.eps), delimiter='/')
        patcher = patch.object(label_song_module, 's', settings)
        patcher.start()
        self.addCleanup(patcher.stop)

    def parsed(self, *folders, **tags):
        release_dir = self.eps.joinpath(*folders)
        release_dir.mkdir(parents=True)
        song = LabelSong(str(release_dir / '13-pat_b_-_conjo_(extended_mix)-sob.mp3'))
        song.tag_collection.set_item(DATE, '2023')
        for name, value in tags.items():
            song.tag_collection.set_item(name, value)
        song.parse()
        return song

    def test_free_and_none_is_never_written_as_the_publisher(self):
        for folder in ('__Free&None', '___Free&None'):
            with self.subTest(folder=folder):
                song = self.parsed(folder, 'FREE - Pat_B_-_USB_Album_3.0-FLASH-EXTRAS-2023-SOB')
                self.assertEqual('', song.publisher())
                self.assertFalse(song.copyright())
                self.assertFalse(song.catalog_number())

    def test_a_publisher_written_by_an_earlier_round_is_emptied(self):
        song = self.parsed(
            '__Free&None',
            'Buren_Van_De_Brandweer_-_Wij_Zijn_Hier-WEB-2022',
            publisher='__Free&None',
            copyright='__Free&None (2022)',
        )
        self.assertEqual('', song.publisher())
        self.assertEqual('', song.copyright())

    def test_a_release_directly_in_the_root_is_not_its_own_publisher(self):
        release = 'K1R331 - Hakim_And_Lakesiders_-_Set_Me_Free-(K1R331)-SINGLE-WEB-2025-SRG'
        song = self.parsed(release)
        self.assertEqual('', song.publisher())
        self.assertEqual('K1R331', song.catalog_number())
        self.assertFalse(song.copyright())


if __name__ == '__main__':
    unittest.main()


class StaleCatalogueNumberTest(unittest.TestCase):
    """Issue #172: a CATALOGNUMBER that holds the whole release folder name is replaced or cleared.

    Before bug report 145 the tagger wrote such a name for every release folder without a
    `<number> - ` prefix. The folder names here are real ones from production's label tree.
    """

    def setUp(self):
        reset_database_helpers()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.eps = Path(tmp.name)
        settings = MagicMock(eps_folder_path=str(self.eps), delimiter='/')
        patcher = patch.object(label_song_module, 's', settings)
        patcher.start()
        self.addCleanup(patcher.stop)

    def parsed(self, label, release, catalogue, nfo=None, nested=False):
        release_dir = self.eps / label / release
        audio_dir = release_dir / release if nested else release_dir
        audio_dir.mkdir(parents=True)
        if nfo is not None:
            (release_dir / '00-release.nfo').write_bytes(nfo)
        song = LabelSong(str(audio_dir / '01-track.mp3'))
        song.tag_collection.set_item(DATE, '2011')
        song.tag_collection.set_item(CATALOG_NUMBER, catalogue)
        song.parse()
        return song

    def test_the_bracketed_number_the_nfo_confirms_replaces_the_folder_name(self):
        release = 'D-Teq_-_Dark_Energy-(BIR030)-WEB-2011-HB'
        # The .nfo of this release on production writes the number without a colon.
        song = self.parsed('Bazz Implant Recordings', release, release, nfo=b'  CAT NR..[ BIR030\n')
        self.assertEqual('BIR030', song.catalog_number())

    def test_the_nfo_is_found_above_a_nested_copy_of_the_release(self):
        release = 'D-Teq_-_Dark_Energy-(BIR030)-WEB-2011-HB'
        song = self.parsed('Bazz Implant Recordings', release, release, nfo=b'Catalog Nr.: BIR030\n', nested=True)
        self.assertEqual('BIR030', song.catalog_number())

    def test_a_bracketed_number_without_an_nfo_to_confirm_it_is_cleared(self):
        """Taking it unconfirmed is the decision issue #172 leaves open."""
        release = 'Producer_Snafu-The_Brown_Cloud-(NGM.02)-Vinyl-2009-OBC'
        song = self.parsed('NGM Records', release, release)
        self.assertEqual('', song.catalog_number())

    def test_an_nfo_that_names_another_number_does_not_confirm_the_brackets(self):
        release = 'D-Teq_-_Dark_Energy-(BIR030)-WEB-2011-HB'
        song = self.parsed('Bazz Implant Recordings', release, release, nfo=b'Catalog Nr.: BIR031\n')
        self.assertEqual('', song.catalog_number())

    def test_a_folder_without_a_bracketed_number_has_its_stale_tag_cleared(self):
        release = 'Teequee-In_Ya_Face_EP-WEB-2009-UKHx'
        song = self.parsed('Bazz Implant Recordings', release, release)
        self.assertEqual('', song.catalog_number())

    def test_the_name_after_a_prefix_the_importer_added_later_takes_the_prefix(self):
        release = 'D-Teq_-_Dark_Energy-(BIR030)-WEB-2011-HB'
        song = self.parsed('Bazz Implant Recordings', 'BIR030 - ' + release, release)
        self.assertEqual('BIR030', song.catalog_number())

    def test_a_number_a_person_or_the_label_wrote_stays(self):
        for index, value in enumerate(('BIR-030', 'BIR030CD', 'D-Teq_-_Dark_Energy')):
            with self.subTest(value=value):
                song = self.parsed(f'Label {index}', 'D-Teq_-_Dark_Energy-(BIR030)-WEB-2011-HB', value)
                self.assertEqual(value, song.catalog_number())

    def test_a_folder_named_only_for_its_number_keeps_it(self):
        song = self.parsed('Fusion Records', 'FUSION001', 'FUSION001')
        self.assertEqual('FUSION001', song.catalog_number())
