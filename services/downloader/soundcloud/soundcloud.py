import concurrent.futures
import logging
import math
import os
import shutil
import time
from datetime import datetime
from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.postprocessor import EmbedThumbnailPP, FFmpegMetadataPP

from services.common.config_store import ConfigStore
from services.common.Helpers.DatabaseConnector import DatabaseConnector
from services.downloader import shutdown
from services.downloader.account_report import (
    BLANK,
    THROTTLED,
    UNAVAILABLE_TRACKS,
    AccountReport,
)
from services.downloader.cookie_profile import snapshot_cookie_profile
from services.downloader.deep_sweep import (
    DeepSweepReport,
    ListingFailed,
    ids_in_text_archive,
    list_flat,
    snapshot_state,
    take_snapshot,
    wanted_tracks,
)
from services.downloader.metadata_date import IsoUploadDatePP
from services.downloader.rate_state import RateLimited, SweepAborted
from services.downloader.redownload import ReplaceExistingPP, redownload_opts, staged_opts
from services.downloader.soundcloud.account_probe import ProbeResult, newest_track
from services.downloader.soundcloud.SoundcloudArchive import SoundcloudArchive
from services.downloader.sweep import SweepPolicy
from services.downloader.write_offs import WriteOffs

from .SoundcloudSongProcessor import SoundcloudSongProcessor

SOURCE = 'soundcloud'

# The duration range this source downloads. A track rejected on it is written
# down together with the duration it was judged on, so widening this brings those
# tracks back without a request spent rediscovering what they are.
DURATION_BOUNDS = (60, 21600)

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
        with DatabaseConnector().connection() as db, db.cursor() as cursor:
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

    def __init__(
        self,
        break_on_existing=True,
        dry_run=False,
        timing=None,
        rate_state=None,
        schedule=None,
        unavailable=None,
        notifier=None,
        deep=False,
    ):
        self._config = ConfigStore()
        self.default_break_on_existing = break_on_existing
        self.dry_run = dry_run
        self.redownload_mode = False
        # Forces the deep path for every account this run, whatever the cadence
        # says. What `--deep` on the CLI turns on.
        self.deep_mode = deep
        self.policy = SweepPolicy(SOURCE, timing=timing, rate_state=rate_state, schedule=schedule, notifier=notifier)
        self.unavailable = (
            unavailable
            if unavailable is not None
            else WriteOffs(SOURCE, retry_days=self.policy.timing.unavailable_retry_days)
        )
        self._profile_snapshot: str | None = None
        # What this sweep learned per account, waiting to be written to the
        # schedule once the account's future comes back.
        self._learned: dict[str, datetime] = {}
        self._seen_tracks: dict[str, str] = {}
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
            report.note_extracted(info.get('id'), info.get('timestamp'))
            if self.unavailable.should_skip(account, info.get('id'), DURATION_BOUNDS):
                logging.info("Skipping track '%s' (written off before)", info.get('title', 'unknown'))
                return 'Known to be unavailable'
            verdict = self._match_filter(info)
            if verdict == 'Outside allowed duration range':
                # Written down rather than only logged: a pass that walks the
                # whole account would otherwise rediscover this track every time,
                # and could never report the account finished.
                duration = int(info.get('duration') or 0)
                reason = 'too_short' if duration < DURATION_BOUNDS[0] else 'too_long'
                self.unavailable.remember(account, info.get('id'), reason, duration=duration)
            return verdict

        return _filter

    def _match_filter(self, info):
        duration = info.get('duration')
        title = info.get('title', 'unknown')
        if not duration or duration < DURATION_BOUNDS[0] or duration > DURATION_BOUNDS[1]:
            logging.info(f"Skipping track '{title}' (duration: {duration}s)")
            return 'Outside allowed duration range'
        account_id = info.get('channel_id') or info.get('uploader_id')
        video_id = info.get('id')
        if not self.redownload_mode and account_id and video_id and SoundcloudArchive.exists(account_id, video_id):
            logging.info(f"Skipping track '{title}' (already in database archive)")
            return 'Already in database archive'
        return None

    def _probe(self, account: str, ydl_opts: dict) -> ProbeResult | None:
        """The account's newest track, or None when the probe cannot answer.

        A refused listing goes to the backoff exactly as a full run's answer would:
        a 429 parks the source, a 403 counts as one blank account and is raised as
        `ListingFailed` so the account is not asked again (see `_refused_listing`).
        Anything else returns None, which falls through to the full run: the probe
        is an optimisation and may never be the reason an account goes unchecked.
        """
        try:
            return newest_track(account, ydl_opts)
        except ListingFailed as exc:
            if self._refused_listing(exc, account):
                raise
            logging.warning('Could not probe %s (%s); doing the full run instead.', account, exc)
            return None
        except Exception as exc:
            rate_limited = self.policy.rate_limit_from(exc, account)
            if rate_limited is not None:
                raise rate_limited from exc
            logging.warning('Could not probe %s (%s); doing the full run instead.', account, exc)
            return None

    def _text_archive_for(self, account: str) -> str | None:
        """The yt-dlp archive file this account's downloads are recorded in."""
        configured = self.downloader_config.get('archive_file')
        if configured:
            return str(configured)
        archive_dir = self.downloader_config.get('archive_dir')
        if not archive_dir:
            return None
        return str(Path(archive_dir) / f'{account}.txt')

    def _held_ids(self, account: str, track_ids: list[str]) -> set[str]:
        """Everything already downloaded, from both records that decide that.

        yt-dlp consults its own text archive, so a track listed there is one it
        will silently refuse to fetch again. Leaving those out would queue the
        same tracks on every pass and never see them arrive.
        """
        held = SoundcloudArchive.held_ids(track_ids)
        held.update(ids_in_text_archive(self._text_archive_for(account)))
        return held

    def deep_sweep_account(self, account: str, ydl_opts: dict) -> DeepSweepReport:
        """Walk an account's whole catalogue and fetch whatever is missing.

        The ordinary run stops at the first archived track, so a run that was
        parked mid-account leaves a hole no later run can reach. This lists the
        account flat -- one request per 200 tracks, nothing resolved -- and
        resolves only what is genuinely absent, which is why it costs the size of
        the gap rather than the size of the account.

        The caller marks the account deep-swept only when the report says the
        pass finished. Being parked or hitting the cap leaves it deep-due, so the
        next ordinary sweep picks the tail up the following day rather than the
        following month.
        """
        self.policy.guard(account)
        url = f'https://soundcloud.com/{account}/tracks'
        listing = self._list_or_park(url, ydl_opts, account)
        ids = [entry.track_id for entry in listing]
        held = self._held_ids(account, ids)
        write_offs = self.unavailable.load_many(account, ids)
        wanted = wanted_tracks(
            listing, held, write_offs, self.timing.unavailable_retry_days, self.unavailable.now(), DURATION_BOUNDS
        )
        batch = wanted[: self.timing.deep_sweep_max_downloads]
        logging.info(
            'Deep sweep of %s: %d listed, %d held, %d written off, %d missing, fetching %d.',
            account,
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
                self.policy.guard(account)
                # Recorded before the download, not after: a track the pass never
                # reached must not be charged with a failed attempt, or three
                # interrupted passes write it off for a month.
                attempted.append(entry)
                self.download_url(entry.url, ydl_opts, account=account)
            finished = True
        except RateLimited:
            parked = True
            raise
        finally:
            report = self._settle_deep(
                account, listing, held, write_offs, wanted, batch, attempted, parked, interrupted=not finished
            )
            logging.info('Deep sweep of %s: %s', account, report.summary())
        return report

    def _list_or_park(self, url: str, ydl_opts: dict, account: str) -> list:
        """The flat listing, or `ListingFailed` saying why there is none.

        Whatever the reason, the account was not checked, so it must be neither
        marked deep-swept nor counted as progress against a blank run. A refusal
        is also fed to the backoff first (see `_refused_listing`).
        """
        try:
            return list_flat(url, ydl_opts)
        except ListingFailed as exc:
            self._refused_listing(exc, account)
            raise

    def _refused_listing(self, exc: ListingFailed, account: str) -> bool:
        """Feed a failed listing to the backoff; return whether SoundCloud refused it.

        A 429 parks the source outright, as it does everywhere. A 403 is read the
        way a full run that got nothing back is read (see `_settle`): one blank
        account, and only `block_threshold` of them in a row park the source -- an
        account that is private or blocked in this region answers 403 too. When
        that threshold is reached the `RateLimited` is raised from here.
        """
        if exc.status == 429:
            raise self.policy.park('429', account) from exc
        if exc.status != 403:
            return False
        rate_limited = self.policy.note_blank(account)
        if rate_limited is not None:
            raise rate_limited from exc
        return True

    def _settle_deep(
        self, account: str, listing, held, write_offs, wanted, batch, attempted, parked: bool, interrupted: bool = False
    ) -> DeepSweepReport:
        """Count what actually arrived, and write off what did not.

        One extra lookup per pass. A track that neither downloaded nor rejected
        has to be counted, or a single permanently broken track keeps its account
        incomplete and re-swept every day forever.
        """
        arrived = self._held_ids(account, [entry.track_id for entry in attempted]) if attempted else set()
        downloaded = 0
        for entry in attempted:
            if entry.track_id in arrived:
                downloaded += 1
                continue
            if parked:
                # The sweep was stopped mid-batch; nothing was wrong with this
                # track, we simply never asked about it.
                continue
            if self.unavailable.should_skip(account, entry.track_id, DURATION_BOUNDS):
                # Rejected during this very pass. A decision, not a failure.
                continue
            self.unavailable.note_failure(account, entry.track_id)
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
            self.unavailable.load_many(account, ids),
            self.timing.unavailable_retry_days,
            self.unavailable.now(),
            DURATION_BOUNDS,
            snapshot_state(report, interrupted),
        )
        self.policy.record_snapshot(account, snapshot)
        return report

    def _check_account(self, account: str, ydl_opts: dict) -> None:
        """One account: ask what its newest track is, and only dig in if it is new.

        A listing SoundCloud refused with a 403 has already been counted as a blank
        account; the account is left there, exactly like a full run that came back
        empty, rather than asked a second time.
        """
        try:
            self._check_account_inner(account, ydl_opts)
        except ListingFailed as exc:
            if exc.status != 403:
                raise
            logging.info('%s; counted as an account that gave nothing back.', exc)

    def _check_account_inner(self, account: str, ydl_opts: dict) -> None:
        """The deep pass when due, else the probe and, if it finds something new, the full run."""
        if self.deep_mode or self.policy.deep_due(account):
            try:
                report = self.deep_sweep_account(account, ydl_opts)
            except ListingFailed as exc:
                if exc.status == 403:
                    raise
                # No listing, but not a refusal either. The account stays deep-due,
                # counts as no progress, and still gets the ordinary check below.
                logging.warning('%s; checking the account the ordinary way instead.', exc)
            else:
                if report.complete:
                    self.policy.mark_deep_swept(account)
                # Only reached when the listing came back: a refused one raises out
                # of the pass above, so a 403 storm can no longer reset the blank run.
                self.policy.note_progress()
                return
        probe = self._probe(account, ydl_opts)
        if probe is not None:
            self._seen_tracks[account] = probe.track_id
            if SoundcloudArchive.track_exists(probe.track_id):
                logging.info('%s has nothing new; newest track %s is already archived.', account, probe.track_id)
                # Not optional: without this a stretch of quiet accounts leaves
                # the blank run untouched, and the next genuinely blank account
                # can tip the source over block_threshold and park it.
                self.policy.note_progress()
                return
        self.download_account(account, ydl_opts)

    def _record_upload_date(self, account: str, report: AccountReport) -> None:
        """Remember the newest upload this run saw, for the tier ladder."""
        if report.newest_timestamp is None:
            return
        self._learned[account] = datetime.fromtimestamp(report.newest_timestamp)

    def _checked_kwargs(self, account: str) -> dict:
        """What this sweep learned about the account, consumed as it is reported."""
        learned = {}
        upload_at = self._learned.pop(account, None)
        if upload_at is not None:
            learned['last_upload_at'] = upload_at
        track_id = self._seen_tracks.pop(account, None)
        if track_id is not None:
            learned['last_seen_track_id'] = track_id
        return learned

    def download_account(self, name: str, yt_dl_opts: dict = None):
        self.policy.guard(name)
        link = f'http://soundcloud.com/{name}/tracks'
        logging.info(f'Downloading from SoundCloud account: {name}')
        self.download_url(link, yt_dl_opts, account=name)
        logging.info(f'Finished downloading from: {name}')

    def download_url(self, url: str, yt_dl_opts: dict = None, account: str | None = None, replace: str | None = None):
        """
        Download tracks from a specific SoundCloud URL (account, playlist, or single track).

        `replace` is the library file a redownload replaces. The track is then fetched
        into a staging folder beside it and moved over it in one rename once yt-dlp's own
        post-processors are done, so a failed redownload leaves the old file in place
        (see services/downloader/redownload.py).

        A 429 is written to the rate state and raised as `RateLimited` instead of being
        slept off in place. Parking the source in the database means a restart cannot
        forget about it, and no thread sits blocked for hours.

        A 403 is not the same signal. yt-dlp runs with `ignoreerrors`, so a track that
        is subscriber-only, geo-blocked or since made private simply logs one. Those are
        written off per track and the sweep carries on; only a run of accounts that
        yield nothing at all is read as SoundCloud keeping us out.
        """
        if replace:
            with staged_opts(yt_dl_opts or {}, replace) as staged:
                self._download_url(url, staged, account, replace)
            return
        self._download_url(url, yt_dl_opts, account, None)

    def _download_url(self, url: str, yt_dl_opts: dict | None, account: str | None, replace: str | None) -> None:
        """download_url's body: the attempts, and what each one's report means."""
        account = account or account_from_url(url)
        for attempt in range(1, self.timing.retry_attempts + 1):
            report = AccountReport()
            opts = (yt_dl_opts or {}).copy()
            opts['logger'] = report
            opts['match_filter'] = self._make_match_filter(account, report)
            try:
                with YoutubeDL(opts) as ydl:
                    # Before FFmpegMetadata: EmbedThumbnail rewrites an mp3 as ID3v2.3,
                    # which cuts an undelimited date to the year (bug report 088).
                    ydl.add_post_processor(IsoUploadDatePP(), when='pre_process')
                    ydl.add_post_processor(FFmpegMetadataPP(ydl))
                    ydl.add_post_processor(EmbedThumbnailPP(ydl))
                    if replace:
                        ydl.add_post_processor(ReplaceExistingPP(replace))
                    ydl.add_post_processor(SoundcloudSongProcessor(opts))
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
                if shutdown.is_requested():
                    raise SweepAborted(f'Abandoned {url}; the {SOURCE} worker is shutting down.') from e
                logging.warning(f'Attempt {attempt} failed for {url}: {e}', exc_info=True)
                time.sleep(5 * attempt)
        logging.error(f'SoundCloud download failed for {url} after {self.timing.retry_attempts} attempts.')

    def _settle(self, report: AccountReport, account: str, url: str) -> None:
        """Act on what one account's run reported.

        Raises `RateLimited` only when the evidence supports it: an explicit 429, or
        enough accounts in a row that gave nothing back.
        """
        self._record_upload_date(account, report)
        outcome = report.outcome
        if outcome == THROTTLED:
            raise self.policy.park('429', url)
        if outcome == UNAVAILABLE_TRACKS:
            for track_id in report.forbidden_tracks:
                self.unavailable.remember(account, track_id, reason='403')
            logging.info(
                '%d track(s) of %s are not available to us; the rest of the account was fine.',
                len(report.forbidden_tracks),
                account,
            )
            self.policy.note_progress()
            return
        if outcome == BLANK:
            rate_limited = self.policy.note_blank(account)
            if rate_limited is not None:
                raise rate_limited
            return
        self.policy.note_progress()

    def run(self, account: str = '', break_on_existing_arg: bool | None = None, redownload: bool = False):
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
            batch = accounts[i : i + burst_size]
            batch_num = i // burst_size + 1
            logging.info(f'Processing batch {batch_num} of {total_batches}')
            try:
                processed = self._process_batch(batch, break_on_existing_arg, redownload, processed)
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
            # Left unsorted: the schedule orders whatever is due by overdue-ness.
            return accounts
        return [account]

    def _process_batch(self, batch, break_on_existing_arg, redownload, processed):
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
                    self.policy.mark_checked(acc, **self._checked_kwargs(acc))
                except RateLimited as exc:
                    rate_limited = exc
                except SweepAborted as exc:
                    logging.info(str(exc))
                except Exception as exc:
                    logging.error(f'Unhandled error downloading {acc}: {exc}')
        if rate_limited is not None:
            raise rate_limited
        return processed

    def _prepare_ydl_opts(self, acc, break_on_existing_arg, redownload):
        ydl_opts = self.downloader_config['ydl_opts'].copy()
        ydl_opts['simulate'] = self.dry_run
        # The only checkpoint that is reachable during a download. Without it the
        # worker sits inside one multi-minute call and never sees the stop the
        # deploy asked for, so SIGKILL arrives with the pass unrecorded.
        ydl_opts['progress_hooks'] = [*ydl_opts.get('progress_hooks', []), shutdown.abort_hook]
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
            # Explicit, not left to the configured `nooverwrites: False`: a redownload
            # exists to replace the file, and yt-dlp skips an existing one otherwise.
            ydl_opts = redownload_opts(ydl_opts)
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
        values = self._config.get_many(
            [
                'soundcloud_folder',
                'soundcloud_archive',
                'soundcloud_cookies',
                'ffmpeg_location',
                'soundcloud_user_agent',
            ]
        )
        self.downloader_config = {
            'output_folder': values.get('soundcloud_folder') or None,
            'archive_dir': values.get('soundcloud_archive') or None,
            'cookies_file': values.get('soundcloud_cookies') or 'soundcloud.com_cookies.txt',
            'ffmpeg_location': values.get('ffmpeg_location') or '/usr/bin',
            'user_agent': values.get('soundcloud_user_agent') or FIREFOX_USER_AGENT,
            'enabled': True,
            'archive_file': None,
            'ydl_opts': {},
        }
        if not self.downloader_config['output_folder'] or not self.downloader_config['archive_dir']:
            if getattr(self, 'downloader_config', {}).get('enabled', True):
                logging.warning(
                    'Missing required configuration for SoundCloud downloads. SoundCloud downloads will be disabled.'
                )
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
            'http_headers': {'User-Agent': self.downloader_config['user_agent']},
            'outtmpl': f"{self.downloader_config['output_folder']}/%(uploader)s/%(title)s.%(ext)s",
            'compat_opts': ['filename'],
            'nooverwrites': False,
            # No `nopart`: yt-dlp writes to `<name>.part` and renames on completion, so a
            # download cut off by SIGKILL or a dropped connection never sits in the tree
            # under its real name for the tagger and the scanner to pick up. The archive
            # row is written by SoundcloudSongProcessor, a post-processor, which only runs
            # after that rename. (A `no_part: True` stood here for years; yt-dlp spells the
            # option `nopart`, so it never did anything -- removed rather than corrected.)
            # `EmbedThumbnailPP` (added in download_url) embeds a thumbnail *file*: it reads
            # `info['thumbnails'][i]['filepath']` and, finding none, prints "There are no
            # thumbnails on disk" and returns the info untouched. The CLI's --embed-thumbnail
            # implies --write-thumbnail; adding the post-processor through the API does not, so
            # without this every SoundCloud download landed without artwork -- 387 of 149.626
            # tracks on production had any, and the web UI drew the placeholder for the rest.
            'writethumbnail': True,
            'format': 'bestaudio[ext=mp3]',
            'quiet': False,
            'ignoreerrors': True,
            'set_file_timestamp': True,
            'ffmpeg_location': self.downloader_config['ffmpeg_location'],
            'lazy_playlist': True,
            **self.timing.to_ydl_opts(),
        }
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
