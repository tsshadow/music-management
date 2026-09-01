import logging
import os

from services.common.Helpers.DatabaseConnector import DatabaseConnector
from services.downloader.youtube.YoutubeAccount import AUDIO


class YoutubeArchive:
    """Utility helpers for interacting with the `downloads_youtube_archive` table.

    Rows are keyed by (video_id, download_type): a channel that is both an audio
    and a video source has to be able to archive the same video twice, once per
    form. Before migrate_v6 the key was video_id alone, so whichever pass ran
    first blocked the other one forever.
    """

    @staticmethod
    def exists(account: str, video_id: str, download_type: str = AUDIO) -> bool:
        """Return True if the video was already archived for the account in this form."""
        try:
            with DatabaseConnector().connection() as conn, conn.cursor() as cursor:
                cursor.execute(
                    '\n                    SELECT 1 FROM downloads_youtube_archive\n'
                    '                    WHERE account = %s AND video_id = %s AND download_type = %s\n'
                    '                    ',
                    (account, video_id, download_type),
                )
                return cursor.fetchone() is not None
        except Exception as e:
            logging.warning(f'Could not check archive for {account}/{video_id}: {e}', exc_info=True)
            return False

    @staticmethod
    def held_ids(account: str, video_ids, download_type: str = AUDIO) -> set[str]:
        """Which of these video ids are archived for this account in this form.

        Keyed the way the table is keyed: a channel that is both an audio and a
        video source holds the same video twice, once per form, and a deep pass
        of one form must not read the other form's row as its own.

        A database error is raised rather than swallowed; see
        `SoundcloudArchive.held_ids` for why.
        """
        ids = [str(video_id) for video_id in video_ids]
        if not ids:
            return set()
        found: set[str] = set()
        with DatabaseConnector().connection() as conn, conn.cursor() as cursor:
            for start in range(0, len(ids), 500):
                chunk = ids[start : start + 500]
                placeholders = ', '.join(['%s'] * len(chunk))
                cursor.execute(
                    'SELECT video_id FROM downloads_youtube_archive '
                    'WHERE account = %s AND download_type = %s '
                    f'AND video_id IN ({placeholders})',
                    (account, download_type, *chunk),
                )
                found.update(str(row[0]) for row in cursor.fetchall())
        return found

    @staticmethod
    def insert(account: str, video_id: str, path: str, url: str, title: str, download_type: str = AUDIO):
        """Insert a newly downloaded track into the downloads_youtube_archive table."""
        if not all([account, video_id, url]):
            logging.warning(f'Missing fields for archive insert: account={account}, video_id={video_id}, url={url}')
            return
        try:
            with DatabaseConnector().connection() as conn, conn.cursor() as cursor:
                cursor.execute(
                    'INSERT IGNORE INTO downloads_youtube_accounts (name, download_type) VALUES (%s, %s)',
                    (account, download_type),
                )
                cursor.execute(
                    '\n                    INSERT IGNORE INTO downloads_youtube_archive '
                    '(account, video_id, filename, path, url, title, download_type)\n'
                    '                    VALUES (%s, %s, %s, %s, %s, %s, %s)\n'
                    '                    ',
                    (account, video_id, os.path.basename(path), path, url, title, download_type),
                )
                conn.commit()
                logging.debug(f'Added to downloads_youtube_archive: {account}/{video_id} ({download_type})')
        except Exception as e:
            logging.error(f'Failed to insert archive info for {path}: {e}', exc_info=True)
