import logging
import os
import requests
import urllib.parse
from pathlib import Path
import yt_dlp
from postprocessing.Song.Helpers.BrokenSongHelper import BrokenSongHelper
from postprocessing.Song.Helpers.BrokenSongArtistLookupHelper import BrokenSongArtistLookupHelper

class FileRepair:
    def __init__(self):
        self.broken_helper = BrokenSongHelper()
        self.artist_lookup = BrokenSongArtistLookupHelper()
        self.failed_downloads = []

    def run(self):
        self.import_accounts()
        try:
            rows = self.broken_helper.get_all()

            for song_id, path, error_code in rows:
                path_lower = path.lower()

                if "soundcloud" in path_lower:
                    success = self.repair_soundcloud(song_id, path)
                elif "youtube" in path_lower:
                    success = self.repair_youtube(song_id, path)
                else:
                    logging.info(f"[SKIP] Unsupported path (not SoundCloud or YouTube): {path}")
                    continue

                if success:
                    self.broken_helper.remove(song_id)
                    self.try_delete_file(path)

            if self.failed_downloads:
                logging.warning("\n⚠️ Permanently failed downloads:")
                for song_id, path, url in self.failed_downloads:
                    logging.warning(f"- {path} (tried {url})")

        except Exception as e:
            logging.error(f"Error during repair run: {e}")

    def import_accounts(self):
        path = "/volume1/Music/Soundcloud/accounts.txt"
        if not os.path.exists(path):
            logging.warning("No Accounts.txt file found.")
            return

        with open(path, "r") as f:
            for line in f:
                normalized_name = line.strip()
                if not normalized_name:
                    continue
                url = f"https://soundcloud.com/{normalized_name}"
                raw_name = self.fetch_uploader_info(url)
                if raw_name:
                    self.artist_lookup.insert_if_missing(raw_name, normalized_name)
                else:
                    logging.warning(f"Uploader info could not be fetched for {url}")

    def repair_soundcloud(self, song_id: int, path: str) -> bool:
        url = self.derive_soundcloud_url(path)
        if not url:
            return False
        logging.info(f"[SoundCloud] Attempting redownload from {url}")
        success = self.download_from_soundcloud(url, path)
        if not success:
            artist = path.split("/Music/Soundcloud/")[-1].split("/")[0].strip().lower()
            self.artist_lookup.insert_if_missing(artist)
            self.failed_downloads.append((song_id, path, url))
        return success

    def repair_youtube(self, song_id: int, path: str) -> bool:
        url = self.derive_youtube_url(path)
        if not url:
            return False
        logging.info(f"[YouTube] Attempting redownload from {url}")
        success = self.download_from_youtube(url, path)
        if not success:
            self.failed_downloads.append((song_id, path, url))
        return success

    def derive_soundcloud_url(self, path: str) -> str:
        try:
            parts = path.split("/Music/Soundcloud/")[-1].split("/")
            artist = parts[0].strip().lower()
            title = os.path.splitext(parts[1])[0].strip().lower()

            normalized_artist = self.artist_lookup.get_normalized_name(artist)
            if not normalized_artist:
                return None

            title_slug = title.replace(" ", "-")
            artist_encoded = urllib.parse.quote(normalized_artist, safe="")
            title_encoded = urllib.parse.quote(title_slug, safe="")

            url = f"https://soundcloud.com/{artist_encoded}/{title_encoded}"
            return url
        except Exception as e:
            logging.error(f"Failed to derive SoundCloud URL for {path}: {e}")
            return None

    def derive_youtube_url(self, path: str) -> str:
        try:
            filename = os.path.basename(path)
            title = os.path.splitext(filename)[0].replace(" ", "-").lower()
            return f"https://www.youtube.com/watch?v={title}"
        except Exception as e:
            logging.error(f"Failed to derive YouTube URL for {path}: {e}")
            return None

    def try_delete_file(self, path: str):
        try:
            os.remove(path)
            logging.info(f"[DELETE] Verwijderd: {path}")
        except Exception as e:
            logging.warning(f"Kon bestand niet verwijderen: {path} ({e})")

    def download_from_soundcloud(self, url: str, target_path: str) -> bool:
        try:
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': str(Path(target_path)),
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'm4a',
                    'preferredquality': '192',
                }],
                'quiet': True,
                'noplaylist': True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            return True
        except Exception as e:
            logging.error(f"SoundCloud download failed for {target_path}: {e}")
            return False

    def download_from_youtube(self, url: str, target_path: str) -> bool:
        try:
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': str(Path(target_path)),
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'm4a',
                    'preferredquality': '192',
                }],
                'quiet': True,
                'noplaylist': True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            return True
        except Exception as e:
            logging.error(f"YouTube download failed for {target_path}: {e}")
            return False

    def fetch_uploader_info(self, url):
        try:
            ydl_opts = {
                'quiet': True,
                'cookiefile': '/volume1/Music/Soundcloud/cookies.txt',
                'extract_flat': True
            }
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                info = ydl.extract_info(url, download=False)
                return info.get("uploader")
        except Exception as e:
            logging.warning(f"Failed to fetch uploader for {url}: {e}")
            return None

if __name__ == "__main__":
    repairer = FileRepair()
    repairer.run()