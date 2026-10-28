import logging
import time

import requests
from requests.exceptions import Timeout

from services.common.user_agent import build_user_agent

from .base import ArtistImageProvider, ProviderRateLimited, ProviderUnavailable, has_retry_after, parse_retry_after

USER_AGENT = build_user_agent('MusicManagementArtistImageFetcher', '1.0')


class MusicBrainzArtistProvider(ArtistImageProvider):
    """Metadata only: the MBID and the external ids MusicBrainz links an artist to."""

    API_URL = 'https://musicbrainz.org/ws/2/artist'
    _last_call_time = 0
    _min_delay = 1.1
    # (connect, read). Raising only the read half was not enough: measured against
    # musicbrainz.org on 2026-08-24 every failure landed at exactly 5.0s, which is the
    # connect half, and urllib3 reports it as "Read timed out. (read timeout=5)" -- the
    # wording says read, the number is the connect budget. Under load the host takes
    # seconds just to accept the connection, and a full search then answers in about
    # seven. Both halves now have room; a host that is genuinely down still fails fast
    # enough, because nothing waits on this.
    _timeout = (15, 30)
    _attempts = 2
    _retry_backoff = 2.0
    # Wait this long after a 429 that carries no usable Retry-After header.
    DEFAULT_RETRY_AFTER = 30
    # Never wait longer than this on one rate limit, whatever the header says.
    MAX_RETRY_AFTER = 600

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
        itself. Each attempt that times out is logged at INFO -- it is one artist, and
        every WARNING is a push on the phone; the fetcher's run summary counts the
        artists MusicBrainz could not answer for.
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
                self.logger.info('MusicBrainz timed out (attempt %d/%d): %s', attempt + 1, self._attempts, timeout)
        raise last_timeout

    def _check_status(self, response):
        """Raise for an answer that is MusicBrainz not answering; True for a 200.

        429 is a rate limit. MusicBrainz documents 503 as its rate-limit answer too, so
        a 503 that carries `Retry-After` is treated the same way; a bare 503 or any
        other 5xx is the service being down. Both are about the run, not the artist.
        Any other status (404 for an unknown MBID, 400 for a query it cannot parse) is
        a real answer: there is nothing to find, and False is returned.
        """
        status = response.status_code
        if status == 429 or (status == 503 and has_retry_after(response)):
            retry_after = parse_retry_after(response, self.DEFAULT_RETRY_AFTER, self.MAX_RETRY_AFTER)
            raise ProviderRateLimited(f'MusicBrainz: answered {status} (retry after {retry_after:.0f}s)', retry_after)
        if status >= 500:
            raise ProviderUnavailable(f'MusicBrainz: answered {status}')
        return status == 200

    def get_artist_metadata(self, artist_name, mbid=None):
        """MBID and external ids (Spotify, SoundCloud, Last.fm) for one artist.

        Returns None when MusicBrainz looked and found nothing. Raises
        ProviderRateLimited on a 429 (or a 503 with `Retry-After`), and
        ProviderUnavailable when it could not answer -- a timeout after every attempt,
        a transport error, a 5xx or an unreadable body. Nothing is logged above INFO
        here: the fetcher counts the non-answers into its run summary.
        """
        self._rate_limit()
        headers = {'User-Agent': USER_AGENT}
        if mbid:
            url = f'{self.API_URL}/{mbid}'
            params = {'inc': 'url-rels', 'fmt': 'json'}
        else:
            url = self.API_URL
            params = {'query': f'artist:{artist_name}', 'fmt': 'json', 'limit': 1}
        try:
            response = self._get(url, params, headers)
        except Timeout as e:
            raise ProviderUnavailable(f'MusicBrainz: timed out after {self._attempts} attempts: {e}') from e
        except Exception as e:
            raise ProviderUnavailable(f'MusicBrainz: lookup failed: {e}') from e
        if not self._check_status(response):
            return None
        try:
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
        except (ValueError, AttributeError, TypeError) as e:
            raise ProviderUnavailable(f'MusicBrainz: could not read the answer: {e}') from e
