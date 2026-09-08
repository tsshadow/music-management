"""What a retag can read back about a download, and what it refuses to guess.

Two claims are worth pinning here. A file is matched on the absolute path the archive
recorded and on nothing else -- a basename fallback would hand one channel's metadata to
another channel's file of the same name. And every failure answers None: this runs inside
a tagging round, where losing the extra info is a smaller loss than losing the round.
"""

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from services.tests.connector_fakes import fake_connector
from services.tests.mock_base import setup_mocks

setup_mocks()

from services.tagger import download_info  # noqa: E402
from services.tagger.constants import SongTypeEnum  # noqa: E402

SOUNDCLOUD_PATH = '/mnt/music/Soundcloud/Deathmask/Concussion - Hardcore Will Never Die.mp3'
YOUTUBE_PATH = "/mnt/music/Youtube/Partyraiser Recordings/KVN - The Flyin' Dutchman.m4a"


class DownloadInfoTestCase(unittest.TestCase):
    def setUp(self):
        self.connector, self.connection = fake_connector()
        self.cursor = self.connection.cursor.return_value.__enter__.return_value
        self.cursor.fetchone.return_value = None
        patcher = patch.object(download_info, 'DatabaseConnector', return_value=self.connector)
        patcher.start()
        self.addCleanup(patcher.stop)

    def answer(self, blob):
        self.cursor.fetchone.return_value = (blob,)

    def executed(self):
        return self.cursor.execute.call_args


class StoredInfoTest(DownloadInfoTestCase):
    def test_a_soundcloud_file_is_looked_up_by_the_column_that_holds_its_path(self):
        self.answer(json.dumps({'genre': 'Uptempo Hardcore'}))
        info = download_info.stored_info(SOUNDCLOUD_PATH, SongTypeEnum.SOUNDCLOUD)
        sql, params = self.executed().args
        assert 'downloads_soundcloud_archive' in sql
        assert 'filename = %s' in sql
        assert params == (SOUNDCLOUD_PATH,)
        assert info == {'genre': 'Uptempo Hardcore'}

    def test_a_youtube_file_is_looked_up_by_path_not_by_filename(self):
        # The YouTube table keeps the basename in `filename` and the absolute path in
        # `path`; matching the basename would collide across channels.
        self.answer(json.dumps({'track': 'The Flyin Dutchman'}))
        download_info.stored_info(YOUTUBE_PATH, SongTypeEnum.YOUTUBE)
        sql, params = self.executed().args
        assert 'downloads_youtube_archive' in sql
        assert 'path = %s' in sql
        assert 'filename' not in sql
        assert params == (YOUTUBE_PATH,)

    def test_a_path_object_is_matched_as_the_string_the_archive_stored(self):
        self.answer(json.dumps({'genre': 'Hardstyle'}))
        download_info.stored_info(Path(SOUNDCLOUD_PATH), SongTypeEnum.SOUNDCLOUD)
        _, params = self.executed().args
        assert params == (SOUNDCLOUD_PATH,)

    def test_a_label_file_costs_no_query(self):
        assert download_info.stored_info('/mnt/music/EPs/Texcore/TEX001 - Release/01.mp3', SongTypeEnum.LABEL) is None
        assert not self.cursor.execute.called

    def test_a_file_with_no_archive_row_gets_nothing(self):
        self.cursor.fetchone.return_value = None
        assert download_info.stored_info(SOUNDCLOUD_PATH, SongTypeEnum.SOUNDCLOUD) is None

    def test_a_row_whose_blob_is_null_gets_nothing(self):
        # Every row that predates migrate_v21 is exactly this.
        self.answer(None)
        assert download_info.stored_info(SOUNDCLOUD_PATH, SongTypeEnum.SOUNDCLOUD) is None

    def test_an_unreadable_blob_does_not_reach_the_caller(self):
        self.answer('{not json')
        assert download_info.stored_info(SOUNDCLOUD_PATH, SongTypeEnum.SOUNDCLOUD) is None

    def test_a_blob_that_is_not_an_object_does_not_reach_the_caller(self):
        # _apply_extra_info calls .get() on whatever it is handed.
        self.answer(json.dumps(['a list']))
        assert download_info.stored_info(SOUNDCLOUD_PATH, SongTypeEnum.SOUNDCLOUD) is None

    def test_an_unreachable_database_does_not_stop_the_round(self):
        self.cursor.execute.side_effect = RuntimeError('database is gone')
        assert download_info.stored_info(SOUNDCLOUD_PATH, SongTypeEnum.SOUNDCLOUD) is None


if __name__ == '__main__':
    unittest.main()
