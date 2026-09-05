"""Thin read-only client for LMS's Subsonic API, used by the radio scheduler.

Authentication uses the `apiKey` Subsonic parameter, which LMS resolves to a
user through its auth-token service (see SubsonicResource.cpp:517-519).
"""

import logging
import os

import requests

logger = logging.getLogger('music-manager.lms-subsonic')

CLIENT_NAME = 'muma-radio'
API_VERSION = '1.16.1'


class LmsNotConfigured(RuntimeError):
    """No LMS address is configured, so there is nothing safe to call."""


def lms_base_url() -> str:
    """Where to reach LMS, from the environment. Never guessed.

    This used to fall back to a hardcoded ``http://lms:5082``. On the deployment
    that is right -- ``lms`` is the container_name of the separately deployed LMS
    stack, on the shared ``music-management_db`` network -- and that is exactly
    what made it dangerous everywhere else: a bare hostname is resolved by
    whatever DNS the host has. On the office LAN ``lms`` resolves to
    192.0.2.27, so a container started without LMS configuration called
    *production* every five seconds, and neither end said so. Production's LMS
    logs the rejection without a client address, so it reads as a fault in
    production's own radio thread; it took reading the reverse proxy's access log
    to see the requests were coming from a developer workstation.

    ``MUMA_SERVER_HOSTS`` is read as well, because that is the variable compose
    actually sets for this service (``docker/docker-compose.yml``, with a comment
    explaining the ``lms:5082`` value). The old code did not read it, so the
    deployment was working by coincidence: the hardcoded default happened to
    equal the configured value.

    Raises ``LmsNotConfigured`` when nothing is set. The only caller reaches this
    through ``radio.py``, which already logs and skips the round, so an
    unconfigured environment now produces one clear message per attempt instead
    of silent traffic to someone else's server.
    """
    for name in ('LMS_URL', 'LMS_HOSTS', 'MUMA_SERVER_HOSTS'):
        url = (os.getenv(name) or '').split(',')[0].strip()
        if url:
            if not url.startswith('http'):
                url = 'http://' + url
            return url.rstrip('/')

    raise LmsNotConfigured(
        'No LMS address configured: set LMS_URL, LMS_HOSTS or MUMA_SERVER_HOSTS. '
        'There is deliberately no default -- a bare hostname like "lms" resolves '
        'through the host DNS and has reached production from a developer machine.'
    )


def _auth_params() -> dict:
    return {
        'apiKey': os.getenv('MUMA_SERVER_SUBSONIC_API_KEY') or os.getenv('LMS_SUBSONIC_API_KEY', ''),
        'v': API_VERSION,
        'c': CLIENT_NAME,
        'f': 'json',
    }


def normalize_song(song: dict):
    """Map a Subsonic `song` node to the radio timeline shape, or None if unusable."""
    track_id = song.get('id')
    duration = song.get('duration') or 0
    if not track_id or duration <= 0:
        return None
    return {
        'track_id': str(track_id),
        'title': song.get('title') or '',
        'artist': song.get('artist') or '',
        'album': song.get('album') or '',
        'cover_art': song.get('coverArt'),
        'duration_ms': int(duration) * 1000,
    }


# A radio channel's filter, as stored, keyed the way it reaches LMS. Anything
# absent or blank is not sent at all, which is what makes an empty filter mean
# "the whole library".
FILTER_FIELDS = {
    'label': 'label',
    'genre': 'genre',
    'artist': 'artist',
    'length': 'length',
    'year': 'year',
    'rating_min': 'ratingMin',
    'rating_max': 'ratingMax',
    'duration_min': 'durationMin',
    'duration_max': 'durationMax',
}


def build_filter_params(channel_filter: dict) -> dict:
    """Turn a stored channel filter into getSongsByFilter query parameters."""
    params = {}
    for key, param in FILTER_FIELDS.items():
        value = (channel_filter or {}).get(key)
        if value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
            if not value:
                continue
        params[param] = value
    # Only meaningful alongside a rating bound, and false is LMS's default, so
    # sending it unconditionally would be noise.
    if ('ratingMin' in params or 'ratingMax' in params) and (channel_filter or {}).get('include_unrated'):
        params['includeUnrated'] = 'true'
    return params


def fetch_candidate_tracks(channel_filter, size: int = 20, timeout: float = 10.0) -> list:
    """Fetch `size` playable tracks matching a channel filter.

    An empty filter draws from the whole library. Results come back randomised by
    LMS, so unlike the old getSongsByGenre path there is nothing to shuffle here.
    """
    params = _auth_params()
    params.update(build_filter_params(channel_filter))
    params['count'] = size

    response = requests.get(lms_base_url() + '/rest/getSongsByFilter', params=params, timeout=timeout)
    response.raise_for_status()
    body = response.json().get('subsonic-response') or {}
    if body.get('status') != 'ok':
        error = body.get('error') or {}
        raise RuntimeError(f"LMS returned status={body.get('status')} error={error.get('message')}")

    songs = (body.get('songsByFilter') or {}).get('song') or []
    if isinstance(songs, dict):
        songs = [songs]
    return [t for t in (normalize_song(s) for s in songs) if t]
