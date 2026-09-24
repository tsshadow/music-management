import logging
import time

import requests

from .base import ArtistImageProvider, ProviderRateLimited, ProviderUnavailable, credential


class SpotifyArtistImageProvider(ArtistImageProvider):
    TOKEN_URL = 'https://accounts.spotify.com/api/token'
    SEARCH_URL = 'https://api.spotify.com/v1/search'
    # Used when the token response omits expires_in; Spotify documents 3600 s.
    DEFAULT_TOKEN_LIFETIME = 3600
    # Renew this many seconds before the token would expire.
    TOKEN_REFRESH_MARGIN = 60
    # Wait this long after a 429 that carries no usable Retry-After header.
    DEFAULT_RETRY_AFTER = 30
    # Never wait longer than this on one 429, whatever the header says.
    MAX_RETRY_AFTER = 600

    def __init__(self, client_id=None, client_secret=None):
        self.client_id = client_id or credential('spotify_client_id', 'SPOTIFY_CLIENT_ID')
        self.client_secret = client_secret or credential('spotify_client_secret', 'SPOTIFY_CLIENT_SECRET')
        self._token = None
        self._token_expires_at = 0.0
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

    def _retry_after(self, response):
        """Seconds to wait after a 429, read from `Retry-After` and bounded.

        Spotify sends whole seconds. A missing, unreadable or HTTP-date value falls
        back to `DEFAULT_RETRY_AFTER`; the result lies between 1 s and
        `MAX_RETRY_AFTER`, so a hostile or broken header cannot park the run for a day.
        """
        headers = getattr(response, 'headers', None) or {}
        try:
            value = headers.get('Retry-After')
        except AttributeError:
            value = None
        seconds = float(self.DEFAULT_RETRY_AFTER)
        if isinstance(value, (str, int, float)) and not isinstance(value, bool):
            try:
                seconds = float(value)
            except ValueError:
                seconds = float(self.DEFAULT_RETRY_AFTER)
        return min(max(seconds, 1.0), float(self.MAX_RETRY_AFTER))

    def _rate_limited(self, what, response):
        """The ProviderRateLimited for a 429 on `what`, carrying the bounded wait."""
        retry_after = self._retry_after(response)
        return ProviderRateLimited(f'Spotify: {what} answered 429 (retry after {retry_after:.0f}s)', retry_after)

    def _get_token(self):
        """Return a valid client-credentials access token, requesting a new one when needed.

        Spotify's client-credentials tokens expire after `expires_in` seconds (3600 in
        practice). The token is renewed `TOKEN_REFRESH_MARGIN` seconds before that, so a
        bulk run over tens of thousands of artists does not turn every lookup after the
        first hour into a 401.
        """
        if self._token and time.monotonic() < self._token_expires_at:
            return self._token
        self._token = None
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
        if resp.status_code == 429:
            raise self._rate_limited('token request', resp)
        if resp.status_code != 200:
            raise ProviderUnavailable(f'Spotify: token request answered {resp.status_code}')
        try:
            body = resp.json()
            token = body.get('access_token')
            expires_in = body.get('expires_in')
        except (ValueError, AttributeError) as e:
            raise ProviderUnavailable(f'Spotify: could not read the token response: {e}') from e
        if not token:
            raise ProviderUnavailable('Spotify: token response carried no access_token')
        try:
            lifetime = float(expires_in) if expires_in is not None else self.DEFAULT_TOKEN_LIFETIME
        except (TypeError, ValueError):
            lifetime = self.DEFAULT_TOKEN_LIFETIME
        self._token = token
        self._token_expires_at = time.monotonic() + max(lifetime - self.TOKEN_REFRESH_MARGIN, 0)
        return self._token

    def _request(self, url, params=None):
        """GET `url` with the bearer token; on a 401 renew the token once and retry.

        A 401 mid-run means the token expired or was revoked early. One renewal is
        worth trying; a second 401 is returned to the caller, which treats it as
        Spotify not answering.
        """
        token = self._get_token()
        response = requests.get(url, params=params, headers={'Authorization': f'Bearer {token}'}, timeout=5)
        if response.status_code == 401:
            self._token = None
            token = self._get_token()
            response = requests.get(url, params=params, headers={'Authorization': f'Bearer {token}'}, timeout=5)
        return response

    def get_artist_images(self, artist_name, mbid=None, external_ids=None):
        """Return image candidates from Spotify, by known id or by name search."""
        self._get_token()
        candidates = []
        spotify_id = external_ids.get('spotify') if external_ids else None
        try:
            if spotify_id:
                response = self._request(f'https://api.spotify.com/v1/artists/{spotify_id}')
            else:
                response = self._request(self.SEARCH_URL, params={'q': artist_name, 'type': 'artist', 'limit': 5})
        except ProviderUnavailable:
            raise
        except Exception as e:
            raise ProviderUnavailable(f'Spotify: lookup failed: {e}') from e
        # A known artist id that Spotify no longer has is a real answer; anything else
        # that is not a 200 -- 401 on a revoked credential, 429 on the rate limit, a
        # 5xx -- is Spotify not answering, and the artist must not be judged on it.
        if response.status_code == 404 and spotify_id:
            return []
        if response.status_code == 429:
            raise self._rate_limited('lookup', response)
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
