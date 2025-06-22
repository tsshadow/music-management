import logging
import argparse
import signal
from time import sleep

from data.settings import Settings
from postprocessing.repair import FileRepair
from postprocessing.sanitizer import Sanitizer
from postprocessing.tagger import Tagger
from postprocessing.analyze import Analyze
from processing.converter import Converter
from processing.epsflattener import EpsFlattener
from processing.extractor import Extractor
from processing.mover import Mover
from processing.renamer import Renamer
from downloader.youtube import YoutubeDownloader
from downloader.soundcloud import SoundcloudDownloader
import faulthandler
faulthandler.register(signal.SIGUSR1)

class Step:
    def __init__(self, name, condition_keys, action):
        """
        :param name: Human-readable step name (used in logs)
        :param condition_keys: List of step triggers (e.g. ['rename'] or ['download', 'download-youtube'])
        :param action: Callable to execute (e.g. youtube_downloader.run)
        """
        self.name = name
        self.condition_keys = set(condition_keys)
        self.action = action

    def should_run(self, steps):
        return bool(self.condition_keys.intersection(steps)) or "all" in steps

    def run(self, steps):
        if self.should_run(steps):
            try:
                self.action()
                logging.info(f"{self.name} completed.")
            except Exception as e:
                logging.error(f"{self.name} failed: {e}")


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
        "--break-on-existing",
        help="optional break on existing for downloaders",
        default=False
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s  %(filename)s:%(lineno)s [%(levelname)s] %(message)s',
        force=True
    )

    logging.info("Starting music importer")
    sleep(1)

    settings = Settings()
    youtube_downloader = YoutubeDownloader()
    soundcloud_downloader = SoundcloudDownloader(break_on_existing=args.break_on_existing)
    tagger = Tagger()
    extractor = Extractor()
    renamer = Renamer()
    mover = Mover()
    converter = Converter()
    sanitizer = Sanitizer()
    flattener = EpsFlattener()
    repair = FileRepair()
    analyze_step = Analyze()

    steps = args.step.split(",") if args.step != "all" else ["all"]

    valid_steps = {
        "all",
        "convert",
        "download", "download-soundcloud", "download-youtube",
        "flatten",
        "import", "extract", "move", "rename",
        "manual",
        "repair",
        "sanitize",
        "tag", "tag-generic", "tag-labels", "tag-soundcloud", "tag-youtube",
        "analyze"
    }
    for step in steps:
        if step not in valid_steps:
            parser.error(f"Invalid step: {step}")

    def run_tagger():
        parse_all = "tag" in steps or "all" in steps
        tagger.run(
            parse_labels=parse_all or "tag-labels" in steps,
            parse_soundcloud=parse_all or "tag-soundcloud" in steps,
            parse_youtube=parse_all or "tag-youtube" in steps,
            parse_generic=parse_all or "tag-generic" in steps,
        )

    steps_to_run = [
        Step("Extractor", ["import", "extract"], extractor.run),
        Step("Renamer", ["import", "rename"], renamer.run),
        Step("Mover", ["import", "move"], mover.run),
        Step("Converter", ["convert"], converter.run),
        Step("Sanitizer", ["sanitize"], sanitizer.run),
        # Step("Repair", ["repair"], repair.run),
        Step("Flattener", ["flatten"], flattener.run),
        # Step("YouTube Downloader", ["download", "download-youtube"], youtube_downloader.run),
        Step("SoundCloud Downloader", ["download", "download-soundcloud"], lambda: soundcloud_downloader.run(
            account=args.account or "",
        )),
        Step("Analyze", ["analyze"], analyze_step.run),
        Step("Tagger", ["tag", "tag-labels", "tag-soundcloud", "tag-youtube", "tag-generic"], run_tagger),
    ]

    while True:
        try:
            logging.info("Starting process...")

            for step in steps_to_run:
                step.run(steps)

        except KeyboardInterrupt:
            logging.info("Process interrupted by user. Exiting.")
            break
        except Exception as e:
            logging.error(f"Unexpected error: {e}")

        if "all" not in steps:
            break

        logging.info(f"Waiting for 3600 seconds.")
        sleep(3600)


if __name__ == "__main__":
    main()
