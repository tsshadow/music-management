import logging

from numpy.testing.print_coercion_tables import print_new_cast_table

from postprocessing.Song.Helpers.DatabaseConnector import DatabaseConnector


class SoundcloudArchive:
    """
    Utility class for interacting with the `soundcloud_archive` database table.

    Provides static methods to:
    - Check whether a track already exists in the archive.
    - Insert new entries after successful download and metadata enrichment.

    This ensures that we avoid duplicate downloads and retain metadata
    for historical and tagging purposes.
    """

    @staticmethod
    def exists(account: str, video_id: str) -> bool:
        try:
            conn = DatabaseConnector().connect()
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT 1 FROM soundcloud_archive WHERE account = %s AND video_id = %s
                """, (account, video_id))
                return cursor.fetchone() is not None
        except Exception as e:
            logging.warning(f"Could not check archive for {account}/{video_id}: {e}", exc_info=True)
            return False

    @staticmethod
    def _get_uploader_id(self_info):
        return self_info.get("channel_id") or self_info.get("uploader_id") or None

    @staticmethod
    def insert(account_name: str, account_id: str, video_id: str, path: str, url: str, title: str):
        if not all([account_name, video_id, url]):
            logging.warning(f"Missing fields for archive insert: {account_id=}, {video_id=}, {url=}")
            return

        try:
            conn = DatabaseConnector().connect()
            with conn.cursor() as cursor:
                # check of account al bekend is
                cursor.execute("SELECT soundcloud_id FROM soundcloud_accounts WHERE name = %s", (account_name,))
                existing = cursor.fetchone()
                print(existing, account_id, account_name)
                if existing is None:
                    logging.info(f"Inserting new account: name={account_name}, soundcloud_id={account_id}")
                    cursor.execute("""
                        INSERT IGNORE INTO soundcloud_accounts (name, soundcloud_id)
                        VALUES (%s, %s)
                    """, (account_name, account_id))

                elif existing[0] is None and account_id:
                    logging.info(f"Updating account '{account_name}' with missing soundcloud_id: {account_id}")
                    cursor.execute("""
                        UPDATE soundcloud_accounts SET soundcloud_id = %s WHERE name = %s
                    """, (account_id, account_name))

                # Insert track in archive
                cursor.execute("""
                    INSERT IGNORE INTO soundcloud_archive (account, video_id, filename, url, title)
                    VALUES (%s, %s, %s, %s, %s)
                """, (account_id, video_id, path, url, title))

                conn.commit()
                logging.debug(f"Added to soundcloud_archive: {account_id}/{video_id}")
        except Exception as e:
            logging.error(f"Failed to insert archive info for {path}: {e}", exc_info=True)
