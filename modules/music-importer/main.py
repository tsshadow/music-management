import logging
import argparse
import signal
from time import sleep
from services.common.settings import Settings
from services.other.repair import FileRepair
from services.other.sanitizer import Sanitizer
from services.tagger.tagger import Tagger
from services.analyzer.analyzer import Analyze
from services.other.artistfixer import ArtistFixer
from services.other.converter import Converter
from services.other.epsflattener import EpsFlattener
from services.importer_service.extractor import Extractor
from services.importer_service.mover import Mover
from services.importer_service.renamer import Renamer
from downloader.youtube import YoutubeDownloader
from downloader.soundcloud import SoundcloudDownloader
from downloader.telegram import TelegramDownloader
from services.common.api import start_api_server
from services.common.api.step import Step
import faulthandler
faulthandler.register(signal.SIGUSR1)

def main():
    parser = argparse.ArgumentParser(description='Run specific steps of the music importer')
    parser.add_argument('--step', help='Comma-separated list of steps to run. If omitted, all steps are run.', default='all')
    parser.add_argument('--account', help='optional dj')
    parser.add_argument('--sleeptime', help='time to sleep between repeating steps')
    parser.add_argument('--break-on-existing', help='optional break on existing for downloaders', action='store_true')
    parser.add_argument('--repeat', help='Repeat every hour', action='store_true')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s  %(filename)s:%(lineno)s [%(levelname)s] %(message)s', force=True)
    logging.info('Starting music importer')
    sleep(1)
    start_api_server()
    settings = Settings()
    youtube_downloader = YoutubeDownloader()
    soundcloud_downloader = SoundcloudDownloader(break_on_existing=args.break_on_existing)
    telegram_downloader = TelegramDownloader()
    tagger = Tagger()
    extractor = Extractor()
    renamer = Renamer()
    mover = Mover()
    converter = Converter()
    sanitizer = Sanitizer()
    flattener = EpsFlattener()
    repair = FileRepair()
    analyze_step = Analyze()
    artist_fixer = ArtistFixer()
    step_arg = args.step.lower()
    steps = step_arg.split(',') if step_arg != 'all' else ['all']
    valid_steps = {'all', 'convert', 'download', 'download-soundcloud', 'download-youtube, 'download-telegram', 'flatten', 'import', 'extract', 'move', 'rename', 'manual', 'repair', 'sanitize', 'tag', 'tag-generic', 'tag-labels', 'tag-soundcloud', 'tag-youtube, 'tag-telegram', 'analyze', 'artistfixer'}
    for step in steps:
        if step not in valid_steps:
            parser.error(f'Invalid step: {step}')

    def run_tagger():
        parse_all = 'tag' in steps or 'all' in steps
        tagger.run(parse_labels=parse_all or 'tag-labels' in steps, parse_soundcloud=parse_all or 'tag-soundcloud' in steps, parse_youtube=parse_all or 'tag-youtube in steps, parse_generic=parse_all or 'tag-generic' in steps, parse_telegram=parse_all or 'tag-telegram' in steps)
    steps_to_run = [Step('Extractor', ['import', 'extract'], extractor.run), Step('Renamer', ['import', 'rename'], renamer.run), Step('Mover', ['import', 'move'], mover.run), Step('Converter', ['convert'], converter.run), Step('Sanitizer', ['sanitize'], sanitizer.run), Step('Flattener', ['flatten'], flattener.run), Step('YouTube Downloader', ['download', 'download-youtube], youtube_downloader.run), Step('SoundCloud Downloader', ['download', 'download-soundcloud'], lambda: soundcloud_downloader.run(account=args.account or '')), Step('Telegram Downloader', ['download-telegram'], lambda: telegram_downloader.run(args.account or '')), Step('Analyze', ['analyze'], analyze_step.run), Step('ArtistFixer', ['artistfixer'], artist_fixer.run), Step('Tagger', ['tag', 'tag-labels', 'tag-soundcloud', 'tag-youtube, 'tag-generic', 'tag-telegram'], run_tagger)]
    while True:
        try:
            logging.info('Starting process...')
            for step in steps_to_run:
                step.run(steps)
        except KeyboardInterrupt:
            logging.info('Process interrupted by user. Exiting.')
            break
        except Exception as e:
            logging.error(f'Unexpected error: {e}')
        if not args.repeat:
            break
        logging.info(f'Waiting for {args.sleeptime or 300} seconds.')
        sleep(int(args.sleeptime) or 300)
if __name__ == '__main__':
    main()