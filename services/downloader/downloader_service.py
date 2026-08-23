import argparse
import faulthandler
import logging
import os
import signal
import time
from collections.abc import Callable, Iterable, Sequence

from services.common.config_store import ConfigStore as Settings
from services.common.Helpers.logging_setup import setup_logging
from services.downloader import shutdown
from services.downloader.sweep import SweepPolicy

faulthandler.register(signal.SIGUSR1)

# Used when the settings cannot be read at all; still far calmer than the five
# minute loop this service used to run on.
FALLBACK_SLEEP_SECONDS = 900

def parse_args(argv: Sequence[str] | None=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Run specific steps of the music downloader service (YouTube, SoundCloud, Telegram)')
    parser.add_argument('--step', help='Comma-separated list of steps to run (youtube,soundcloud,telegram). If omitted, all steps are run.', default='')
    parser.add_argument('--account', help='Optional DJ / account name to limit downloads', default=None)
    parser.add_argument('--sleeptime', type=int, default=None, help='Override the sweep interval from the downloader settings, in seconds')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--break-on-existing', dest='break_on_existing', help='Break early when an already-downloaded item is encountered', action='store_true')
    group.add_argument('--no-break-on-existing', dest='break_on_existing', help='Do not break early on existing items', action='store_false')
    parser.set_defaults(break_on_existing=True)
    parser.add_argument('--deep', action='store_true',
                        help='Walk each account in full and fetch everything the archive is '
                             'missing, instead of stopping at the newest track already held. '
                             'Happens on its own every deep_sweep_days; this forces it now.')
    parser.add_argument('--repeat', help='Repeat the steps in a loop, sleeping between runs', action='store_true')
    return parser.parse_args(argv)

def _current_timing(source: str):
    """The effective timing of one source, including its backoff multiplier."""
    return SweepPolicy(source).timing

def sweep_sleep_seconds(steps: Iterable[str], override: int | None,
                        load: Callable[[str], object]=_current_timing) -> int:
    """How long to sleep before the next round of the configured steps.

    A step that is still backing off has a stretched interval, so the loop
    automatically slows down with it. The shortest interval wins, because a step
    that is due should not wait for a slower one.
    """
    if override is not None:
        return override
    intervals = []
    for step in steps:
        try:
            intervals.append(load(step).sweep_interval)
        except Exception as exc:
            logging.warning('Could not read the sweep interval for %s: %s', step, exc)
    if not intervals:
        return FALLBACK_SLEEP_SECONDS
    return min(intervals)

class DownloaderService:

    def __init__(self) -> None:
        self.settings = Settings()
        self.dry_run = getattr(self.settings, 'dryrun', False)

    def download(self, source: str, account: str | None, break_on_existing: bool,
                 deep: bool = False) -> None:
        if source == 'youtube':
            from services.downloader.youtube.youtube import YoutubeDownloader
            youtube_downloader = YoutubeDownloader(break_on_existing=break_on_existing, dry_run=self.dry_run, deep=deep)
            youtube_downloader.run(account=account)
        elif source == 'soundcloud':
            from services.downloader.soundcloud.soundcloud import SoundcloudDownloader
            soundcloud_downloader = SoundcloudDownloader(break_on_existing=break_on_existing, dry_run=self.dry_run, deep=deep)
            soundcloud_downloader.run(account=account)
        elif source == 'telegram':
            from services.downloader.telegram.telegram import TelegramDownloader
            telegram_downloader = TelegramDownloader(dry_run=self.dry_run)
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
    setup_logging('downloader')
    # Armed before anything downloads. Python ends the process outright on an
    # unhandled SIGTERM, so without this a deploy takes the worker mid-pass and
    # no `finally` gets to write down what it had learned.
    shutdown.install_handlers()
    args = parse_args()
    downloader_service = DownloaderService()
    if args.step:
        steps = {s.strip() for s in args.step.split(',') if s.strip()}
    else:
        steps = {'youtube', 'soundcloud', 'telegram'}
    while True:
        if shutdown.is_requested():
            break
        if 'youtube' in steps:
            downloader_service.download('youtube', break_on_existing=args.break_on_existing, account=args.account, deep=args.deep)
        if 'soundcloud' in steps:
            downloader_service.download('soundcloud', break_on_existing=args.break_on_existing, account=args.account, deep=args.deep)
        if 'telegram' in steps:
            downloader_service.download('telegram', break_on_existing=args.break_on_existing, account=args.account)
        if not args.repeat:
            logging.info('Repeat flag not set; exiting after single run.')
            break
        if shutdown.is_requested():
            logging.info('Shutting down; not sleeping until the next round.')
            break
        sleeptime = sweep_sleep_seconds(sorted(steps), args.sleeptime)
        logging.info('Sleeping for %d seconds before next run.', sleeptime)
        time.sleep(sleeptime)
if __name__ == '__main__':
    main()
