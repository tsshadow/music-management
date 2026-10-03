"""A CATALOGNUMBER holding the whole release folder name is replaced or emptied (issue #172)."""

import os
import tempfile
import unittest

from services.tagger.constants import CATALOG_NUMBER
from services.tagger.Song.rules.HealStaleCatalogueNumberRule import (
    HealStaleCatalogueNumberRule,
    release_directory,
    stale_values,
)
from services.tagger.Song.Tag import Tag

RELEASE = 'D-Teq_-_Dark_Energy-(BIR030)-WEB-2011-HB'


class _Collection:
    """has_item/get_item_as_string/set_item over real Tags, so change tracking is the real one."""

    def __init__(self, **tags):
        self.tags = {name: Tag(name, value) for name, value in tags.items()}

    def has_item(self, name):
        return name in self.tags

    def get_item_as_string(self, name):
        return self.tags[name].to_string()

    def set_item(self, name, value):
        self.tags[name].set(value)


class _Song:
    def __init__(self, path, **tags):
        self._path = path
        self.tag_collection = _Collection(**tags)

    def path(self):
        return self._path


class HealStaleCatalogueNumberRuleTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.label = os.path.join(tmp.name, 'Bazz Implant Recordings')

    def song(self, release, value, nfo=None):
        directory = os.path.join(self.label, release)
        os.makedirs(directory)
        if nfo is not None:
            with open(os.path.join(directory, '00-release.nfo'), 'wb') as handle:
                handle.write(nfo)
        song = _Song(os.path.join(directory, '01-track.mp3'), **{CATALOG_NUMBER: value})
        HealStaleCatalogueNumberRule(release).apply(song)
        return song.tag_collection.tags[CATALOG_NUMBER]

    def test_a_confirmed_bracketed_number_replaces_the_name(self):
        tag = self.song(RELEASE, RELEASE, nfo=b'CAT NR..[ BIR030\n')
        self.assertEqual('BIR030', tag.to_string())
        self.assertTrue(tag.has_changes())

    def test_a_bracketed_number_without_an_nfo_replaces_the_name(self):
        tag = self.song(RELEASE, RELEASE)
        self.assertEqual('BIR030', tag.to_string())
        self.assertTrue(tag.has_changes())

    def test_an_nfo_with_another_number_leaves_the_name(self):
        tag = self.song(RELEASE, RELEASE, nfo=b'CAT NR..[ BIR031\n')
        self.assertEqual(RELEASE, tag.to_string())
        self.assertFalse(tag.has_changes())

    def test_a_name_without_a_number_is_emptied_so_the_save_drops_it(self):
        name = 'Teequee-In_Ya_Face_EP-WEB-2009-UKHx'
        tag = self.song(name, name)
        self.assertEqual('', tag.to_string())
        self.assertTrue(tag.has_changes())

    def test_any_other_value_is_left_alone(self):
        tag = self.song(RELEASE, 'BIR-030')
        self.assertFalse(tag.has_changes())

    def test_a_song_without_the_tag_gets_none(self):
        song = _Song(os.path.join(self.label, RELEASE, '01-track.mp3'))
        HealStaleCatalogueNumberRule(RELEASE).apply(song)
        self.assertEqual({}, song.tag_collection.tags)

    def test_the_stale_values_include_the_name_after_its_prefix(self):
        self.assertEqual({'BIR030 - ' + RELEASE, RELEASE}, stale_values('BIR030 - ' + RELEASE))
        self.assertEqual(set(), stale_values(''))

    def test_the_release_directory_is_the_outer_copy(self):
        path = os.path.join('/eps', 'Label', RELEASE, RELEASE, '01.mp3')
        self.assertEqual(os.path.join('/eps', 'Label', RELEASE), release_directory(path, RELEASE))
        self.assertEqual('/eps/Label/x', release_directory('/eps/Label/x/01.mp3', RELEASE))
