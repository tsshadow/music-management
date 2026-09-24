import logging

import requests

from .base import ArtistImageProvider, ProviderUnavailable, credential

# Last.fm stopped serving artist photos in 2019; `artist.getinfo` now answers every
# artist with the same grey star placeholder, recognisable by this hash in its URL.
# Accepting it gave every artist with an MBID the same picture, scored +100 as a
# "known match".
LASTFM_PLACEHOLDER_HASH = '2a96cbd8b46e442fc41c2b86b821562f'


def is_placeholder_image(url):
    """Whether `url` is Last.fm's generic placeholder rather than a real artist photo."""
    return bool(url) and LASTFM_PLACEHOLDER_HASH in url


class LastFmArtistImageProvider(ArtistImageProvider):
    API_URL = 'https://ws.audioscrobbler.com/2.0/'

    def __init__(self, api_key=None):
        self.api_key = api_key or credential('lastfm_api_key', 'LASTFM_API_KEY')
        self.logger = logging.getLogger(__name__)
        if not self.configured:
            self.logger.warning('Last.fm API key (LASTFM_API_KEY) not found. Last.fm provider will be disabled.')

    @property
    def name(self):
        return 'lastfm'

    @property
    def configured(self):
        return bool(self.api_key)

    def get_artist_images(self, artist_name, mbid=None, external_ids=None):
        if not self.configured:
            raise ProviderUnavailable('Last.fm: no API key configured')
        candidates = []
        try:
            params = {'method': 'artist.getinfo', 'artist': artist_name, 'api_key': self.api_key, 'format': 'json'}
            if mbid:
                params['mbid'] = mbid
            response = requests.get(self.API_URL, params=params, timeout=5)
        except Exception as e:
            raise ProviderUnavailable(f'Last.fm: lookup failed: {e}') from e
        # Last.fm answers an unknown artist with 200 and an error body (code 6), so a
        # non-200 is the service or the key, never the artist.
        if response.status_code != 200:
            raise ProviderUnavailable(f'Last.fm: lookup answered {response.status_code}')
        try:
            data = response.json()
            artist = data.get('artist', {})
            images = artist.get('image', [])
            for img in images:
                url = img.get('#text')
                if is_placeholder_image(url):
                    continue
                if img.get('size') in ['extralarge', 'mega'] and url:
                    candidates.append(
                        {
                            'source': self.name,
                            'source_id': artist.get('mbid') or artist.get('name'),
                            'name': artist.get('name'),
                            'mbid': artist.get('mbid'),
                            'url': img.get('#text'),
                            'width': None,
                            'height': None,
                            'confidence': 0,
                            'is_known_match': bool(mbid),
                            'metadata': {
                                'artist_name': artist.get('name'),
                                'listeners': artist.get('stats', {}).get('listeners'),
                                'playcount': artist.get('stats', {}).get('playcount'),
                                'bio': artist.get('bio', {}).get('summary'),
                            },
                        }
                    )
        except (ValueError, AttributeError, TypeError) as e:
            raise ProviderUnavailable(f'Last.fm: could not read the answer: {e}') from e
        return candidates
