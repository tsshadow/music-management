from time import sleep
from processing.extractor import Extractor
from processing.mover import Mover
from processing.renamer import Renamer
from data.settings import Settings
from postprocessing.tagger import Tagger
import logging

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s  %(filename)s [%(levelname)s] %(message)s', force=True)
    logging.info("Starting music importer")
    sleep(5)

    # Initialize settings and components
    settings = Settings()
    tagger = Tagger()
    extractor = Extractor()
    renamer = Renamer()
    mover = Mover()

    # Configure logging

    while True:
        try:
            logging.info("Starting process...")

            # Extraction process
            try:
                extractor.extract()
                logging.info("Extraction completed.")
            except Exception as e:
                logging.error(f"Extractor failed: {e}")

            # Renaming process
            try:
                renamer.rename()
                logging.info("Renaming completed.")
            except Exception as e:
                logging.error(f"Renamer failed: {e}")

            # Moving process
            try:
                mover.move()
                logging.info("Moving completed.")
            except Exception as e:
                logging.error(f"Mover failed: {e}")

            # Tagging process
            try:
                tagger.tag()
                logging.info("Tagging completed.")
            except Exception as e:
                logging.error(f"Tagger failed: {e}")

        except KeyboardInterrupt:
            logging.info("Process interrupted by user. Exiting.")
            break
        except Exception as e:
            logging.error(f"Unexpected error: {e}")

        logging.info("Waiting for 3600 seconds.")
        sleep(3600)
