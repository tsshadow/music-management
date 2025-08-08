from step import Step
from postprocessing.sanitizer import Sanitizer
from postprocessing.analyze import Analyze
from postprocessing.artistfixer import ArtistFixer
from processing.converter import Converter
from processing.epsflattener import EpsFlattener
from processing.extractor import Extractor
from processing.mover import Mover
from processing.renamer import Renamer
from downloader.youtube import YoutubeDownloader
from downloader.soundcloud import SoundcloudDownloader
from downloader.telegram import TelegramDownloader
from .run_tagger import run_tagger

# instantiate processors and downloaders
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

steps_to_run = [
    Step("Extractor", ["import", "extract"], extractor.run),
    Step("Renamer", ["import", "rename"], renamer.run),
    Step("Mover", ["import", "move"], mover.run),
    Step("Converter", ["convert"], converter.run),
    Step("Sanitizer", ["sanitize"], sanitizer.run),
    Step("Flattener", ["flatten"], flattener.run),
    Step("YouTube Downloader", ["download", "download-youtube"], youtube_downloader.run),
    Step("SoundCloud Downloader", ["download", "download-soundcloud"], lambda: soundcloud_downloader.run(account="")),
    Step("Telegram Downloader", ["download-telegram"], lambda: telegram_downloader.run("")),
    Step("Analyze", ["analyze"], analyze_step.run),
    Step("ArtistFixer", ["artistfixer"], artist_fixer.run),
    Step(
        "Tagger",
        ["tag", "tag-labels", "tag-soundcloud", "tag-youtube", "tag-generic", "tag-telegram"],
        run_tagger,
    ),
]

step_map = {key: step for step in steps_to_run for key in step.condition_keys}

__all__ = ["steps_to_run", "step_map"]
