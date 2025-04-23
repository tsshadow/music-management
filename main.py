import logging
import argparse
from time import sleep

from data.settings import Settings
from postprocessing.repair import FileRepair
from postprocessing.sanitizer import Sanitizer
from postprocessing.tagger import Tagger
from processing.converter import Converter
from processing.extractor import Extractor
from processing.mover import Mover
from processing.renamer import Renamer

def main():
    parser = argparse.ArgumentParser(description="Run specific steps of the music importer")
    parser.add_argument(
        "--step",
        choices=["extract", "rename", "move", "tag", "convert", "sanitize", "repair", "all"],
        help="Run only the specified step. If omitted, all steps are run.",
        default="all"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s  %(filename)s:%(lineno)s [%(levelname)s] %(message)s',
        force=True
    )

    logging.info("Starting music importer")
    sleep(5)

    settings = Settings()
    tagger = Tagger()
    extractor = Extractor()
    renamer = Renamer()
    mover = Mover()
    converter = Converter()
    sanitizer = Sanitizer()
    repair = FileRepair()

    while True:
        try:
            logging.info("Starting process...")

            if args.step in ("extract", "all"):
                try:
                    extractor.run()
                    logging.info("Extraction completed.")
                except Exception as e:
                    logging.error(f"Extractor failed: {e}")

            if args.step in ("rename", "all"):
                try:
                    renamer.run()
                    logging.info("Renaming completed.")
                except Exception as e:
                    logging.error(f"Renamer failed: {e}")

            if args.step in ("move", "all"):
                try:
                    mover.run()
                    logging.info("Moving completed.")
                except Exception as e:
                    logging.error(f"Mover failed: {e}")

            if args.step in ("tag", "all"):
                try:
                    tagger.run()
                    logging.info("Tagging completed.")
                except Exception as e:
                    logging.error(f"Tagger failed: {e}")

            if args.step in ("convert", "all"):
                try:
                    converter.run()
                    logging.info("Converter completed.")
                except Exception as e:
                    logging.error(f"Converter failed: {e}")

            if args.step in ("sanitize", "all"):
                try:
                    sanitizer.run()
                    logging.info("Sanitizing completed.")
                except Exception as e:
                    logging.error(f"Sanitizer failed: {e}")

            if args.step in ("repair"):
                try:
                    repair.run()
                    logging.info("Repair completed.")
                except Exception as e:
                    logging.error(f"Repair failed: {e}")

        except KeyboardInterrupt:
            logging.info("Process interrupted by user. Exiting.")
            break
        except Exception as e:
            logging.error(f"Unexpected error: {e}")

        if args.step != "all":
            break

        logging.info(f"Waiting for {3600} seconds.")
        sleep(3600)

if __name__ == "__main__":
    main()
