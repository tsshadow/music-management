import unittest
from postprocessing.Song.Tag import Tag

class TestTag(unittest.TestCase):

    def test_init_with_string(self):
        tag = Tag("artist", "A;B")
        self.assertEqual(tag.to_array(), ["A", "B"])
        self.assertFalse(tag.has_changes())

    def test_init_with_list_and_resplit(self):
        tag = Tag("genre", ["Hardcore/Industrial"])
        self.assertEqual(tag.to_array(), ["Hardcore", "Industrial"])

    def test_to_string_and_array(self):
        tag = Tag("genre", ["Techno", "Hardcore"])
        self.assertEqual(tag.to_string(), "Techno;Hardcore")
        self.assertEqual(tag.to_array(), ["Techno", "Hardcore"])

    def test_add_unique_value(self):
        tag = Tag("label", "Foo")
        tag.add("Bar")
        self.assertEqual(tag.to_array(), ["Foo", "Bar"])
        self.assertTrue(tag.has_changes())

    def test_add_existing_value_does_not_change(self):
        tag = Tag("label", "Foo;Bar")
        tag.add("Foo")
        self.assertEqual(tag.to_array(), ["Foo", "Bar"])
        self.assertFalse(tag.has_changes())

    def test_remove_value(self):
        tag = Tag("artist", "A;B;C")
        tag.remove("B")
        self.assertEqual(tag.to_array(), ["A", "C"])
        self.assertTrue(tag.has_changes())

    def test_sort(self):
        tag = Tag("genre", "Techno;Hardcore;Ambient")
        tag.sort()
        self.assertEqual(tag.to_array(), ["Ambient", "Hardcore", "Techno"])
        self.assertTrue(tag.has_changes())

    def test_deduplicate(self):
        tag = Tag("genre", "Hardcore;Hardcore;Techno")
        tag.deduplicate()
        self.assertEqual(tag.to_array(), ["Hardcore", "Techno"])
        self.assertTrue(tag.has_changes())

    def test_recapitalize(self):
        tag = Tag("artist", "hardcore;speedcore")
        tag.recapitalize()
        self.assertEqual(tag.to_array(), ["Hardcore", "Speedcore"])
        self.assertTrue(tag.has_changes())

    def test_strip(self):
        tag = Tag("artist", "  A ; B ")
        tag.strip()
        self.assertEqual(tag.to_array(), ["A", "B"])
        self.assertTrue(tag.has_changes())

    def test_regex_splitting(self):
        tag = Tag("artist", "A feat. B & C")
        tag.regex()
        self.assertIn("A", tag.to_array())
        self.assertIn("B", tag.to_array())
        self.assertIn("C", tag.to_array())

    def test_set_with_string(self):
        tag = Tag("genre", "Hardcore")
        tag.set("Hardcore;Industrial")
        self.assertEqual(tag.to_array(), ["Hardcore", "Industrial"])
        self.assertTrue(tag.has_changes())

    def test_set_with_list(self):
        tag = Tag("genre", "Hardcore")
        tag.set(["Hardcore/Industrial"])
        self.assertEqual(tag.to_array(), ["Hardcore", "Industrial"])
        self.assertTrue(tag.has_changes())

    def test_equality_and_copy(self):
        a = Tag("genre", "Hardcore;Techno")
        b = a.copy()
        self.assertEqual(a, b)
        self.assertIsNot(a, b)

    def test_len_and_iter(self):
        tag = Tag("artist", "A;B;C")
        self.assertEqual(len(tag), 3)
        self.assertEqual(list(tag), ["A", "B", "C"])

    def test_str_output(self):
        tag = Tag("title", "My Track")
        self.assertEqual(str(tag), "title: My Track")


if __name__ == "__main__":
    unittest.main()
