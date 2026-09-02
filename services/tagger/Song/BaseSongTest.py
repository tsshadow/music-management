import os
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch

from mutagen.easyid3 import EasyID3
from mutagen.flac import VCFLACDict
from mutagen.mp4 import MP4StreamInfoError
from mutagen.oggopus import OggOpusVComment

from services.tagger.constants import (
    ARTIST,
    DATE,
    FESTIVAL,
    GENRE,
    ORIGINAL_DATE,
    TITLE,
    TRACK_NUMBER,
    AACTags,
    FLACTags,
    MP3Tags,
    MP4Tags,
    MusicFileType,
    OPUSTags,
    WAVTags,
)
from services.tagger.Song import BaseSong as BaseSong_module
from services.tagger.Song.BaseSong import BaseSong, ExtensionNotSupportedException, log_broken_file
from services.tagger.Song.SongHelper import merge_and_sort_genres, split_artists
from services.tagger.Song.Tag import Tag


class BaseSongTest(unittest.TestCase):
    @patch('services.tagger.Song.BaseSong.MP3')
    @patch('services.tagger.Song.BaseSong.EasyID3')
    def test_initialization_with_supported_extension(self, _mock_easyid3, mock_mp3):
        mock_file = MagicMock()
        mock_file.tags = EasyID3()
        mock_mp3.return_value = mock_file
        song = BaseSong('some/path/test.mp3')
        self.assertEqual(song.extension(), '.mp3')
        self.assertEqual(song.filename(), 'test.mp3')

    def test_initialization_with_unsupported_extension(self):
        with self.assertRaises(ExtensionNotSupportedException):
            BaseSong('file.unsupported')

    def test_split_artists(self):
        result = split_artists('Artist A & Artist B feat. Artist C')
        self.assertIn('Artist A', result)
        self.assertIn('Artist B', result)
        self.assertIn('Artist C', result)

    def test_merge_and_sort_genres(self):
        a = ['Techno', 'Hardcore']
        b = ['Hardcore', 'Industrial']
        merged = merge_and_sort_genres(a, b)
        self.assertEqual(merged, ['Hardcore', 'Industrial', 'Techno'])

    def test_sort_genres(self):
        song = BaseSong.__new__(BaseSong)
        mock_tag = MagicMock()
        mock_tag.value = ['Techno', 'Hardcore', 'Ambient']

        def mock_sort():
            mock_tag.value.sort()

        mock_tag.sort.side_effect = mock_sort
        tag_collection = MagicMock()
        tag_collection.has_item.return_value = True
        tag_collection.get_item.return_value = mock_tag
        song.tag_collection = tag_collection
        song.sort_genres()
        self.assertEqual(mock_tag.value, ['Ambient', 'Hardcore', 'Techno'])

    def test_tag_accessors_delegate_to_tag_collection(self):
        song = BaseSong.__new__(BaseSong)
        tag_collection = MagicMock()
        tag_collection.get_item_as_string.return_value = 'test'
        tag_collection.get_item_as_array.return_value = ['test1', 'test2']
        song.tag_collection = tag_collection
        self.assertEqual(song.artist(), 'test')
        self.assertEqual(song.library_artists(), ['test1', 'test2'])
        self.assertEqual(song.genre(), 'test')
        self.assertEqual(song.rules_genres(), ['test1', 'test2'])

    def test_set_tag_mp3(self):
        song = BaseSong.__new__(BaseSong)
        song.type = MusicFileType.MP3
        song.music_file = {}
        tag = Mock()
        tag.tag = ARTIST
        tag.to_string.return_value = 'New Artist'
        song.set_tag(tag)
        self.assertEqual(song.music_file[ARTIST], 'New Artist')

    @patch('services.tagger.Song.BaseSong.logging')
    def test_save_file_saves_only_if_changed(self, _mock_logging):
        tag = Tag(tag=ARTIST, value='Original Artist')
        tag.set('Some Artist')
        song = BaseSong.__new__(BaseSong)
        song.music_file = MagicMock()
        song.path = MagicMock()
        song.set_tag = MagicMock()
        tag_collection = MagicMock()
        tag_collection.get.return_value = {ARTIST: tag}
        song.tag_collection = tag_collection
        song.save_file()
        song.music_file.save.assert_called_once()

    @patch('services.tagger.Song.BaseSong.logging')
    def test_save_file_does_not_announce_a_write_that_failed(self, mock_logging):
        tag = Tag(tag=ARTIST, value='Original Artist')
        tag.set('Some Artist')
        song = BaseSong.__new__(BaseSong)
        song.music_file = MagicMock()
        song.music_file.save.side_effect = PermissionError(13, 'Permission denied')
        song.path = MagicMock()
        song.set_tag = MagicMock()
        tag_collection = MagicMock()
        tag_collection.get.return_value = {ARTIST: tag}
        song.tag_collection = tag_collection
        with self.assertRaises(PermissionError):
            song.save_file()
        announced = [c for c in mock_logging.info.call_args_list if 'File saved' in str(c)]
        self.assertEqual([], announced)

    @patch('services.tagger.Song.BaseSong.logging')
    def test_a_tag_mutagen_refuses_does_not_take_the_other_tags_down(self, mock_logging):
        """A key the format does not accept used to abort the whole save.

        That is how the podcast tag was lost: mutagen raised on `podcast`, the exception
        left `save_file` before `music_file.save()`, and every other tag the rules had
        just produced for that file went with it -- silently, because the parallel worker
        returned the error instead of logging it.
        """
        good = Tag(tag=ARTIST, value='Original Artist')
        good.set('Angerfist')
        bad = Tag(tag='podcast', value='')
        bad.set("Twisted's Darkside Podcast")
        song = BaseSong.__new__(BaseSong)
        song.music_file = MagicMock()
        song.path = MagicMock(return_value='/music/a.mp3')
        written = []

        def set_tag(tag):
            if tag.tag == 'podcast':
                raise KeyError("'podcast' is not a valid key")
            written.append(tag.tag)

        song.set_tag = set_tag
        tag_collection = MagicMock()
        tag_collection.get.return_value = {'podcast': bad, ARTIST: good}
        song.tag_collection = tag_collection

        song.save_file()

        self.assertEqual([ARTIST], written)
        song.music_file.save.assert_called_once()
        refused = [c for c in mock_logging.error.call_args_list if 'podcast' in str(c)]
        self.assertEqual(1, len(refused))

    def test_apply_extra_info_sets_artist(self):
        song = BaseSong.__new__(BaseSong)
        tag_collection = MagicMock()
        tag_collection.get_item_as_string.return_value = ''
        song.tag_collection = tag_collection
        info = {'library_artists': ['Test Artist']}
        song._apply_extra_info(info)
        tag_collection.set_item.assert_called_once_with(ARTIST, 'Test Artist')

    @patch('services.tagger.Song.BaseSong.logging')
    def test_length_returns_none_on_error(self, _mock_logging):
        song = BaseSong.__new__(BaseSong)
        song.path = lambda: 'fakepath'
        song.music_file = object()
        self.assertIsNone(song.length())

    def test_remixers_accessor(self):
        song = BaseSong.__new__(BaseSong)
        tag_collection = MagicMock()
        tag_collection.get_item_as_array.return_value = ['Remixer1', 'Remixer2']
        song.tag_collection = tag_collection
        self.assertEqual(song.remixers(), ['Remixer1', 'Remixer2'])


class BaseSongLoadingTest(unittest.TestCase):
    """Covers what __init__ does per container format."""

    def setUp(self):
        # `s` is a mocked ConfigStore here, so every setting reads as a truthy mock.
        # The real store answers analyze_bpm with its declared default, which is off,
        # and these tests assert on the exact rule list.
        patcher = patch.object(BaseSong_module.s, 'analyze_bpm', False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_wav_without_a_tag_block_gets_one(self):
        music_file = MagicMock()
        music_file.tags = None

        with patch('services.tagger.Song.BaseSong.WAVE', return_value=music_file):
            song = BaseSong('some/path/test.wav')

        music_file.add_tags.assert_called_once()
        self.assertEqual(song.type, MusicFileType.WAV)

    def flac_file(self):
        music_file = MagicMock()
        music_file.tags = VCFLACDict()
        return music_file

    def opus_file(self):
        music_file = MagicMock()
        music_file.tags = OggOpusVComment()
        return music_file

    def test_a_flac_is_normalized_on_load(self):
        with (
            patch('services.tagger.Song.BaseSong.FLAC', return_value=self.flac_file()),
            patch('services.tagger.Song.BaseSong.NormalizeFlacTagsRule') as normalize,
        ):
            BaseSong('some/path/test.flac')

        normalize.return_value.apply.assert_called_once()

    def test_every_song_gets_the_title_cleaning_rule(self):
        with patch('services.tagger.Song.BaseSong.OggOpus', return_value=self.opus_file()):
            song = BaseSong('some/path/test.opus')

        self.assertEqual([type(rule).__name__ for rule in song.rules], ['CleanTitleRule'])

    def test_bpm_analysis_is_added_when_it_is_switched_on(self):
        # The setting lives in ConfigStore now, not in a module constant, so it can be
        # turned on from the config page instead of by editing the file.
        with (
            patch('services.tagger.Song.BaseSong.OggOpus', return_value=self.opus_file()),
            patch.object(BaseSong_module.s, 'analyze_bpm', True),
        ):
            song = BaseSong('some/path/test.opus')

        self.assertEqual([type(rule).__name__ for rule in song.rules], ['CleanTitleRule', 'AnalyzeBpmRule'])

    def test_bpm_analysis_stays_out_of_the_rules_when_it_is_off(self):
        with (
            patch('services.tagger.Song.BaseSong.OggOpus', return_value=self.opus_file()),
            patch.object(BaseSong_module.s, 'analyze_bpm', False),
        ):
            song = BaseSong('some/path/test.opus')

        self.assertNotIn('AnalyzeBpmRule', [type(rule).__name__ for rule in song.rules])

    def test_extra_info_from_a_downloader_dump_is_applied_on_load(self):
        with patch('services.tagger.Song.BaseSong.OggOpus', return_value=self.opus_file()):
            song = BaseSong('some/path/test.opus', extra_info={'title': 'Raise Your Fist'})

        self.assertEqual(song.title(), 'Raise Your Fist')

    def test_an_unreadable_m4a_is_deleted_and_logged(self):
        with (
            patch('services.tagger.Song.BaseSong.MP4', side_effect=MP4StreamInfoError('broken')),
            patch('services.tagger.Song.BaseSong.os.remove') as remove,
            patch('services.tagger.Song.BaseSong.log_broken_file') as log_broken,
        ):
            song = BaseSong('some/path/test.m4a')

        remove.assert_called_once_with('some/path/test.m4a')
        log_broken.assert_called_once_with('some/path/test.m4a')
        self.assertFalse(hasattr(song, 'tag_collection'))

    def test_an_unreadable_m4a_that_cannot_be_deleted_does_not_break_the_load(self):
        with (
            patch('services.tagger.Song.BaseSong.MP4', side_effect=MP4StreamInfoError('broken')),
            patch('services.tagger.Song.BaseSong.os.remove', side_effect=OSError('read-only')),
        ):
            song = BaseSong('some/path/test.m4a')

        self.assertFalse(hasattr(song, 'tag_collection'))

    def test_log_broken_file_appends_one_line_per_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_file = os.path.join(tmp, 'broken-files.log')
            with patch('services.tagger.Song.BaseSong.LOG_FILE', log_file):
                log_broken_file('/music/a.m4a')
                log_broken_file('/music/b.m4a')

            with open(log_file, encoding='utf-8') as handle:
                self.assertEqual(handle.read().splitlines(), ['/music/a.m4a', '/music/b.m4a'])


class BaseSongTagWritingTest(unittest.TestCase):
    """set_tag dispatches to a writer per container format."""

    def song(self, file_type, music_file):
        song = BaseSong.__new__(BaseSong)
        song.type = file_type
        song.music_file = music_file
        return song

    def tag(self, name, value):
        tag = Mock()
        tag.tag = name
        tag.to_string.return_value = value
        return tag

    def test_an_empty_value_removes_the_tag_instead_of_writing_it(self):
        song = self.song(MusicFileType.MP3, MagicMock())
        song.tag_collection = MagicMock()
        song.tag_collection.get.return_value = {ARTIST: 'x'}

        song.set_tag(self.tag(ARTIST, '   '))

        song.music_file.pop.assert_called_once_with(ARTIST)

    def test_a_flac_tag_is_written_under_its_vorbis_name(self):
        song = self.song(MusicFileType.FLAC, {})

        song.set_tag(self.tag(ARTIST, 'Angerfist'))

        self.assertEqual(song.music_file, {'ARTIST': 'Angerfist'})

    def test_an_opus_tag_is_written_under_its_vorbis_name(self):
        song = self.song(MusicFileType.OPUS, {})

        song.set_tag(self.tag(GENRE, 'Hardcore'))

        self.assertEqual(song.music_file, {'GENRE': 'Hardcore'})

    def test_a_tag_the_format_does_not_know_is_skipped(self):
        song = self.song(MusicFileType.FLAC, {})

        song.set_tag(self.tag(TRACK_NUMBER, '3'))

        self.assertEqual(song.music_file, {})

    def test_a_wav_tag_becomes_an_id3_text_frame(self):
        music_file = MagicMock()
        music_file.tags = {}
        song = self.song(MusicFileType.WAV, music_file)

        song.set_tag(self.tag(ARTIST, 'Angerfist'))

        self.assertEqual(music_file.tags['TPE1'].text, ['Angerfist'])

    def test_a_wav_tag_without_an_id3_frame_becomes_a_txxx_frame(self):
        music_file = MagicMock()
        song = self.song(MusicFileType.WAV, music_file)

        song.set_tag(self.tag(FESTIVAL, 'Defqon.1'))

        music_file.tags.add.assert_called_once()

    def test_an_m4a_tag_is_written_under_its_atom(self):
        music_file = MagicMock()
        music_file.tags = {}
        song = self.song(MusicFileType.M4A, music_file)

        song.set_tag(self.tag(ARTIST, 'Angerfist'))

        self.assertEqual(music_file.tags['©ART'], 'Angerfist')

    def test_an_m4a_tag_without_an_atom_becomes_a_freeform_atom(self):
        music_file = MagicMock()
        music_file.tags = {}
        song = self.song(MusicFileType.M4A, music_file)

        song.set_tag(self.tag(FESTIVAL, 'Defqon.1'))

        self.assertEqual(music_file.tags['----:com.apple.iTunes:FESTIVAL'], [b'Defqon.1'])

    def m4a_song(self, tags):
        song = BaseSong.__new__(BaseSong)
        song.type = MusicFileType.M4A
        song._path = '/mnt/music/Livesets/set.m4a'
        song.music_file = MagicMock()
        song.music_file.tags = tags
        song.tag_collection = MagicMock()
        song.tag_collection.get.return_value = {}
        return song

    def test_a_differently_cased_atom_is_folded_into_the_canonical_one(self):
        song = self.m4a_song({'----:com.apple.iTunes:festival': [b'Reverze']})

        self.assertTrue(song.normalize_custom_atoms())

        self.assertEqual(song.music_file.tags, {'----:com.apple.iTunes:FESTIVAL': [b'Reverze']})

    def test_the_canonical_atom_wins_when_both_are_present(self):
        song = self.m4a_song(
            {
                '----:com.apple.iTunes:FESTIVAL': [b'Reverze'],
                '----:com.apple.iTunes:festival': [b'Defqon'],
            }
        )

        self.assertTrue(song.normalize_custom_atoms())

        self.assertEqual(song.music_file.tags, {'----:com.apple.iTunes:FESTIVAL': [b'Reverze']})

    def test_every_custom_atom_is_folded_not_just_the_festival(self):
        song = self.m4a_song(
            {
                '----:com.apple.iTunes:Publisher': [b'Q-dance'],
                '----:com.apple.iTunes:parsed': [b'1'],
            }
        )

        self.assertTrue(song.normalize_custom_atoms())

        self.assertEqual(
            sorted(song.music_file.tags),
            [
                '----:com.apple.iTunes:PARSED',
                '----:com.apple.iTunes:PUBLISHER',
            ],
        )

    def test_a_file_that_is_already_canonical_is_left_alone(self):
        tags = {'----:com.apple.iTunes:FESTIVAL': [b'Reverze'], '©ART': 'Angerfist'}
        song = self.m4a_song(dict(tags))

        self.assertFalse(song.normalize_custom_atoms())

        self.assertEqual(song.music_file.tags, tags)

    def test_only_m4a_files_are_folded(self):
        song = self.m4a_song({'----:com.apple.iTunes:festival': [b'Reverze']})
        song.type = MusicFileType.MP3

        self.assertFalse(song.normalize_custom_atoms())

        self.assertIn('----:com.apple.iTunes:festival', song.music_file.tags)

    def test_saving_folds_the_atoms_even_when_no_value_changed(self):
        song = self.m4a_song({'----:com.apple.iTunes:festival': [b'Reverze']})

        song.save_file()

        self.assertEqual(song.music_file.tags, {'----:com.apple.iTunes:FESTIVAL': [b'Reverze']})
        song.music_file.save.assert_called_once()

    def test_saving_a_canonical_file_writes_nothing(self):
        song = self.m4a_song({'----:com.apple.iTunes:FESTIVAL': [b'Reverze']})

        song.save_file()

        song.music_file.save.assert_not_called()

    def test_delete_tag_removes_it_from_the_file_and_the_collection(self):
        song = BaseSong.__new__(BaseSong)
        song.music_file = MagicMock()
        song.tag_collection = MagicMock()
        collection = {ARTIST: 'Angerfist'}
        song.tag_collection.get.return_value = collection

        song.delete_tag(ARTIST)

        song.music_file.pop.assert_called_once_with(ARTIST)
        self.assertEqual(collection, {})

    def test_delete_tag_leaves_a_tag_the_file_does_not_have(self):
        song = BaseSong.__new__(BaseSong)
        song.music_file = MagicMock()
        song.music_file.get.return_value = None
        song.tag_collection = MagicMock()
        song.tag_collection.get.return_value = {}

        song.delete_tag(ARTIST)

        song.music_file.pop.assert_not_called()

    def test_saving_a_song_that_never_loaded_does_nothing(self):
        song = BaseSong.__new__(BaseSong)

        song.save_file()

    def test_saving_without_changes_leaves_the_file_untouched(self):
        song = BaseSong.__new__(BaseSong)
        song.music_file = MagicMock()
        song.tag_collection = MagicMock()
        song.tag_collection.get.return_value = {ARTIST: Tag(tag=ARTIST, value='Angerfist')}

        song.save_file()

        song.music_file.save.assert_not_called()


class BaseSongExtraInfoTest(unittest.TestCase):
    def setUp(self):
        self.song = BaseSong.__new__(BaseSong)
        self.collection = MagicMock()
        self.collection.get_item_as_string.return_value = ''
        self.song.tag_collection = self.collection

    def test_the_uploader_stands_in_for_a_missing_artist(self):
        self.song._apply_extra_info({'uploader': 'Masters of Hardcore'})

        self.collection.set_item.assert_any_call(ARTIST, 'Masters of Hardcore')

    def test_the_channel_is_the_last_resort_for_an_artist(self):
        self.song._apply_extra_info({'channel': 'Q-dance'})

        self.collection.set_item.assert_any_call(ARTIST, 'Q-dance')

    def test_a_plain_artist_field_is_used_when_there_is_no_artist_list(self):
        self.song._apply_extra_info({'artist': 'Angerfist'})

        self.collection.set_item.assert_any_call(ARTIST, 'Angerfist')

    def test_an_artist_already_on_the_file_is_not_overwritten(self):
        self.collection.get_item_as_string.return_value = 'Angerfist'

        self.song._apply_extra_info({'uploader': 'Masters of Hardcore', 'title': 'Raise Your Fist'})

        self.collection.set_item.assert_not_called()

    def test_the_title_and_upload_date_are_taken_over(self):
        self.song._apply_extra_info({'title': 'Raise Your Fist', 'upload_date': '20240101'})

        self.collection.set_item.assert_any_call(TITLE, 'Raise Your Fist')
        self.collection.set_item.assert_any_call(DATE, '20240101')

    def test_a_genre_is_added_rather_than_replacing_what_is_there(self):
        self.song._apply_extra_info({'genre': 'Hardcore'})

        self.collection.get_item.return_value.add.assert_called_once_with('Hardcore')

    def test_an_empty_dump_changes_nothing(self):
        self.song._apply_extra_info({})

        self.collection.set_item.assert_not_called()


class BaseSongMiscTest(unittest.TestCase):
    def test_length_comes_from_the_file_info(self):
        song = BaseSong.__new__(BaseSong)
        song.music_file = MagicMock()
        song.music_file.info.length = 212.5

        self.assertEqual(song.length(), 212.5)

    def test_parse_runs_the_rules_and_then_saves(self):
        song = BaseSong.__new__(BaseSong)
        song.run_all_rules = MagicMock()
        song.save_file = MagicMock()

        song.parse()

        song.run_all_rules.assert_called_once()
        song.save_file.assert_called_once()

    def test_run_all_rules_applies_every_rule_to_the_song(self):
        song = BaseSong.__new__(BaseSong)
        first, second = MagicMock(), MagicMock()
        song.rules = [first, second]

        song.run_all_rules()

        first.apply.assert_called_once_with(song)
        second.apply.assert_called_once_with(song)

    def test_sort_genres_does_nothing_without_a_genre_tag(self):
        song = BaseSong.__new__(BaseSong)
        song.tag_collection = MagicMock()
        song.tag_collection.has_item.return_value = False

        song.sort_genres()

        song.tag_collection.get_item.assert_not_called()

    def test_the_string_form_lists_only_the_fields_that_are_set(self):
        song = BaseSong.__new__(BaseSong)
        song.tag_collection = MagicMock()
        song._path = '/music/test.mp3'
        song.title = lambda: 'Raise Your Fist'
        song.artist = lambda: 'Angerfist'
        song.album = lambda: ''
        song.genre = lambda: 'Hardcore'
        song.publisher = lambda: ''

        self.assertEqual(
            str(song),
            'Title=Raise Your Fist\nArtists=Angerfist\nGenre=Hardcore\nPath=/music/test.mp3',
        )


class OriginalDateTagTest(unittest.TestCase):
    """The original release date needs a mapping in every format the tagger writes."""

    def test_original_date_is_mapped_for_every_text_format(self):
        self.assertEqual(MP3Tags[ORIGINAL_DATE], 'originaldate')
        self.assertEqual(FLACTags[ORIGINAL_DATE], 'ORIGINALDATE')
        self.assertEqual(OPUSTags[ORIGINAL_DATE], 'ORIGINALDATE')
        self.assertEqual(AACTags[ORIGINAL_DATE], 'ORIGINALDATE')
        self.assertEqual(WAVTags[ORIGINAL_DATE], 'TDOR')

    def test_m4a_is_left_unmapped_so_the_freeform_fallback_applies(self):
        """_set_m4a_tag builds ----:com.apple.iTunes:ORIGINALDATE itself, with the MP4FreeForm
        wrapping a direct MP4Tags mapping would skip."""
        self.assertNotIn(ORIGINAL_DATE, MP4Tags)

    def test_the_standard_name_is_itself_the_mp3_key(self):
        """BaseSong.set_tag writes `music_file[tag.tag]` on the MP3 path, using the standard tag
        name directly, so that name has to be a key EasyID3 accepts. `originaldate` is one — it is
        native to EasyID3 and writes a real TDOR frame. mutagen is stubbed in this suite
        (services/tests/mock_base.py), so that fact cannot be asserted here, only relied on."""
        self.assertEqual(ORIGINAL_DATE, MP3Tags[ORIGINAL_DATE])

    def test_original_date_accessor_reads_the_tag(self):
        song = MagicMock()
        song.tag_collection.get_item_as_string = MagicMock(return_value='2026-01-16')
        self.assertEqual(BaseSong.original_date(song), '2026-01-16')
        song.tag_collection.get_item_as_string.assert_called_once_with(ORIGINAL_DATE)


if __name__ == '__main__':
    unittest.main()
