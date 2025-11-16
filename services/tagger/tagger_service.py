import argparse
import logging
import signal
from pathlib import Path
from time import sleep

import faulthandler

from services.common.api import start_api_server
from services.common.settings import Settings
from services.tagger.constants import SongTypeEnum
from services.tagger.tagger import Tagger  # Adjust this import if your module path is different

faulthandler.register(signal.SIGUSR1)


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments for the tagger service.

    The service can:
      - Run the full tagging pipeline (all sources), or
      - Tag a specific folder for a single source type.
    """
    parser = argparse.ArgumentParser(
        description="Run the music tagger service (label, soundcloud, youtube, generic, telegram)."
    )

    parser.add_argument(
        "--type",
        dest="tag_type",
        default="all",
        help=(
            "Tag type to process: one of "
            "'label', 'soundcloud', 'youtube', 'generic', 'telegram', or 'all' "
            "(default: all). When used together with --folder, must NOT be 'all'."
        ),
    )
    parser.add_argument(
        "--folder",
        help=(
            "Optional folder to tag. When provided, only this folder is processed "
            "for the given --type."
        ),
    )
    parser.add_argument(
        "--sleeptime",
        type=int,
        default=300,
        help="Time in seconds to sleep between repeated runs (default: 300).",
    )
    parser.add_argument(
        "--repeat",
        help="Repeat the tagging run in a loop, sleeping between runs.",
        action="store_true",
    )

    return parser.parse_args()


class TaggerService:
    """
    High-level tagger service that exposes Tagger functionality in a reusable way.

    Public API:
      - run_full(...): run the full tagging pipeline across all standard folders.
      - tag(tag_type, folder): tag a single folder for a specific type
        (label, soundcloud, youtube, generic, telegram).
    """

    def __init__(self) -> None:
        # Load global settings (paths, configuration, etc.)
        self.settings = Settings()

        # Underlying Tagger instance that knows how to parse & tag files.
        self.tagger = Tagger()

        # Start the lightweight API server (for health checks, control, etc.)
        start_api_server()

    @staticmethod
    def _map_tag_type(tag_type: str) -> SongTypeEnum:
        """
        Map a human-readable type string to a SongTypeEnum value.

        Raises:
            ValueError if the type is unknown.
        """
        mapping = {
            "label": SongTypeEnum.LABEL,
            "soundcloud": SongTypeEnum.SOUNDCLOUD,
            "youtube": SongTypeEnum.YOUTUBE,
            "generic": SongTypeEnum.GENERIC,
            "telegram": SongTypeEnum.TELEGRAM,
        }

        normalized = tag_type.lower()
        if normalized not in mapping:
            raise ValueError(
                f"Unknown tag type '{tag_type}'. "
                f"Expected one of: {', '.join(mapping.keys())}."
            )

        return mapping[normalized]

    def tag(self, tag_type: str, folder: str | Path, extra_info) -> None:
        """
        Tag a specific folder for a single source type.

        Args:
            tag_type: One of 'label', 'soundcloud', 'youtube', 'generic', 'telegram'.
            folder:  Folder path to process.
        """
        song_type = self._map_tag_type(tag_type)
        path = Path(folder)

        if not path.exists() or not path.is_dir():
            raise ValueError(f"Folder does not exist or is not a directory: {path}")

        logging.info("Tagging folder '%s' as type '%s'", path, song_type.name)
        self.tagger.parse_folder(path, song_type,extra_info)
        logging.info("Finished tagging folder '%s' (%s)", path, song_type.name)

    def run_full(
        self,
        *,
        parse_labels: bool = True,
        parse_soundcloud: bool = True,
        parse_youtube: bool = True,
        parse_generic: bool = True,
        parse_telegram: bool = True,
    ) -> None:
        """
        Run the full tagging pipeline, similar to Tagger.run().

        Each boolean controls whether that specific category will be processed.
        """
        logging.info(
            "Starting full tagging run "
            "(labels=%s, soundcloud=%s, youtube=%s, generic=%s, telegram=%s)",
            parse_labels,
            parse_soundcloud,
            parse_youtube,
            parse_generic,
            parse_telegram,
        )

        self.tagger.run(
            parse_labels=parse_labels,
            parse_soundcloud=parse_soundcloud,
            parse_youtube=parse_youtube,
            parse_generic=parse_generic,
            parse_telegram=parse_telegram,
        )

        logging.info("Full tagging run completed.")


def main() -> None:
    # Configure logging for the entire service
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(filename)s:%(lineno)s [%(levelname)s] %(message)s",
        force=True,
    )

    args = parse_args()
    logging.info("Starting music tagger service")

    tagger_service = TaggerService()

    # Pre-calculate which modes to use based on CLI arguments
    folder = args.folder
    tag_type = args.tag_type.lower()

    # If a folder is specified, we expect a single concrete type (not "all")
    if folder and tag_type == "all":
        raise SystemExit(
            "Error: When using --folder, you must specify --type as one of "
            "'label', 'soundcloud', 'youtube', 'generic', 'telegram' (not 'all')."
        )

    # For "full" mode (no folder), allow comma-separated types
    enabled_types: set[str] = set()
    if not folder:
        # Example: --type label,soundcloud
        if tag_type:
            enabled_types = {t.strip().lower() for t in tag_type.split(",") if t.strip()}
        if not enabled_types or "all" in enabled_types:
            enabled_types = {"all"}

    while True:
        try:
            if folder:
                # Single-folder mode: tag only the given folder and type.
                tagger_service.tag(tag_type, folder)
            else:
                # Full mode: run Tagger.run with flags derived from enabled types.
                parse_labels = "all" in enabled_types or "label" in enabled_types
                parse_soundcloud = "all" in enabled_types or "soundcloud" in enabled_types
                parse_youtube = "all" in enabled_types or "youtube" in enabled_types
                parse_generic = "all" in enabled_types or "generic" in enabled_types
                parse_telegram = "all" in enabled_types or "telegram" in enabled_types

                tagger_service.run_full(
                    parse_labels=parse_labels,
                    parse_soundcloud=parse_soundcloud,
                    parse_youtube=parse_youtube,
                    parse_generic=parse_generic,
                    parse_telegram=parse_telegram,
                )

        except KeyboardInterrupt:
            logging.info("Process interrupted by user. Exiting.")
            break
        except Exception:
            logging.exception("Unexpected error during tagger run")

        if not args.repeat:
            logging.info("Repeat flag not set; exiting after a single run.")
            break

        logging.info("Waiting for %d seconds before next tagger run.", args.sleeptime)
        sleep(args.sleeptime)


if __name__ == "__main__":
    main()
