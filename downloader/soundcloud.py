import concurrent.futures
import json
import logging
import math
import os
import random
import subprocess
import time

from yt_dlp import YoutubeDL
from yt_dlp.postprocessor import PostProcessor, FFmpegMetadataPP, EmbedThumbnailPP

from data.DatabaseConnector import DatabaseConnector
from postprocessing.Song.SoundcloudSong import SoundcloudSong

class SoundcloudSongProcessor(PostProcessor):
    def run(self, info):
        path = info.get('filepath') or info.get('_filename')  # depending on yt-dlp version
        url = info.get('webpage_url')
        if path and url:
            logging.info(f"Postprocessing downloaded file: {path}")
            try:
                # Dump full info
                result = subprocess.run(
                    ["yt-dlp", "--dump-single-json", "--no-playlist", url],
                    capture_output=True,
                    text=True,
                    check=True
                )
                enriched_info = json.loads(result.stdout)
                logging.debug(f"Enriched info dump keys: {list(enriched_info.keys())}")

                # add enriched info
                info.update(enriched_info)


                # pass enriched info
                SoundcloudSong(path, enriched_info)

            except subprocess.CalledProcessError as e:
                logging.error(f"Failed to enrich metadata for {url}: {e.stderr}")
                SoundcloudSong(path)
            except Exception as e:
                logging.error(f"SoundcloudSong failed for {path}: {e}", exc_info=True)
        else:
            logging.warning("Postprocessor: no path or URL found in info dict")
        return [], info

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
    def __init__(self, max_workers=1, burst_size=60, min_pause=1, max_pause=5):
        self.output_folder = os.getenv("soundcloud_folder")
        self.archive_file = os.getenv("soundcloud_archive")
        self.cookies_file = os.getenv("soundcloud_cookies", "soundcloud.com_cookies.txt")

        if not self.output_folder or not self.archive_file:
            raise ValueError("Missing required environment variables: soundcloud_folder or soundcloud_archive")

        if not os.path.isdir(self.output_folder):
            raise FileNotFoundError(f"Output folder does not exist: {self.output_folder}")

        archive_dir = os.path.dirname(self.archive_file)
        if archive_dir and not os.path.exists(archive_dir):
            raise FileNotFoundError(f"Directory for archive file does not exist: {archive_dir}")

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
            'download_archive': self.archive_file,
            'compat_opts': ['filename'],
            'nooverwrites': False,
            'no_part': True,
            'format': 'bestaudio[ext=mp3]',
            'match_filter': self._match_filter,
            'quiet': False,
            # 'break_on_existing': True,
            'cookies': self.cookies_file,
        }

    def _match_filter(self, info):
        duration = info.get("duration")
        title = info.get("title", "unknown")
        if not duration or duration < 60 or duration > 10800:
            logging.info(f"Skipping track '{title}' (duration: {duration}s)")
            return "Outside allowed duration range"
        return None

    def download_account(self, name: str):
        link = f"http://soundcloud.com/{name}/tracks"
        logging.info(f"Downloading from SoundCloud account: {name}")

        for attempt in range(1, 4):
            try:
                with YoutubeDL(self.ydl_opts) as ydl:
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
                elif 'already in the archive' in msg:
                    logging.info(f"All tracks for {name} already in archive — skipping.")
                    return  # ✅ don't retry
                else:
                    logging.warning(f"Attempt {attempt} failed for {name}: {e}")
                    time.sleep(5 * attempt)

        logging.error(f"SoundCloud download failed for {name} after 3 attempts.")


    def run(self, account=""):
        if not account:
            accounts = get_accounts_from_db()
            if not accounts:
                logging.warning("No SoundCloud accounts found in the database.")
                return
            accounts.sort()
        else:
            accounts = [account]
            self.ydl_opts['download_archive'] = "archives/" + account + ".txt"

        total_batches = math.ceil(len(accounts) / self.burst_size)

        for i in range(0, len(accounts), self.burst_size):
            batch = accounts[i:i + self.burst_size]
            batch_num = i // self.burst_size + 1
            logging.info(f"Processing batch {batch_num} of {total_batches}")

            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                executor.map(self.download_account, batch)

            if i + self.burst_size < len(accounts):
                pause = random.randint(self.min_pause, self.max_pause)
                logging.info(f"Throttling pause: sleeping {pause} seconds...")
                time.sleep(pause)
