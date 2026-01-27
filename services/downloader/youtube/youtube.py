import concurrent.futures
import logging
import os
import random
import time
from typing import Optional
from yt_dlp import YoutubeDL
from services.common.Helpers.DatabaseConnector import DatabaseConnector
from services.downloader.youtube.YoutubeSongProcessor import YoutubeSongProcessor


class YoutubeDownloader:

    def __init__(self, break_on_existing: bool = True, max_workers: int = 1, burst_size: int = 10, min_pause: int = 1,
                 max_pause: int = 5, socket_timeout: int = 30):
        """
        Initializes the YoutubeDownloader instance with configuration settings.
    
        Args:
            break_on_existing (bool): Whether to stop processing if existing content is detected.
            max_workers (int): Maximum number of worker threads for concurrency.
            burst_size (int): Number of accounts to process in one batch.
            min_pause (int): Minimum pause duration (in seconds) between batches.
            max_pause (int): Maximum pause duration (in seconds) between batches.
            socket_timeout (int): Timeout value (in seconds) for network connections.
        """
        self.output_folder = os.getenv('youtube_folder')
        self.video_folder = os.getenv('youtube_video_folder')
        self.archive_dir = os.getenv('youtube_archive')
        self.ffmpeg_location = os.getenv('ffmpeg-location', '/usr/bin')
        self.max_workers = max_workers
        self.burst_size = burst_size
        self.min_pause = min_pause
        self.max_pause = max_pause
        self.socket_timeout = socket_timeout
        self.default_break_on_existing = break_on_existing
        if not self.output_folder or not self.video_folder or not self.archive_dir:
            logging.warning(
                'Missing required environment variables for youtube_folder, youtube_video_folder or youtube_archive. YouTube downloads will be disabled.')
            self.output_folder = None
            self.video_folder = None
            self.archive_dir = None
            self.enabled = False
        else:
            os.makedirs(self.output_folder, exist_ok=True)
            os.makedirs(self.video_folder, exist_ok=True)
            os.makedirs(self.archive_dir, exist_ok=True)
            self.enabled = True
        self.cookies_file = os.getenv('YT_COOKIES')
        self.user_agent = os.getenv('YT_USER_AGENT')
        if not self.enabled:
            self._base_ydl_opts = {}
            return
        self._base_ydl_opts = {'compat_opts': ['filename'], 'nooverwrites': True,
                               'ffmpeg_location': self.ffmpeg_location, 'match_filter': self._match_filter,
                               'socket_timeout': self.socket_timeout,
                               'extractor_args': {
                                   'youtubetab': {
                                       'skip': ['authcheck'],
                                   }
                               }
                               }
        self._base_ydl_opts.update(self._cookie_options())
        if self.user_agent:
            self._base_ydl_opts['user_agent'] = self.user_agent

    def _cookie_options(self) -> dict:
        """
        Build yt-dlp cookie-related options.
    
        Returns:
            dict: A dictionary of cookie options, either using a provided `cookies.txt` file
                  or falling back to using cookies from the browser (Firefox).
        """
        opts: dict = {}
        if self.cookies_file:
            if os.path.exists(self.cookies_file):
                logging.info(f'Using cookies.txt from YT_COOKIES: {self.cookies_file}')
                opts['cookies'] = self.cookies_file
                return opts
            else:
                logging.warning(
                    f'YT_COOKIES is set but file not found: {self.cookies_file}. Falling back to cookiesfrombrowser=firefox.')
        opts['cookiesfrombrowser'] = ('firefox',)
        logging.info('Using cookiesfrombrowser=firefox (no YT_COOKIES file).')
        return opts

    def _build_ydl_opts(self, archive_file: str, break_on_existing: bool = True, redownload: bool = False,
                        download_type: str = 'audio', min_duration: int = 60,
                        output_folder_override: Optional[str] = None) -> dict:
        """
        Constructs yt-dlp options based on the given download requirements.
    
        Args:
            archive_file (str): Path to the archive file for already downloaded videos.
            break_on_existing (bool): Whether to stop processing if an existing video is detected.
            redownload (bool): Whether to force redownload of archived content.
            download_type (str): 'audio' or 'video'.
            min_duration (int): Minimum duration in seconds.
            output_folder_override (str): Optional custom output folder.
    
        Returns:
            dict: A dictionary containing yt-dlp configuration options.
        """
        opts = {**self._base_ydl_opts}
        opts['min_duration_limit'] = min_duration  # Used in _match_filter

        base_folder = output_folder_override or (self.video_folder if download_type == 'video' else self.output_folder)

        if download_type == 'video':
            opts['outtmpl'] = f'{base_folder}/%(uploader)s/%(title)s.%(ext)s'
            opts['postprocessors'] = [{'key': 'EmbedThumbnail'}, {'key': 'FFmpegMetadata'}]
            opts['keepvideo'] = True
            opts['format'] = 'bestvideo+bestaudio/best'
        else:
            opts['outtmpl'] = f'{base_folder}/%(uploader)s/%(title)s.%(ext)s'
            opts['format'] = 'bestaudio/best'
            opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'm4a'},
                                      {'key': 'EmbedThumbnail'}, {'key': 'FFmpegMetadata'}]
            opts['keepvideo'] = False

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
        min_duration = info.get('min_duration_limit', 60)
        if not duration or duration < min_duration or duration > 36000:
            logging.info(f"Skipping video '{title}' (duration: {duration}s, min required: {min_duration}s)")
            return 'Outside allowed duration range'
        return None

    def download_account(self, name: str, download_type: str = 'audio', break_on_existing: Optional[bool] = None, 
                         redownload: bool = False, min_duration: int = 60, 
                         output_folder_override: Optional[str] = None, ydl_opts: dict = None):
        """
        Downloads videos from a specific YouTube account.
    
        Args:
            name (str): The name or username of the account.
            download_type (str): 'audio' or 'video'.
            break_on_existing (bool, optional): Overrides default break_on_existing.
            redownload (bool): Force redownload.
            min_duration (int): Minimum duration.
            output_folder_override (str): Optional output folder override.
            ydl_opts (dict, optional): Specific YouTubeDL configuration options.
    
        Retries the download process up to 3 times in case of errors.
        """
        link = f'http://www.youtube.com/{name}'
        archive_dir = os.path.join(self.archive_dir, download_type)
        os.makedirs(archive_dir, exist_ok=True)
        archive_file = os.path.join(archive_dir, f'{name}.txt')
        
        effective_break = self.default_break_on_existing if break_on_existing is None else break_on_existing
        
        opts_template = ydl_opts or self._build_ydl_opts(
            archive_file, 
            break_on_existing=effective_break,
            redownload=redownload,
            download_type=download_type,
            min_duration=min_duration,
            output_folder_override=output_folder_override
        )
        for attempt in range(1, 4):
            try:
                opts = dict(opts_template)
                if 'postprocessors' in opts_template:
                    opts['postprocessors'] = [pp.copy() if isinstance(pp, dict) else pp for pp in
                                              opts_template['postprocessors']]
                with self._create_ydl(opts) as ydl:
                    logging.info(f'Downloading from account: {name} ({link})')
                    ydl.download([link])
                logging.info(f'Finished downloading from: {name}')
                return
            except Exception as e:
                msg = str(e)
                if '403' in msg:
                    wait_time = random.randint(60, 300)
                    logging.warning(f'403 Forbidden for {name}. Pausing {wait_time}s before retry...')
                    time.sleep(wait_time)
                elif '404' in msg:
                    logging.info(f'Got 404 for {name} — skipping video.')
                    return
                elif 'already been recorded' in msg or 'already in the archive' in msg:
                    logging.info(f'All videos for {name} already in archive — skipping further attempts.')
                    return
                elif 'timed out' in msg.lower():
                    logging.warning(f'Timeout encountered for {name}. Attempt {attempt} failed: {e}')
                    time.sleep(5 * attempt)
                elif 'premieres in' in msg.lower():
                    logging.warning(f'Premieres in {name}. Skipping.')
                    return
                elif "the downloaded file is empty" in msg.lower():
                    logging.warning(f"The downloaded file for {name} is empty. Possibly a live stream that hasn't finished or is restricted. Skipping.")
                    return
                elif 'This channel does not have a streams tab' in msg.lower():
                    return
                else:
                    logging.warning(f'Attempt {attempt} failed for {name}: {e}', exc_info=True)
                    time.sleep(5 * attempt)
        logging.error(f'YouTube download failed for {name} after 3 attempts.')

    def download_link(self, url: str, download_type: str = 'audio', breakOnExisting: bool = True, redownload: bool = False):
        """
        Download a single video using a direct URL.
    
        Args:
            url (str): The URL of the video to download.
            download_type (str): 'audio' or 'video'.
            breakOnExisting (bool): Whether to skip download if the video already exists.
            redownload (bool): Whether to force redownloading of existing content.
    
        Logs errors if the download fails.
        """
        """Download a single video using a direct URL."""
        archive_dir = os.path.join(self.archive_dir, download_type)
        os.makedirs(archive_dir, exist_ok=True)
        archive_file = os.path.join(archive_dir, 'manual.txt')
        try:
            opts = self._build_ydl_opts(archive_file, break_on_existing=breakOnExisting, redownload=redownload,
                                        download_type=download_type)
            with self._create_ydl(opts) as ydl:
                logging.info(f'Downloading from url: {url}')
                ydl.download([url])
            logging.info('Finished downloading video')
        except Exception as e:
            logging.error(f'Download failed for {url}: {e}', exc_info=True)

    def get_accounts_from_db(self):
        """
        Fetches a list of YouTube accounts with their settings from the database.
    
        Returns:
            list: A list of dicts with account settings.
        """
        try:
            db = DatabaseConnector().connect()
            with db.cursor() as cursor:
                cursor.execute('SELECT name, download_type, min_duration, output_folder_override FROM youtube_accounts')
                accounts = []
                for row in cursor.fetchall():
                    accounts.append({
                        'name': row[0],
                        'download_type': row[1] or 'audio',
                        'min_duration': row[2] or 60,
                        'output_folder_override': row[3]
                    })
            return accounts
        except Exception as e:
            logging.error(f'Failed to fetch Youtube accounts from DB: {e}')
            return []

    def run(self, breakOnExisting: Optional[bool] = None, redownload: bool = False, account: str = '', **kwargs):
        """
        Executes the downloading process for YouTube accounts.
    
        Args:
            breakOnExisting (Optional[bool]): Overrides the instance's setting to stop on existing content.
            redownload (bool): Enforce redownloading of videos.
            account (str): Specific YouTube account to process (defaults to all accounts).
            **kwargs: Additional arguments such as download_type.
    
        Processes accounts in batches and allows throttling between batches.
        """
        if not getattr(self, 'enabled', True):
            logging.warning('YouTube downloader is not configured; skipping run().')
            return
        download_type = kwargs.get('download_type')
        try:
            if account:
                # If a specific account name is provided, we still need its settings from DB
                all_accounts = self.get_accounts_from_db()
                accounts = [acc for acc in all_accounts if acc['name'] == account]
                if not accounts:
                    # Fallback if account not in DB (e.g. manual override)
                    accounts = [{'name': account, 'download_type': 'audio', 'min_duration': 60,
                                 'output_folder_override': None}]
            else:
                accounts = self.get_accounts_from_db()
        except Exception as e:
            logging.error(f'Database error while fetching YouTube accounts: {e}')
            return
        if download_type:
            accounts = [acc for acc in accounts if acc["download_type"] == download_type]
        if not accounts:
            logging.warning('No YouTube accounts found in the database.')
            return
        total_accounts = len(accounts)
        accounts.sort(key=lambda x: x['name'])
        total_batches = (total_accounts + self.burst_size - 1) // self.burst_size
        for i in range(0, total_accounts, self.burst_size):
            batch = accounts[i:i + self.burst_size]
            batch_index = i // self.burst_size + 1
            logging.info('Processing YouTube batch %s of %s', batch_index, total_batches)
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {}
                for acc_settings in batch:
                    acc_name = acc_settings['name']
                    effective_break = self.default_break_on_existing if breakOnExisting is None else breakOnExisting
                    
                    futures[executor.submit(
                        self.download_account, 
                        acc_name, 
                        download_type=acc_settings['download_type'],
                        break_on_existing=effective_break,
                        redownload=redownload,
                        min_duration=acc_settings['min_duration'],
                        output_folder_override=acc_settings['output_folder_override']
                    )] = acc_name
                for future in concurrent.futures.as_completed(futures):
                    acc = futures[future]
                    try:
                        future.result()
                    except Exception as exc:
                        logging.error(f'Unhandled error downloading {acc}: {exc}')
            if i + self.burst_size < total_accounts:
                pause = random.randint(self.min_pause, self.max_pause)
                logging.info(f'Throttling pause: sleeping {pause} seconds...')
                time.sleep(pause)
