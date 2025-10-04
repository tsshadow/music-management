import concurrent.futures
import logging
import math
import os
import random
import time
from typing import Optional

from yt_dlp import YoutubeDL
from yt_dlp.postprocessor import FFmpegMetadataPP, EmbedThumbnailPP

from api.jobs import job_manager

from downloader.SoundcloudProcessor import SoundcloudSongProcessor
from postprocessing.Song.Helpers.DatabaseConnector import DatabaseConnector
from pathlib import Path



def get_accounts_from_db():
    try:
        db = DatabaseConnector().connect()
        with db.cursor() as cursor:
            cursor.execute("SELECT name FROM soundcloud_accounts")
            accounts = [row[0] for row in cursor.fetchall()]
        return accounts
    except Exception as e:
        logging.error(f"Failed to fetch SoundCloud accounts from DB: {e}")
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
    def __init__(self, break_on_existing=True, max_workers=1, burst_size=10, min_pause=1, max_pause=5):
        self.output_folder = os.getenv("soundcloud_folder")
        self.archive_dir = os.getenv("soundcloud_archive")
        self.cookies_file = os.getenv("soundcloud_cookies", "soundcloud.com_cookies.txt")
        self.ffmpeg_location = os.getenv("ffmpeg-location", "usr/bin/local")
        self.default_break_on_existing = break_on_existing

        if not self.output_folder or not self.archive_dir:
            logging.warning(
                "Missing required environment variables: soundcloud_folder or soundcloud_archive. "
                "SoundCloud downloads will be disabled."
            )
            self.output_folder = None
            self.archive_dir = None
            self.enabled = False
            return

        if not os.path.isdir(self.output_folder):
            raise FileNotFoundError(f"Output folder does not exist: {self.output_folder}")

        if os.path.isfile(self.archive_dir):
            self.archive_file = self.archive_dir
        else:
            os.makedirs(self.archive_dir, exist_ok=True)
            self.archive_file = None

        self.enabled = True
        self.max_workers = max_workers
        self.burst_size = burst_size
        self.min_pause = min_pause
        self.max_pause = max_pause

        self.ydl_opts = {
            'http_headers': {
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/120.0.0.0 Safari/537.36'
                )
            },
            'outtmpl': f'{self.output_folder}/%(uploader)s/%(title)s.%(ext)s',
            'compat_opts': ['filename'],
            'nooverwrites': False,
            'no_part': True,
            'format': 'bestaudio[ext=mp3]',
            'match_filter': self._match_filter,
            'quiet': False,
            'set_file_timestamp': True,
            'cookies': self.cookies_file,
            "ffmpeg_location": self.ffmpeg_location,
        }

        if break_on_existing:
            self.ydl_opts['break_on_existing'] = True

    def _match_filter(self, info):
        duration = info.get("duration")
        title = info.get("title", "unknown")
        if not duration or duration < 60 or duration > 21600:
            logging.info(f"Skipping track '{title}' (duration: {duration}s)")
            return "Outside allowed duration range"
        return None

    def download_account(self, name: str, yt_dl_opts: dict = None):
        link = f"http://soundcloud.com/{name}/tracks"
        logging.info(f"Downloading from SoundCloud account: {name}")

        for attempt in range(1, 4):
            try:
                with YoutubeDL(yt_dl_opts) as ydl:
                    ydl.add_post_processor(FFmpegMetadataPP(ydl))
                    ydl.add_post_processor(EmbedThumbnailPP(ydl))
                    ydl.add_post_processor(SoundcloudSongProcessor())
                    ydl.download([link])
                logging.info(f"Finished downloading from: {name}")
                return
            except Exception as e:
                msg = str(e)
                if '403' in msg:
                    wait_time = random.randint(60, 300)
                    logging.warning(f"403 Forbidden for {name}. Pausing {wait_time}s before retry...")
                    time.sleep(wait_time)
                elif '404' in msg:
                    logging.info(f"Got 404 for {name} — skip song.")
                elif 'already in the archive' in msg:
                    logging.info(f"All tracks for {name} already in archive — skipping.")
                    return  # ✅ don't retry
                else:
                    logging.warning(f"Attempt {attempt} failed for {name}: {e}", exc_info=True)
                    time.sleep(5 * attempt)

        logging.error(f"SoundCloud download failed for {name} after 3 attempts.")

    def run(
        self,
        account: str = "",
        download: bool = True,
        breakOnExisting: Optional[bool] = None,
        redownload: bool = False,
    ):
        if not getattr(self, "enabled", True):
            logging.warning("SoundCloud downloader is not configured; skipping run().")
            return

        if not account:
            accounts = get_accounts_from_db()
            if not accounts:
                logging.warning("No SoundCloud accounts found in the database.")
                return
            accounts.sort()
        else:
            accounts = [account]

        total_accounts = len(accounts)
        processed = 0
        total_batches = math.ceil(total_accounts / self.burst_size)

        for i in range(0, total_accounts, self.burst_size):
            batch = accounts[i:i + self.burst_size]
            batch_num = i // self.burst_size + 1
            logging.info(f"Processing batch {batch_num} of {total_batches}")

            with concurrent.futures.ThreadPoolExecutor(max_workers=32) as executor:
                futures = {}
                for acc in batch:
                    # Clone ydl_opts and set archive file (shared or per-account)
                    ydl_opts = self.ydl_opts.copy()
                    effective_break = (
                        self.default_break_on_existing if breakOnExisting is None else breakOnExisting
                    )
                    if effective_break:
                        ydl_opts['break_on_existing'] = True
                    else:
                        ydl_opts.pop('break_on_existing', None)

                    if not redownload:
                        if self.archive_file:
                            ydl_opts['download_archive'] = str(self.archive_file)
                            logging.info(f"Using shared archive: {self.archive_file}")
                        else:
                            account_archive = Path(self.archive_dir) / f"{acc}.txt"
                            ydl_opts['download_archive'] = str(account_archive)
                            logging.info(f"Using per-account archive: {account_archive} for {acc}")
                    else:
                        ydl_opts.pop('download_archive', None)
                        logging.info(f"Redownload enabled — skipping archive for {acc}.")
                    futures[executor.submit(self.download_account, acc, ydl_opts)] = acc

                for future in concurrent.futures.as_completed(futures):
                    acc = futures[future]
                    processed += 1
                    job_manager.publish({
                        "type": "soundcloud-account",
                        "account": acc,
                        "current": processed,
                        "total": total_accounts,
                    })

            if i + self.burst_size < total_accounts:
                pause = random.randint(self.min_pause, self.max_pause)
                logging.info(f"Throttling pause: sleeping {pause} seconds...")
                time.sleep(pause)
