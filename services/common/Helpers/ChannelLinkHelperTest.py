"""ChannelLinkHelper: the tagger's view of the channel links (docs/designs/channel-links)."""

import unittest
from unittest.mock import MagicMock, patch

from services.common.Helpers.ChannelLinkHelper import LINKS_SQL, ChannelLink, ChannelLinkHelper


class ChannelLinkHelperTest(unittest.TestCase):
    def setUp(self):
        patcher = patch('services.common.Helpers.ChannelLinkHelper.DatabaseConnector')
        self.addCleanup(patcher.stop)
        connector = patcher.start()
        self.connection = MagicMock()
        self.cursor = self.connection.cursor.return_value.__enter__.return_value
        connector.return_value.connect.return_value = self.connection

    def test_a_file_is_placed_under_its_channel_the_way_the_scanner_does(self):
        helper = ChannelLinkHelper(preload=False)
        helper.set_links([('soundcloud', 'BRAIN IMPACT', 'Brain Impact Records', None)])
        # Folder case and spacing differ; normalize_channel_name is the same key the scanner stores.
        link = helper.link_for('/mnt/music/Soundcloud/Brain  Impact/track.mp3')
        self.assertEqual(ChannelLink(label='Brain Impact Records', artist=None), link)

    def test_no_channel_or_no_link_is_none(self):
        helper = ChannelLinkHelper(preload=False)
        helper.set_links([('soundcloud', 'Traxtorm', 'Traxtorm Records', None)])
        self.assertIsNone(helper.link_for('/mnt/music/EPs/Traxtorm/TRAX1/track.mp3'))
        self.assertIsNone(helper.link_for('/mnt/music/Youtube/Traxtorm/track.mp3'))
        self.assertIsNone(helper.link_for(None))

    def test_a_row_linked_to_nothing_usable_is_dropped(self):
        helper = ChannelLinkHelper(preload=False)
        # The artist half is NULL when the linked artist is no longer approved (LINKS_SQL).
        helper.set_links([('youtube', 'Rejected Artist', None, None)])
        self.assertIsNone(helper.link_for('/mnt/music/Youtube/Rejected Artist/track.mp3'))

    def test_the_load_reads_every_linked_channel_from_either_cursor_kind(self):
        self.cursor.fetchall.return_value = [
            ('soundcloud', 'traxtorm', 'Traxtorm Records', None),
            {'platform': 'youtube', 'normalized_name': 'd-sturb', 'label_name': None, 'artist_name': 'D-Sturb'},
        ]
        helper = ChannelLinkHelper()
        self.cursor.execute.assert_called_once_with(LINKS_SQL)
        self.assertEqual('Traxtorm Records', helper.link_for('/m/Soundcloud/Traxtorm/a.mp3').label)
        self.assertEqual('D-Sturb', helper.link_for('/m/Youtube/D-Sturb/a.mp3').artist)
        self.connection.close.assert_called()

    def test_only_approved_artists_are_loaded(self):
        self.assertIn("r.state = 'white'", LINKS_SQL)

    def test_a_failed_reload_keeps_the_links_it_had(self):
        self.cursor.fetchall.return_value = [('soundcloud', 'traxtorm', 'Traxtorm Records', None)]
        helper = ChannelLinkHelper()
        self.cursor.execute.side_effect = RuntimeError('database gone')
        helper.reload()
        self.assertEqual('Traxtorm Records', helper.link_for('/m/Soundcloud/Traxtorm/a.mp3').label)

    def test_the_map_expires_so_another_process_sees_a_new_link(self):
        self.cursor.fetchall.return_value = []
        helper = ChannelLinkHelper()
        self.assertIsNone(helper.link_for('/m/Soundcloud/Traxtorm/a.mp3'))
        self.cursor.fetchall.return_value = [('soundcloud', 'traxtorm', 'Traxtorm Records', None)]
        helper._loaded_at -= ChannelLinkHelper.STALE_AFTER_SECONDS + 1
        self.assertEqual('Traxtorm Records', helper.link_for('/m/Soundcloud/Traxtorm/a.mp3').label)


if __name__ == '__main__':
    unittest.main()
