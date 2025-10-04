import concurrent.futures
import logging
import os
import random
import time

from yt_dlp import YoutubeDL

from downloader.YoutubeSongProcessor import YoutubeSongProcessor
from postprocessing.Song.Helpers.DatabaseConnector import DatabaseConnector


class YoutubeDownloader:
    def __init__(
        self,
        break_on_existing: bool = True,
        max_workers: int = 1,
        burst_size: int = 10,
        min_pause: int = 1,
        max_pause: int = 5,
        socket_timeout: int = 30,
    ):
        self.output_folder = os.getenv("youtube_folder")
        self.archive_dir = os.getenv("youtube_archive")
        self.ffmpeg_location = os.getenv("ffmpeg-location", "usr/bin/local")

        self.max_workers = max_workers
        self.burst_size = burst_size
        self.min_pause = min_pause
        self.max_pause = max_pause
        self.socket_timeout = socket_timeout
        self.default_break_on_existing = break_on_existing

        if not self.output_folder or not self.archive_dir:
            logging.warning(
                "Missing required environment variables for youtube_folder or youtube_archive. "
                "YouTube downloads will be disabled."
            )
            self.output_folder = None
            self.archive_dir = None
            self.enabled = False
        else:
            os.makedirs(self.output_folder, exist_ok=True)
            os.makedirs(self.archive_dir, exist_ok=True)
            self.enabled = True

        # Read optional cookie/user-agent env once
        self.cookies_file = os.getenv("YT_COOKIES")  # expected to be a path to cookies.txt
        self.user_agent = os.getenv("YT_USER_AGENT")  # optional: keep UA aligned with browser

        if not self.enabled:
            self._base_ydl_opts = {}
            return

        self._base_ydl_opts = {
            "outtmpl": f"{self.output_folder}/%(uploader)s/%(title)s.%(ext)s",
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "m4a"},
                {"key": "EmbedThumbnail"},
                {"key": "FFmpegMetadata"},
            ],
            "compat_opts": ["filename"],
            "nooverwrites": True,
            "keepvideo": False,
            "ffmpeg_location": self.ffmpeg_location,
            "match_filter": self._match_filter,
            "socket_timeout": self.socket_timeout,
        }

        # Merge cookie options and user agent on the base options
        self._base_ydl_opts.update(self._cookie_options())
        if self.user_agent:
            self._base_ydl_opts["user_agent"] = self.user_agent

    def _cookie_options(self) -> dict:
        """
        Build yt-dlp cookie-related options.
        Prefer a provided cookies.txt (YT_COOKIES) if it exists; otherwise
        fall back to reading from a Firefox profile inside the container.
        """
        opts: dict = {}
        if self.cookies_file:
            if os.path.exists(self.cookies_file):
                logging.info(f"Using cookies.txt from YT_COOKIES: {self.cookies_file}")
                opts["cookies"] = self.cookies_file
                return opts
            else:
                logging.warning(
                    f"YT_COOKIES is set but file not found: {self.cookies_file}. "
                    "Falling back to cookiesfrombrowser=firefox."
                )

        # Fallback: read directly from Firefox profile (container-side)
        opts["cookiesfrombrowser"] = ("firefox",)
        logging.info("Using cookiesfrombrowser=firefox (no YT_COOKIES file).")
        return opts

    def _build_ydl_opts(self, archive_file: str, break_on_existing: bool = True) -> dict:
        opts = {**self._base_ydl_opts}
        if "postprocessors" in self._base_ydl_opts:
            opts["postprocessors"] = [
                pp.copy() if isinstance(pp, dict) else pp
                for pp in self._base_ydl_opts["postprocessors"]
            ]
        opts["download_archive"] = archive_file
        if break_on_existing:
            opts["break_on_existing"] = True
        return opts

    def _create_ydl(self, ydl_opts: dict) -> YoutubeDL:
        ydl = YoutubeDL(ydl_opts)
        ydl.add_post_processor(YoutubeSongProcessor())
        return ydl

    def _match_filter(self, info):
        duration = info.get("duration")
        title = info.get("title", "unknown")
        if not duration or duration < 60 or duration > 21600:
            logging.info(f"Skipping video '{title}' (duration: {duration}s)")
            return "Outside allowed duration range"
        return None

    def download_account(self, name: str, ydl_opts: dict = None):
        link = f"http://www.youtube.com/{name}"
        archive_file = os.path.join(self.archive_dir, f"{name}.txt")
        opts_template = ydl_opts or self._build_ydl_opts(
            archive_file, break_on_existing=self.default_break_on_existing
        )

        for attempt in range(1, 4):
            try:
                opts = dict(opts_template)
                if "postprocessors" in opts_template:
                    opts["postprocessors"] = [
                        pp.copy() if isinstance(pp, dict) else pp
                        for pp in opts_template["postprocessors"]
                    ]
                with self._create_ydl(opts) as ydl:
                    logging.info(f"Downloading from account: {name}")
                    ydl.download([link])
                logging.info(f"Finished downloading from: {name}")
                return
            except Exception as e:
                msg = str(e)
                if "403" in msg:
                    wait_time = random.randint(60, 300)
                    logging.warning(
                        f"403 Forbidden for {name}. Pausing {wait_time}s before retry..."
                    )
                    time.sleep(wait_time)
                elif "404" in msg:
                    logging.info(f"Got 404 for {name} — skipping video.")
                    return
                elif "already been recorded" in msg or "already in the archive" in msg:
                    logging.info(
                        f"All videos for {name} already in archive — skipping further attempts."
                    )
                    return
                elif "timed out" in msg.lower():
                    logging.warning(
                        f"Timeout encountered for {name}. Attempt {attempt} failed: {e}"
                    )
                    time.sleep(5 * attempt)
                else:
                    logging.warning(
                        f"Attempt {attempt} failed for {name}: {e}", exc_info=True
                    )
                    time.sleep(5 * attempt)

        logging.error(f"YouTube download failed for {name} after 3 attempts.")

    def download_link(self, url: str, breakOnExisting: bool = True):
        """Download a single video using a direct URL."""
        archive_file = os.path.join(self.archive_dir, "manual.txt")

        try:
            opts = self._build_ydl_opts(archive_file, break_on_existing=breakOnExisting)
            with self._create_ydl(opts) as ydl:
                logging.info(f"Downloading from url: {url}")
                ydl.download([url])
            logging.info("Finished downloading video")
        except Exception as e:
            logging.error(f"Download failed for {url}: {e}", exc_info=True)

    def get_accounts_from_db(self):
        try:
            db = DatabaseConnector().connect()
            with db.cursor() as cursor:
                cursor.execute("SELECT name FROM youtube_accounts")
                accounts = [row[0] for row in cursor.fetchall()]
            return accounts
        except Exception as e:
            logging.error(f"Failed to fetch Youtube accounts from DB: {e}")
            return []

    def run(self):
        if not getattr(self, "enabled", True):
            logging.warning("YouTube downloader is not configured; skipping run().")
            return

        try:
            accounts = self.get_accounts_from_db()
        except Exception as e:
            logging.error(f"Database error while fetching YouTube accounts: {e}")
            return

        if not accounts:
            logging.warning("No YouTube accounts found in the database.")
            return

        total_accounts = len(accounts)
        accounts.sort()

        total_batches = (total_accounts + self.burst_size - 1) // self.burst_size

        for i in range(0, total_accounts, self.burst_size):
            batch = accounts[i : i + self.burst_size]
            batch_index = i // self.burst_size + 1
            logging.info(
                "Processing YouTube batch %s of %s", batch_index, total_batches
            )

            with concurrent.futures.ThreadPoolExecutor(
                max_workers=self.max_workers
            ) as executor:
                futures = {}
                for acc in batch:
                    account_archive = os.path.join(self.archive_dir, f"{acc}.txt")
                    ydl_opts = self._build_ydl_opts(
                        account_archive, break_on_existing=self.default_break_on_existing
                    )
                    futures[executor.submit(self.download_account, acc, ydl_opts)] = acc

                for future in concurrent.futures.as_completed(futures):
                    acc = futures[future]
                    try:
                        future.result()
                    except Exception as exc:
                        logging.error(f"Unhandled error downloading {acc}: {exc}")

            if i + self.burst_size < total_accounts:
                pause = random.randint(self.min_pause, self.max_pause)
                logging.info(f"Throttling pause: sleeping {pause} seconds...")
                time.sleep(pause)
