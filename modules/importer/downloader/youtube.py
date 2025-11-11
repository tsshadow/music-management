import concurrent.futures
import logging
import os
import random
import time
from typing import Optional

from yt_dlp import YoutubeDL

from api.config_store import ConfigStore
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
        self._config = ConfigStore()
        self.max_workers = max_workers
        self.burst_size = burst_size
        self.min_pause = min_pause
        self.max_pause = max_pause
        self.socket_timeout = socket_timeout
        self.default_break_on_existing = break_on_existing
        self._subscriptions = []
        self._apply_config()
        for key in [
            "youtube_folder",
            "youtube_archive",
            "ffmpeg_location",
            "yt_cookies",
            "yt_user_agent",
        ]:
            self._subscriptions.append(
                self._config.subscribe(key, lambda _value, k=key: self._apply_config())
            )

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

    def _apply_config(self) -> None:
        values = self._config.get_many(
            ["youtube_folder", "youtube_archive", "ffmpeg_location", "yt_cookies", "yt_user_agent"]
        )
        self.output_folder = values.get("youtube_folder") or None
        self.archive_dir = values.get("youtube_archive") or None
        self.ffmpeg_location = values.get("ffmpeg_location") or "usr/bin/local"
        self.cookies_file = values.get("yt_cookies") or None
        self.user_agent = values.get("yt_user_agent") or None

        if not self.output_folder or not self.archive_dir:
            if getattr(self, "enabled", True):
                logging.warning(
                    "Missing required configuration for YouTube downloads. YouTube downloads will be disabled."
                )
            self.enabled = False
            self._base_ydl_opts = {}
            return

        os.makedirs(self.output_folder, exist_ok=True)
        os.makedirs(self.archive_dir, exist_ok=True)
        self.enabled = True

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

        self._base_ydl_opts.update(self._cookie_options())
        if self.user_agent:
            self._base_ydl_opts["user_agent"] = self.user_agent

    def _build_ydl_opts(
        self,
        archive_file: str,
        break_on_existing: bool = True,
        redownload: bool = False,
    ) -> dict:
        opts = {**self._base_ydl_opts}
        if "postprocessors" in self._base_ydl_opts:
            opts["postprocessors"] = [
                pp.copy() if isinstance(pp, dict) else pp
                for pp in self._base_ydl_opts["postprocessors"]
            ]
        if not redownload:
            opts["download_archive"] = archive_file
        else:
            opts.pop("download_archive", None)
        if break_on_existing:
            opts["break_on_existing"] = True
        else:
            opts.pop("break_on_existing", None)
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

    def download_link(
        self,
        url: str,
        breakOnExisting: bool = True,
        redownload: bool = False,
    ):
        """Download a single video using a direct URL."""
        archive_file = os.path.join(self.archive_dir, "manual.txt")

        try:
            opts = self._build_ydl_opts(
                archive_file,
                break_on_existing=breakOnExisting,
                redownload=redownload,
            )
            with self._create_ydl(opts) as ydl:
                logging.info(f"Downloading from url: {url}")
                ydl.download([url])
        except Exception as e:
            logging.error(f"Failed to download {url}: {e}")
            raise

    def download_accounts(self, accounts: list[str], break_on_existing: bool = True):
        if not self.enabled:
            logging.warning("YouTube downloader is disabled; skipping download_accounts().")
            return

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [
                executor.submit(
                    self.download_account,
                    account,
                    self._build_ydl_opts(
                        os.path.join(self.archive_dir, f"{account}.txt"),
                        break_on_existing=break_on_existing,
                    ),
                )
                for account in accounts
            ]
            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logging.error(f"Error downloading account: {e}")

    def run(self):
        if not self.enabled:
            logging.warning("YouTube downloader is disabled; skipping run().")
            return

        accounts = DatabaseConnector().get_youtube_accounts()
        for i in range(0, len(accounts), self.burst_size):
            batch = accounts[i : i + self.burst_size]
            logging.info(f"Processing batch: {batch}")
            self.download_accounts(batch, break_on_existing=self.default_break_on_existing)
            if i + self.burst_size < len(accounts):
                pause = random.randint(self.min_pause, self.max_pause)
                logging.info(f"Pausing for {pause} seconds before next batch")
                time.sleep(pause)

    def manual_download(self, url: str, break_on_existing: Optional[bool] = None, redownload: bool = False):
        if break_on_existing is None:
            break_on_existing = self.default_break_on_existing
        return self.download_link(url, break_on_existing, redownload=redownload)

    def manual_account_download(self, account: str, redownload: bool = False):
        return self.download_account(
            account,
            self._build_ydl_opts(
                os.path.join(self.archive_dir, f"{account}.txt"),
                break_on_existing=self.default_break_on_existing,
                redownload=redownload,
            ),
        )
