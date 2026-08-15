import logging
import time

import requests
from requests.exceptions import Timeout

from .base import ArtistImageProvider


class MusicBrainzArtistProvider(ArtistImageProvider):
    API_URL = 'https://musicbrainz.org/ws/2/artist'
    _last_call_time = 0
    _min_delay = 1.1
    # (connect, read). musicbrainz.org answers a search in well under a second when
    # it is healthy and in ten-plus seconds when it is not; a flat 5s turned every
    # slow spell into a logged failure. Connecting is still expected to be quick.
    _timeout = (5, 20)
    _attempts = 2
    _retry_backoff = 2.0

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    @property
    def name(self):
        return 'musicbrainz'

    def _rate_limit(self):
        elapsed = time.time() - MusicBrainzArtistProvider._last_call_time
        if elapsed < self._min_delay:
            time.sleep(self._min_delay - elapsed)
        MusicBrainzArtistProvider._last_call_time = time.time()

    def get_artist_images(self, artist_name, mbid=None, external_ids=None):
        return []

    def _get(self, url, params, headers):
        """GET with one retry, because a MusicBrainz timeout is usually transient.

        Only timeouts are retried: an HTTP error or a malformed body will not fix
        itself, and the caller treats both as "no metadata" anyway.
        """
        last_timeout = None
        for attempt in range(self._attempts):
            if attempt:
                time.sleep(self._retry_backoff * attempt)
                self._rate_limit()
            try:
                return requests.get(url, params=params, headers=headers, timeout=self._timeout)
            except Timeout as timeout:
                last_timeout = timeout
                self.logger.warning('MusicBrainz timed out (attempt %d/%d): %s',
                                    attempt + 1, self._attempts, timeout)
        raise last_timeout

    def get_artist_metadata(self, artist_name, mbid=None):
        self._rate_limit()
        try:
            headers = {'User-Agent': 'MusicManagementArtistImageFetcher/1.0 (https://github.com/muma/music-management)'}
            if mbid:
                url = f'{self.API_URL}/{mbid}'
                params = {'inc': 'url-rels', 'fmt': 'json'}
            else:
                url = self.API_URL
                params = {'query': f'artist:{artist_name}', 'fmt': 'json', 'limit': 1}
            response = self._get(url, params, headers)
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
            metadata = {'mbid': artist.get('id'), 'name': artist.get('name'), 'external_ids': {}}
            relations = artist.get('relations', [])
            for rel in relations:
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
        except Timeout as e:
            # Already reported per attempt above. An unreachable MusicBrainz is a
            # third party being slow, not a fault in this service, so it does not
            # earn an ERROR line per artist.
            self.logger.warning('MusicBrainz metadata lookup timed out, giving up: %s', e)
            return None
        except Exception as e:
            self.logger.error('MusicBrainz metadata lookup failed: %s', e)
            return None