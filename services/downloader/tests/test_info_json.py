"""What survives the trip from a yt-dlp info dict into a database column, and what does not.

The two things this has to get right are opposites, which is why they are worth pinning:
nothing that answers a question later may be dropped, and nothing that only describes how
the file was fetched may be kept. Get the first wrong and the column is useless; get the
second wrong and 210.000 rows carry a few hundred kilobytes of expired URLs each.
"""

import json
import unittest

from services.downloader import info_json

# The fields worth having, in the shape both extractors deliver them.
SOUNDCLOUD = {
    'id': '123',
    'title': 'Gabber Cowboy',
    'genre': 'Uptempo Hardcore',
    'tags': ['hardcore', 'uptempo'],
    'description': 'Out now on Texcore',
    'uploader': 'Lil Texas',
    'upload_date': '20260910',
    'license': 'all-rights-reserved',
}

YOUTUBE = {
    'id': 'abc',
    'title': 'Lil Texas & Albino - Gabber Cowboy',
    # The music-credit panel, which is harder evidence than splitting the title.
    'artists': ['Lil Texas', 'Albino'],
    'track': 'Gabber Cowboy',
    'album': 'Gabber Cowboy',
    'release_year': 2026,
    'categories': ['Music'],
    'chapters': [{'start_time': 0, 'title': 'Intro'}],
}


class PruneTest(unittest.TestCase):
    def test_nothing_in_hands_back_nothing(self):
        self.assertIsNone(info_json.to_json(None))
        self.assertIsNone(info_json.to_json({}))

    def test_the_soundcloud_fields_no_tag_ever_sees_are_kept(self):
        stored = json.loads(info_json.to_json(SOUNDCLOUD))
        self.assertEqual('Uptempo Hardcore', stored['genre'])
        self.assertEqual(['hardcore', 'uptempo'], stored['tags'])
        self.assertEqual('Out now on Texcore', stored['description'])
        self.assertEqual('all-rights-reserved', stored['license'])

    def test_the_youtube_music_credits_are_kept(self):
        stored = json.loads(info_json.to_json(YOUTUBE))
        self.assertEqual(['Lil Texas', 'Albino'], stored['artists'])
        self.assertEqual('Gabber Cowboy', stored['track'])
        self.assertEqual(2026, stored['release_year'])
        self.assertEqual([{'start_time': 0, 'title': 'Intro'}], stored['chapters'])

    def test_the_transport_detail_is_dropped(self):
        """Almost all of a raw dict's weight, and stale within hours of the download."""
        bulky = {
            **YOUTUBE,
            'formats': [{'format_id': '140', 'url': 'https://expiring'}],
            'thumbnails': [{'url': 'https://thumb'}],
            'automatic_captions': {'en': [{'url': 'https://caption'}]},
            'heatmap': [{'value': 1.0}],
            'http_headers': {'User-Agent': 'x'},
            'url': 'https://expiring',
        }
        stored = json.loads(info_json.to_json(bulky))
        for dropped in ('formats', 'thumbnails', 'automatic_captions', 'heatmap', 'http_headers', 'url'):
            self.assertNotIn(dropped, stored)
        self.assertEqual('Gabber Cowboy', stored['track'])

    def test_yt_dlps_private_keys_do_not_travel(self):
        stored = json.loads(info_json.to_json({**SOUNDCLOUD, '_filename': '/tmp/x.m4a', '__files_to_move': {}}))
        self.assertFalse([key for key in stored if key.startswith('_')])

    def test_a_value_json_cannot_take_does_not_lose_the_whole_dict(self):
        """An extractor can put a date or a set in there; one odd value is not worth
        throwing the metadata away over."""
        stored = json.loads(info_json.to_json({**SOUNDCLOUD, 'odd': {1, 2}}))
        self.assertEqual('Uptempo Hardcore', stored['genre'])

    def test_a_description_past_the_ceiling_is_dropped_and_the_rest_kept(self):
        """A link dump says more about the channel than about the track."""
        stored = json.loads(info_json.to_json({**SOUNDCLOUD, 'description': 'x' * (info_json.MAX_BYTES + 1)}))
        self.assertNotIn('description', stored)
        self.assertEqual('Uptempo Hardcore', stored['genre'])

    def test_a_dict_still_too_large_without_its_description_is_not_stored(self):
        """Refused rather than truncated: half a JSON document is not a JSON document."""
        self.assertIsNone(info_json.to_json({**SOUNDCLOUD, 'tags': ['x' * 1000] * 200}))


if __name__ == '__main__':
    unittest.main()
