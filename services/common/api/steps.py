from .step import Step
from .run_tagger import run_tagger
from services.downloader.youtube.youtube import YoutubeDownloader
from services.downloader.soundcloud.soundcloud import SoundcloudDownloader
from services.downloader.telegram.telegram import TelegramDownloader
from services.other.repair import FileRepair
from services.other.sanitizer import Sanitizer

from services.importer.extractor import Extractor
from services.importer.mover import Mover
from services.importer.renamer import Renamer

def run_youtube(steps, **kwargs):
    url = kwargs.pop('url', None)
    if url:
        YoutubeDownloader().download_link(url=url, **kwargs)
    else:
        YoutubeDownloader().run(**kwargs)

def run_soundcloud(steps, **kwargs):
    SoundcloudDownloader().run(**kwargs)

def run_telegram(steps, **kwargs):
    # Telegram usually needs an account
    account = kwargs.get('account')
    if account:
        TelegramDownloader().run(account)

def run_import(steps, **kwargs):
    Extractor().run(steps)
    Renamer().run(steps)
    Mover().run(steps)

def run_repair(steps, **kwargs):
    FileRepair().run()

def run_sanitizer(steps, **kwargs):
    Sanitizer().run()

steps_to_run = [
    Step('youtube', run_youtube),
    Step('manual-youtube', run_youtube),
    Step('soundcloud', run_soundcloud),
    Step('telegram', run_telegram),
    Step('tag', run_tagger, condition_keys=['tag', 'tag-labels', 'tag-soundcloud', 'tag-youtube', 'tag-generic', 'tag-telegram']),
    Step('import', run_import),
    Step('repair', run_repair),
    Step('sanitizer', run_sanitizer),
]

step_map = {s.name: s for s in steps_to_run}
# Add specific tagging steps to the map as well, although they all use run_tagger
for k in ['tag-labels', 'tag-soundcloud', 'tag-youtube', 'tag-generic', 'tag-telegram']:
    step_map[k] = step_map['tag']
