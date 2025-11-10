import io
import os
import sys
import tempfile
import types
import unittest

from yt_dlp.utils import sanitize_filename


_orig_youtube_song_module = sys.modules.get("postprocessing.Song.YoutubeSong")
_orig_youtube_archive_module = sys.modules.get("downloader.YoutubeArchive")


class DummyTagCollection:
    def __init__(self):
        self.values = {}

    def set_item(self, tag, value):
        self.values[tag] = value


class DummySong:
    last_instance = None

    def __init__(self, path, extra_info=None):
        self.path = path
        self.extra_info = extra_info
        self.tag_collection = DummyTagCollection()
        self.parse_called = False
        DummySong.last_instance = self

    def parse(self):
        self.parse_called = True


class DummyYoutubeArchive:
    inserted = []

    @staticmethod
    def exists(account, video_id):
        return False

    @staticmethod
    def insert(account, video_id, path, url, title):
        DummyYoutubeArchive.inserted.append((account, video_id, path, url, title))


dummy_song_module = types.ModuleType("postprocessing.Song.YoutubeSong")
dummy_song_module.YoutubeSong = DummySong
sys.modules["postprocessing.Song.YoutubeSong"] = dummy_song_module

dummy_archive_module = types.ModuleType("downloader.YoutubeArchive")
dummy_archive_module.YoutubeArchive = DummyYoutubeArchive
sys.modules["downloader.YoutubeArchive"] = dummy_archive_module


from downloader.YoutubeSongProcessor import YoutubeSongProcessor


class DummyDownloader:
    def __init__(self, base_dir, html):
        self.base_dir = base_dir
        self.html = html
        self.params = {}

    def prepare_filename(self, info):
        uploader = info.get("uploader") or info.get("channel") or "NA"
        title = info.get("title") or info.get("id") or "download"
        ext = info.get("ext", "m4a")

        uploader_dir = sanitize_filename(uploader, restricted=True) or "NA"
        title_part = sanitize_filename(title, restricted=True) or info.get("id", "download")

        path = os.path.join(self.base_dir, uploader_dir, f"{title_part}.{ext}")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return path

    def urlopen(self, url):
        return io.BytesIO(self.html.encode("utf-8"))

    def to_console_title(self, *args, **kwargs):
        return None

    def evaluate_outtmpl(self, template, info_dict=None, **kwargs):
        return ""


class YoutubeSongProcessorTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        DummyYoutubeArchive.inserted.clear()
        DummySong.last_instance = None

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_recovers_title_and_renames_file(self):
        html = (
            "<html><head><meta property=\"og:title\" "
            "content=\"Noiseflow | Defqon.1 2025\"></head><body></body></html>"
        )

        processor = YoutubeSongProcessor()
        processor._downloader = DummyDownloader(self.temp_dir.name, html)

        info = {
            "id": "5mKayZadF4g",
            "title": "youtube video #5mKayZadF4g",
            "fulltitle": "youtube video #5mKayZadF4g",
            "extractor": "youtube",
            "uploader": "Q-dance",
            "uploader_id": "qdance",
            "ext": "m4a",
            "webpage_url": "https://www.youtube.com/watch?v=5mKayZadF4g",
        }

        original_path = processor._downloader.prepare_filename(info)
        with open(original_path, "wb") as handle:
            handle.write(b"data")

        info["filepath"] = original_path
        info["_filename"] = original_path
        info["requested_downloads"] = [
            {
                "filepath": original_path,
                "_filename": original_path,
                "filename": os.path.basename(original_path),
            }
        ]

        expected_info = dict(info)
        expected_info["title"] = "Noiseflow | Defqon.1 2025"
        expected_path = processor._downloader.prepare_filename(expected_info)

        processor.run(info)

        self.assertEqual(info["title"], "Noiseflow | Defqon.1 2025")
        self.assertEqual(info["fulltitle"], "Noiseflow | Defqon.1 2025")
        self.assertEqual(os.path.normpath(info["filepath"]), os.path.normpath(expected_path))
        self.assertFalse(os.path.exists(original_path))
        self.assertTrue(os.path.exists(expected_path))
        self.assertEqual(
            os.path.normpath(info["requested_downloads"][0]["filepath"]),
            os.path.normpath(expected_path),
        )
        self.assertEqual(
            os.path.normpath(info["requested_downloads"][0]["_filename"]),
            os.path.normpath(expected_path),
        )
        self.assertEqual(
            DummyYoutubeArchive.inserted[-1],
            (
                "qdance",
                "5mKayZadF4g",
                info["filepath"],
                info["webpage_url"],
                "Noiseflow | Defqon.1 2025",
            ),
        )
        self.assertIsNotNone(DummySong.last_instance)
        self.assertIs(DummySong.last_instance.extra_info, info)
        self.assertEqual(
            DummySong.last_instance.tag_collection.values.get("title"),
            "Noiseflow | Defqon.1 2025",
        )
        self.assertTrue(DummySong.last_instance.parse_called)


def tearDownModule():
    if _orig_youtube_song_module is not None:
        sys.modules["postprocessing.Song.YoutubeSong"] = _orig_youtube_song_module
    else:
        sys.modules.pop("postprocessing.Song.YoutubeSong", None)

    if _orig_youtube_archive_module is not None:
        sys.modules["downloader.YoutubeArchive"] = _orig_youtube_archive_module
    else:
        sys.modules.pop("downloader.YoutubeArchive", None)


if __name__ == "__main__":
    unittest.main()
