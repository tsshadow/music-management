import errno
import logging
import os
import threading

import pymysql.cursors
from dotenv import load_dotenv

from services.common.Helpers.DatabaseConnector import DatabaseConnector
from services.music_manager.database import transaction

from .matcher import ArtistMatcher
from .normalizer import ArtistNameNormalizer
from .providers.base import ProviderRateLimited, ProviderUnavailable, forget_logged_once, log_once
from .providers.lastfm import LastFmArtistImageProvider
from .providers.musicbrainz import MusicBrainzArtistProvider
from .providers.soundcloud import SoundCloudArtistImageProvider
from .providers.spotify import SpotifyArtistImageProvider
from .storage import ImageDownloader, ImageStorage

load_dotenv()

# errno values that mean the image directory itself cannot take a file: not one
# artist's problem but the whole run's, and the one storage failure worth an ERROR.
STORAGE_UNWRITABLE_ERRNOS = frozenset({errno.EACCES, errno.EPERM, errno.EROFS, errno.ENOSPC, errno.EDQUOT})

# Set by the manager's "clear portrait" action; the bulk run and a plain single-artist
# fetch leave such an artist alone.
CLEARED_STATUS = 'cleared'


class ArtistImageFetcher:
    """Finds, downloads and stores a portrait per artist, one artist at a time.

    A bulk run calls `start_run()`, then `fetch_for_artist()` per artist, then
    `log_run_summary()`. Per-artist trouble -- a provider (MusicBrainz included) that
    could not answer, a portrait that could not be downloaded or saved -- is logged at
    INFO and counted; the run as a whole gets at most two WARNINGs (the first rate
    limit, and the summary), because every WARNING is a push on the phone. The one
    ERROR a run can add is an image directory that cannot be written, logged once.
    """

    def __init__(self, db_conn=None, stop_event=None):
        self.db_conn = db_conn or DatabaseConnector().connect()
        self.logger = logging.getLogger(__name__)
        # Set it to cut a rate-limit pause short; the paused artist is then deferred.
        self.stop_event = stop_event or threading.Event()
        self.start_run()
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
        # Logged once per process at full level (then DEBUG), like the providers' own
        # complaints: the manager builds a fetcher for every single-artist fetch.
        if enabled_providers:
            forget_logged_once('no-image-provider')
            self.logger.info(f'ArtistImageFetcher initialized with providers: {enabled_providers}')
        else:
            log_once(
                self.logger,
                'no-image-provider',
                logging.ERROR,
                'ArtistImageFetcher has no configured image provider: set the Spotify client id and '
                'secret (Management > Configuration, or SPOTIFY_CLIENT_ID/SPOTIFY_CLIENT_SECRET). Nothing will be '
                'fetched and no artist will be marked as failed.',
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

    def start_run(self):
        """Reset the per-run counters that `log_run_summary()` reports on."""
        self.run_stats = {
            'deferred': 0,
            'rate_limit_pauses': 0,
            'pause_seconds': 0.0,
            # Provider name -> how many times it could not answer for an artist.
            'provider_failures': {},
            # Portraits a provider found that could not be downloaded or saved.
            'download_failures': 0,
        }
        self._rate_limit_warned = False
        self._storage_error_logged = False

    def log_run_summary(self):
        """Log one line about the run and return its counters.

        WARNING when something was deferred, a download failed or the run had to
        pause, INFO otherwise. This is the only per-run WARNING besides the first rate
        limit. Provider non-answers alone do not raise it: a MusicBrainz timeout costs
        the artist its external ids, not its lookup.
        """
        stats = dict(self.run_stats)
        stats['provider_failures'] = dict(self.run_stats['provider_failures'])
        message = f'Artist image run: {self.format_run_summary(stats)}'
        if stats['deferred'] or stats['rate_limit_pauses'] or stats['download_failures']:
            self.logger.warning(message)
        else:
            self.logger.info(message)
        return stats

    @staticmethod
    def format_run_summary(stats):
        """One line with every run counter, as `log_run_summary()` logs it."""
        failures = stats.get('provider_failures') or {}
        per_provider = ', '.join(f'{name} {count}' for name, count in sorted(failures.items())) or 'none'
        return (
            f"{stats['deferred']} artist(s) deferred because a provider could not answer, "
            f"{stats['rate_limit_pauses']} rate-limit pause(s), {stats['pause_seconds']:.0f}s paused in total, "
            f"{stats['download_failures']} image download(s) failed, "
            f'provider non-answers: {per_provider}'
        )

    def _count_provider_failure(self, provider_name):
        """Count one non-answer of `provider_name` for the run summary."""
        failures = self.run_stats['provider_failures']
        failures[provider_name] = failures.get(provider_name, 0) + 1

    def _pause_for_rate_limit(self, provider_name, artist_name, retry_after):
        """Pause the whole run for `retry_after` seconds; False when stopped meanwhile.

        The first rate limit of a run is a WARNING, every later one INFO: the summary
        at the end carries the count and the total time.
        """
        self.run_stats['rate_limit_pauses'] += 1
        self.run_stats['pause_seconds'] += retry_after
        message = f'Provider {provider_name} rate limited the run at {artist_name}; pausing {retry_after:.0f}s'
        if self._rate_limit_warned:
            self.logger.info(message)
        else:
            self._rate_limit_warned = True
            self.logger.warning(f'{message} (further rate limits in this run are logged at INFO)')
        return not self.stop_event.wait(retry_after)

    def _ask_provider(self, provider, artist_name, mbid, external_ids):
        """Ask one provider for candidates; after a rate limit, pause and ask once more.

        Raises ProviderUnavailable when the provider still cannot answer, or when the
        run was stopped during the pause.
        """
        return self._with_rate_limit_pause(
            provider.name, artist_name, lambda: provider.get_artist_images(artist_name, mbid, external_ids)
        )

    def _with_rate_limit_pause(self, provider_name, artist_name, call):
        """Run `call`; after a rate limit, pause the run and run it once more."""
        try:
            return call()
        except ProviderRateLimited as e:
            if not self._pause_for_rate_limit(provider_name, artist_name, e.retry_after):
                raise ProviderUnavailable(f'{provider_name}: stopped while waiting out a rate limit') from e
        return call()

    def _musicbrainz_metadata(self, artist_name, mbid):
        """MusicBrainz metadata for one artist, or None when it has none or could not answer.

        A non-answer is logged at INFO and counted per provider: the artist is still
        looked up by name, only without the external ids MusicBrainz would have added.
        """
        try:
            return self._with_rate_limit_pause(
                'musicbrainz', artist_name, lambda: self.mb_provider.get_artist_metadata(artist_name, mbid)
            )
        except Exception as e:  # ProviderUnavailable, or a provider that blew up
            self.logger.info(f'MusicBrainz could not answer for {artist_name}: {e}')
            self._count_provider_failure('musicbrainz')
            return None

    def fetch_for_artist(self, artist_id, artist_name=None, force_refresh=False, override_cleared=False):
        """Look up, download and store a portrait for one artist; True when it has one.

        `force_refresh` looks up an artist that already has a primary image. An artist
        whose portrait was cleared by hand (`image_status = 'cleared'`) is left alone
        unless `override_cleared` is set: clearing is a curation decision, and the
        start-up bulk run used to undo it within a restart.
        """
        with self.db_conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                'SELECT id, name, mbid, primary_image_id, image_status FROM library_artists WHERE id = %s',
                (artist_id,),
            )
            artist = cursor.fetchone()
        if not artist_name:
            if not artist:
                self.logger.error(f'Artist with ID {artist_id} not found')
                return False
            artist_name = artist['name']
        mbid = artist.get('mbid') if artist else None
        primary_image_id = artist.get('primary_image_id') if artist else None
        image_status = artist.get('image_status') if artist else None
        if primary_image_id and (not force_refresh):
            self.logger.info(f'Artist {artist_name} already has a primary image. Skipping.')
            return True
        if image_status == CLEARED_STATUS and not override_cleared:
            self.logger.info(f'Portrait of {artist_name} was cleared by hand; not looking it up again.')
            return False
        if self.blind:
            # No verdict without a witness: the status is left exactly as it was.
            # INFO: construction already logged the missing provider as an ERROR once per process,
            # and a blind bulk run would otherwise repeat it per artist.
            self.logger.info(f'No image provider configured; not looking up {artist_name}')
            return False
        self.logger.info(f'Fetching images for artist: {artist_name} (ID: {artist_id})')
        external_ids = self._get_external_ids(artist_id)
        mb_metadata = self._musicbrainz_metadata(artist_name, mbid)
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
                provider_candidates = self._ask_provider(provider, artist_name, mbid, external_ids)
                self.logger.info(
                    f'Provider {provider.name} found {len(provider_candidates)} candidates for {artist_name}'
                )
                for cand in provider_candidates:
                    cand['confidence'] = self.matcher.calculate_confidence(target_artist, cand)
                    candidates.append(cand)
            except ProviderUnavailable as e:
                # INFO, not WARNING: one line per artist, and every WARNING is a push.
                # The run summary reports how many artists this deferred.
                self.logger.info(f'Provider {provider.name} could not answer for {artist_name}: {e}')
                self._count_provider_failure(provider.name)
                unavailable.append(provider.name)
            except Exception as e:
                # A provider that blew up did not look either. INFO for the same reason
                # as above; the summary counts it with the other non-answers.
                self.logger.info(f'Provider {provider.name} failed for {artist_name}: {e}')
                self._count_provider_failure(provider.name)
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
                self.run_stats['deferred'] += 1
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
                raise RuntimeError('Failed to download image data')
            image_meta = self.storage.save_image(artist_id, best_candidate['source'], image_data)
            image_id = self._save_image_to_db(artist_id, best_candidate, image_meta)
            self._set_primary_image(artist_id, image_id)
            if best_candidate.get('source_id') and best_candidate['source'] not in external_ids:
                self._save_external_id(artist_id, best_candidate['source'], best_candidate['source_id'])
            return True
        except Exception as e:
            # A provider did find the artist; what failed is the CDN, the disk or the
            # database. That is no verdict about the artist either, so the status stays
            # and the next run tries again -- `failed` would have hidden a findable
            # artist for ARTIST_IMAGE_RETRY_AFTER_DAYS over one network blip.
            self._record_download_failure(artist_name, e)
            return False

    def _record_download_failure(self, artist_name, error):
        """Count a portrait that could not be downloaded or saved, and log it.

        One artist's failure is INFO; the summary reports the count. An image directory
        that cannot be written is the whole run's failure: that is an ERROR, logged once
        per run, and every later artist hitting it is INFO again.
        """
        self.run_stats['download_failures'] += 1
        systemic = isinstance(error, OSError) and error.errno in STORAGE_UNWRITABLE_ERRNOS
        if systemic and not self._storage_error_logged:
            self._storage_error_logged = True
            self.logger.error(
                f'Artist image directory {self.storage.storage_path} cannot be written: {error} '
                '(further failures in this run are logged at INFO and counted in the summary)'
            )
            return
        self.logger.info(f'Failed to download or save the image for {artist_name}; deferred: {error}')

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
        """Flag `image_id` as the artist's primary image and point the artist at it, atomically.

        One transaction (bug report 115). On the pooled connection each UPDATE used to
        commit on its own, and on the CLI's plain connection a failure left the first
        UPDATEs pending until the next artist's commit published them -- either way the
        manager could flag one image while the artist pointed at another.
        """
        with transaction(self.db_conn), self.db_conn.cursor() as cursor:
            cursor.execute('UPDATE library_artist_images SET is_primary = 0 WHERE artist_id = %s', (artist_id,))
            cursor.execute('UPDATE library_artist_images SET is_primary = 1 WHERE id = %s', (image_id,))
            cursor.execute(
                "\n                UPDATE library_artists\n                SET primary_image_id = %s, image_updated_at = NOW(), image_status = 'active'\n                WHERE id = %s\n            ",
                (image_id, artist_id),
            )

    def _update_artist_image_status(self, artist_id, status):
        with self.db_conn.cursor() as cursor:
            cursor.execute(
                'UPDATE library_artists SET image_status = %s, image_updated_at = NOW() WHERE id = %s',
                (status, artist_id),
            )
        self.db_conn.commit()
