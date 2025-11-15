import argparse
import logging
import signal
from time import sleep

import faulthandler

from api import start_api_server
from data.settings import Settings
from downloader.soundcloud import SoundcloudDownloader
from downloader.telegram import TelegramDownloader
from downloader.youtube import YoutubeDownloader
from postprocessing.analyze import Analyze
from postprocessing.artistfixer import ArtistFixer
from postprocessing.sanitizer import Sanitizer
from postprocessing.tagger import Tagger
from processing.converter import Converter
from processing.epsflattener import EpsFlattener
from processing.extractor import Extractor
from processing.mover import Mover
from processing.renamer import Renamer

from services import (
    StepContext,
    create_default_steps,
    execute_pipeline_step,
    DownloadService,
    TaggingService,
)

faulthandler.register(signal.SIGUSR1)


def main():
    parser = argparse.ArgumentParser(description="Run specific steps of the music importer")
    parser.add_argument(
        "--step",
        help="Comma-separated list of steps to run. If omitted, all steps are run.",
        default="all"
    )
    parser.add_argument(
        "--account",
        help="optional dj",
    )
    parser.add_argument(
        "--sleeptime",
        help="time to sleep between repeating steps",
    )
    parser.add_argument(
        "--break-on-existing",
        help="optional break on existing for downloaders",
        action="store_true",
    )
    parser.add_argument(
        "--repeat",
        help="Repeat every hour",
        action="store_true",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s  %(filename)s:%(lineno)s [%(levelname)s] %(message)s',
        force=True
    )

    logging.info("Starting music importer")
    sleep(1)

    # Start the lightweight API server for job tracking
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
    analyze_step = Analyze()
    artist_fixer = ArtistFixer()

    step_arg = args.step.lower()
    steps = step_arg.split(",") if step_arg != "all" else ["all"]

    valid_steps = {
        "all",
        "convert",
        "download", "download-soundcloud", "download-youtube", "download-telegram", "manual-youtube",
        "flatten",
        "import", "extract", "move", "rename",
        "manual",
        "repair",
        "sanitize",
        "tag", "tag-generic", "tag-labels", "tag-soundcloud", "tag-youtube", "tag-telegram",
        "analyze",
        "artistfixer"
    }
    for step in steps:
        if step not in valid_steps:
            parser.error(f"Invalid step: {step}")

    download_service = DownloadService(
        youtube=youtube_downloader,
        soundcloud=soundcloud_downloader,
        telegram=telegram_downloader,
        settings=settings,
    )
    tagging_service = TaggingService(tagger)

    pipeline_steps = create_default_steps(
        extractor=extractor,
        renamer=renamer,
        mover=mover,
        converter=converter,
        sanitizer=sanitizer,
        flattener=flattener,
        analyzer=analyze_step,
        artist_fixer=artist_fixer,
        download_service=download_service,
        tagging_service=tagging_service,
    )

    runtime_options = {
        "account": args.account or None,
        "break_on_existing": args.break_on_existing,
    }

    while True:
        context = StepContext(
            download_service=download_service,
            tagging_service=tagging_service,
            extras={"source": "cli"},
        )
        try:
            logging.info("Starting process...")

            for step in pipeline_steps:
                execute_pipeline_step(step, steps, context, runtime_options)

        except KeyboardInterrupt:
            logging.info("Process interrupted by user. Exiting.")
            break
        except Exception as e:
            logging.error(f"Unexpected error: {e}")

        if not args.repeat:
            break

        logging.info(f"Waiting for {args.sleeptime or 300} seconds.")
        sleep(int(args.sleeptime) or 300)


if __name__ == "__main__":
    main()
