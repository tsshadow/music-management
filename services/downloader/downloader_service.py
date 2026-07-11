import argparse
import logging
import os
import signal
from time import sleep
import faulthandler
from services.common.config_store import ConfigStore as Settings
from services.downloader.youtube.youtube import YoutubeDownloader
from services.downloader.soundcloud.soundcloud import SoundcloudDownloader
from services.downloader.telegram.telegram import TelegramDownloader
faulthandler.register(signal.SIGUSR1)

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Run specific steps of the music downloader service (YouTube, SoundCloud, Telegram)')
    parser.add_argument('--step', help='Comma-separated list of steps to run (youtube,soundcloud,telegram). If omitted, all steps are run.', default='')
    parser.add_argument('--account', help='Optional DJ / account name to limit downloads', default=None)
    parser.add_argument('--sleeptime', type=int, default=300, help='Time in seconds to sleep between repeating steps (default: 300)')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--break-on-existing', dest='break_on_existing', help='Break early when an already-downloaded item is encountered', action='store_true')
    group.add_argument('--no-break-on-existing', dest='break_on_existing', help='Do not break early on existing items', action='store_false')
    parser.set_defaults(break_on_existing=True)
    parser.add_argument('--repeat', help='Repeat the steps in a loop, sleeping between runs', action='store_true')
    return parser.parse_args()

class DownloaderService:

    def __init__(self) -> None:
        self.settings = Settings()

    def download(self, source: str, account: str | None, break_on_existing: bool) -> None:
        if source == 'youtube':
            youtube_downloader = YoutubeDownloader(break_on_existing=break_on_existing)
            youtube_downloader.run(account=account)
        elif source == 'soundcloud':
            soundcloud_downloader = SoundcloudDownloader(break_on_existing=break_on_existing)
            soundcloud_downloader.run(account=account)
        elif source == 'telegram':
            telegram_downloader = TelegramDownloader()
            if account:
                accounts = [account]
            else:
                telegram_accounts = getattr(self.settings, 'telegram_accounts', os.getenv('telegram_accounts', ''))
                if telegram_accounts:
                    accounts = [a.strip() for a in telegram_accounts.split(',') if a.strip()]
                else:
                    logging.warning('Telegram selected but no --account or telegram_accounts env var provided; skipping Telegram downloader.')
                    return
            for acc in accounts:
                logging.info(f'Starting Telegram download for channel: {acc}')
                telegram_downloader.run(acc)
        else:
            raise ValueError(f'Unknown source: {source}')

def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s  %(filename)s:%(lineno)s [%(levelname)s] %(message)s', force=True)
    args = parse_args()
    downloader_service = DownloaderService()
    if args.step:
        steps = {s.strip() for s in args.step.split(',') if s.strip()}
    else:
        steps = {'youtube', 'soundcloud', 'telegram'}
    while True:
        if 'youtube' in steps:
            downloader_service.download('youtube', break_on_existing=args.break_on_existing, account=args.account)
        if 'soundcloud' in steps:
            downloader_service.download('soundcloud', break_on_existing=args.break_on_existing, account=args.account)
        if 'telegram' in steps:
            downloader_service.download('telegram', break_on_existing=args.break_on_existing, account=args.account)
        if not args.repeat:
            logging.info('Repeat flag not set; exiting after single run.')
            break
        logging.info('Sleeping for %d seconds before next run.', args.sleeptime)
        sleep(args.sleeptime)
if __name__ == '__main__':
    main()