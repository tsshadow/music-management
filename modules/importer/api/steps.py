"""Pipeline step registry for the FastAPI server."""
from __future__ import annotations

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
    DownloadService,
    StepContext,
    StepDefinition,
    TaggingService,
    create_default_steps,
)

# Instantiate processors and services once so they can maintain subscriptions/state.
youtube_downloader = YoutubeDownloader()
soundcloud_downloader = SoundcloudDownloader()
telegram_downloader = TelegramDownloader()
extractor = Extractor()
renamer = Renamer()
mover = Mover()
converter = Converter()
sanitizer = Sanitizer()
flattener = EpsFlattener()
analyze_step = Analyze()
artist_fixer = ArtistFixer()
tagger = Tagger()

_download_service = DownloadService(
    youtube=youtube_downloader,
    soundcloud=soundcloud_downloader,
    telegram=telegram_downloader,
)
_tagging_service = TaggingService(tagger)

steps_to_run: tuple[StepDefinition, ...] = tuple(
    create_default_steps(
        extractor=extractor,
        renamer=renamer,
        mover=mover,
        converter=converter,
        sanitizer=sanitizer,
        flattener=flattener,
        analyzer=analyze_step,
        artist_fixer=artist_fixer,
        download_service=_download_service,
        tagging_service=_tagging_service,
    )
)


def create_context() -> StepContext:
    return StepContext(
        download_service=_download_service,
        tagging_service=_tagging_service,
        extras={"source": "api"},
    )


def _step_keys(step: StepDefinition) -> set[str]:
    return step.selectors


step_map = {key: step for step in steps_to_run for key in _step_keys(step)}

__all__ = ["steps_to_run", "step_map", "create_context"]
