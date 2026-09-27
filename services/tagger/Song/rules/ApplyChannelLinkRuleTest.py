"""ApplyChannelLinkRule: a channel's link as evidence for its downloads' tags (docs/designs/channel-links).

The first class asks the rule what it does. The second parses real SoundCloud and YouTube songs
through their whole rule stack with a link in the tagger's helper, because a rule that passes its
own test can still be wired into nothing (it has happened: InferGenreFromLabelRule sat in no song
type's list for months).
"""

import unittest
from unittest.mock import patch

import pytest

from services.tests.mock_base import reset_database_helpers

pytestmark = pytest.mark.mock_base('mutagen', 'yt_dlp', 'Cache')

from services.common import channels
from services.common.Helpers.Cache import databaseHelpers
from services.common.Helpers.ChannelLinkHelper import ChannelLinkHelper
from services.common.import_queue import ImportQueue
from services.tagger.constants import ARTIST, PUBLISHER, TITLE
from services.tagger.Song.rules.ApplyChannelLinkRule import ApplyChannelLinkRule
from services.tagger.Song.SoundcloudSong import SoundcloudSong
from services.tagger.Song.YoutubeSong import YoutubeSong


def fixed_import_queue():
    """is_label consults the configured import queue; pin it so no setting decides a test."""
    return patch.object(channels, '_import_queue', return_value=ImportQueue('/mnt/music/intake'))


class FakeTags:
    """The two tag reads and the one write the rule uses."""

    def __init__(self, values):
        self.values = dict(values)

    def set_item(self, tag, value):
        self.values[tag] = value


class FakeSong:
    """A download as the rule sees it: a path, a publisher, artists and the channel's stand-ins."""

    def __init__(self, path, publisher='Soundcloud', artists=(), stand_ins=()):
        self._path = path
        self.tag_collection = FakeTags({PUBLISHER: publisher, ARTIST: ';'.join(artists)})
        self._stand_ins = list(stand_ins)

    def path(self):
        return self._path

    def publisher(self):
        return self.tag_collection.values[PUBLISHER]

    def library_artists(self):
        value = self.tag_collection.values[ARTIST]
        return value.split(';') if value else []

    def channel_stand_ins(self):
        return self._stand_ins


def helper(*rows):
    linked = ChannelLinkHelper(preload=False)
    linked.set_links(rows)
    return linked


PATH = '/mnt/music/Soundcloud/Hysta Official/Some Track.mp3'


class ApplyChannelLinkRuleTest(unittest.TestCase):
    def setUp(self):
        queue = fixed_import_queue()
        queue.start()
        self.addCleanup(queue.stop)

    def apply(self, song, *rows):
        ApplyChannelLinkRule(helper=helper(*rows)).apply(song)
        return song.tag_collection.values

    def test_a_linked_label_replaces_the_platform_publisher(self):
        song = FakeSong(PATH, publisher='Soundcloud', artists=['Hysta'])
        self.assertEqual(
            'Hysta Records', self.apply(song, ('soundcloud', 'hysta official', 'Hysta Records', None))[PUBLISHER]
        )

    def test_an_empty_publisher_gets_the_label_but_a_real_label_is_never_overwritten(self):
        empty = FakeSong(PATH, publisher='')
        self.assertEqual(
            'Hysta Records', self.apply(empty, ('soundcloud', 'Hysta Official', 'Hysta Records', None))[PUBLISHER]
        )
        curated = FakeSong(PATH, publisher='Dirty Workz')
        self.assertEqual(
            'Dirty Workz', self.apply(curated, ('soundcloud', 'Hysta Official', 'Hysta Records', None))[PUBLISHER]
        )

    def test_the_stand_in_artist_is_replaced_in_any_spelling_and_a_title_artist_is_kept(self):
        song = FakeSong(
            PATH,
            artists=['HYSTA-OFFICIAL', 'Angerfist'],
            stand_ins=['Hysta Official', 'hysta_official_uploader'],
        )
        values = self.apply(song, ('soundcloud', 'Hysta Official', None, 'Hysta'))
        self.assertEqual('Hysta;Angerfist', values[ARTIST])

    def test_an_artist_the_title_named_is_left_alone(self):
        song = FakeSong(PATH, artists=['Angerfist'], stand_ins=['Hysta Official'])
        self.assertEqual('Angerfist', self.apply(song, ('soundcloud', 'Hysta Official', None, 'Hysta'))[ARTIST])

    def test_no_artist_at_all_gets_the_linked_one(self):
        song = FakeSong(PATH, artists=[], stand_ins=['Hysta Official'])
        self.assertEqual('Hysta', self.apply(song, ('soundcloud', 'Hysta Official', None, 'Hysta'))[ARTIST])

    def test_replacing_does_not_leave_the_artist_twice(self):
        song = FakeSong(PATH, artists=['Hysta Official', 'Hysta'], stand_ins=['Hysta Official'])
        self.assertEqual('Hysta', self.apply(song, ('soundcloud', 'Hysta Official', None, 'Hysta'))[ARTIST])

    def test_an_unlinked_channel_or_another_platform_changes_nothing(self):
        song = FakeSong(PATH, artists=['Hysta Official'], stand_ins=['Hysta Official'])
        before = dict(song.tag_collection.values)
        self.assertEqual(before, self.apply(song, ('youtube', 'Hysta Official', 'Hysta Records', 'Hysta')))
        self.assertEqual(before, self.apply(song, ('soundcloud', 'Other', 'Hysta Records', 'Hysta')))

    def test_a_file_outside_any_channel_changes_nothing(self):
        song = FakeSong('/mnt/music/EPs/Dirty Workz/DWX1/track.mp3', publisher='Dirty Workz', artists=['A'])
        before = dict(song.tag_collection.values)
        self.assertEqual(before, self.apply(song, ('soundcloud', 'Dirty Workz', 'X', 'Y')))


class ChannelLinkWiredTest(unittest.TestCase):
    """The rule in the running stack: a real song type, parsed end to end."""

    def setUp(self):
        reset_database_helpers()
        queue = fixed_import_queue()
        queue.start()
        self.addCleanup(queue.stop)

    def test_a_soundcloud_download_from_a_linked_channel_carries_its_label_and_artist(self):
        databaseHelpers['channelLinkHelper'].set_links([('soundcloud', 'Hysta Official', 'Hysta Records', 'Hysta')])
        song = SoundcloudSong('/tmp/Soundcloud/Hysta Official/RIJE MOAT.mp3', {'uploader': 'Hysta Official'})
        song.tag_collection.set_item(TITLE, 'RIJE MOAT')
        song.parse()
        self.assertEqual('Hysta Records', song.publisher())
        self.assertEqual('Hysta', song.artist())

    def test_a_youtube_download_from_a_label_channel_keeps_the_artist_its_title_named(self):
        databaseHelpers['channelLinkHelper'].set_links([('youtube', 'Q-dance', 'Q-dance Records', None)])
        song = YoutubeSong('/tmp/Youtube/Q-dance/track.mp3', {'uploader': 'Q-dance'})
        song.tag_collection.set_item(TITLE, 'Angerfist - Raise Your Fist')
        song.parse()
        self.assertEqual('Q-dance Records', song.publisher())
        self.assertEqual('Angerfist', song.artist())

    def test_a_linked_labels_genre_rules_reach_the_download(self):
        databaseHelpers['channelLinkHelper'].set_links([('soundcloud', 'Traxtorm', 'Traxtorm Records', None)])
        databaseHelpers['labelGenreHelper'].get.side_effect = lambda name: (
            ['Hardcore'] if name == 'Traxtorm Records' else []
        )
        song = SoundcloudSong('/tmp/Soundcloud/Traxtorm/track.mp3', {'uploader': 'Traxtorm'})
        song.tag_collection.set_item(TITLE, 'Angerfist - Raise Your Fist')
        song.parse()
        self.assertIn('Hardcore', song.rules_genres())

    def test_without_a_link_a_download_is_tagged_as_before(self):
        song = SoundcloudSong('/tmp/Soundcloud/Hysta Official/RIJE MOAT.mp3', {'uploader': 'Hysta Official'})
        song.tag_collection.set_item(TITLE, 'RIJE MOAT')
        song.parse()
        self.assertEqual('Soundcloud', song.publisher())
        self.assertEqual('Hysta Official', song.artist())


if __name__ == '__main__':
    unittest.main()
