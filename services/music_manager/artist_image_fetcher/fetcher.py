import logging
import os
from datetime import datetime

import pymysql.cursors
from dotenv import load_dotenv

from services.common.Helpers.DatabaseConnector import DatabaseConnector

from .matcher import ArtistMatcher
from .normalizer import ArtistNameNormalizer
from .providers.base import ProviderUnavailable
from .providers.lastfm import LastFmArtistImageProvider
from .providers.musicbrainz import MusicBrainzArtistProvider
from .providers.soundcloud import SoundCloudArtistImageProvider
from .providers.spotify import SpotifyArtistImageProvider
from .storage import ImageDownloader, ImageStorage

load_dotenv()


class ArtistImageFetcher:
    def __init__(self, db_conn=None):
        self.db_conn = db_conn or DatabaseConnector().connect()
        self.logger = logging.getLogger(__name__)
        self.normalizer = ArtistNameNormalizer()
        self.matcher = ArtistMatcher(self.db_conn)
        storage_path = os.getenv('ARTIST_IMAGE_STORAGE_PATH') or os.getenv('STORAGE_PATH') or '/mnt/music/artists'
        public_base_url = os.getenv('ARTIST_IMAGE_PUBLIC_BASE_URL', '/media/artist-images')
        self.storage = ImageStorage(storage_path, public_base_url)
        self.downloader = ImageDownloader()
        self.mb_provider = MusicBrainzArtistProvider()
        # SoundCloud is a stub that has never produced a candidate, so a run with only
        # SoundCloud is a blind run -- see `configured_providers`.
        self.providers = [
            SpotifyArtistImageProvider(),
            SoundCloudArtistImageProvider(self.db_conn),
            LastFmArtistImageProvider(),
        ]
        enabled_providers = [p.name for p in self.configured_providers]
        if enabled_providers:
            self.logger.info(f'ArtistImageFetcher initialized with providers: {enabled_providers}')
        else:
            self.logger.error(
                'ArtistImageFetcher has no configured image provider: set the Spotify client id and '
                'secret (Beheer > Config, or SPOTIFY_CLIENT_ID/SPOTIFY_CLIENT_SECRET). Nothing will be '
                'fetched and no artist will be marked as failed.'
            )

    @property
    def configured_providers(self):
        """The providers that can actually answer.

        Only these are asked, and only a run that has at least one records `failed` for an
        artist. Between 2026-08-22 and 2026-09-21 production ran with none -- the image no
        longer carried the .env that held the Spotify credentials -- and every one of the
        45.000 artists it asked about was written down as unfindable.
        """
        return [p for p in self.providers if p.configured and p.name != 'soundcloud']

    @property
    def blind(self):
        """True when no provider is configured: a run that can find nothing, whoever it asks."""
        return not self.configured_providers

    def fetch_for_artist(self, artist_id, artist_name=None, force_refresh=False):
        if not artist_name:
            with self.db_conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(
                    'SELECT id, name, mbid, primary_image_id FROM library_artists WHERE id = %s', (artist_id,)
                )
                artist = cursor.fetchone()
                if not artist:
                    self.logger.error(f'Artist with ID {artist_id} not found')
                    return False
                artist_name = artist['name']
                mbid = artist['mbid']
                primary_image_id = artist['primary_image_id']
        else:
            with self.db_conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute('SELECT id, mbid, primary_image_id FROM library_artists WHERE id = %s', (artist_id,))
                res = cursor.fetchone()
                mbid = res['mbid'] if res else None
                primary_image_id = res['primary_image_id'] if res else None
        if primary_image_id and (not force_refresh):
            self.logger.info(f'Artist {artist_name} already has a primary image. Skipping.')
            return True
        if self.blind:
            # No verdict without a witness: the status is left exactly as it was.
            self.logger.warning(f'No image provider configured; not looking up {artist_name}')
            return False
        self.logger.info(f'Fetching images for artist: {artist_name} (ID: {artist_id})')
        external_ids = self._get_external_ids(artist_id)
        mb_metadata = self.mb_provider.get_artist_metadata(artist_name, mbid)
        if mb_metadata:
            if not mbid:
                mbid = mb_metadata['mbid']
                self._update_artist_mbid(artist_id, mbid)
            for source, sid in mb_metadata['external_ids'].items():
                if source not in external_ids:
                    external_ids[source] = sid
                    self._save_external_id(artist_id, source, sid)
        candidates = []
        unavailable = []
        target_artist = {'id': artist_id, 'name': artist_name, 'mbid': mbid}
        for provider in self.configured_providers:
            try:
                provider_candidates = provider.get_artist_images(artist_name, mbid, external_ids)
                self.logger.info(
                    f'Provider {provider.name} found {len(provider_candidates)} candidates for {artist_name}'
                )
                for cand in provider_candidates:
                    cand['confidence'] = self.matcher.calculate_confidence(target_artist, cand)
                    candidates.append(cand)
            except ProviderUnavailable as e:
                self.logger.warning(f'Provider {provider.name} could not answer for {artist_name}: {e}')
                unavailable.append(provider.name)
            except Exception as e:
                # A provider that blew up did not look either.
                self.logger.error(f'Provider {provider.name} failed for {artist_name}: {e}')
                unavailable.append(provider.name)
        source_priority = {'spotify': 1, 'soundcloud': 2, 'lastfm': 3, 'musicbrainz': 4}
        candidates.sort(key=lambda x: (x['confidence'], -source_priority.get(x['source'], 99)), reverse=True)
        best_candidate = None
        for cand in candidates:
            if self.matcher.is_candidate(cand['confidence']):
                best_candidate = cand
                break
        if not best_candidate:
            if unavailable:
                # Somebody who could have known did not answer: not a verdict. The artist
                # keeps its status and is asked about again on the next run.
                self.logger.info(f'No candidates for {artist_name} while {unavailable} could not answer; deferred.')
                return False
            self.logger.info(f'No good candidates found for {artist_name}.')
            self._update_artist_image_status(artist_id, 'failed')
            return False
        try:
            if 'image_data' in best_candidate and best_candidate['image_data']:
                image_data = best_candidate['image_data']
            else:
                image_data = self.downloader.download(best_candidate['url'])
            if not image_data:
                raise Exception('Failed to download image data')
            image_meta = self.storage.save_image(artist_id, best_candidate['source'], image_data)
            image_id = self._save_image_to_db(artist_id, best_candidate, image_meta)
            self._set_primary_image(artist_id, image_id)
            if best_candidate.get('source_id') and best_candidate['source'] not in external_ids:
                self._save_external_id(artist_id, best_candidate['source'], best_candidate['source_id'])
            self._update_manifest(artist_id, artist_name, best_candidate, image_meta)
            return True
        except Exception as e:
            self.logger.error(f'Failed to save image for {artist_name}: {e}')
            self._update_artist_image_status(artist_id, 'failed')
            return False

    def _get_external_ids(self, artist_id):
        ids = {}
        with self.db_conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute('SELECT source, external_id FROM artist_external_ids WHERE artist_id = %s', (artist_id,))
            for row in cursor.fetchall():
                ids[row['source']] = row['external_id']
        return ids

    def _save_external_id(self, artist_id, source, external_id):
        with self.db_conn.cursor() as cursor:
            query = '\n                INSERT INTO artist_external_ids (artist_id, source, external_id, created_at)\n                VALUES (%s, %s, %s, NOW())\n                ON DUPLICATE KEY UPDATE updated_at = NOW()\n            '
            cursor.execute(query, (artist_id, source, external_id))
        self.db_conn.commit()

    def _update_artist_mbid(self, artist_id, mbid):
        with self.db_conn.cursor() as cursor:
            cursor.execute('UPDATE library_artists SET mbid = %s WHERE id = %s', (mbid, artist_id))
        self.db_conn.commit()

    def _save_image_to_db(self, artist_id, candidate, meta):
        with self.db_conn.cursor() as cursor:
            query = '\n                INSERT INTO library_artist_images\n                (artist_id, source, source_id, original_url, cached_path, public_path, width, height, mime_type, file_size, confidence, created_at)\n                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())\n            '
            cursor.execute(
                query,
                (
                    artist_id,
                    candidate['source'],
                    candidate['source_id'],
                    candidate.get('url'),
                    meta['cached_path'],
                    meta['public_path'],
                    meta['width'],
                    meta['height'],
                    meta['mime_type'],
                    meta['file_size'],
                    candidate['confidence'],
                ),
            )
            image_id = cursor.lastrowid
        self.db_conn.commit()
        return image_id

    def _set_primary_image(self, artist_id, image_id):
        with self.db_conn.cursor() as cursor:
            cursor.execute('UPDATE library_artist_images SET is_primary = 0 WHERE artist_id = %s', (artist_id,))
            cursor.execute('UPDATE library_artist_images SET is_primary = 1 WHERE id = %s', (image_id,))
            cursor.execute(
                "\n                UPDATE library_artists\n                SET primary_image_id = %s, image_updated_at = NOW(), image_status = 'active'\n                WHERE id = %s\n            ",
                (image_id, artist_id),
            )
        self.db_conn.commit()

    def _update_artist_image_status(self, artist_id, status):
        with self.db_conn.cursor() as cursor:
            cursor.execute(
                'UPDATE library_artists SET image_status = %s, image_updated_at = NOW() WHERE id = %s',
                (status, artist_id),
            )
        self.db_conn.commit()

    def _update_manifest(self, artist_id, artist_name, candidate, meta):
        import json

        manifest_path = os.path.join(self.storage.storage_path, 'manifest.json')
        manifest = []
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path) as f:
                    manifest = json.load(f)
            except (OSError, ValueError):
                manifest = []
        manifest = [e for e in manifest if e['artist_id'] != artist_id]
        manifest.append(
            {
                'artist_id': artist_id,
                'name': artist_name,
                'image': meta['public_path'],
                'primary_jpg': f'{self.storage.public_base_url}/{artist_id}/primary.jpg',
                'thumb_160': f'{self.storage.public_base_url}/{artist_id}/thumb_160.jpg',
                'source': candidate['source'],
                'confidence': candidate['confidence'],
                'updated_at': datetime.now().isoformat(),
            }
        )
        try:
            with open(manifest_path, 'w') as f:
                json.dump(manifest, f, indent=2)
        except Exception as e:
            self.logger.error(f'Failed to update manifest: {e}')
