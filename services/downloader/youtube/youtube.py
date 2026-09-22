import concurrent.futures
import logging
import os
import shutil
import time
from datetime import datetime

from yt_dlp import YoutubeDL

from services.common.config_store import ConfigStore
from services.common.Helpers.DatabaseConnector import DatabaseConnector
from services.common.job_manager import job_manager
from services.downloader import shutdown
from services.downloader.deep_sweep import (
    DeepSweepReport,
    ids_in_text_archive,
    list_flat,
    snapshot_state,
    take_snapshot,
    wanted_tracks,
)
from services.downloader.rate_state import RateLimited, SweepAborted
from services.downloader.sweep import SweepPolicy
from services.downloader.write_offs import WriteOffs
from services.downloader.youtube.DropCategoryGenre import DropCategoryGenrePP
from services.downloader.youtube.YoutubeAccount import (
    AUDIO,
    DEFAULT_MIN_DURATION,
    VIDEO,
    YoutubeAccount,
)
from services.downloader.youtube.YoutubeArchive import YoutubeArchive
from services.downloader.youtube.YoutubeSongProcessor import YoutubeSongProcessor

SOURCE = 'youtube'

# Six hours. Long enough for any festival broadcast, short enough to keep a
# round-the-clock livestream rerun out of the library.
MAX_DURATION = 21600

# No height cap: the video pass exists for event channels that publish 4K
# aftermovies, and asking for less would be throwing away the reason it exists.
# The `/best` tail only fires for videos that have no separate streams at all;
# the ffmpeg check in run() is what keeps that tail from quietly meaning 360p,
# which is exactly how the existing pile of 640x360 files came about.
VIDEO_FORMAT = 'bestvideo*+bestaudio/best'


class YoutubeDownloader:
    def __init__(
        self,
        break_on_existing: bool = True,
        dry_run: bool = False,
        timing=None,
        rate_state=None,
        schedule=None,
        socket_timeout: int = 30,
        notifier=None,
        write_offs=None,
        deep: bool = False,
    ):
        """
        Initializes the YoutubeDownloader instance with configuration settings.

        Args:
            break_on_existing (bool): Whether to stop processing if existing content is detected.
            dry_run (bool): If True, only simulate the download process.
            timing: Effective timing settings; loaded from the database when omitted.
            rate_state: Persisted backoff state; loaded from the database when omitted.
            schedule: Per-account check schedule; loaded from the database when omitted.
            socket_timeout (int): Timeout value (in seconds) for network connections.
            notifier: Optional notifier for SweepPolicy; defaults to None (lazy-loads at runtime).
            write_offs: The ledger of videos deliberately not fetched; built from
                the database when omitted.
            deep (bool): Force the deep path for every channel this run, whatever
                the cadence says. What `--deep` on the CLI turns on.
        """
        self._config = ConfigStore()
        self.policy = SweepPolicy(SOURCE, timing=timing, rate_state=rate_state, schedule=schedule, notifier=notifier)
        values = self._config.get_many(
            [
                'youtube_folder',
                'youtube_video_folder',
                'youtube_archive',
                'ffmpeg_location',
                'yt_cookies',
                'yt_user_agent',
            ]
        )
        self.downloader_config = {
            'output_folder': values.get('youtube_folder'),
            'video_folder': values.get('youtube_video_folder'),
            'archive_dir': values.get('youtube_archive'),
            'ffmpeg_location': values.get('ffmpeg_location') or '/usr/bin',
            'cookies_file': values.get('yt_cookies'),
            'user_agent': values.get('yt_user_agent'),
            'enabled': False,
            'video_enabled': False,
        }
        self.socket_timeout = socket_timeout
        self.default_break_on_existing = break_on_existing
        self.dry_run = dry_run
        self.redownload_mode = False
        self.deep_mode = deep
        self.write_offs = (
            write_offs
            if write_offs is not None
            else WriteOffs(SOURCE, retry_days=self.policy.timing.unavailable_retry_days)
        )
        if not self.downloader_config['output_folder'] or not self.downloader_config['archive_dir']:
            logging.warning(
                'Missing required configuration for youtube_folder or youtube_archive. YouTube downloads will be disabled.'
            )
            self.downloader_config['output_folder'] = None
            self.downloader_config['archive_dir'] = None
            self.downloader_config['enabled'] = False
        else:
            os.makedirs(self.downloader_config['output_folder'], exist_ok=True)
            os.makedirs(self.downloader_config['archive_dir'], exist_ok=True)
            self.downloader_config['enabled'] = True
        if not self.downloader_config['enabled']:
            self._base_ydl_opts = {}
            self._video_ydl_opts = {}
            return
        self._base_ydl_opts = {
            'outtmpl': f"{self.downloader_config['output_folder']}/%(uploader)s/%(title)s.%(ext)s",
            'postprocessors': [
                {'key': 'FFmpegExtractAudio', 'preferredcodec': 'm4a'},
                {'key': 'EmbedThumbnail'},
                {'key': 'FFmpegMetadata'},
            ],
            # The EmbedThumbnail post-processor above embeds a thumbnail *file*; the CLI's
            # --embed-thumbnail implies --write-thumbnail, the API does not. See the same
            # comment in the SoundCloud downloader: without this the post-processor runs, finds
            # nothing on disk and silently embeds nothing.
            'writethumbnail': True,
            'compat_opts': ['filename'],
            'nooverwrites': True,
            'keepvideo': False,
            'ffmpeg_location': self.downloader_config['ffmpeg_location'],
            'match_filter': self._match_filter,
            'ignoreerrors': True,
            'socket_timeout': self.socket_timeout,
            'playlist_random': True,
            'http_chunk_size': 10 * 1024 * 1024,
            'extractor_args': {'youtubetab': {'skip': ['authcheck']}},
            **self.timing.to_ydl_opts(),
        }
        self._base_ydl_opts.update(self._cookie_options())
        if self.downloader_config['user_agent']:
            self._base_ydl_opts['user_agent'] = self.downloader_config['user_agent']
        self._video_ydl_opts = self._build_video_base_opts()

    def _build_video_base_opts(self) -> dict:
        """The yt-dlp options for a channel marked as video.

        Same transport, cookies and pacing as the audio side; what differs is that
        nothing extracts the audio track out again, and that the file lands in its
        own tree rather than between the m4a files of a channel.

        That tree still sits under the music root, so LMS and the scanner do walk
        it. What keeps an mkv out of the library is the extension filter on the
        other side: the tagger and importer only accept audio extensions, and LMS
        only indexes audio formats.
        """
        video_folder = self.downloader_config['video_folder']
        if not video_folder:
            logging.info('No youtube_video_folder configured; channels marked as video will be skipped.')
            return {}
        os.makedirs(video_folder, exist_ok=True)
        opts = {**self._base_ydl_opts}
        opts['outtmpl'] = f'{video_folder}/%(uploader)s/%(title)s.%(ext)s'
        opts['format'] = VIDEO_FORMAT
        opts['merge_output_format'] = 'mkv'
        opts['postprocessors'] = [{'key': 'EmbedThumbnail'}, {'key': 'FFmpegMetadata'}]
        self.downloader_config['video_enabled'] = True
        return opts

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
            logging.warning(
                f'YT_COOKIES is set but file not found: {cookies_file}. Falling back to cookiesfrombrowser=firefox.'
            )
        opts['cookiesfrombrowser'] = ('firefox',)
        logging.info('Using cookiesfrombrowser=firefox (no YT_COOKIES file).')
        return opts

    def _build_ydl_opts(
        self, archive_file: str, break_on_existing: bool = True, redownload: bool = False, download_type: str = AUDIO
    ) -> dict:
        """
        Constructs yt-dlp options based on the given download requirements.

        Args:
            archive_file (str): Path to the archive file for already downloaded videos.
            break_on_existing (bool): Whether to stop processing if an existing video is detected.
            redownload (bool): Whether to force redownload of archived content.
            download_type (str): 'audio' or 'video'; picks which base options to start from.

        Returns:
            dict: A dictionary containing yt-dlp configuration options.
        """
        base = self._video_ydl_opts if download_type == VIDEO else self._base_ydl_opts
        opts = {**base}
        opts['simulate'] = self.dry_run
        # The only checkpoint that is reachable during a download. Without it the
        # worker sits inside one multi-minute call and never sees the stop the
        # deploy asked for, so SIGKILL arrives with the pass unrecorded.
        opts['progress_hooks'] = [*base.get('progress_hooks', []), shutdown.abort_hook]
        if 'postprocessors' in base:
            opts['postprocessors'] = [pp.copy() if isinstance(pp, dict) else pp for pp in base['postprocessors']]
        if not redownload:
            opts['download_archive'] = archive_file
        else:
            opts.pop('download_archive', None)
        if break_on_existing:
            opts['break_on_existing'] = True
        else:
            opts.pop('break_on_existing', None)
        return opts

    def _create_ydl(self, ydl_opts: dict, download_type: str = AUDIO) -> YoutubeDL:
        """
        Creates and configures a YoutubeDL instance.

        Args:
            ydl_opts (dict): Options to pass to the YoutubeDL instance.
            download_type (str): 'audio' or 'video'; decides how the result is archived
                and whether the tagger runs on it.

        Returns:
            YoutubeDL: A YoutubeDL instance configured with the given options.
        """
        ydl = YoutubeDL(ydl_opts)
        ydl.add_post_processor(DropCategoryGenrePP(), when='pre_process')
        ydl.add_post_processor(YoutubeSongProcessor(download_type=download_type))
        return ydl

    def _match_filter(self, info):
        """Filter for a download without account context: the old 60s floor applies."""
        return self._filter_for(YoutubeAccount(name='', download_type=AUDIO))(info)

    def _filter_for(self, account: YoutubeAccount):
        """Build the match filter for one account row.

        The duration floor comes from the row rather than a constant, because the
        video channels are all set to 1200 seconds to keep trailers and teasers
        out while the audio channels stay at 60.
        """
        min_duration = account.min_duration or DEFAULT_MIN_DURATION
        download_type = account.download_type

        ledger_key = account.schedule_key
        bounds = (min_duration, MAX_DURATION)

        def match_filter(info):
            duration = info.get('duration')
            title = info.get('title', 'unknown')
            if self.write_offs.should_skip(ledger_key, info.get('id'), bounds):
                logging.info(f"Skipping video '{title}' (written off before)")
                return 'Known to be unavailable'
            if not duration or duration < min_duration or duration > MAX_DURATION:
                logging.info(f"Skipping video '{title}' (duration: {duration}s)")
                # Written down rather than only logged: a pass that walks the
                # whole channel would otherwise rediscover this video every time,
                # and could never report the channel finished.
                reason = 'too_short' if (duration or 0) < min_duration else 'too_long'
                self.write_offs.remember(ledger_key, info.get('id'), reason, duration=int(duration or 0))
                return 'Outside allowed duration range'
            uploader = info.get('uploader_id') or info.get('channel_id') or info.get('uploader') or info.get('channel')
            video_id = info.get('id')
            if (
                not self.redownload_mode
                and uploader
                and video_id
                and YoutubeArchive.exists(uploader, video_id, download_type)
            ):
                logging.info(f"Skipping video '{title}' (already in database archive)")
                return 'Already in database archive'
            return None

        return match_filter

    def _held_ids(self, account: YoutubeAccount, video_ids: list[str]) -> set[str]:
        """Everything already downloaded, from both records that decide that.

        yt-dlp consults its own text archive, so a video listed there is one it
        will silently refuse to fetch again. Leaving those out would queue the
        same videos on every pass and never see them arrive.
        """
        held = YoutubeArchive.held_ids(account.name, video_ids, account.download_type)
        held.update(ids_in_text_archive(self._archive_file_for(account)))
        return held

    def download_url(self, url: str, ydl_opts: dict, account: YoutubeAccount) -> None:
        """Fetch one video by URL, with the guards a whole channel gets.

        The deep pass hands over individual videos rather than the channel page,
        so nothing pages and `break_on_existing` has nothing to stop.
        """
        for attempt in range(1, self.timing.retry_attempts + 1):
            try:
                opts = dict(ydl_opts)
                if 'postprocessors' in ydl_opts:
                    opts['postprocessors'] = [
                        pp.copy() if isinstance(pp, dict) else pp for pp in ydl_opts['postprocessors']
                    ]
                with self._create_ydl(opts, download_type=account.download_type) as ydl:
                    ydl.download([url])
                return
            except RateLimited:
                raise
            except Exception as exc:
                rate_limited = self.policy.rate_limit_from(exc, url)
                if rate_limited is not None:
                    raise rate_limited from exc
                if '404' in str(exc):
                    logging.info('Got 404 for %s — skip.', url)
                    return
                if shutdown.is_requested():
                    raise SweepAborted(f'Abandoned {url}; the {SOURCE} worker is shutting down.') from exc
                logging.warning('Attempt %d failed for %s: %s', attempt, url, exc)
                time.sleep(5 * attempt)
        logging.error('YouTube download failed for %s after %d attempts.', url, self.timing.retry_attempts)

    def deep_sweep_account(self, account: YoutubeAccount, ydl_opts: dict) -> DeepSweepReport:
        """Walk a channel's whole videos tab and fetch whatever is missing.

        The ordinary run stops at the first archived video, so a run parked
        mid-channel leaves a hole no later run can reach. This lists the tab flat
        -- ids only, nothing resolved -- and resolves only what is absent, so the
        cost follows the size of the gap rather than the size of the channel.

        The tab is named explicitly rather than left to the bare channel URL, so
        the listing is the same set of videos the ordinary run downloads from.
        """
        self.policy.guard(account.name)
        ledger_key = account.schedule_key
        bounds = (account.min_duration or DEFAULT_MIN_DURATION, MAX_DURATION)
        url = f'https://www.youtube.com/{account.name}/videos'
        listing = list_flat(url, ydl_opts)
        ids = [entry.track_id for entry in listing]
        held = self._held_ids(account, ids)
        write_offs = self.write_offs.load_many(ledger_key, ids)
        wanted = wanted_tracks(listing, held, write_offs, self.timing.unavailable_retry_days, datetime.now(), bounds)
        batch = wanted[: self.timing.deep_sweep_max_downloads]
        logging.info(
            'Deep sweep of %s (%s): %d listed, %d held, %d written off, %d missing, fetching %d.',
            account.name,
            account.download_type,
            len(listing),
            len(held),
            len(write_offs),
            len(wanted),
            len(batch),
        )
        parked = False
        # Reached the end of the batch. Anything else -- a rate limit, a stop
        # request, an unexpected error -- leaves the tail unreached, and the
        # count stored says so.
        finished = False
        attempted: list = []
        try:
            for entry in batch:
                self.policy.guard(account.name)
                # Recorded before the download, not after: a video the pass never
                # reached must not be charged with a failed attempt, or three
                # interrupted passes write it off for a month.
                attempted.append(entry)
                self.download_url(entry.url, ydl_opts, account)
            finished = True
        except RateLimited:
            parked = True
            raise
        finally:
            report = self._settle_deep(
                account, listing, held, write_offs, wanted, batch, attempted, parked, bounds, interrupted=not finished
            )
            logging.info('Deep sweep of %s (%s): %s', account.name, account.download_type, report.summary())
        return report

    def _settle_deep(
        self,
        account: YoutubeAccount,
        listing,
        held,
        write_offs,
        wanted,
        batch,
        attempted,
        parked: bool,
        bounds,
        interrupted: bool = False,
    ) -> DeepSweepReport:
        """Count what actually arrived, and write off what did not.

        One extra lookup per pass. A video that neither downloaded nor rejected
        has to be counted, or a single permanently broken video keeps its channel
        incomplete and re-swept every day forever.
        """
        ledger_key = account.schedule_key
        arrived = self._held_ids(account, [entry.track_id for entry in attempted]) if attempted else set()
        downloaded = 0
        for entry in attempted:
            if entry.track_id in arrived:
                downloaded += 1
                continue
            if parked:
                # The sweep was stopped mid-batch; nothing was wrong with this
                # video, we simply never asked about it.
                continue
            if self.write_offs.should_skip(ledger_key, entry.track_id, bounds):
                # Rejected during this very pass. A decision, not a failure.
                continue
            self.write_offs.note_failure(ledger_key, entry.track_id)
        report = DeepSweepReport(
            listed=len(listing),
            held=len(held),
            written_off=len(write_offs),
            wanted=len(wanted),
            downloaded=downloaded,
            capped=len(wanted) > len(batch),
            parked=parked,
        )
        # Re-read after the failures above were recorded, so the count stored is
        # the one the next pass would start from.
        ids = [entry.track_id for entry in listing]
        snapshot = take_snapshot(
            listing,
            held,
            arrived,
            self.write_offs.load_many(ledger_key, ids),
            self.timing.unavailable_retry_days,
            datetime.now(),
            bounds,
            snapshot_state(report, interrupted),
        )
        self.policy.record_snapshot(ledger_key, snapshot)
        return report

    def _check_account(self, account: YoutubeAccount, ydl_opts: dict) -> None:
        """One channel: the deep path when it is due one, the ordinary run otherwise."""
        if self.deep_mode or self.policy.deep_due(account.schedule_key):
            report = self.deep_sweep_account(account, ydl_opts)
            if report.complete:
                self.policy.mark_deep_swept(account.schedule_key)
            return
        self.download_account(account, ydl_opts)

    def _archive_file_for(self, account: YoutubeAccount) -> str:
        """Where yt-dlp keeps its own record of what it already fetched.

        Audio keeps the flat `<channel>.txt` it has always used. Video gets a
        subdirectory, so the two forms of the same channel do not read each
        other's list and conclude there is nothing left to do.
        """
        archive_dir = self.downloader_config['archive_dir']
        if account.is_video:
            archive_dir = os.path.join(archive_dir, 'video')
            os.makedirs(archive_dir, exist_ok=True)
        return os.path.join(archive_dir, f'{account.name}.txt')

    def download_account(self, account, ydl_opts: dict = None):
        """
        Downloads videos from a specific YouTube account.

        A 403 or 429 is recorded in the rate state and raised as `RateLimited`, which
        stops the sweep. Waiting it out in place would block a thread for hours and
        would be forgotten on the next restart.
        """
        account = account if isinstance(account, YoutubeAccount) else YoutubeAccount(name=account)
        name = account.name
        self.policy.guard(name)
        link = f'http://www.youtube.com/{name}'
        opts_template = ydl_opts or self._build_ydl_opts(
            self._archive_file_for(account),
            break_on_existing=self.default_break_on_existing,
            download_type=account.download_type,
        )
        for attempt in range(1, self.timing.retry_attempts + 1):
            try:
                opts = dict(opts_template)
                if 'postprocessors' in opts_template:
                    opts['postprocessors'] = [
                        pp.copy() if isinstance(pp, dict) else pp for pp in opts_template['postprocessors']
                    ]
                with self._create_ydl(opts, download_type=account.download_type) as ydl:
                    logging.info(f'Downloading {account.download_type} from account: {name} ({link})')
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

    def download_link(
        self, url: str, breakOnExisting: bool = True, redownload: bool = False, download_type: str = AUDIO
    ):
        """
        Download a single video using a direct URL.

        Args:
            url (str): The URL of the video to download.
            breakOnExisting (bool): Whether to skip download if the video already exists.
            redownload (bool): Whether to force redownloading of existing content.
            download_type (str): 'audio' keeps the m4a extraction; 'video' keeps the
                highest available video and writes it to the video folder.

        Logs errors if the download fails.
        """
        self.redownload_mode = redownload
        if download_type == VIDEO and not self._video_ready():
            return
        archive_dir = self.downloader_config['archive_dir']
        if download_type == VIDEO:
            archive_dir = os.path.join(archive_dir, 'video')
            os.makedirs(archive_dir, exist_ok=True)
        archive_file = os.path.join(archive_dir, 'manual.txt')
        try:
            opts = self._build_ydl_opts(
                archive_file, break_on_existing=breakOnExisting, redownload=redownload, download_type=download_type
            )
            with self._create_ydl(opts, download_type=download_type) as ydl:
                logging.info(f'Downloading from url: {url}')
                ydl.download([url])
            logging.info('Finished downloading video')
        except Exception as e:
            logging.error(f'Download failed for {url}: {e}', exc_info=True)

    def get_accounts_from_db(self) -> list[YoutubeAccount]:
        """
        Fetches the YouTube account rows from the database.

        Returns:
            list[YoutubeAccount]: One entry per row. A channel that is both an audio
            and a video source appears twice, which is what the composite primary key
            (name, download_type) is for.
        """
        try:
            with DatabaseConnector().connection() as db, db.cursor() as cursor:
                cursor.execute('SELECT name, download_type, min_duration, active FROM downloads_youtube_accounts')
                accounts = [YoutubeAccount.from_row(row) for row in cursor.fetchall()]
            return accounts
        except Exception as e:
            logging.error(f'Failed to fetch Youtube accounts from DB: {e}')
            return []

    def _ffmpeg_available(self) -> bool:
        """Whether yt-dlp will be able to merge separate video and audio streams.

        Without ffmpeg it silently falls back to the one progressive stream YouTube
        still serves, which is 640x360. Refusing to run beats filling the disk with
        that again.
        """
        location = self.downloader_config.get('ffmpeg_location')
        if location:
            candidate = os.path.join(location, 'ffmpeg') if os.path.isdir(location) else location
            if os.path.exists(candidate):
                return True
        return shutil.which('ffmpeg') is not None

    def _video_ready(self) -> bool:
        """Whether the video pass may run at all."""
        if not self.downloader_config.get('video_enabled'):
            logging.warning('Channels are marked as video but youtube_video_folder is not configured; skipping them.')
            return False
        if not self._ffmpeg_available():
            logging.error(
                'ffmpeg was not found at %s. Skipping the YouTube video pass, because without it '
                'yt-dlp falls back to the 360p progressive stream.',
                self.downloader_config.get('ffmpeg_location'),
            )
            return False
        return True

    def run(self, break_on_existing_arg: bool | None = None, redownload: bool = False, account: str = ''):
        if not getattr(self, 'downloader_config', {}).get('enabled', True):
            logging.warning('YouTube downloader is not configured; skipping run().')
            return
        if not self.policy.begin():
            return
        self.redownload_mode = redownload
        accounts = self._get_accounts(account)
        if not accounts:
            return
        # Audio first, deliberately. It is the bigger list and the one the library
        # is actually built from; a rate limit hit halfway should cost the video
        # pass, not the music.
        audio_accounts = [entry for entry in accounts if not entry.is_video]
        video_accounts = [entry for entry in accounts if entry.is_video]
        if not self._run_pass(audio_accounts, AUDIO, break_on_existing_arg, redownload, bool(account)):
            return
        if (
            video_accounts
            and self._video_ready()
            and not self._run_pass(video_accounts, VIDEO, break_on_existing_arg, redownload, bool(account))
        ):
            return
        self.policy.finish()

    def _run_pass(
        self,
        accounts: list[YoutubeAccount],
        download_type: str,
        break_on_existing_arg,
        redownload: bool,
        explicit_account: bool,
    ) -> bool:
        """Sweep one set of accounts. Returns False when the sweep was parked."""
        if not accounts:
            return True
        if not explicit_account:
            accounts = self._due(accounts)
            if not accounts:
                logging.info('No YouTube %s channels are due for a check yet.', download_type)
                return True
        total_accounts = len(accounts)
        burst_size = self.timing.burst_size
        total_batches = (total_accounts + burst_size - 1) // burst_size
        processed = 0
        for i in range(0, total_accounts, burst_size):
            batch = accounts[i : i + burst_size]
            batch_index = i // burst_size + 1
            logging.info('Processing YouTube %s batch %s of %s', download_type, batch_index, total_batches)
            try:
                processed = self._process_batch(batch, break_on_existing_arg, redownload, processed, total_accounts)
            except RateLimited as exc:
                logging.warning('Stopping the YouTube sweep: %s', exc)
                return False
            if i + burst_size < total_accounts:
                self.policy.throttle()
        return True

    def _due(self, accounts: list[YoutubeAccount]) -> list[YoutubeAccount]:
        """Filter by the sweep schedule, which stores audio and video separately."""
        by_key = {entry.schedule_key: entry for entry in accounts}
        return [by_key[key] for key in self.policy.due(list(by_key)) if key in by_key]

    def _get_accounts(self, account: str) -> list[YoutubeAccount]:
        try:
            rows = [YoutubeAccount(name=account)] if account else self.get_accounts_from_db()
        except Exception as e:
            logging.error(f'Database error while fetching YouTube accounts: {e}')
            return []
        rows = [self._as_account(row) for row in rows]
        if not rows:
            logging.warning('No YouTube accounts found in the database.')
            return []
        skipped = [row.name for row in rows if not row.active]
        if skipped:
            logging.info('Skipping %d inactive YouTube channels.', len(skipped))
        rows = [row for row in rows if row.active]
        rows.sort(key=lambda row: (row.download_type, row.name))
        return rows

    @staticmethod
    def _as_account(row) -> YoutubeAccount:
        """Accept plain names too, so a caller passing strings keeps working."""
        return row if isinstance(row, YoutubeAccount) else YoutubeAccount(name=row)

    def _process_batch(self, batch, break_on_existing_arg, redownload, processed, total_accounts):
        batch = [self._as_account(entry) for entry in batch]
        rate_limited = None
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.timing.max_workers) as executor:
            futures = {}
            for acc in batch:
                ydl_opts = self._prepare_ydl_opts(acc, break_on_existing_arg, redownload)
                futures[executor.submit(self._check_account, acc, ydl_opts)] = acc
            for future in concurrent.futures.as_completed(futures):
                acc = futures[future]
                processed += 1
                try:
                    future.result()
                    self.policy.mark_checked(acc.schedule_key)
                except RateLimited as exc:
                    rate_limited = exc
                except SweepAborted as exc:
                    logging.info(str(exc))
                except Exception as exc:
                    logging.error(f'Unhandled error downloading {acc.name}: {exc}')
                job_manager.publish(
                    {
                        'type': 'youtube-account',
                        'account': acc.name,
                        'download_type': acc.download_type,
                        'current': processed,
                        'total': total_accounts,
                    }
                )
        if rate_limited is not None:
            raise rate_limited
        return processed

    def _prepare_ydl_opts(self, acc, break_on_existing_arg, redownload):
        acc = self._as_account(acc)
        effective_break = self.default_break_on_existing if break_on_existing_arg is None else break_on_existing_arg
        opts = self._build_ydl_opts(
            self._archive_file_for(acc),
            break_on_existing=effective_break,
            redownload=redownload,
            download_type=acc.download_type,
        )
        opts['match_filter'] = self._filter_for(acc)
        return opts
