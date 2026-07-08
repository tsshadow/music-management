import os
import requests
import logging
from .base import ArtistImageProvider

class LastFmArtistImageProvider(ArtistImageProvider):
    API_URL = 'https://ws.audioscrobbler.com/2.0/'

    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv('LASTFM_API_KEY')
        self.logger = logging.getLogger(__name__)
        if not self.api_key:
            self.logger.warning("Last.fm API key (LASTFM_API_KEY) not found. Last.fm provider will be disabled.")

    @property
    def name(self):
        return "lastfm"

    def get_artist_images(self, artist_name, mbid=None, external_ids=None):
        if not self.api_key:
            return []

        candidates = []
        try:
            params = {
                'method': 'artist.getinfo',
                'artist': artist_name,
                'api_key': self.api_key,
                'format': 'json'
            }
            if mbid:
                params['mbid'] = mbid
                
            response = requests.get(self.API_URL, params=params, timeout=5)
            if response.status_code != 200:
                return []

            data = response.json()
            artist = data.get('artist', {})
            images = artist.get('image', [])
            
            # Last.fm returns images in different sizes: small, medium, large, extralarge, mega
            # We want the largest ones
            for img in images:
                if img.get('size') in ['extralarge', 'mega'] and img.get('#text'):
                    candidates.append({
                        'source': self.name,
                        'source_id': artist.get('mbid') or artist.get('name'),
                        'name': artist.get('name'),
                        'mbid': artist.get('mbid'),
                        'url': img.get('#text'),
                        'width': None, 
                        'height': None,
                        'confidence': 0,
                        'metadata': {
                            'artist_name': artist.get('name'),
                            'listeners': artist.get('stats', {}).get('listeners'),
                            'playcount': artist.get('stats', {}).get('playcount'),
                            'bio': artist.get('bio', {}).get('summary')
                        }
                    })
        except Exception as e:
            self.logger.error('Last.fm artist image lookup failed: %s', e)

        return candidates
