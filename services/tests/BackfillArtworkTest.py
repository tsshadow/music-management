"""Covers services/downloader/artwork.py and scripts/backfill_artwork.py.

The backfill writes into files that are already in the library, so what matters is what it
refuses to do: replace a cover somebody already has, embed an error page, or substitute an
uploader's avatar for a track the platform has no artwork for.
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from services.downloader.artwork import (
    chunked,
    mime_type,
    soundcloud_artwork_url,
    usable_image,
    youtube_artwork_urls,
)

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'backfill_artwork.py'

spec = importlib.util.spec_from_file_location('backfill_artwork', SCRIPT)
assert spec is not None and spec.loader is not None
backfill = importlib.util.module_from_spec(spec)
sys.modules['backfill_artwork'] = backfill
spec.loader.exec_module(backfill)

JPEG = b'\xff\xd8\xff' + b'\x00' * 4000
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 4000


class SoundcloudUrlsTest:
    def test_the_thumbnail_is_asked_for_in_a_size_worth_embedding(self):
        # The API answers with the 100x100 variant; every upload also has t500x500.
        url = soundcloud_artwork_url('https://i1.sndcdn.com/artworks-abc-large.jpg')
        assert url == 'https://i1.sndcdn.com/artworks-abc-t500x500.jpg'

    def test_a_png_keeps_its_extension(self):
        url = soundcloud_artwork_url('https://i1.sndcdn.com/artworks-abc-large.png')
        assert url == 'https://i1.sndcdn.com/artworks-abc-t500x500.png'

    def test_a_url_that_is_not_web_is_refused(self):
        # urllib speaks file://, and this URL comes out of a third party's JSON.
        assert soundcloud_artwork_url('file:///etc/passwd') is None
        assert soundcloud_artwork_url('ftp://host/art-large.jpg') is None

    def test_a_track_the_platform_has_no_artwork_for_yields_nothing(self):
        # Not the uploader's avatar: the same face on every track of a channel looks like the
        # library found something when it did not.
        assert soundcloud_artwork_url(None) is None
        assert soundcloud_artwork_url('') is None


class YoutubeUrlsTest:
    def test_every_size_is_offered_largest_first(self):
        urls = youtube_artwork_urls('abc123')
        assert urls[0] == 'https://i.ytimg.com/vi/abc123/maxresdefault.jpg'
        assert urls[-1] == 'https://i.ytimg.com/vi/abc123/default.jpg'
        assert len(urls) == 5

    def test_without_a_video_id_there_is_nothing_to_ask_for(self):
        assert youtube_artwork_urls(None) == []
        assert youtube_artwork_urls('') == []


class UsableImageTest:
    def test_a_jpeg_and_a_png_are_accepted(self):
        assert usable_image(JPEG)
        assert usable_image(PNG)
        assert mime_type(JPEG) == 'image/jpeg'
        assert mime_type(PNG) == 'image/png'

    def test_an_error_page_is_not_an_image(self):
        assert not usable_image(b'<!DOCTYPE html><html>404' + b' ' * 4000)

    def test_a_grey_placeholder_is_too_small_to_be_a_cover(self):
        # YouTube serves one of these for a missing maxresdefault on some CDN nodes rather
        # than answering 404, which would otherwise be embedded as if it were artwork.
        assert not usable_image(b'\xff\xd8\xff' + b'\x00' * 100)

    def test_nothing_at_all_is_not_an_image(self):
        assert not usable_image(None)
        assert not usable_image(b'')


class ChunkedTest:
    def test_the_last_batch_is_short_rather_than_dropped(self):
        assert list(chunked([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]]

    def test_nothing_in_yields_nothing(self):
        assert list(chunked([], 50)) == []


class CandidatesTest:
    def cursor_with(self, rows):
        cursor = MagicMock()
        cursor.fetchall.return_value = rows
        return cursor

    def test_the_archive_of_one_platform_is_read(self):
        # Tuples, not dicts: the downloader images hand out a plain cursor.
        cursor = self.cursor_with([('/music/a.mp3', '1', 'x')])

        rows = backfill.candidates(cursor, 'soundcloud')

        assert rows == [('/music/a.mp3', '1', 'x')]
        assert 'downloads_soundcloud_archive' in cursor.execute.call_args.args[0]

    def test_one_channel_can_be_singled_out_for_a_first_run(self):
        # SoundCloud's archive column is the numeric user id for 157.712 of its 157.713 rows,
        # so the folder is the only thing that answers to a channel name a person would type.
        cursor = self.cursor_with([])

        backfill.candidates(cursor, 'youtube', account='gabberhead')

        statement, params = cursor.execute.call_args.args
        assert 'AND (account = %s OR filename LIKE %s)' in statement
        assert params[-2:] == ('gabberhead', '%/gabberhead/%')

    def test_a_row_that_names_no_file_or_no_track_is_left_out_by_the_query(self):
        cursor = self.cursor_with([])

        backfill.candidates(cursor, 'soundcloud')

        statement, params = cursor.execute.call_args.args
        assert 'filename <> %s' in statement
        assert 'video_id <> %s' in statement
        assert params[0] == '' and params[1] == ''


class SoundcloudBatchLookupTest:
    def test_the_ids_are_asked_for_in_batches_with_the_resolved_client_id(self):
        responses = []

        def fake_urlopen(url, timeout=None):
            responses.append(url)
            payload = MagicMock()
            payload.__enter__ = lambda self: self
            payload.__exit__ = lambda *args: False
            return payload

        with (
            patch.object(backfill.urllib.request, 'urlopen', side_effect=fake_urlopen),
            patch.object(
                backfill.json, 'load', return_value=[{'id': 1, 'artwork_url': 'https://i1.sndcdn.com/a-large.jpg'}]
            ),
            patch.object(backfill.time, 'sleep'),
        ):
            found = backfill.soundcloud_artwork_urls([1, 2], 'CID', sleep=0)

        assert found == {'1': 'https://i1.sndcdn.com/a-t500x500.jpg'}
        assert 'ids=1,2' in responses[0]
        assert 'client_id=CID' in responses[0]

    def test_a_failing_batch_is_skipped_rather_than_ending_the_run(self):
        # The ids come from an archive going back years; one deleted track answers for its
        # whole batch, and that must not cost the other 149.000 files their artwork.
        with (
            patch.object(backfill.urllib.request, 'urlopen', side_effect=backfill.urllib.error.URLError('gone')),
            patch.object(backfill.time, 'sleep'),
        ):
            assert backfill.soundcloud_artwork_urls([1], 'CID', sleep=0) == {}

    def test_a_track_without_artwork_is_not_in_the_answer(self):
        payload = [{'id': 7, 'artwork_url': None}]
        opened = MagicMock()
        opened.__enter__ = lambda self: self
        opened.__exit__ = lambda *args: False
        with (
            patch.object(backfill.urllib.request, 'urlopen', return_value=opened),
            patch.object(backfill.json, 'load', return_value=payload),
            patch.object(backfill.time, 'sleep'),
        ):
            assert backfill.soundcloud_artwork_urls([7], 'CID', sleep=0) == {}


# `services/tests/mock_base.py` replaces `mutagen` with a bare module that has no `File`, so
# every patch of it here has to create the attribute rather than replace one.
class DownloadTest:
    def test_a_non_web_url_is_never_fetched(self):
        with patch.object(backfill.urllib.request, 'urlopen') as opened:
            assert backfill.download('file:///etc/passwd') is None
        opened.assert_not_called()


# `services/tests/mock_base.py` replaces `mutagen` with a bare module that has no `File`, so
# every patch of it here has to create the attribute rather than replace one.
class WriteArtworkTest:
    def test_a_file_that_already_has_a_cover_is_left_alone(self):
        audio = MagicMock()
        with (
            patch.object(backfill, 'has_artwork', return_value=True),
            patch('mutagen.File', return_value=audio, create=True),
        ):
            assert backfill.write_artwork('/music/a.mp3', JPEG) is False
        audio.save.assert_not_called()

    def test_a_file_without_one_is_written_once(self):
        audio = MagicMock()
        with (
            patch.object(backfill, 'has_artwork', return_value=False),
            patch.object(backfill, 'embed_artwork', return_value=True) as embed,
            patch('mutagen.File', return_value=audio, create=True),
        ):
            assert backfill.write_artwork('/music/a.mp3', JPEG) is True
        embed.assert_called_once_with(audio, JPEG)
        audio.save.assert_called_once()

    def test_a_file_mutagen_cannot_read_costs_one_file_not_the_run(self):
        with patch('mutagen.File', side_effect=OSError('truncated'), create=True):
            assert backfill.write_artwork('/music/a.mp3', JPEG) is False

    def test_a_file_that_cannot_be_written_is_reported_as_not_written(self):
        audio = MagicMock()
        audio.save.side_effect = OSError('read-only')
        with (
            patch.object(backfill, 'has_artwork', return_value=False),
            patch.object(backfill, 'embed_artwork', return_value=True),
            patch('mutagen.File', return_value=audio, create=True),
        ):
            assert backfill.write_artwork('/music/a.mp3', JPEG) is False


class RunPlatformTest:
    def args(self, **overrides):
        return backfill.parse_args(
            ['--sleep', '0', *[part for key, value in overrides.items() for part in (f'--{key}', str(value))]]
        )

    def test_a_dry_run_writes_nothing(self, capsys):
        cursor = MagicMock()
        cursor.fetchall.return_value = [('/music/a.mp3', '1', 'x')]
        with (
            patch.object(backfill, 'needs_artwork', return_value=True),
            patch.object(backfill, 'soundcloud_client_id', return_value='CID'),
            patch.object(backfill, 'soundcloud_artwork_urls', return_value={'1': 'https://art/1-t500x500.jpg'}),
            patch.object(backfill, 'write_artwork') as write,
            patch.object(backfill, 'download') as fetch,
        ):
            wanted, written, without = backfill.run_platform(cursor, 'soundcloud', backfill.parse_args(['--dry-run']))

        assert (wanted, written, without) == (1, 1, 0)
        write.assert_not_called()
        fetch.assert_not_called()

    def test_youtube_needs_no_api_call_at_all(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [('/music/v.m4a', 'abc', 'ch')]
        with (
            patch.object(backfill, 'needs_artwork', return_value=True),
            patch.object(backfill, 'soundcloud_client_id', side_effect=AssertionError('youtube must not ask')),
            patch.object(backfill, 'download', return_value=JPEG),
            patch.object(backfill, 'write_artwork', return_value=True) as write,
            patch.object(backfill.time, 'sleep'),
        ):
            wanted, written, without = backfill.run_platform(cursor, 'youtube', backfill.parse_args([]))

        assert (wanted, written, without) == (1, 1, 0)
        write.assert_called_once_with('/music/v.m4a', JPEG)

    def test_a_track_the_platform_has_no_artwork_for_is_counted_not_written(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [('/music/a.mp3', '1', 'x')]
        with (
            patch.object(backfill, 'needs_artwork', return_value=True),
            patch.object(backfill, 'soundcloud_client_id', return_value='CID'),
            patch.object(backfill, 'soundcloud_artwork_urls', return_value={}),
            patch.object(backfill, 'write_artwork') as write,
        ):
            wanted, written, without = backfill.run_platform(cursor, 'soundcloud', backfill.parse_args([]))

        assert (wanted, written, without) == (1, 0, 1)
        write.assert_not_called()

    def test_the_limit_stops_the_run(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [(f'/music/{i}.m4a', f'v{i}', 'ch') for i in range(5)]
        with (
            patch.object(backfill, 'needs_artwork', return_value=True),
            patch.object(backfill, 'download', return_value=JPEG),
            patch.object(backfill, 'write_artwork', return_value=True) as write,
            patch.object(backfill.time, 'sleep'),
        ):
            _wanted, written, _without = backfill.run_platform(cursor, 'youtube', backfill.parse_args(['--limit', '2']))

        assert written == 2
        assert write.call_count == 2

    def test_a_file_that_already_has_a_picture_is_never_considered(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [('/music/a.mp3', '1', 'x')]
        with (
            patch.object(backfill, 'needs_artwork', return_value=False),
            patch.object(backfill, 'soundcloud_client_id', side_effect=AssertionError('nothing to look up')),
            patch.object(backfill, 'write_artwork') as write,
        ):
            wanted, written, without = backfill.run_platform(cursor, 'soundcloud', backfill.parse_args([]))

        assert (wanted, written, without) == (0, 0, 0)
        write.assert_not_called()


class MainTest:
    def test_without_a_database_it_reports_a_failure_rather_than_running(self):
        connector = MagicMock()
        connector.return_value.connection.side_effect = RuntimeError('not configured')
        with patch.object(backfill, 'DatabaseConnector', connector):
            assert backfill.main([]) == 1

    def test_both_platforms_run_unless_one_is_named(self):
        with (
            patch.object(backfill, 'DatabaseConnector', MagicMock()),
            patch.object(backfill, 'run_platform', return_value=(0, 0, 0)) as run,
        ):
            assert backfill.main(['--dry-run']) == 0
            assert [call.args[1] for call in run.call_args_list] == ['soundcloud', 'youtube']

            run.reset_mock()
            assert backfill.main(['--platform', 'youtube']) == 0
            assert [call.args[1] for call in run.call_args_list] == ['youtube']


if __name__ == '__main__':
    sys.exit(pytest.main([__file__]))
