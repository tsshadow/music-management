import logging
import requests
from typing import Optional

from api.config_store import ConfigStore


class DiscogsLookup:
    API_URL = "https://api.discogs.com/database/search"

    def __init__(self, token: Optional[str] = None, store: Optional[ConfigStore] = None):
        self.name = "Discogs"
        self._store = store or ConfigStore()
        self.token = token if token is not None else self._store.get("discogs_token")
        if token is None:
            self._store.subscribe("discogs_token", self._set_token)

    def _set_token(self, value: Optional[str]) -> None:
        self.token = value or ""

    def is_known_artist(self, name: str) -> bool:
        if not self.token:
            return False
        try:
            response = requests.get(
                self.API_URL,
                params={"q": name, "type": "artist", "token": self.token},
                timeout=5,
            )
            if response.status_code != 200:
                return False
            data = response.json()
            for result in data.get("results", []):
                if result.get("title", "").lower() == name.lower():
                    return True
        except Exception as e:
            logging.error("Discogs lookup failed: %s", e)
        return False


class MusicBrainzLookup:
    API_URL = "https://musicbrainz.org/ws/2/artist"

    def __init__(self):
        self.name = "MusicBrainz"
    def is_known_artist(self, name: str) -> bool:
        try:
            response = requests.get(
                self.API_URL,
                params={"query": name, "fmt": "json", "limit": 1},
                headers={"User-Agent": "MusicImporter/1.0 (codex@example.com)"},
                timeout=5,
            )
            if response.status_code != 200:
                return False
            data = response.json()
            for artist in data.get("artists", []):
                if artist.get("name", "").lower() == name.lower():
                    return True
        except Exception as e:
            logging.error("MusicBrainz lookup failed: %s", e)
        return False


class LastfmLookup:
    API_URL = "https://ws.audioscrobbler.com/2.0/"

    def __init__(self, api_key: Optional[str] = None, store: Optional[ConfigStore] = None):
        self.name = "Last.fm"
        self._store = store or ConfigStore()
        self.api_key = api_key if api_key is not None else self._store.get("lastfm_api_key")
        if api_key is None:
            self._store.subscribe("lastfm_api_key", self._set_api_key)

    def _set_api_key(self, value: Optional[str]) -> None:
        self.api_key = value or ""

    def is_known_artist(self, name: str) -> bool:
        if not self.api_key:
            return False
        try:
            response = requests.get(
                self.API_URL,
                params={
                    "method": "artist.getinfo",
                    "artist": name,
                    "api_key": self.api_key,
                    "format": "json",
                },
                timeout=5,
            )
            if response.status_code != 200:
                return False
            data = response.json()
            artist = data.get("artist")
            if artist and artist.get("name", "").lower() == name.lower():
                return True
        except Exception as e:
            logging.error("Last.fm lookup failed: %s", e)
        return False


class SpotifyLookup:
    TOKEN_URL = "https://accounts.spotify.com/api/token"
    SEARCH_URL = "https://api.spotify.com/v1/search"

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        store: Optional[ConfigStore] = None,
    ):
        self.name = "Spotify"
        self._store = store or ConfigStore()
        self.client_id = client_id if client_id is not None else self._store.get("spotify_client_id")
        self.client_secret = (
            client_secret if client_secret is not None else self._store.get("spotify_client_secret")
        )
        self._token: Optional[str] = None
        if client_id is None:
            self._store.subscribe("spotify_client_id", self._set_client_id)
        if client_secret is None:
            self._store.subscribe("spotify_client_secret", self._set_client_secret)

    def _get_token(self) -> Optional[str]:
        if self._token:
            return self._token
        if not self.client_id or not self.client_secret:
            return None
        try:
            resp = requests.post(
                self.TOKEN_URL,
                data={"grant_type": "client_credentials"},
                auth=(self.client_id, self.client_secret),
                timeout=5,
            )
            if resp.status_code == 200:
                self._token = resp.json().get("access_token")
        except Exception as e:
            logging.error("Spotify token retrieval failed: %s", e)
        return self._token

    def _set_client_id(self, value: Optional[str]) -> None:
        self.client_id = value or ""
        self._token = None

    def _set_client_secret(self, value: Optional[str]) -> None:
        self.client_secret = value or ""
        self._token = None

    def is_known_artist(self, name: str) -> bool:
        token = self._get_token()
        if not token:
            return False
        try:
            response = requests.get(
                self.SEARCH_URL,
                params={"q": name, "type": "artist", "limit": 1},
                headers={"Authorization": f"Bearer {token}"},
                timeout=5,
            )
            if response.status_code != 200:
                return False
            data = response.json()
            artists = data.get("artists", {}).get("items", [])
            for artist in artists:
                if artist.get("name", "").lower() == name.lower():
                    return True
        except Exception as e:
            logging.error("Spotify lookup failed: %s", e)
        return False


class ExternalArtistLookup:
    """Check if an artist exists on various external music services."""

    def __init__(self):
        store = ConfigStore()
        self.services = [
            DiscogsLookup(store=store),
            MusicBrainzLookup(),
            LastfmLookup(store=store),
            SpotifyLookup(store=store),
        ]

    def is_known_artist(self, name: str) -> bool:
        for service in self.services:
            try:
                if service.is_known_artist(name):
                    print(f"found at service: {service.name}")
                    return True
            except Exception as e:
                logging.error("Lookup error with %s: %s", service.__class__.__name__, e)
        return False
