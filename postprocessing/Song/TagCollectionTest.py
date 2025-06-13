import unittest
from unittest.mock import MagicMock

from mutagen.id3 import TPE1

from postprocessing.Song.TagCollection import TagCollection, UnsupportedExtension
from postprocessing.Song.Tag import Tag
from postprocessing.constants import ARTIST, GENRE

# Format-specific mock types
from mutagen.easyid3 import EasyID3
from mutagen.flac import VCFLACDict
from mutagen.wave import _WaveID3
from mutagen.mp4 import MP4Tags, MP4FreeForm


class TagCollectionTest(unittest.TestCase):
    def test_mp3_tags_mapped_correctly(self):
        tags = EasyID3()
        tags["artist"] = ["Test Artist"]
        collection = TagCollection(tags)
        self.assertTrue(collection.has_item(ARTIST))
        self.assertEqual(collection.get_item_as_string(ARTIST), "Test Artist")

    def test_flac_tags_mapped_correctly(self):
        tags = VCFLACDict()
        tags["ARTIST"] = ["Test Artist"]
        collection = TagCollection(tags)
        self.assertTrue(collection.has_item(ARTIST))
        self.assertEqual(collection.get_item_as_string(ARTIST), "Test Artist")

    def test_wav_tags_mapped_correctly(self):
        tags = _WaveID3()
        tags["TPE1"] = TPE1(encoding=3, text=["Test Artist"])
        collection = TagCollection(tags)
        self.assertTrue(collection.has_item(ARTIST))
        self.assertEqual(collection.get_item_as_string(ARTIST), "Test Artist")

    def test_m4a_standard_tag_mapped_correctly(self):
        tags = MP4Tags()
        tags["\xa9ART"] = ["Test Artist"]
        collection = TagCollection(tags)
        self.assertTrue(collection.has_item(ARTIST))
        self.assertEqual(collection.get_item_as_string(ARTIST), "Test Artist")

    def test_m4a_custom_tag_handled(self):
        tags = MP4Tags()
        tags["----:com.apple.iTunes:genre"] = [MP4FreeForm(b"Hardcore")]
        collection = TagCollection(tags)
        self.assertTrue(collection.has_item(GENRE))
        self.assertEqual(collection.get_item_as_string(GENRE), "Hardcore")

    def test_unknown_tag_type_raises(self):
        class DummyTags: pass
        with self.assertRaises(UnsupportedExtension):
            TagCollection(DummyTags())

    def test_add_and_get_tag(self):
        collection = TagCollection(None)
        collection.add("test_tag", "hello world")
        self.assertTrue(collection.has_item("test_tag"))
        self.assertEqual(collection.get_item_as_string("test_tag"), "hello world")

    def test_set_item_creates_tag_if_missing(self):
        collection = TagCollection(None)
        self.assertFalse(collection.has_item("test"))
        collection.set_item("test", "value")
        self.assertTrue(collection.has_item("test"))
        self.assertEqual(collection.get_item_as_string("test"), "value")

    def test_get_item_as_array_returns_list(self):
        tag = Tag("genre", ["Hardcore", "Uptempo"])
        collection = TagCollection(None)
        collection.tags["genre"] = tag
        self.assertEqual(collection.get_item_as_array("genre"), ["Hardcore", "Uptempo"])

    def test_get_item_returns_tag_object(self):
        collection = TagCollection(None)
        tag = collection.get_item("test_tag")
        self.assertIsInstance(tag, Tag)
        self.assertEqual(tag.tag, "test_tag")

    def test_copy_creates_equivalent_collection(self):
        collection = TagCollection(None)
        collection.set_item("test", "value")
        copied = collection.copy()
        self.assertNotEqual(id(collection), id(copied))
        self.assertEqual(copied.get_item_as_string("test"), "value")
        self.assertEqual(collection, copied)

    def test_str_contains_all_keys(self):
        collection = TagCollection(None)
        collection.set_item("artist", "My Artist")
        output = str(collection)
        self.assertIn("artist: My Artist", output)


if __name__ == "__main__":
    unittest.main()
