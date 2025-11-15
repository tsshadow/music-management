import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from ...postprocessing.constants import SongTypeEnum

from ...services import (
    DownloadService,
    StepContext,
    TaggingOptions,
    TaggingService,
    create_default_steps,
    execute_pipeline_step,
)


class FakeYoutubeDownloader:
    def __init__(self, folder: Path):
        self.output_folder = str(folder)
        self.manual_calls = []
        self.account_calls = []
        self.run_called = 0

    def run(self):
        self.run_called += 1

    def manual_download(self, url, *_args, **_kwargs):
        self.manual_calls.append(url)

    def manual_account_download(self, account, *_args, **_kwargs):
        self.account_calls.append(account)


class FakeSoundcloudDownloader:
    def __init__(self, folder: Path):
        self.output_folder = str(folder)
        self.default_break_on_existing = True
        self.calls = []

    def run(self, account="", breakOnExisting=None, redownload=False):
        self.calls.append({
            "account": account,
            "break": breakOnExisting,
            "redownload": redownload,
        })


class FakeTelegramDownloader:
    def __init__(self, folder: Path):
        self.output_folder = str(folder)
        self.calls = []

    def run(self, channel, limit=None):
        self.calls.append({"channel": channel, "limit": limit})


class FakeTagger:
    def __init__(self):
        self.run_calls = []
        self.parse_calls = []

    def run(self, **kwargs):
        self.run_calls.append(kwargs)

    def parse_folder(self, folder, song_type):
        self.parse_calls.append((str(folder), getattr(song_type, "name", song_type)))


class ProcessorStub:
    def __init__(self):
        self.calls = 0

    def run(self):
        self.calls += 1


class DownloadServiceTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.youtube = FakeYoutubeDownloader(root / "Youtube")
        self.soundcloud = FakeSoundcloudDownloader(root / "Soundcloud")
        self.telegram = FakeTelegramDownloader(root / "Telegram")
        self.service = DownloadService(
            youtube=self.youtube,
            soundcloud=self.soundcloud,
            telegram=self.telegram,
            settings=SimpleNamespace(music_folder_path=str(root)),
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_youtube_account_metadata(self):
        result = self.service.download_youtube(account="artist")
        self.assertIn("artist", self.youtube.account_calls)
        self.assertEqual(len(result.items), 1)
        item = result.items[0]
        self.assertEqual(item.song_type.name, SongTypeEnum.YOUTUBE.name)
        self.assertEqual(item.target_dir, Path(self.youtube.output_folder) / "artist")

    def test_soundcloud_run_metadata(self):
        result = self.service.download_soundcloud()
        self.assertEqual(len(result.items), 1)
        item = result.items[0]
        self.assertEqual(item.song_type.name, SongTypeEnum.SOUNDCLOUD.name)
        self.assertEqual(item.target_dir, Path(self.soundcloud.output_folder))

    def test_manual_youtube_metadata(self):
        url = "http://example.com/video"
        result = self.service.download_youtube(url=url)
        self.assertIn(url, self.youtube.manual_calls)
        self.assertEqual(result.items[0].identifier, url)


class PipelineFlowTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.youtube = FakeYoutubeDownloader(root / "Youtube")
        self.soundcloud = FakeSoundcloudDownloader(root / "Soundcloud")
        self.telegram = FakeTelegramDownloader(root / "Telegram")
        self.tagger = FakeTagger()
        self.download_service = DownloadService(
            youtube=self.youtube,
            soundcloud=self.soundcloud,
            telegram=self.telegram,
            settings=SimpleNamespace(music_folder_path=str(root)),
        )
        self.tagging_service = TaggingService(self.tagger)

        self.extractor = ProcessorStub()
        self.renamer = ProcessorStub()
        self.mover = ProcessorStub()
        self.converter = ProcessorStub()
        self.sanitizer = ProcessorStub()
        self.flattener = ProcessorStub()
        self.analyzer = ProcessorStub()
        self.artist_fixer = ProcessorStub()

        self.steps = list(
            create_default_steps(
                extractor=self.extractor,
                renamer=self.renamer,
                mover=self.mover,
                converter=self.converter,
                sanitizer=self.sanitizer,
                flattener=self.flattener,
                analyzer=self.analyzer,
                artist_fixer=self.artist_fixer,
                download_service=self.download_service,
                tagging_service=self.tagging_service,
            )
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def _step(self, key):
        for step in self.steps:
            if key in step.selectors:
                return step
        raise AssertionError(f"Step {key} not found")

    def test_metadata_passed_to_tagger(self):
        context = StepContext(self.download_service, self.tagging_service)
        download_step = self._step("download-youtube")
        execute_pipeline_step(download_step, {"download-youtube"}, context, {"account": "dj"})
        self.assertTrue(context.download_metadata.items)

        tag_step = self._step("tag")
        execute_pipeline_step(tag_step, {"tag"}, context, {})
        self.assertEqual(len(self.tagger.parse_calls), 1)
        path, song_type = self.tagger.parse_calls[0]
        self.assertIn("Youtube", path)
        self.assertEqual(song_type, SongTypeEnum.YOUTUBE.name)
        self.assertTrue(context.tagging_results[0].used_metadata)

    def test_tagging_without_metadata_runs_full_scan(self):
        options = TaggingOptions.from_selection(["tag", "tag-soundcloud"])
        result = self.tagging_service.tag(options)
        self.assertEqual(len(self.tagger.run_calls), 1)
        self.assertFalse(result.used_metadata)
