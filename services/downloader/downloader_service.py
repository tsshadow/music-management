import argparse
import logging
import signal
from time import sleep
import subprocess

import faulthandler

from services.common.api import start_api_server
from services.common.settings import Settings
from services.common.Helpers.DatabaseConnector import DatabaseConnector
from services.downloader.youtube.youtube import YoutubeDownloader
from soundcloud.soundcloud import SoundcloudDownloader
from services.downloader.telegram.telegram import TelegramDownloader

faulthandler.register(signal.SIGUSR1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run specific steps of the music downloader service (YouTube, SoundCloud, Telegram)"
    )

    parser.add_argument(
        "--step",
        help="Comma-separated list of steps to run (youtube,soundcloud,telegram). If omitted, all steps are run.",
        default="",
    )
    parser.add_argument(
        "--account",
        help="Optional DJ / account name to limit downloads",
        default=None,
    )
    parser.add_argument(
        "--sleeptime",
        type=int,
        default=300,
        help="Time in seconds to sleep between repeating steps (default: 300)",
    )

    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--break-on-existing",
        dest="break_on_existing",
        help="Break early when an already-downloaded item is encountered",
        action="store_true",
    )
    group.add_argument(
        "--no-break-on-existing",
        dest="break_on_existing",
        help="Do not break early on existing items",
        action="store_false",
    )
    parser.set_defaults(break_on_existing=True)

    parser.add_argument(
        "--repeat",
        help="Repeat the steps in a loop, sleeping between runs",
        action="store_true",
    )

    parser.add_argument(
        "--redownload",
        help="Forces a redownload of all files, even if they already exist in the target folder.",
        action="store_true",
    )

    return parser.parse_args()


class DownloaderService:
    def __init__(self) -> None:
        self.settings = Settings()

        # Verify database connection before proceeding
        db_connector = DatabaseConnector()
        db_connector.verify_connection()

        start_api_server()

    def download(self, source: str, account: str | None, break_on_existing: bool, redownload: bool) -> None:
        if source == "youtube":
            try:
                version = subprocess.check_output(["yt-dlp", "--version"], text=True).strip()
                print(f"yt-dlp version: {version}")
            except FileNotFoundError:
                print("yt-dlp executable not found in system PATH.")
            except subprocess.SubprocessError as e:
                print(f"Error fetching yt-dlp version: {e}")
            
            youtube_downloader = YoutubeDownloader(
                break_on_existing=break_on_existing
            )
            youtube_downloader.run(account=account, redownload=redownload)

        elif source == "soundcloud":
            soundcloud_downloader = SoundcloudDownloader(
                break_on_existing=break_on_existing,
            )
            soundcloud_downloader.run(account=account, redownload=redownload)

        elif source == "telegram":
            if not account:
                logging.warning("Telegram selected but no --account provided; skipping Telegram downloader.")
                return
            telegram_downloader = TelegramDownloader()
            telegram_downloader.run(account)

        else:
            raise ValueError(f"Unknown source: {source}")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(filename)s:%(lineno)s [%(levelname)s] %(message)s",
        force=True,
    )

    args = parse_args()
    downloader_service = DownloaderService()

    if args.step:
        steps = {s.strip() for s in args.step.split(",") if s.strip()}
    else:
        steps = {"youtube", "soundcloud", "telegram"}


    while True:
        if "youtube" in steps:
            downloader_service.download(
                "youtube",
                break_on_existing=args.break_on_existing,
                account=args.account,
                redownload=args.redownload
            )

        if "soundcloud" in steps:
            downloader_service.download(
                "soundcloud",
                break_on_existing=args.break_on_existing,
                account=args.account,
                redownload=args.redownload
            )

        if "telegram" in steps:
            downloader_service.download(
                "telegram",
                break_on_existing=args.break_on_existing,
                account=args.account,
                redownload=args.redownload
            )

        if not args.repeat:
            logging.info("Repeat flag not set; exiting after single run.")
            break

        logging.info("Sleeping for %d seconds before next run.", args.sleeptime)
        sleep(args.sleeptime)


if __name__ == "__main__":
    main()
