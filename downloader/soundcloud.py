import concurrent.futures
import subprocess
import logging
import os

from data.DatabaseConnector import DatabaseConnector


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
    def __init__(self):
        self.output_folder = os.getenv("soundcloud_folder")
        self.archive_file = os.getenv("soundcloud_archive")
        self.executable = os.getenv("ytdlp")

        if not self.output_folder or not self.archive_file or not self.executable:
            raise ValueError("Missing required environment variables for youtube_folder, youtube_archive, or ytdlp")

    def download_account(self, name: str):
        link = f"http://www.soundcloud.com/{name}/tracks"
        command = [
            self.executable,
            '--output', f'{self.output_folder}/%(uploader)s/%(title)s.%(ext)s',
            "--download-archive", self.archive_file,
            "--embed-metadata",
            "--embed-thumbnail",
            "--compat-options", "filename",
            "--no-overwrites",
            "-x",
            "--audio-format", "m4a",
            "--audio-quality", "0",
            "--break-on-existing",
            "--postprocessor-args", "ffmpeg:-acodec aac",
            "--no-post-overwrites",
            "--no-part",
            "--format", "bestaudio/best",
            link
        ]

        try:
            logging.info(f"Downloading from SoundCloud account: {name}")
            subprocess.run(command, check=True)
            logging.info(f"Finished downloading from: {name}")
        except subprocess.CalledProcessError as e:
            logging.error(f"SoundCloud download failed for {name}: {e}")

    def run(self):
        accounts = get_accounts_from_db()
        if not accounts:
            logging.warning("No SoundCloud accounts found in the database.")
            return

        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
            executor.map(self.download_account, accounts)
