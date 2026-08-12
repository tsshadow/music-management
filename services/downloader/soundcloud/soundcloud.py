import concurrent.futures
import logging
import math
import os
import shutil
import time
from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.postprocessor import EmbedThumbnailPP, FFmpegMetadataPP

from services.common.config_store import ConfigStore
from services.common.Helpers.DatabaseConnector import DatabaseConnector
from services.common.job_manager import job_manager
from services.downloader.cookie_profile import snapshot_cookie_profile
from services.downloader.rate_state import RateLimited, SweepAborted
from services.downloader.soundcloud.account_report import (
    BLANK,
    THROTTLED,
    UNAVAILABLE_TRACKS,
    AccountReport,
)
from services.downloader.soundcloud.SoundcloudArchive import SoundcloudArchive
from services.downloader.soundcloud.unavailable_tracks import UnavailableTracks
from services.downloader.sweep import SweepPolicy

from .SoundcloudSongProcessor import SoundcloudSongProcessor

SOURCE = 'soundcloud'

# The cookies are taken from the Firefox container that sits logged in on
# soundcloud.com, so the client that presents them says Firefox too. SoundCloud's
# anti-bot layer ties the cookie it issued to the client that holds it, and the
# hardcoded Chrome 120 that used to sit here matched neither the cookies nor any
# browser released this decade. Overridable through the `soundcloud_user_agent`
# setting, which should track the Firefox in docker-compose.
FIREFOX_USER_AGENT = 'Mozilla/5.0 (X11; Linux x86_64; rv:151.0) Gecko/20100101 Firefox/151.0'

def account_from_url(url: str) -> str:
    """The account a SoundCloud URL belongs to, for reporting and write-offs."""
    parts = [part for part in str(url).split('/') if part]
    return parts[2] if len(parts) > 2 else str(url)

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

    How often and how fast this runs comes from `services.downloader.timing`; how
    hard it is currently holding back comes from `services.downloader.rate_state`,
    which remembers a 429 across restarts. Both can be handed in by the caller,
    which is how the tests stay away from the database.
    """

    def __init__(self, break_on_existing=True, dry_run=False, timing=None, rate_state=None,
                 schedule=None, unavailable=None, notifier=None):
        self._config = ConfigStore()
        self.default_break_on_existing = break_on_existing
        self.dry_run = dry_run
        self.redownload_mode = False
        self.policy = SweepPolicy(SOURCE, timing=timing, rate_state=rate_state, schedule=schedule,
                                  notifier=notifier)
        self.unavailable = unavailable if unavailable is not None else UnavailableTracks(
            retry_days=self.policy.timing.unavailable_retry_days)
        self._profile_snapshot: str | None = None
        self._subscriptions = []
        self._apply_config()
        for key in ['soundcloud_folder', 'soundcloud_archive', 'soundcloud_cookies', 'ffmpeg_location']:
            self._subscriptions.append(self._config.subscribe(key, lambda _value, k=key: self._apply_config()))

    @property
    def timing(self):
        return self.policy.timing

    @property
    def rate_state(self):
        return self.policy.rate_state

    def _make_match_filter(self, account: str, report: AccountReport):
        """The match filter bound to one account's run.

        Reaching this at all means yt-dlp read a track's metadata, which is the
        signal that separates "one track is not for us" from "we are being kept
        out": an account that yields no metadata *and* a 403 gave us nothing.
        """
        def _filter(info):
            report.note_extracted(info.get('id'))
            if self.unavailable.should_skip(account, info.get('id')):
                logging.info("Skipping track '%s' (answered 403 before)", info.get('title', 'unknown'))
                return 'Known to be unavailable'
            return self._match_filter(info)
        return _filter

    def _match_filter(self, info):
        duration = info.get('duration')
        title = info.get('title', 'unknown')
        if not duration or duration < 60 or duration > 21600:
            logging.info(f"Skipping track '{title}' (duration: {duration}s)")
            return 'Outside allowed duration range'
        account_id = info.get('channel_id') or info.get('uploader_id')
        video_id = info.get('id')
        if not self.redownload_mode and account_id and video_id and SoundcloudArchive.exists(account_id, video_id):
            logging.info(f"Skipping track '{title}' (already in database archive)")
            return 'Already in database archive'
        return None

    def download_account(self, name: str, yt_dl_opts: dict=None):
        self.policy.guard(name)
        link = f'http://soundcloud.com/{name}/tracks'
        logging.info(f'Downloading from SoundCloud account: {name}')
        self.download_url(link, yt_dl_opts, account=name)
        logging.info(f'Finished downloading from: {name}')

    def download_url(self, url: str, yt_dl_opts: dict=None, account: str | None=None):
        """
        Download tracks from a specific SoundCloud URL (account, playlist, or single track).

        A 429 is written to the rate state and raised as `RateLimited` instead of being
        slept off in place. Parking the source in the database means a restart cannot
        forget about it, and no thread sits blocked for hours.

        A 403 is not the same signal. yt-dlp runs with `ignoreerrors`, so a track that
        is subscriber-only, geo-blocked or since made private simply logs one. Those are
        written off per track and the sweep carries on; only a run of accounts that
        yield nothing at all is read as SoundCloud keeping us out.
        """
        account = account or account_from_url(url)
        for attempt in range(1, self.timing.retry_attempts + 1):
            report = AccountReport()
            opts = (yt_dl_opts or {}).copy()
            opts['logger'] = report
            opts['match_filter'] = self._make_match_filter(account, report)
            try:
                with YoutubeDL(opts) as ydl:
                    ydl.add_post_processor(FFmpegMetadataPP(ydl))
                    ydl.add_post_processor(EmbedThumbnailPP(ydl))
                    ydl.add_post_processor(SoundcloudSongProcessor())
                    ydl.download([url])

                self._settle(report, account, url)
                return
            except RateLimited:
                raise
            except Exception as e:
                msg = str(e)
                rate_limited = self.policy.rate_limit_from(e, url)
                if rate_limited is not None:
                    raise rate_limited from e
                if '404' in msg:
                    logging.info(f'Got 404 for {url} — skip.')
                    return
                if 'already in the archive' in msg:
                    logging.info(f'Track for {url} already in archive — skipping.')
                    return
                logging.warning(f'Attempt {attempt} failed for {url}: {e}', exc_info=True)
                time.sleep(5 * attempt)
        logging.error(f'SoundCloud download failed for {url} after {self.timing.retry_attempts} attempts.')

    def _settle(self, report: AccountReport, account: str, url: str) -> None:
        """Act on what one account's run reported.

        Raises `RateLimited` only when the evidence supports it: an explicit 429, or
        enough accounts in a row that gave nothing back.
        """
        outcome = report.outcome
        if outcome == THROTTLED:
            raise self.policy.park('429', url)
        if outcome == UNAVAILABLE_TRACKS:
            for track_id in report.forbidden_tracks:
                self.unavailable.remember(account, track_id, reason='403')
            logging.info('%d track(s) of %s are not available to us; the rest of the '
                         'account was fine.', len(report.forbidden_tracks), account)
            self.policy.note_progress()
            return
        if outcome == BLANK:
            rate_limited = self.policy.note_blank(account)
            if rate_limited is not None:
                raise rate_limited
            return
        self.policy.note_progress()

    def run(self, account: str='', break_on_existing_arg: bool | None=None, redownload: bool=False):
        if not getattr(self, 'downloader_config', {}).get('enabled', True):
            logging.warning('SoundCloud soundcloud is not configured; skipping run().')
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
                logging.info('No SoundCloud accounts are due for a check yet.')
                return
        total_accounts = len(accounts)
        burst_size = self.timing.burst_size
        total_batches = math.ceil(total_accounts / burst_size)
        processed = 0
        for i in range(0, total_accounts, burst_size):
            batch = accounts[i:i + burst_size]
            batch_num = i // burst_size + 1
            logging.info(f'Processing batch {batch_num} of {total_batches}')
            try:
                processed = self._process_batch(batch, break_on_existing_arg, redownload, processed, total_accounts)
            except RateLimited as exc:
                logging.warning('Stopping the SoundCloud sweep: %s', exc)
                return
            if i + burst_size < total_accounts:
                self.policy.throttle()
        self.policy.finish()

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
                job_manager.publish({'type': 'soundcloud-account', 'account': acc, 'current': processed, 'total': total_accounts})
        if rate_limited is not None:
            raise rate_limited
        return processed

    def _prepare_ydl_opts(self, acc, break_on_existing_arg, redownload):
        ydl_opts = self.downloader_config['ydl_opts'].copy()
        ydl_opts['simulate'] = self.dry_run
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

    def _snapshot_profile(self, profile: str | None) -> str | None:
        """Point yt-dlp at a checkpointed copy of the live Firefox profile.

        Firefox is still running and writes cookies through a write-ahead log that
        yt-dlp's own copy step does not carry over, so the freshest cookie -- the
        rotating anti-bot one -- can be missing from what the downloader presents.
        Falls back to the live profile when a snapshot cannot be taken.
        """
        if not profile:
            return profile
        if self._profile_snapshot:
            shutil.rmtree(self._profile_snapshot, ignore_errors=True)
            self._profile_snapshot = None
        snapshot = snapshot_cookie_profile(profile)
        if snapshot is None:
            return profile
        self._profile_snapshot = snapshot
        return snapshot

    def _apply_config(self) -> None:
        values = self._config.get_many(['soundcloud_folder', 'soundcloud_archive', 'soundcloud_cookies', 'ffmpeg_location', 'soundcloud_user_agent'])
        self.downloader_config = {'output_folder': values.get('soundcloud_folder') or None, 'archive_dir': values.get('soundcloud_archive') or None, 'cookies_file': values.get('soundcloud_cookies') or 'soundcloud.com_cookies.txt', 'ffmpeg_location': values.get('ffmpeg_location') or '/usr/bin', 'user_agent': values.get('soundcloud_user_agent') or FIREFOX_USER_AGENT, 'enabled': True, 'archive_file': None, 'ydl_opts': {}}
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
        self.downloader_config['ydl_opts'] = {'http_headers': {'User-Agent': self.downloader_config['user_agent']}, 'outtmpl': f"{self.downloader_config['output_folder']}/%(uploader)s/%(title)s.%(ext)s", 'compat_opts': ['filename'], 'nooverwrites': False, 'no_part': True, 'format': 'bestaudio[ext=mp3]', 'quiet': False, 'ignoreerrors': True, 'set_file_timestamp': True, 'ffmpeg_location': self.downloader_config['ffmpeg_location'], 'lazy_playlist': True, **self.timing.to_ydl_opts()}
        cookies_file = self.downloader_config['cookies_file']
        if cookies_file:
            if cookies_file.startswith('firefox:'):
                parts = cookies_file.split(':', 1)
                profile = parts[1] if len(parts) > 1 else None
                profile = self._snapshot_profile(profile)
                logging.info(f'Using cookiesfrombrowser=firefox with profile: {profile} for SoundCloud')
                self.downloader_config['ydl_opts']['cookiesfrombrowser'] = ('firefox', profile)
            else:
                self.downloader_config['ydl_opts']['cookies'] = cookies_file
        else:
            self.downloader_config['ydl_opts']['cookiesfrombrowser'] = ('firefox',)
        if self.default_break_on_existing:
            self.downloader_config['ydl_opts']['break_on_existing'] = True
