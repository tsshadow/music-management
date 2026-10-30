"""The redownload's source lookup against a real MariaDB.

It used to be `filename LIKE '%<name>%' LIMIT 1`, with the name's `_` and `%` left as
wildcards, so a redownload could fetch a different track. What only MariaDB can prove is
that the escaped `LIKE` takes the name literally and that the archive's case-insensitive
collation does not let a case twin through. See
docs/bug-reports/051-a-failing-file-is-retried-every-round-forever.md.
"""

import pytest

from services.music_manager.routers.library import AmbiguousSource, _redownload_source

pytestmark = pytest.mark.integration


def test_a_redownload_finds_its_source_by_the_exact_path_and_takes_the_name_literally(db):
    """`filename LIKE '%<name>%' LIMIT 1` picked 'DJ Intro_1.mp3' for 'Intro_1.mp3', and `_`
    matched any character."""
    with db.cursor() as cursor:
        cursor.execute(
            'INSERT INTO downloads_soundcloud_archive (account, video_id, filename, url) VALUES '
            "('a', '1', '/music/Soundcloud/a/DJ Intro_1.mp3', 'wrong'), "
            "('a', '2', '/music/Soundcloud/a/IntroX1.mp3', 'wrong too'), "
            "('a', '3', '/music/Soundcloud/a/Intro_1.mp3', 'right')"
        )
        assert _redownload_source(cursor, '/music/Soundcloud/a/Intro_1.mp3') == ('right', 'soundcloud')
        # The archive's collation is case-insensitive; the path is not.
        assert _redownload_source(cursor, '/music/Soundcloud/a/intro_1.mp3') == (None, None)

        # Moved since: no stored path matches, the name does -- literally, in the same folder.
        cursor.execute("DELETE FROM downloads_soundcloud_archive WHERE video_id = '3'")
        cursor.execute(
            'INSERT INTO downloads_soundcloud_archive (account, video_id, filename, url) '
            "VALUES ('a', '4', '/old/root/a/Intro_1.mp3', 'moved')"
        )
        assert _redownload_source(cursor, '/music/Soundcloud/a/Intro_1.mp3') == ('moved', 'soundcloud')

        cursor.execute(
            'INSERT INTO downloads_youtube_archive (account, video_id, filename, path, url, title, download_type) '
            "VALUES ('a', 'y', 'Intro_1.mp3', NULL, 'youtube', 'Intro', 'audio')"
        )
        with pytest.raises(AmbiguousSource):
            _redownload_source(cursor, '/music/Soundcloud/a/Intro_1.mp3')

        assert _redownload_source(cursor, '/music/Soundcloud/a/Nothing.mp3') == (None, None)
