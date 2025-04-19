import logging
from time import sleep

from data.settings import Settings
from postprocessing.sanitizer import Sanitizer
from postprocessing.tagger import Tagger
from processing.converter import Converter
from processing.extractor import Extractor
from processing.mover import Mover
from processing.renamer import Renamer

if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s  %(filename)s:%(lineno)s [%(levelname)s] %(message)s',
        force=True
    )

    logging.info("Starting music importer")

    # Give the user time to visually confirm it's starting (debugging convenience)
    sleep(5)

    # Initialize settings and components
    settings = Settings()
    tagger = Tagger()
    extractor = Extractor()
    renamer = Renamer()
    mover = Mover()
    converter = Converter()
    sanitizer = Sanitizer()

    while True:
        try:
            logging.info("Starting process...")

            try:
                extractor.run()
                logging.info("Extraction completed.")
            except Exception as e:
                logging.error(f"Extractor failed: {e}")

            try:
                renamer.run()
                logging.info("Renaming completed.")
            except Exception as e:
                logging.error(f"Renamer failed: {e}")

            try:
                mover.run()
                logging.info("Moving completed.")
            except Exception as e:
                logging.error(f"Mover failed: {e}")

            try:
                tagger.run()
                logging.info("Tagging completed.")
            except Exception as e:
                logging.error(f"Tagger failed: {e}")

            try:
                converter.run()
                logging.info("Converter completed.")
            except Exception as e:
                logging.error(f"Converter failed: {e}")

            try:
                sanitizer.run()
                logging.info("Sanitizing completed.")
            except Exception as e:
                logging.error(f"Sanitizing failed: {e}")

        except KeyboardInterrupt:
            logging.info("Process interrupted by user. Exiting.")
            break
        except Exception as e:
            logging.error(f"Unexpected error: {e}")

        logging.info(f"Waiting for {3600} seconds.")
        sleep(3600)
