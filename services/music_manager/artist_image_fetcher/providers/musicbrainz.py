import requests
import logging
import time
from .base import ArtistImageProvider

class MusicBrainzArtistProvider(ArtistImageProvider):
    API_URL = 'https://musicbrainz.org/ws/2/artist'
    _last_call_time = 0
    _min_delay = 1.1 # 1 request per second + buffer

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    @property
    def name(self):
        return "musicbrainz"

    def _rate_limit(self):
        elapsed = time.time() - MusicBrainzArtistProvider._last_call_time
        if elapsed < self._min_delay:
            time.sleep(self._min_delay - elapsed)
        MusicBrainzArtistProvider._last_call_time = time.time()

    def get_artist_images(self, artist_name, mbid=None, external_ids=None):
        # MusicBrainz is mainly for metadata, but we can check for links
        # Returns empty image list but can be used to enrich external_ids
        return []

    def get_artist_metadata(self, artist_name, mbid=None):
        self._rate_limit()
        try:
            headers = {'User-Agent': 'MusicManagementArtistImageFetcher/1.0 (https://github.com/tsshadow/music-management)'}
            if mbid:
                url = f"{self.API_URL}/{mbid}"
                params = {'inc': 'url-rels', 'fmt': 'json'}
            else:
                url = self.API_URL
                params = {'query': f'artist:{artist_name}', 'fmt': 'json', 'limit': 1}

            response = requests.get(url, params=params, headers=headers, timeout=5)
            if response.status_code != 200:
                return None

            data = response.json()
            if mbid:
                artist = data
            else:
                artists = data.get('artists', [])
                if not artists:
                    return None
                artist = artists[0]

            metadata = {
                'mbid': artist.get('id'),
                'name': artist.get('name'),
                'external_ids': {}
            }

            # Extract external IDs from relations
            relations = artist.get('relations', [])
            for rel in relations:
                target_type = rel.get('target-type')
                url_data = rel.get('url', {})
                resource = url_data.get('resource', '')

                if 'spotify.com/artist/' in resource:
                    spotify_id = resource.split('/')[-1].split('?')[0]
                    metadata['external_ids']['spotify'] = spotify_id
                elif 'soundcloud.com/' in resource:
                    sc_id = resource.split('/')[-1]
                    metadata['external_ids']['soundcloud'] = sc_id
                elif 'last.fm/music/' in resource:
                    lfm_name = resource.split('/')[-1]
                    metadata['external_ids']['lastfm'] = lfm_name

            return metadata
        except Exception as e:
            self.logger.error('MusicBrainz metadata lookup failed: %s', e)
            return None
