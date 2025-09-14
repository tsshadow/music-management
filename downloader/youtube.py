import logging
import os
import concurrent.futures

from yt_dlp import YoutubeDL

from downloader.YoutubeSongProcessor import YoutubeSongProcessor
from postprocessing.Song.Helpers.DatabaseConnector import DatabaseConnector


class YoutubeDownloader:
    def __init__(self):
        self.output_folder = os.getenv("youtube_folder")
        self.archive_dir = os.getenv("youtube_archive")

        if not self.output_folder or not self.archive_dir:
            logging.warning(
                "Missing required environment variables for youtube_folder or youtube_archive. "
                "YouTube downloads will be disabled."
            )
            self.output_folder = None
            self.archive_dir = None
        else:
            os.makedirs(self.output_folder, exist_ok=True)
            os.makedirs(self.archive_dir, exist_ok=True)

        # Read optional cookie/user-agent env once
        self.cookies_file = os.getenv("YT_COOKIES")  # expected to be a path to cookies.txt
        self.user_agent = os.getenv("YT_USER_AGENT")  # optional: keep UA aligned with browser

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

    def _create_ydl(self, archive_file: str, break_on_existing: bool = True) -> YoutubeDL:
        opts = {
            "outtmpl": f"{self.output_folder}/%(uploader)s/%(title)s.%(ext)s",
            "download_archive": archive_file,
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "m4a"},
                {"key": "EmbedThumbnail"},
                {"key": "FFmpegMetadata"},
            ],
            "compat_opts": ["filename"],
            "nooverwrites": True,
            "keepvideo": False,
            "ffmpeg_location": "/usr/local/bin",
        }

        # Merge cookie options
        opts.update(self._cookie_options())

        # Optional: set a specific User-Agent to match the browser
        if self.user_agent:
            opts["user_agent"] = self.user_agent

        if break_on_existing:
            opts["break_on_existing"] = True

        ydl = YoutubeDL(opts)
        ydl.add_post_processor(YoutubeSongProcessor())
        return ydl

    def download_account(self, name: str):
        link = f"http://www.youtube.com/{name}"
        archive_file = os.path.join(self.archive_dir, f"{name}.txt")

        try:
            ydl = self._create_ydl(archive_file)
            logging.info(f"Downloading from account: {name}")
            ydl.download([link])
            logging.info(f"Finished downloading from: {name}")
        except Exception as e:
            logging.error(f"Download failed for {name}: {e}", exc_info=True)

    def download_link(self, url: str, breakOnExisting: bool = True):
        """Download a single video using a direct URL."""
        archive_file = os.path.join(self.archive_dir, "manual.txt")

        try:
            ydl = self._create_ydl(archive_file, break_on_existing=breakOnExisting)
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
        if not self.output_folder or not self.archive_dir:
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

        # You can increase max_workers if you want concurrent downloads
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            executor.map(self.download_account, accounts)
