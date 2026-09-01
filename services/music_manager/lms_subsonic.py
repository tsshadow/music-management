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


def lms_base_url() -> str:
    url = os.getenv('LMS_URL') or (os.getenv('LMS_HOSTS') or '').split(',')[0].strip()
    if not url:
        url = 'http://lms:5082'
    if not url.startswith('http'):
        url = 'http://' + url
    return url.rstrip('/')


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
