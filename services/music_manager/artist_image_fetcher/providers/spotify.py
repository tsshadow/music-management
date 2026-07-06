import os
import requests
import logging
from .base import ArtistImageProvider

class SpotifyArtistImageProvider(ArtistImageProvider):
    TOKEN_URL = 'https://accounts.spotify.com/api/token'
    SEARCH_URL = 'https://api.spotify.com/v1/search'

    def __init__(self, client_id=None, client_secret=None):
        self.client_id = client_id or os.getenv('SPOTIFY_CLIENT_ID')
        self.client_secret = client_secret or os.getenv('SPOTIFY_CLIENT_SECRET')
        self._token = None
        self.logger = logging.getLogger(__name__)
        if not self.client_id or not self.client_secret:
            self.logger.warning("Spotify API credentials (SPOTIFY_CLIENT_ID/SECRET) not found. Spotify provider will be disabled.")

    @property
    def name(self):
        return "spotify"

    def _get_token(self):
        if self._token:
            return self._token
        if not self.client_id or not self.client_secret:
            return None
        try:
            resp = requests.post(self.TOKEN_URL, data={'grant_type': 'client_credentials'}, 
                                 auth=(self.client_id, self.client_secret), timeout=5)
            if resp.status_code == 200:
                self._token = resp.json().get('access_token')
        except Exception as e:
            self.logger.error('Spotify token retrieval failed: %s', e)
        return self._token

    def get_artist_images(self, artist_name, mbid=None, external_ids=None):
        token = self._get_token()
        if not token:
            return []

        candidates = []
        try:
            # If we have a spotify_id in external_ids, we could use that directly
            spotify_id = external_ids.get('spotify') if external_ids else None
            
            if spotify_id:
                # Direct lookup
                url = f"https://api.spotify.com/v1/artists/{spotify_id}"
                response = requests.get(url, headers={'Authorization': f'Bearer {token}'}, timeout=5)
            else:
                # Search
                params = {'q': artist_name, 'type': 'artist', 'limit': 5}
                response = requests.get(self.SEARCH_URL, params=params, 
                                        headers={'Authorization': f'Bearer {token}'}, timeout=5)

            if response.status_code != 200:
                return []

            data = response.json()
            artists = [data] if spotify_id else data.get('artists', {}).get('items', [])

            for artist in artists:
                images = artist.get('images', [])
                for img in images:
                    candidates.append({
                        'source': self.name,
                        'source_id': artist.get('id'),
                        'url': img.get('url'),
                        'width': img.get('width'),
                        'height': img.get('height'),
                        'confidence': 0, # Will be calculated by matcher
                        'metadata': {
                            'artist_name': artist.get('name'),
                            'popularity': artist.get('popularity'),
                            'followers': artist.get('followers', {}).get('total')
                        }
                    })
        except Exception as e:
            self.logger.error('Spotify artist image lookup failed: %s', e)

        return candidates
