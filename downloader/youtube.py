import subprocess
import logging
import os


class YoutubeDownloader:
    def __init__(self, ):
        self.output_folder = os.getenv("youtube_folder")
        self.archive_file = os.getenv("youtube_archive")
        self.accounts_file = os.getenv("youtube_accounts")
        self.executable = os.getenv("ytdlp")

    def download_account(self, name: str):
        link = f'http://www.youtube.com/{name}'
        command = [
            self.executable,
            '--output', self.output_folder,
            '--download-archive', self.archive_file,
            '--embed-metadata',
            '--embed-thumbnail',
            '--compat-options', 'filename',
            '--no-overwrites',
            '--extract-audio',
            '--no-keep-video',
            '--format', 'm4a',
            link
        ]

        try:
            logging.info(f"Downloading from account: {name}")
            subprocess.run(command, check=True)
            logging.info(f"Finished downloading from: {name}")
        except subprocess.CalledProcessError as e:
            logging.error(f"Download failed for {name}: {e}")

    def run(self):
        if not os.path.exists(self.accounts_file):
            logging.warning(f"Accounts file not found: {self.accounts_file}")
            return

        with open(self.accounts_file, encoding='utf-8') as f:
            accounts = [line.strip() for line in f if line.strip()]

        for account in accounts:
            self.download_account(account)
