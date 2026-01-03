import argparse
import logging
import signal
from time import sleep

import faulthandler

from services.common.settings import Settings
from services.importer.extractor import Extractor
from services.importer.mover import Mover
from services.importer.renamer import Renamer
from services.common.api import start_api_server
from services.common.api.step import Step

faulthandler.register(signal.SIGUSR1)


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments for the importer service.

    The importer always runs all steps in order:
    Extractor -> Renamer -> Mover.

    Options:
      --sleeptime   Time (in seconds) to sleep between repeated runs.
      --repeat      If set, the importer will run in a loop.
    """
    parser = argparse.ArgumentParser(
        description="Run the music importer pipeline (Extractor -> Renamer -> Mover)."
    )

    parser.add_argument(
        "--sleeptime",
        type=int,
        default=300,
        help="Time in seconds to sleep between repeated runs (default: 300).",
    )
    parser.add_argument(
        "--repeat",
        help="Repeat the importer pipeline in a loop, sleeping between runs.",
        action="store_true",
    )

    return parser.parse_args()


class ImporterService:
    """
    High-level importer service that runs the full import pipeline.

    The pipeline consists of three tightly-coupled steps:
      1. Extractor
      2. Renamer
      3. Mover

    These steps are designed to be executed together and in this order.
    """

    def __init__(self) -> None:
        # Load global settings (database, paths, etc.)
        self.settings = Settings()

        # Initialize all importer components
        self.extractor = Extractor()
        self.renamer = Renamer()
        self.mover = Mover()

        # Define the ordered pipeline steps
        self.steps: list[Step] = [
            Step("Extractor", self.extractor.run),
            Step("Renamer", self.renamer.run),
            Step("Mover", self.mover.run),
        ]

        # Start the API server for health checks, metrics, control, etc.
        start_api_server()

    def run_import(self) -> None:
        """
        Run the full import pipeline once.

        Each Step receives the full list of steps, just like in the original
        implementation. This allows a step to inspect or control the rest
        of the pipeline if needed.
        """
        logging.info("Starting importer pipeline...")
        step_keys = {step.name.lower() for step in self.steps}
        for step in self.steps:
            logging.info("Running step: %s", step.name)
            step.run(step_keys)
        logging.info("Importer pipeline completed.")


def main() -> None:
    # Configure logging for the entire process
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(filename)s:%(lineno)s [%(levelname)s] %(message)s",
        force=True,
    )

    args = parse_args()
    logging.info("Starting music importer service")

    importer_service = ImporterService()

    while True:
        try:
            importer_service.run_import()
        except KeyboardInterrupt:
            logging.info("Process interrupted by user. Exiting.")
            break
        except Exception:
            # Log full stack trace for unexpected errors
            logging.exception("Unexpected error during importer run")

        if not args.repeat:
            logging.info("Repeat flag not set; exiting after a single run.")
            break

        logging.info("Waiting for %d seconds before next importer run.", args.sleeptime)
        sleep(args.sleeptime)


if __name__ == "__main__":
    main()
