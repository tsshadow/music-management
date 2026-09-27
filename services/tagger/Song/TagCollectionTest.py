import unittest

from mutagen.easyid3 import EasyID3
from mutagen.flac import VCFLACDict
from mutagen.id3 import TDOR, TDRC, TPE1
from mutagen.id3._specs import ID3TimeStamp
from mutagen.mp4 import MP4FreeForm, MP4Tags
from mutagen.wave import _WaveID3

from services.tagger.constants import (
    ALBUM,
    ALBUM_ARTIST,
    ARTIST,
    DATE,
    FESTIVAL,
    GENRE,
    ORIGINAL_DATE,
    ORIGINAL_TITLE,
    REMIXER,
)
from services.tagger.Song.Tag import Tag
from services.tagger.Song.TagCollection import TagCollection, UnsupportedExtension


class TagCollectionTest(unittest.TestCase):
    def test_an_empty_tag_keeps_its_baseline_when_a_value_is_added(self):
        # [A] -> [] -> [A] is no change; replacing the emptied Tag object would have lost
        # the value it started with and reported the round trip as a write.
        collection = TagCollection(None)
        collection.tags = {ARTIST: Tag(ARTIST, 'Angerfist')}
        collection.tags[ARTIST].set('')
        collection.add(ARTIST, 'Angerfist')
        self.assertFalse(collection.tags[ARTIST].has_changes())

    def test_mp3_tags_mapped_correctly(self):
        tags = EasyID3()
        tags['artist'] = ['Test Artist']
        collection = TagCollection(tags)
        self.assertTrue(collection.has_item(ARTIST))
        self.assertEqual(collection.get_item_as_string(ARTIST), 'Test Artist')

    def test_flac_tags_mapped_correctly(self):
        tags = VCFLACDict()
        tags['ARTIST'] = ['Test Artist']
        collection = TagCollection(tags)
        self.assertTrue(collection.has_item(ARTIST))
        self.assertEqual(collection.get_item_as_string(ARTIST), 'Test Artist')

    def test_wav_tags_mapped_correctly(self):
        tags = _WaveID3()
        tags['TPE1'] = TPE1(encoding=3, text=['Test Artist'])
        collection = TagCollection(tags)
        self.assertTrue(collection.has_item(ARTIST))
        self.assertEqual(collection.get_item_as_string(ARTIST), 'Test Artist')

    def test_a_wav_date_frame_reads_as_text(self):
        # Bug report 118: TDRC holds ID3TimeStamp objects, not str. Split as they were, every
        # WAV date logged "Could not split date value ['2023']" and stayed an object.
        tags = _WaveID3()
        tags['TDRC'] = TDRC(encoding=3, text=['2023'])
        tags['TDOR'] = TDOR(encoding=3, text=['2021-05-04'])
        self.assertIsInstance(tags['TDRC'].text[0], ID3TimeStamp)
        with self.assertNoLogs(level='WARNING'):
            collection = TagCollection(tags)
        self.assertEqual(collection.get_item_as_array(DATE), ['2023'])
        self.assertEqual(collection.get_item_as_array(ORIGINAL_DATE), ['2021-05-04'])
        self.assertTrue(all(isinstance(v, str) for v in collection.get_item_as_array(DATE)))
        self.assertFalse(collection.get_item(DATE).has_changes())

    def test_m4a_standard_tag_mapped_correctly(self):
        tags = MP4Tags()
        tags['©ART'] = ['Test Artist']
        collection = TagCollection(tags)
        self.assertTrue(collection.has_item(ARTIST))
        self.assertEqual(collection.get_item_as_string(ARTIST), 'Test Artist')

    def test_m4a_custom_tag_handled(self):
        tags = MP4Tags()
        tags['----:com.apple.iTunes:genre'] = [MP4FreeForm(b'Hardcore')]
        collection = TagCollection(tags)
        self.assertTrue(collection.has_item(GENRE))
        self.assertEqual(collection.get_item_as_string(GENRE), 'Hardcore')

    def test_unknown_tag_type_raises(self):

        class DummyTags:
            pass

        with self.assertRaises(UnsupportedExtension):
            TagCollection(DummyTags())

    def test_add_and_get_tag(self):
        collection = TagCollection(None)
        collection.add('test_tag', 'hello world')
        self.assertTrue(collection.has_item('test_tag'))
        self.assertEqual(collection.get_item_as_string('test_tag'), 'hello world')

    def test_set_item_creates_tag_if_missing(self):
        collection = TagCollection(None)
        self.assertFalse(collection.has_item('test'))
        collection.set_item('test', 'value')
        self.assertTrue(collection.has_item('test'))
        self.assertEqual(collection.get_item_as_string('test'), 'value')

    def test_get_item_as_array_returns_list(self):
        tag = Tag('genre', ['Hardcore', 'Uptempo'])
        collection = TagCollection(None)
        collection.tags['genre'] = tag
        self.assertEqual(collection.get_item_as_array('genre'), ['Hardcore', 'Uptempo'])

    def test_get_item_returns_tag_object(self):
        collection = TagCollection(None)
        tag = collection.get_item('test_tag')
        self.assertIsInstance(tag, Tag)
        self.assertEqual(tag.tag, 'test_tag')

    def test_copy_creates_equivalent_collection(self):
        collection = TagCollection(None)
        collection.set_item('test', 'value')
        copied = collection.copy()
        self.assertNotEqual(id(collection), id(copied))
        self.assertEqual(copied.get_item_as_string('test'), 'value')
        self.assertEqual(collection, copied)

    def test_str_contains_all_keys(self):
        collection = TagCollection(None)
        collection.set_item('artist', 'My Artist')
        output = str(collection)
        self.assertIn('artist: My Artist', output)

    def test_m4a_album_and_album_artist_read_from_their_itunes_atoms(self):
        tags = MP4Tags()
        tags['\u00a9alb'] = ['Thunderdome 2025']
        tags['aART'] = ['Various Artists']
        collection = TagCollection(tags)
        self.assertEqual(collection.get_item_as_string(ALBUM), 'Thunderdome 2025')
        self.assertEqual(collection.get_item_as_string(ALBUM_ARTIST), 'Various Artists')
        self.assertFalse(collection.get_item(ALBUM).has_changes())

    def test_m4a_remixer_and_original_title_read_from_freeform_atoms(self):
        tags = MP4Tags()
        tags['----:com.apple.iTunes:REMIXER'] = [MP4FreeForm(b'Dj Mad Dog;Angerfist')]
        tags['----:com.apple.iTunes:ORIGINAL_TITLE'] = [MP4FreeForm(b'A - B - C (24/7 Edit)')]
        collection = TagCollection(tags)
        self.assertEqual(collection.get_item_as_array(REMIXER), ['Dj Mad Dog', 'Angerfist'])
        self.assertEqual(collection.get_item_as_string(ORIGINAL_TITLE), 'A - B - C (24/7 Edit)')
        self.assertFalse(collection.get_item(REMIXER).has_changes())

    def test_legacy_m4a_atoms_are_read_and_marked_for_rewriting(self):
        tags = MP4Tags()
        tags['REMI'] = ['Dj Mad Dog']
        tags['ORIG'] = ['A - B - C']
        tags['TALB'] = ['Various Artists']
        tags['----:com.apple.iTunes:ALBUM'] = [MP4FreeForm(b'Youtube (Q-dance)')]
        collection = TagCollection(tags)
        self.assertEqual(collection.get_item_as_string(REMIXER), 'Dj Mad Dog')
        self.assertEqual(collection.get_item_as_string(ORIGINAL_TITLE), 'A - B - C')
        self.assertEqual(collection.get_item_as_string(ALBUM_ARTIST), 'Various Artists')
        self.assertEqual(collection.get_item_as_string(ALBUM), 'Youtube (Q-dance)')
        for key in (REMIXER, ORIGINAL_TITLE, ALBUM_ARTIST, ALBUM):
            self.assertTrue(collection.get_item(key).has_changes(), key)

    def test_the_correct_m4a_atom_wins_over_a_legacy_one_in_either_order(self):
        for order in (('REMI', '----:com.apple.iTunes:REMIXER'), ('----:com.apple.iTunes:REMIXER', 'REMI')):
            tags = MP4Tags()
            for key in order:
                tags[key] = ['Old'] if key == 'REMI' else [MP4FreeForm(b'New')]
            collection = TagCollection(tags)
            self.assertEqual(collection.get_item_as_string(REMIXER), 'New')
            self.assertFalse(collection.get_item(REMIXER).has_changes())

    def test_a_lower_case_freeform_twin_does_not_override_the_canonical_atom(self):
        tags = MP4Tags()
        tags['----:com.apple.iTunes:FESTIVAL'] = [MP4FreeForm(b'Reverze')]
        tags['----:com.apple.iTunes:festival'] = [MP4FreeForm(b'Defqon')]
        collection = TagCollection(tags)
        self.assertEqual(collection.get_item_as_string(FESTIVAL), 'Reverze')


if __name__ == '__main__':
    unittest.main()
