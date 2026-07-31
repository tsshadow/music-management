import concurrent.futures
import logging
import os
import time
from typing import Optional
from yt_dlp import YoutubeDL
from services.common.Helpers.DatabaseConnector import DatabaseConnector
from services.common.config_store import ConfigStore
from services.downloader.rate_state import RateLimited, SweepAborted
from services.downloader.sweep import SweepPolicy
from services.downloader.youtube.YoutubeArchive import YoutubeArchive
from services.downloader.youtube.YoutubeSongProcessor import YoutubeSongProcessor
from services.common.job_manager import job_manager

SOURCE = 'youtube'

class YoutubeDownloader:

    def __init__(self, break_on_existing: bool=True, dry_run: bool=False,
                 timing=None, rate_state=None, schedule=None, socket_timeout: int=30):
        """
        Initializes the YoutubeDownloader instance with configuration settings.

        Args:
            break_on_existing (bool): Whether to stop processing if existing content is detected.
            dry_run (bool): If True, only simulate the download process.
            timing: Effective timing settings; loaded from the database when omitted.
            rate_state: Persisted backoff state; loaded from the database when omitted.
            schedule: Per-account check schedule; loaded from the database when omitted.
            socket_timeout (int): Timeout value (in seconds) for network connections.
        """
        self._config = ConfigStore()
        self.policy = SweepPolicy(SOURCE, timing=timing, rate_state=rate_state, schedule=schedule)
        values = self._config.get_many(['youtube_folder', 'youtube_archive', 'ffmpeg_location', 'yt_cookies', 'yt_user_agent'])
        self.downloader_config = {'output_folder': values.get('youtube_folder'), 'archive_dir': values.get('youtube_archive'), 'ffmpeg_location': values.get('ffmpeg_location') or '/usr/bin', 'cookies_file': values.get('yt_cookies'), 'user_agent': values.get('yt_user_agent'), 'enabled': False}
        self.socket_timeout = socket_timeout
        self.default_break_on_existing = break_on_existing
        self.dry_run = dry_run
        self.redownload_mode = False
        if not self.downloader_config['output_folder'] or not self.downloader_config['archive_dir']:
            logging.warning('Missing required configuration for youtube_folder or youtube_archive. YouTube downloads will be disabled.')
            self.downloader_config['output_folder'] = None
            self.downloader_config['archive_dir'] = None
            self.downloader_config['enabled'] = False
        else:
            os.makedirs(self.downloader_config['output_folder'], exist_ok=True)
            os.makedirs(self.downloader_config['archive_dir'], exist_ok=True)
            self.downloader_config['enabled'] = True
        if not self.downloader_config['enabled']:
            self._base_ydl_opts = {}
            return
        self._base_ydl_opts = {'outtmpl': f"{self.downloader_config['output_folder']}/%(uploader)s/%(title)s.%(ext)s", 'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'm4a'}, {'key': 'EmbedThumbnail'}, {'key': 'FFmpegMetadata'}], 'compat_opts': ['filename'], 'nooverwrites': True, 'keepvideo': False, 'ffmpeg_location': self.downloader_config['ffmpeg_location'], 'match_filter': self._match_filter, 'ignoreerrors': True, 'socket_timeout': self.socket_timeout, 'playlist_random': True, 'http_chunk_size': 10 * 1024 * 1024, 'extractor_args': {'youtubetab': {'skip': ['authcheck']}}, **self.timing.to_ydl_opts()}
        self._base_ydl_opts.update(self._cookie_options())
        if self.downloader_config['user_agent']:
            self._base_ydl_opts['user_agent'] = self.downloader_config['user_agent']

    @property
    def timing(self):
        return self.policy.timing

    def _cookie_options(self) -> dict:
        """
        Build yt-dlp cookie-related options.

        Returns:
            dict: A dictionary of cookie options, either using a provided `cookies.txt` file
                  or falling back to using cookies from the browser (Firefox).
        """
        opts: dict = {}
        cookies_file = self.downloader_config['cookies_file']
        if cookies_file:
            if cookies_file.startswith('firefox:'):
                parts = cookies_file.split(':', 1)
                profile = parts[1] if len(parts) > 1 else None
                logging.info(f'Using cookiesfrombrowser=firefox with profile: {profile}')
                opts['cookiesfrombrowser'] = ('firefox', profile)
                return opts
            if os.path.exists(cookies_file):
                logging.info(f'Using cookies.txt from YT_COOKIES: {cookies_file}')
                opts['cookies'] = cookies_file
                return opts
            logging.warning(f'YT_COOKIES is set but file not found: {cookies_file}. Falling back to cookiesfrombrowser=firefox.')
        opts['cookiesfrombrowser'] = ('firefox',)
        logging.info('Using cookiesfrombrowser=firefox (no YT_COOKIES file).')
        return opts

    def _build_ydl_opts(self, archive_file: str, break_on_existing: bool=True, redownload: bool=False) -> dict:
        """
        Constructs yt-dlp options based on the given download requirements.

        Args:
            archive_file (str): Path to the archive file for already downloaded videos.
            break_on_existing (bool): Whether to stop processing if an existing video is detected.
            redownload (bool): Whether to force redownload of archived content.

        Returns:
            dict: A dictionary containing yt-dlp configuration options.
        """
        opts = {**self._base_ydl_opts}
        opts['simulate'] = self.dry_run
        if 'postprocessors' in self._base_ydl_opts:
            opts['postprocessors'] = [pp.copy() if isinstance(pp, dict) else pp for pp in self._base_ydl_opts['postprocessors']]
        if not redownload:
            opts['download_archive'] = archive_file
        else:
            opts.pop('download_archive', None)
        if break_on_existing:
            opts['break_on_existing'] = True
        else:
            opts.pop('break_on_existing', None)
        return opts

    def _create_ydl(self, ydl_opts: dict) -> YoutubeDL:
        """
        Creates and configures a YoutubeDL instance.

        Args:
            ydl_opts (dict): Options to pass to the YoutubeDL instance.

        Returns:
            YoutubeDL: A YoutubeDL instance configured with the given options.
        """
        ydl = YoutubeDL(ydl_opts)
        ydl.add_post_processor(YoutubeSongProcessor())
        return ydl

    def _match_filter(self, info):
        """
        Filters videos based on their metadata.

        Args:
            info (dict): Metadata of the video to evaluate.

        Returns:
            str or None: Returns a message string if the video doesn't match criteria; otherwise None.
        """
        duration = info.get('duration')
        title = info.get('title', 'unknown')
        if not duration or duration < 60 or duration > 21600:
            logging.info(f"Skipping video '{title}' (duration: {duration}s)")
            return 'Outside allowed duration range'
        account = info.get('uploader_id') or info.get('channel_id') or info.get('uploader') or info.get('channel')
        video_id = info.get('id')
        if not self.redownload_mode and account and video_id and YoutubeArchive.exists(account, video_id):
            logging.info(f"Skipping video '{title}' (already in database archive)")
            return 'Already in database archive'
        return None

    def download_account(self, name: str, ydl_opts: dict=None):
        """
        Downloads videos from a specific YouTube account.

        A 403 or 429 is recorded in the rate state and raised as `RateLimited`, which
        stops the sweep. Waiting it out in place would block a thread for hours and
        would be forgotten on the next restart.
        """
        self.policy.guard(name)
        link = f'http://www.youtube.com/{name}'
        archive_file = os.path.join(self.downloader_config['archive_dir'], f'{name}.txt')
        opts_template = ydl_opts or self._build_ydl_opts(archive_file, break_on_existing=self.default_break_on_existing)
        for attempt in range(1, self.timing.retry_attempts + 1):
            try:
                opts = dict(opts_template)
                if 'postprocessors' in opts_template:
                    opts['postprocessors'] = [pp.copy() if isinstance(pp, dict) else pp for pp in opts_template['postprocessors']]
                with self._create_ydl(opts) as ydl:
                    logging.info(f'Downloading from account: {name} ({link})')
                    ydl.download([link])
                logging.info(f'Finished downloading from: {name}')
                return
            except RateLimited:
                raise
            except Exception as e:
                msg = str(e)
                rate_limited = self.policy.rate_limit_from(e, name)
                if rate_limited is not None:
                    raise rate_limited from e
                if '404' in msg:
                    logging.info(f'Got 404 for {name} — skipping video.')
                    return
                if 'already been recorded' in msg or 'already in the archive' in msg:
                    logging.info(f'All videos for {name} already in archive — skipping further attempts.')
                    return
                if 'premieres in' in msg.lower():
                    logging.warning(f'Premieres in {name}. Skipping.')
                    return
                if 'this channel does not have a streams tab' in msg.lower():
                    return
                if 'timed out' in msg.lower():
                    logging.warning(f'Timeout encountered for {name}. Attempt {attempt} failed: {e}')
                else:
                    logging.warning(f'Attempt {attempt} failed for {name}: {e}', exc_info=True)
                time.sleep(5 * attempt)
        logging.error(f'YouTube download failed for {name} after {self.timing.retry_attempts} attempts.')

    def download_link(self, url: str, breakOnExisting: bool=True, redownload: bool=False):
        """
        Download a single video using a direct URL.

        Args:
            url (str): The URL of the video to download.
            breakOnExisting (bool): Whether to skip download if the video already exists.
            redownload (bool): Whether to force redownloading of existing content.

        Logs errors if the download fails.
        """
        self.redownload_mode = redownload
        archive_file = os.path.join(self.downloader_config['archive_dir'], 'manual.txt')
        try:
            opts = self._build_ydl_opts(archive_file, break_on_existing=breakOnExisting, redownload=redownload)
            with self._create_ydl(opts) as ydl:
                logging.info(f'Downloading from url: {url}')
                ydl.download([url])
            logging.info('Finished downloading video')
        except Exception as e:
            logging.error(f'Download failed for {url}: {e}', exc_info=True)

    def get_accounts_from_db(self):
        """
        Fetches a list of YouTube account names from the database.

        Returns:
            list: A list of account names, or an empty list if the query fails.
        """
        try:
            db = DatabaseConnector().connect()
            with db.cursor() as cursor:
                cursor.execute('SELECT name FROM downloads_youtube_accounts')
                accounts = [row[0] for row in cursor.fetchall()]
            return accounts
        except Exception as e:
            logging.error(f'Failed to fetch Youtube accounts from DB: {e}')
            return []

    def run(self, break_on_existing_arg: Optional[bool]=None, redownload: bool=False, account: str=''):
        if not getattr(self, 'downloader_config', {}).get('enabled', True):
            logging.warning('YouTube downloader is not configured; skipping run().')
            return
        if not self.policy.begin():
            return
        self.redownload_mode = redownload
        accounts = self._get_accounts(account)
        if not accounts:
            return
        if not account:
            accounts = self.policy.due(accounts)
            if not accounts:
                logging.info('No YouTube channels are due for a check yet.')
                return
        total_accounts = len(accounts)
        burst_size = self.timing.burst_size
        total_batches = (total_accounts + burst_size - 1) // burst_size
        processed = 0
        for i in range(0, total_accounts, burst_size):
            batch = accounts[i:i + burst_size]
            batch_index = i // burst_size + 1
            logging.info('Processing YouTube batch %s of %s', batch_index, total_batches)
            try:
                processed = self._process_batch(batch, break_on_existing_arg, redownload, processed, total_accounts)
            except RateLimited as exc:
                logging.warning('Stopping the YouTube sweep: %s', exc)
                return
            if i + burst_size < total_accounts:
                self.policy.throttle()
        self.policy.finish()

    def _get_accounts(self, account: str) -> list[str]:
        try:
            if account:
                accounts = [account]
            else:
                accounts = self.get_accounts_from_db()
        except Exception as e:
            logging.error(f'Database error while fetching YouTube accounts: {e}')
            return []
        if not accounts:
            logging.warning('No YouTube accounts found in the database.')
            return []
        accounts.sort()
        return accounts

    def _process_batch(self, batch, break_on_existing_arg, redownload, processed, total_accounts):
        rate_limited = None
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.timing.max_workers) as executor:
            futures = {}
            for acc in batch:
                ydl_opts = self._prepare_ydl_opts(acc, break_on_existing_arg, redownload)
                futures[executor.submit(self.download_account, acc, ydl_opts)] = acc
            for future in concurrent.futures.as_completed(futures):
                acc = futures[future]
                processed += 1
                try:
                    future.result()
                    self.policy.mark_checked(acc)
                except RateLimited as exc:
                    rate_limited = exc
                except SweepAborted as exc:
                    logging.info(str(exc))
                except Exception as exc:
                    logging.error(f'Unhandled error downloading {acc}: {exc}')
                job_manager.publish({'type': 'youtube-account', 'account': acc, 'current': processed, 'total': total_accounts})
        if rate_limited is not None:
            raise rate_limited
        return processed

    def _prepare_ydl_opts(self, acc, break_on_existing_arg, redownload):
        account_archive = os.path.join(self.downloader_config['archive_dir'], f'{acc}.txt')
        effective_break = self.default_break_on_existing if break_on_existing_arg is None else break_on_existing_arg
        return self._build_ydl_opts(account_archive, break_on_existing=effective_break, redownload=redownload)
