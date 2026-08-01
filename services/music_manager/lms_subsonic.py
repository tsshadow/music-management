"""Thin read-only client for LMS's Subsonic API, used by the radio scheduler.

Authentication uses the `apiKey` Subsonic parameter, which LMS resolves to a
user through its auth-token service (see SubsonicResource.cpp:517-519).
"""
import logging
import os
import random
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


def fetch_candidate_tracks(genre, size: int = 20, timeout: float = 10.0) -> list:
    """Fetch `size` playable tracks from LMS. Genre None means the whole library."""
    params = _auth_params()
    if genre:
        endpoint = '/rest/getSongsByGenre'
        params['genre'] = genre
        params['count'] = size
        # getSongsByGenre is not randomised server-side, so jump to a random
        # window and shuffle what comes back.
        params['offset'] = random.randint(0, 500)
        node_name = 'songsByGenre'
    else:
        endpoint = '/rest/getRandomSongs'
        params['size'] = size
        node_name = 'randomSongs'

    response = requests.get(lms_base_url() + endpoint, params=params, timeout=timeout)
    response.raise_for_status()
    body = response.json().get('subsonic-response') or {}
    if body.get('status') != 'ok':
        error = body.get('error') or {}
        raise RuntimeError(f"LMS returned status={body.get('status')} error={error.get('message')}")

    songs = (body.get(node_name) or {}).get('song') or []
    if isinstance(songs, dict):
        songs = [songs]
    tracks = [t for t in (normalize_song(s) for s in songs) if t]
    if genre:
        random.shuffle(tracks)
    return tracks
