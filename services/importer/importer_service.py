import argparse
import faulthandler
import logging
import signal
from time import sleep

from services.common.config_store import ConfigStore as Settings
from services.common.Helpers.logging_setup import setup_logging
from services.common.step import Step
from services.importer.extractor import Extractor
from services.importer.flattener import Flattener
from services.importer.mover import Mover
from services.importer.renamer import Renamer

faulthandler.register(signal.SIGUSR1)


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments for the importer service.

    The importer always runs all steps in order:
    Extractor -> Flattener -> Renamer -> Mover.

    Options:
      --sleeptime   Time (in seconds) to sleep between repeated runs.
      --repeat      If set, the importer will run in a loop.
    """
    parser = argparse.ArgumentParser(
        description='Run the music importer pipeline (Extractor -> Flattener -> Renamer -> Mover).'
    )
    parser.add_argument(
        '--sleeptime', type=int, default=300, help='Time in seconds to sleep between repeated runs (default: 300).'
    )
    parser.add_argument(
        '--repeat', help='Repeat the importer pipeline in a loop, sleeping between runs.', action='store_true'
    )
    return parser.parse_args()


class ImporterService:
    """
    High-level importer service that runs the full import pipeline.

    The pipeline consists of four tightly-coupled steps:
      1. Extractor
      2. Flattener
      3. Renamer
      4. Mover

    These steps are designed to be executed together and in this order.
    """

    def __init__(self) -> None:
        self.settings = Settings()
        self.extractor = Extractor()
        self.flattener = Flattener()
        self.renamer = Renamer()
        self.mover = Mover()
        self.dry_run = getattr(self.settings, 'dryrun', False)
        self.steps: list[Step] = [
            Step('Extractor', self.extractor.run),
            Step('Flattener', self.flattener.run),
            Step('Renamer', self.renamer.run),
            Step('Mover', self.mover.run),
        ]

    def run_import(self) -> None:
        """
        Run the full import pipeline once.

        Each Step receives the full list of steps, just like in the original
        implementation. This allows a step to inspect or control the rest
        of the pipeline if needed.
        """
        logging.info(f"Starting importer pipeline... {'(DRY RUN)' if self.dry_run else ''}")
        for step in self.steps:
            logging.info('Running step: %s', step.name)
            step.run(self.steps, dry_run=self.dry_run)
        logging.info('Importer pipeline completed.')


def main() -> None:
    setup_logging('importer')
    args = parse_args()
    logging.info('Starting music importer service')
    importer_service = ImporterService()
    while True:
        try:
            importer_service.run_import()
        except KeyboardInterrupt:
            logging.info('Process interrupted by user. Exiting.')
            break
        except Exception:
            logging.exception('Unexpected error during importer run')
        if not args.repeat:
            logging.info('Repeat flag not set; exiting after a single run.')
            break
        logging.info('Waiting for %d seconds before next importer run.', args.sleeptime)
        sleep(args.sleeptime)


if __name__ == '__main__':
    main()
