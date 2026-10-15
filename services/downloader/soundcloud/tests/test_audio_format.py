"""The SoundCloud format selector, run through yt-dlp's real format selection.

Uses the real yt_dlp on purpose: the defect it guards against (issue #185) was a
selector string that yt-dlp accepted and then matched nothing with.
"""

import unittest

from yt_dlp import YoutubeDL

from services.downloader.soundcloud.soundcloud import AUDIO_FORMAT


def audio(format_id, ext, abr, acodec):
    """One audio-only format entry the way the SoundCloud extractor lists it."""
    return {
        'format_id': format_id,
        'ext': ext,
        'abr': abr,
        'tbr': abr,
        'acodec': acodec,
        'vcodec': 'none',
        'protocol': 'm3u8_native',
        'url': f'https://example.invalid/{format_id}',
    }


# What SoundCloud serves since 2026-10-13, for old and new tracks alike.
AAC_ONLY = [audio('hls_aac_96k', 'm4a', 96, 'mp4a.40.2'), audio('hls_aac_160k', 'm4a', 160, 'mp4a.40.2')]
WITH_MP3 = [audio('hls_mp3_128', 'mp3', 128, 'mp3'), *AAC_ONLY]


def chosen(formats):
    """The format_id yt-dlp picks with AUDIO_FORMAT, or None when nothing matches."""
    with YoutubeDL({'quiet': True}) as ydl:
        selector = ydl.build_format_selector(AUDIO_FORMAT)
        picked = list(selector({'formats': formats, 'has_merged_format': False, 'incomplete_formats': False}))
    return picked[0]['format_id'] if picked else None


class AudioFormatTest(unittest.TestCase):
    def test_a_track_with_only_aac_gets_the_best_aac_stream(self):
        self.assertEqual(chosen(AAC_ONLY), 'hls_aac_160k')

    def test_mp3_still_wins_while_a_track_offers_it(self):
        self.assertEqual(chosen(WITH_MP3), 'hls_mp3_128')


if __name__ == '__main__':
    unittest.main()
