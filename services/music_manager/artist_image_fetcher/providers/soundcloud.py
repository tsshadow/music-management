import logging
import requests
from .base import ArtistImageProvider

class SoundCloudArtistImageProvider(ArtistImageProvider):
    def __init__(self, db_conn=None):
        self.db_conn = db_conn
        self.logger = logging.getLogger(__name__)

    @property
    def name(self):
        return "soundcloud"

    def get_artist_images(self, artist_name, mbid=None, external_ids=None):
        candidates = []
        
        # If we have a soundcloud_id or soundcloud account name, we can try to get the avatar
        sc_account = external_ids.get('soundcloud') if external_ids else None
        
        if not sc_account and self.db_conn:
            # Try to find in downloads_soundcloud_accounts
            try:
                with self.db_conn.cursor() as cursor:
                    # Check if table exists first to avoid error spam
                    cursor.execute("SHOW TABLES LIKE 'downloads_soundcloud_accounts'")
                    if cursor.fetchone():
                        # Search by name match in sc accounts
                        query = "SELECT name, soundcloud_id FROM downloads_soundcloud_accounts WHERE name = %s OR name = %s"
                        cursor.execute(query, (artist_name, artist_name.replace(' ', '-').lower()))
                        row = cursor.fetchone()
                        if row:
                            sc_account = row[0]
            except Exception as e:
                self.logger.debug(f"Could not search SoundCloud accounts in DB: {e}")

        if sc_account:
            # We don't have a direct API to get the avatar without a client ID, 
            # but we can try to use the SoundCloud mobile site or similar if we really wanted to.
            # However, for now, let's assume we might have the avatar URL if we store it, 
            # or we use a placeholder if we can't fetch it easily.
            
            # Actually, yt-dlp can get it.
            # But let's keep it simple: if we don't have an easy way, we skip for now 
            # or just provide the account link as metadata.
            pass

        return candidates
