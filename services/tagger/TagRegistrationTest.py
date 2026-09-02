"""Coverage for services/tagger/tag_registration.py.

The bug this pins: `podcast` was in every tag map but in none of the two registration
blocks, so mutagen refused the key and every MP3 that matched an approved show lost its
whole save. Two copies of the list is what let one of them drift.
"""

import unittest
from unittest.mock import patch

from services.tagger import tag_registration
from services.tagger.constants import (
    FESTIVAL,
    ORIGINAL_TITLE,
    PARSED,
    PODCAST,
    PODCAST_EPISODE,
    PUBLISHER,
    RATING,
    REMIXER,
    MP3Tags,
)


class CustomTagKeysTest(unittest.TestCase):
    """Which names mutagen has to be taught before the tagger may write them."""

    def test_every_tag_the_tagger_invents_is_listed(self):
        """The names that are not part of any format's standard vocabulary.

        Adding one to a tag map without adding it here is exactly how the podcast tag
        was lost, so the list is asserted whole rather than key by key.
        """
        self.assertEqual(
            {PUBLISHER, RATING, PARSED, FESTIVAL, REMIXER, ORIGINAL_TITLE, PODCAST, PODCAST_EPISODE},
            set(tag_registration.CUSTOM_TAG_KEYS),
        )

    def test_the_mp3_key_is_the_standard_name_itself(self):
        """`BaseSong.set_tag` writes `music_file[tag.tag]` on the MP3 path, so the name
        registered here is the one the write uses."""
        for key in tag_registration.CUSTOM_TAG_KEYS:
            self.assertEqual(key, MP3Tags[key])


class RegisterCustomTagKeysTest(unittest.TestCase):
    """That the registration actually reaches mutagen, for both ID3 and MP4.

    mutagen is stubbed in this suite (services/tests/mock_base.py), so what a real
    EasyID3 accepts afterwards cannot be asserted here -- only that every key is offered
    to it.
    """

    def test_registers_every_custom_key_on_both_backends(self):
        with (
            patch.object(tag_registration.EasyID3, 'RegisterTXXXKey') as id3,
            patch.object(tag_registration.EasyMP4Tags, 'RegisterTextKey') as mp4,
        ):
            tag_registration.register_custom_tag_keys()

        registered_id3 = {call.args[0] for call in id3.call_args_list}
        registered_mp4 = {call.args[0] for call in mp4.call_args_list}
        self.assertEqual(set(tag_registration.CUSTOM_TAG_KEYS), registered_id3)
        self.assertEqual(set(tag_registration.CUSTOM_TAG_KEYS), registered_mp4)

    def test_podcast_is_among_them(self):
        """The regression itself: without this the podcast browse stays empty forever,
        because the tag never reaches the file the scanner reads."""
        self.assertIn(PODCAST, tag_registration.CUSTOM_TAG_KEYS)
        self.assertIn(PODCAST_EPISODE, tag_registration.CUSTOM_TAG_KEYS)

    def test_the_rating_frame_keeps_its_upper_case_description(self):
        """Existing files carry `TXXX:RATING`, and a lower-case registration would write
        a second frame beside it rather than update it."""
        with (
            patch.object(tag_registration.EasyID3, 'RegisterTXXXKey') as id3,
            patch.object(tag_registration.EasyMP4Tags, 'RegisterTextKey'),
        ):
            tag_registration.register_custom_tag_keys()

        descriptions = {call.args[0]: call.args[1] for call in id3.call_args_list}
        self.assertEqual('RATING', descriptions[RATING])
        self.assertEqual(PODCAST, descriptions[PODCAST])


if __name__ == '__main__':
    unittest.main()
