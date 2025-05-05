import subprocess
import logging
import os
import concurrent.futures

from data.DatabaseConnector import DatabaseConnector


class YoutubeDownloader:
    def __init__(self):
        self.output_folder = os.getenv("youtube_folder")
        self.archive_file = os.getenv("youtube_archive")
        self.executable = os.getenv("ytdlp")

        if not self.output_folder or not self.archive_file or not self.executable:
            raise ValueError("Missing required environment variables for youtube_folder, youtube_archive, or ytdlp")

    def download_account(self, name: str):
        link = f'http://www.youtube.com/{name}'
        command = [
            self.executable,
            '--output', f'{self.output_folder}/%(uploader)s/%(title)s.%(ext)s',
            '--download-archive', self.archive_file,
            '--embed-metadata',
            '--embed-thumbnail',
            '--compat-options', 'filename',
            '--no-overwrites',
            '--extract-audio',
            '--audio-format', 'm4a',
            '--no-keep-video',
            '--break-on-existing',
            link
        ]

        try:
            logging.info(f"Downloading from account: {name}")
            subprocess.run(command, check=True)
            logging.info(f"Finished downloading from: {name}")
        except subprocess.CalledProcessError as e:
            logging.error(f"Download failed for {name}: {e}")

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
        try:
            accounts = self.get_accounts_from_db()
        except Exception as e:
            logging.error(f"Database error while fetching YouTube accounts: {e}")
            return

        if not accounts:
            logging.warning("No YouTube accounts found in the database.")
            return

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            executor.map(self.download_account, accounts)
