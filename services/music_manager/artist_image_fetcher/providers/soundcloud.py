import logging
import requests
from .base import ArtistImageProvider

class SoundCloudArtistImageProvider(ArtistImageProvider):

    def __init__(self, db_conn=None):
        self.db_conn = db_conn
        self.logger = logging.getLogger(__name__)

    @property
    def name(self):
        return 'soundcloud'

    def get_artist_images(self, artist_name, mbid=None, external_ids=None):
        candidates = []
        sc_account = external_ids.get('soundcloud') if external_ids else None
        if not sc_account and self.db_conn:
            try:
                with self.db_conn.cursor() as cursor:
                    cursor.execute("SHOW TABLES LIKE 'downloads_soundcloud_accounts'")
                    if cursor.fetchone():
                        query = 'SELECT name, soundcloud_id FROM downloads_soundcloud_accounts WHERE name = %s OR name = %s'
                        cursor.execute(query, (artist_name, artist_name.replace(' ', '-').lower()))
                        row = cursor.fetchone()
                        if row:
                            sc_account = row[0]
            except Exception as e:
                self.logger.debug(f'Could not search SoundCloud accounts in DB: {e}')
        if sc_account:
            pass
        return candidates