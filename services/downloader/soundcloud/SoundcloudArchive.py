import logging

from services.common.Helpers.DatabaseConnector import DatabaseConnector


class SoundcloudArchive:
    """
    Utility class for interacting with the `downloads_soundcloud_archive` database table.

    Provides static methods to:
    - Check whether a track already exists in the archive.
    - Insert new entries after successful download and metadata enrichment.

    This ensures that we avoid duplicate downloads and retain metadata
    for historical and tagging purposes.
    """

    @staticmethod
    def exists(account: str, video_id: str) -> bool:
        try:
            with DatabaseConnector().connection() as conn, conn.cursor() as cursor:
                cursor.execute(
                    '\n                    SELECT 1 FROM downloads_soundcloud_archive WHERE account = %s AND video_id = %s\n                ',
                    (account, video_id),
                )
                return cursor.fetchone() is not None
        except Exception as e:
            logging.warning(f'Could not check archive for {account}/{video_id}: {e}', exc_info=True)
            return False

    @staticmethod
    def track_exists(track_id: str) -> bool:
        """Whether this track is already held, whatever account it came from.

        Deliberately does not filter on `account`. That column holds the numeric
        SoundCloud account id -- `SoundcloudSongProcessor` passes `channel_id or
        uploader_id` into both `exists` and `insert` -- while the sweep works in
        account names, so an account-filtered lookup would never match. Track ids
        are globally unique on SoundCloud, so the account adds nothing to this
        question, and leaving it out also covers accounts whose `soundcloud_id`
        was never filled in. `downloads_soundcloud_archive` indexes `video_id`.

        A database that cannot be reached answers "no": that means "do the full
        run", never "skip this account".
        """
        try:
            with DatabaseConnector().connection() as conn, conn.cursor() as cursor:
                cursor.execute('SELECT 1 FROM downloads_soundcloud_archive WHERE video_id = %s LIMIT 1', (track_id,))
                return cursor.fetchone() is not None
        except Exception as e:
            logging.warning(f'Could not check archive for track {track_id}: {e}', exc_info=True)
            return False

    @staticmethod
    def held_ids(track_ids) -> set[str]:
        """Which of these track ids the archive already holds.

        Deliberately does not filter on `account`, for the reason spelled out on
        `track_exists`: that column holds the numeric SoundCloud account id while
        the sweep works in account names. Track ids are globally unique on
        SoundCloud, so the account adds nothing to this question.

        Unlike `track_exists`, a database error is raised rather than answered
        with "no". This decides what a deep pass downloads, and answering
        "nothing is held" would turn one unreadable query into a re-download of
        the entire account.
        """
        ids = [str(track_id) for track_id in track_ids]
        if not ids:
            return set()
        found: set[str] = set()
        with DatabaseConnector().connection() as conn, conn.cursor() as cursor:
            for start in range(0, len(ids), 500):
                chunk = ids[start : start + 500]
                placeholders = ', '.join(['%s'] * len(chunk))
                cursor.execute(
                    f'SELECT video_id FROM downloads_soundcloud_archive WHERE video_id IN ({placeholders})',
                    tuple(chunk),
                )
                found.update(str(row[0]) for row in cursor.fetchall())
        return found

    @staticmethod
    def _get_uploader_id(self_info):
        return self_info.get('channel_id') or self_info.get('uploader_id') or None

    @staticmethod
    def insert(info: dict):
        account_name = info.get('account_name')
        account_id = info.get('account_id')
        video_id = info.get('video_id')
        path = info.get('path')
        url = info.get('url')
        title = info.get('title')
        if not all([account_name, video_id, url]):
            logging.warning(
                f'Missing fields for archive insert: account_id={account_id!r}, video_id={video_id!r}, url={url!r}'
            )
            return
        try:
            with DatabaseConnector().connection() as conn, conn.cursor() as cursor:
                cursor.execute(
                    'SELECT soundcloud_id FROM downloads_soundcloud_accounts WHERE name = %s', (account_name,)
                )
                existing = cursor.fetchone()
                print(existing, account_id, account_name)
                if existing is None:
                    logging.info(f'Inserting new account: name={account_name}, soundcloud_id={account_id}')
                    cursor.execute(
                        '\n                        INSERT IGNORE INTO downloads_soundcloud_accounts (name, soundcloud_id)\n                        VALUES (%s, %s)\n                    ',
                        (account_name, account_id),
                    )
                elif existing[0] is None and account_id:
                    logging.info(f"Updating account '{account_name}' with missing soundcloud_id: {account_id}")
                    cursor.execute(
                        '\n                        UPDATE downloads_soundcloud_accounts SET soundcloud_id = %s WHERE name = %s\n                    ',
                        (account_id, account_name),
                    )
                cursor.execute(
                    '\n                    INSERT IGNORE INTO downloads_soundcloud_archive (account, video_id, filename, url, title)\n                    VALUES (%s, %s, %s, %s, %s)\n                ',
                    (account_id, video_id, path, url, title),
                )
                conn.commit()
                logging.debug(f'Added to downloads_soundcloud_archive: {account_id}/{video_id}')
        except Exception as e:
            logging.error(f'Failed to insert archive info for {path}: {e}', exc_info=True)
