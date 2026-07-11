import concurrent.futures
import logging
import math
import os
import random
import time
from pathlib import Path
from typing import Optional
from yt_dlp import YoutubeDL
from yt_dlp.postprocessor import FFmpegMetadataPP, EmbedThumbnailPP
from services.common.Helpers.DatabaseConnector import DatabaseConnector
from services.common.api.config_store import ConfigStore
from services.common.api.jobs import job_manager
from services.downloader.soundcloud.SoundcloudArchive import SoundcloudArchive
from .SoundcloudSongProcessor import SoundcloudSongProcessor


def get_accounts_from_db():
    try:
        db = DatabaseConnector().connect()
        with db.cursor() as cursor:
            cursor.execute('SELECT name FROM downloads_soundcloud_accounts')
            accounts = [row[0] for row in cursor.fetchall()]
        return accounts
    except Exception as e:
        logging.error(f'Failed to fetch SoundCloud accounts from DB: {e}')
        return []

class SoundcloudDownloader:
    """
    Downloads tracks from SoundCloud accounts listed in the database.

    Features:
    - Downloads only MP3 files that are not yet in the archive.
    - Embeds metadata and optionally thumbnails using FFmpeg.
    - Supports private/follower-only tracks using session cookies.
    - Handles batch downloads with configurable parallelism and throttling.
    - Skips tracks outside a configurable duration range.
    """

    def __init__(self, break_on_existing=True, **kwargs):
        self._config = ConfigStore()
        self.default_break_on_existing = break_on_existing
        self.redownload_mode = False
        self.batch_settings = {
            'max_workers': kwargs.get('max_workers', 1),
            'burst_size': kwargs.get('burst_size', 10),
            'min_pause': kwargs.get('min_pause', 1),
            'max_pause': kwargs.get('max_pause', 5)
        }
        self._subscriptions = []
        self._apply_config()
        for key in ['soundcloud_folder', 'soundcloud_archive', 'soundcloud_cookies', 'ffmpeg_location']:
            self._subscriptions.append(self._config.subscribe(key, lambda _value, k=key: self._apply_config()))

    def _match_filter(self, info):
        duration = info.get('duration')
        title = info.get('title', 'unknown')
        if not duration or duration < 60 or duration > 21600:
            logging.info(f"Skipping track '{title}' (duration: {duration}s)")
            return 'Outside allowed duration range'

        # Check if already in database archive to avoid downloading
        account_id = info.get('channel_id') or info.get('uploader_id')
        video_id = info.get('id')
        if not self.redownload_mode and account_id and video_id and SoundcloudArchive.exists(account_id, video_id):
            logging.info(f"Skipping track '{title}' (already in database archive)")
            return 'Already in database archive'

        return None

    def download_account(self, name: str, yt_dl_opts: dict=None):
        link = f'http://soundcloud.com/{name}/tracks'
        logging.info(f'Downloading from SoundCloud account: {name}')
        self.download_url(link, yt_dl_opts)
        logging.info(f'Finished downloading from: {name}')

    def download_url(self, url: str, yt_dl_opts: dict=None):
        """
        Download tracks from a specific SoundCloud URL (account, playlist, or single track).
        """
        for attempt in range(1, 4):
            try:
                with YoutubeDL(yt_dl_opts) as ydl:
                    ydl.add_post_processor(FFmpegMetadataPP(ydl))
                    ydl.add_post_processor(EmbedThumbnailPP(ydl))
                    ydl.add_post_processor(SoundcloudSongProcessor())
                    ydl.download([url])
                return
            except Exception as e:
                msg = str(e)
                if '429' in msg:
                    wait_time = random.randint(3600, 7200)
                    logging.warning(f'HTTP Error 429: Too Many Requests for {url}. Extremely long pause for {wait_time}s...')
                    time.sleep(wait_time)
                elif '403' in msg:
                    wait_time = random.randint(60, 600)
                    logging.warning(f'403 Forbidden for {url}. Pausing {wait_time}s before retry...')
                    time.sleep(wait_time)
                elif '404' in msg:
                    logging.info(f'Got 404 for {url} — skip.')
                    return
                elif 'already in the archive' in msg:
                    logging.info(f'Track for {url} already in archive — skipping.')
                    return
                else:
                    logging.warning(f'Attempt {attempt} failed for {url}: {e}', exc_info=True)
                    time.sleep(5 * attempt)
        logging.error(f'SoundCloud download failed for {url} after 3 attempts.')

    def run(self, account: str='', break_on_existing_arg: Optional[bool]=None, redownload: bool=False):
        if not getattr(self, 'downloader_config', {}).get('enabled', True):
            logging.warning('SoundCloud soundcloud is not configured; skipping run().')
            return
        
        self.redownload_mode = redownload

        # Defensive: initial wait up to 1 minute
        init_wait = random.randint(5, 60)
        logging.info(f'Defensive start: waiting {init_wait}s before first download...')
        time.sleep(init_wait)

        accounts = self._get_accounts(account)
        if not accounts:
            return

        total_accounts = len(accounts)
        burst_size = self.batch_settings['burst_size']
        total_batches = math.ceil(total_accounts / burst_size)
        processed = 0

        for i in range(0, total_accounts, burst_size):
            batch = accounts[i:i + burst_size]
            batch_num = i // burst_size + 1
            logging.info(f'Processing batch {batch_num} of {total_batches}')
            processed = self._process_batch(batch, break_on_existing_arg, redownload, processed, total_accounts)

    def _get_accounts(self, account: str) -> list[str]:
        if not account:
            accounts = get_accounts_from_db()
            if not accounts:
                logging.warning('No SoundCloud accounts found in the database.')
                return []
            accounts.sort()
            return accounts
        return [account]

    def _process_batch(self, batch, break_on_existing_arg, redownload, processed, total_accounts):
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.batch_settings['max_workers']) as executor:
            futures = {}
            for acc in batch:
                if futures:
                    time.sleep(random.randint(2, 10))

                ydl_opts = self._prepare_ydl_opts(acc, break_on_existing_arg, redownload)
                futures[executor.submit(self.download_account, acc, ydl_opts)] = acc

            for future in concurrent.futures.as_completed(futures):
                acc = futures[future]
                processed += 1
                job_manager.publish({
                    'type': 'soundcloud-account',
                    'account': acc,
                    'current': processed,
                    'total': total_accounts
                })
        return processed

    def _prepare_ydl_opts(self, acc, break_on_existing_arg, redownload):
        ydl_opts = self.downloader_config['ydl_opts'].copy()
        effective_break = self.default_break_on_existing if break_on_existing_arg is None else break_on_existing_arg
        if effective_break:
            ydl_opts['break_on_existing'] = True
        else:
            ydl_opts.pop('break_on_existing', None)

        if not redownload:
            if self.downloader_config['archive_file']:
                ydl_opts['download_archive'] = str(self.downloader_config['archive_file'])
                logging.info(f"Using shared archive: {self.downloader_config['archive_file']}")
            else:
                account_archive = Path(self.downloader_config['archive_dir']) / f'{acc}.txt'
                ydl_opts['download_archive'] = str(account_archive)
                logging.info(f'Using per-account archive: {account_archive} for {acc}')
        else:
            ydl_opts.pop('download_archive', None)
            logging.info(f'Redownload enabled — skipping archive for {acc}.')
        return ydl_opts

    def _apply_config(self) -> None:
        values = self._config.get_many(['soundcloud_folder', 'soundcloud_archive', 'soundcloud_cookies', 'ffmpeg_location'])
        self.downloader_config = {
            'output_folder': values.get('soundcloud_folder') or None,
            'archive_dir': values.get('soundcloud_archive') or None,
            'cookies_file': values.get('soundcloud_cookies') or 'soundcloud.com_cookies.txt',
            'ffmpeg_location': values.get('ffmpeg_location') or '/usr/bin',
            'enabled': True,
            'archive_file': None,
            'ydl_opts': {}
        }

        if not self.downloader_config['output_folder'] or not self.downloader_config['archive_dir']:
            if getattr(self, 'downloader_config', {}).get('enabled', True):
                logging.warning('Missing required configuration for SoundCloud downloads. SoundCloud downloads will be disabled.')
            self.downloader_config['enabled'] = False
            self.downloader_config['ydl_opts'] = {}
            self.downloader_config['archive_file'] = None
            return
        os.makedirs(self.downloader_config['output_folder'], exist_ok=True)
        if os.path.isfile(self.downloader_config['archive_dir']):
            self.downloader_config['archive_file'] = self.downloader_config['archive_dir']
        else:
            os.makedirs(self.downloader_config['archive_dir'], exist_ok=True)
            self.downloader_config['archive_file'] = None
        self.downloader_config['enabled'] = True
        self.downloader_config['ydl_opts'] = {
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            },
            'outtmpl': f"{self.downloader_config['output_folder']}/%(uploader)s/%(title)s.%(ext)s",
            'compat_opts': ['filename'],
            'nooverwrites': False,
            'no_part': True,
            'format': 'bestaudio[ext=mp3]',
            'match_filter': self._match_filter,
            'quiet': False,
            'ignoreerrors': True,
            'set_file_timestamp': True,
            'ffmpeg_location': self.downloader_config['ffmpeg_location'],
            'sleep_interval': 10,
            'max_sleep_interval': 60,
            'sleep_requests': 1,
            'ratelimit': 1024 * 1024,  # Limit to 1MB/s
            'playlist_random': True,
        }

        cookies_file = self.downloader_config['cookies_file']
        if cookies_file:
            if cookies_file.startswith('firefox:'):
                parts = cookies_file.split(':', 1)
                profile = parts[1] if len(parts) > 1 else None
                logging.info(f'Using cookiesfrombrowser=firefox with profile: {profile} for SoundCloud')
                self.downloader_config['ydl_opts']['cookiesfrombrowser'] = ('firefox', profile)
            else:
                self.downloader_config['ydl_opts']['cookies'] = cookies_file
        else:
            self.downloader_config['ydl_opts']['cookiesfrombrowser'] = ('firefox',)

        if self.default_break_on_existing:
            self.downloader_config['ydl_opts']['break_on_existing'] = True
