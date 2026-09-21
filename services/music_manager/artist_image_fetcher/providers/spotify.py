import logging

import requests

from .base import ArtistImageProvider, ProviderUnavailable, credential


class SpotifyArtistImageProvider(ArtistImageProvider):
    TOKEN_URL = 'https://accounts.spotify.com/api/token'
    SEARCH_URL = 'https://api.spotify.com/v1/search'

    def __init__(self, client_id=None, client_secret=None):
        self.client_id = client_id or credential('spotify_client_id', 'SPOTIFY_CLIENT_ID')
        self.client_secret = client_secret or credential('spotify_client_secret', 'SPOTIFY_CLIENT_SECRET')
        self._token = None
        self.logger = logging.getLogger(__name__)
        if not self.configured:
            self.logger.warning(
                'Spotify API credentials (SPOTIFY_CLIENT_ID/SECRET) not found. Spotify provider will be disabled.'
            )

    @property
    def name(self):
        return 'spotify'

    @property
    def configured(self):
        return bool(self.client_id and self.client_secret)

    def _get_token(self):
        if self._token:
            return self._token
        if not self.configured:
            raise ProviderUnavailable('Spotify: no client id/secret configured')
        try:
            resp = requests.post(
                self.TOKEN_URL,
                data={'grant_type': 'client_credentials'},
                auth=(self.client_id, self.client_secret),
                timeout=5,
            )
        except Exception as e:
            raise ProviderUnavailable(f'Spotify: token request failed: {e}') from e
        if resp.status_code != 200:
            raise ProviderUnavailable(f'Spotify: token request answered {resp.status_code}')
        self._token = resp.json().get('access_token')
        if not self._token:
            raise ProviderUnavailable('Spotify: token response carried no access_token')
        return self._token

    def get_artist_images(self, artist_name, mbid=None, external_ids=None):
        token = self._get_token()
        candidates = []
        try:
            spotify_id = external_ids.get('spotify') if external_ids else None
            if spotify_id:
                url = f'https://api.spotify.com/v1/artists/{spotify_id}'
                response = requests.get(url, headers={'Authorization': f'Bearer {token}'}, timeout=5)
            else:
                params = {'q': artist_name, 'type': 'artist', 'limit': 5}
                response = requests.get(
                    self.SEARCH_URL, params=params, headers={'Authorization': f'Bearer {token}'}, timeout=5
                )
        except Exception as e:
            raise ProviderUnavailable(f'Spotify: lookup failed: {e}') from e
        # A known artist id that Spotify no longer has is a real answer; anything else
        # that is not a 200 -- 401 on a revoked credential, 429 on the rate limit, a
        # 5xx -- is Spotify not answering, and the artist must not be judged on it.
        if response.status_code == 404 and spotify_id:
            return []
        if response.status_code != 200:
            raise ProviderUnavailable(f'Spotify: lookup answered {response.status_code}')
        try:
            data = response.json()
            artists = [data] if spotify_id else data.get('artists', {}).get('items', [])
            for artist in artists:
                images = artist.get('images', [])
                for img in images:
                    candidates.append(
                        {
                            'source': self.name,
                            'source_id': artist.get('id'),
                            'name': artist.get('name'),
                            'url': img.get('url'),
                            'width': img.get('width'),
                            'height': img.get('height'),
                            'confidence': 0,
                            'is_known_match': bool(spotify_id),
                            'popularity': artist.get('popularity'),
                            'genres': artist.get('genres'),
                            'metadata': {
                                'artist_name': artist.get('name'),
                                'popularity': artist.get('popularity'),
                                'followers': artist.get('followers', {}).get('total'),
                                'genres': artist.get('genres'),
                            },
                        }
                    )
        except (ValueError, AttributeError, TypeError) as e:
            raise ProviderUnavailable(f'Spotify: could not read the answer: {e}') from e
        return candidates
