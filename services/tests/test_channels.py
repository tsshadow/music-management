"""Where the line between a channel and a label is drawn.

The whole point of this module is what it refuses to call a label, so most of these tests are about
values that used to become one.
"""
import unittest

from services.common.channels import (
    channel_from_path,
    is_label,
    normalize_channel_name,
    path_can_carry_a_label,
)


class IsLabelTest(unittest.TestCase):

    def test_a_platform_is_not_a_label(self):
        # These three between them held 164.372 tracks at the top of the label chart.
        for platform in ('Soundcloud', 'Youtube', 'Telegram'):
            with self.subTest(platform=platform):
                self.assertFalse(is_label(platform))

    def test_case_does_not_rescue_a_platform(self):
        self.assertFalse(is_label('SOUNDCLOUD'))
        self.assertFalse(is_label('  youtube  '))

    def test_a_placeholder_is_not_a_label(self):
        # __TODO is the import folder's own name, stamped onto a release that never left it.
        self.assertFalse(is_label('__TODO'))
        self.assertFalse(is_label('__Free&none'))

    def test_nothing_is_not_a_label(self):
        self.assertFalse(is_label(''))
        self.assertFalse(is_label(None))
        self.assertFalse(is_label('   '))

    def test_a_real_label_still_is_one(self):
        for label in ('Dirty Workz', 'Scantraxx', 'Masters Of Hardcore', 'B2S'):
            with self.subTest(label=label):
                self.assertTrue(is_label(label))


class ChannelFromPathTest(unittest.TestCase):

    def test_a_soundcloud_track_names_its_channel(self):
        found = channel_from_path('/mnt/music/Soundcloud/Dirty Workz/some track.mp3', '/mnt/music')
        self.assertEqual(found, ('soundcloud', 'Dirty Workz'))

    def test_a_youtube_track_names_its_channel(self):
        found = channel_from_path('/mnt/music/Youtube/Q-dance/aftermovie.m4a', '/mnt/music')
        self.assertEqual(found, ('youtube', 'Q-dance'))

    def test_the_channel_survives_extra_folders_below_it(self):
        found = channel_from_path('/mnt/music/Soundcloud/Angerfist/2024/set.mp3', '/mnt/music')
        self.assertEqual(found, ('soundcloud', 'Angerfist'))

    def test_a_label_release_is_not_a_channel(self):
        self.assertIsNone(
            channel_from_path('/mnt/music/EPs/Dirty Workz/DWX123 Release/track.mp3', '/mnt/music')
        )

    def test_a_track_loose_in_the_platform_folder_has_no_channel(self):
        # There is no channel folder here, so there is no channel to record.
        self.assertIsNone(channel_from_path('/mnt/music/Soundcloud/orphan.mp3', '/mnt/music'))

    def test_the_music_root_does_not_have_to_be_given(self):
        found = channel_from_path('/mnt/music/Telegram/somechat/track.mp3')
        self.assertEqual(found, ('telegram', 'somechat'))

    def test_a_root_that_itself_contains_a_platform_name_is_not_confused(self):
        # The root is stripped before the search, so a root like /srv/youtube-archive does not
        # make every file in the library a YouTube channel.
        found = channel_from_path('/srv/youtube/Soundcloud/Rejecta/track.mp3', '/srv/youtube')
        self.assertEqual(found, ('soundcloud', 'Rejecta'))

    def test_an_empty_path_has_no_channel(self):
        self.assertIsNone(channel_from_path(''))


class PathCanCarryALabelTest(unittest.TestCase):
    """The trap the folder restructure sets, and why it is refused structurally.

    The tagger reads a label from the folders above a track. That is right inside the label tree and
    wrong everywhere else -- and once `__Free&None` moves to `/mnt/music/songs/`, the naive answer
    is that every track in it is on a label called "songs".
    """

    def test_a_label_release_carries_a_label(self):
        self.assertTrue(
            path_can_carry_a_label('/mnt/music/labels/Dirty Workz/DWX123/track.mp3', '/mnt/music'))

    def test_the_songs_pile_carries_none(self):
        self.assertFalse(
            path_can_carry_a_label('/mnt/music/songs/Some Release/track.mp3', '/mnt/music'))

    def test_the_import_folder_carries_none(self):
        self.assertFalse(
            path_can_carry_a_label('/mnt/music/import/Some Release/track.mp3', '/mnt/music'))

    def test_a_platform_folder_carries_none(self):
        for platform in ('Soundcloud', 'Youtube', 'Telegram'):
            with self.subTest(platform=platform):
                self.assertFalse(
                    path_can_carry_a_label(f'/mnt/music/{platform}/Chan/track.mp3', '/mnt/music'))

    def test_the_old_eps_tree_still_carries_a_label(self):
        # The restructure has not necessarily run yet, and both layouts have to work meanwhile.
        self.assertTrue(
            path_can_carry_a_label('/mnt/music/EPs/Dirty Workz/DWX123/track.mp3', '/mnt/music'))

    def test_nothing_below_the_root_carries_a_label(self):
        self.assertFalse(path_can_carry_a_label('/mnt/music', '/mnt/music'))
        self.assertFalse(path_can_carry_a_label('', '/mnt/music'))


class NormalizeChannelNameTest(unittest.TestCase):

    def test_one_channel_cannot_become_two(self):
        self.assertEqual(
            normalize_channel_name('Dirty  Workz '),
            normalize_channel_name('dirty workz'),
        )


if __name__ == '__main__':
    unittest.main()
