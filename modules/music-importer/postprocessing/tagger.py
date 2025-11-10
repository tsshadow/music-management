import time
from concurrent.futures import ProcessPoolExecutor, as_completed, ThreadPoolExecutor
from pathlib import Path
import logging
import sys

from mutagen import MutagenError
from mutagen.easyid3 import EasyID3
from mutagen.easymp4 import EasyMP4Tags

from data.settings import Settings
from postprocessing.Song.BaseSong import ExtensionNotSupportedException
from postprocessing.Song.GenericSong import GenericSong
from postprocessing.Song.Helpers.BrokenSongHelper import BrokenSongHelper
from postprocessing.Song.LabelSong import LabelSong
from postprocessing.Song.SoundcloudSong import SoundcloudSong
from postprocessing.Song.YoutubeSong import YoutubeSong
from postprocessing.Song.TelegramSong import TelegramSong
from postprocessing.constants import SongTypeEnum, MP3Tags

# global vars
EasyID3.RegisterTXXXKey('publisher', 'publisher')
EasyID3.RegisterTXXXKey('parsed', 'parsed')
EasyID3.RegisterTXXXKey('festival', 'festival')
EasyID3.RegisterTXXXKey('remixer', 'remixer')
EasyID3.RegisterTXXXKey("original_title", "original_title")
EasyMP4Tags.RegisterTextKey("publisher", "publisher")
EasyMP4Tags.RegisterTextKey("parsed", "parsed")
EasyMP4Tags.RegisterTextKey("festival", "festival")
EasyMP4Tags.RegisterTextKey("original_title", "original_title")

s = Settings()
parse_mp3 = True
parse_flac = True
parse_m4a = True
parse_wav = False  # WAV is currently bugged
parse_aac = False  # AAC has no tags, downloads changed to M4A

broken_song_helper = BrokenSongHelper()

class Tagger:
    """
    Handles automatic tagging of music files using Mutagen,
    based on their source (Label, SoundCloud, YouTube, etc).
    """

    def __init__(self):
        self.parallel = True
        pass

    def run(self, parse_labels=True, parse_soundcloud=True, parse_youtube=True, parse_generic=True, parse_telegram=True):
        """
        Entrypoint for the tagging process.
        Scans various music directories (labels, YouTube, SoundCloud, generic) and applies appropriate tag parsing.
        """
        logging.info("Starting Tag Step with options: {}, {}, {}, {}, {}".format(parse_labels, parse_soundcloud, parse_youtube, parse_generic, parse_telegram))

        if parse_labels:
            self._parse_label_folders()

        if parse_soundcloud:
            self._parse_channel_folders("Soundcloud", SongTypeEnum.SOUNDCLOUD)

        if parse_youtube:
            self._parse_channel_folders("Youtube", SongTypeEnum.YOUTUBE)

        if parse_telegram:
            self._parse_channel_folders("Telegram", SongTypeEnum.TELEGRAM)

        if parse_generic:
           self._parse_generic_folders()


    def _parse_label_folders(self):
        """
        Parses the EPS folder which contains label/ep/song hierarchies.
        """
        eps_root = Path(s.eps_folder_path)
        label_folders = sorted([f for f in eps_root.iterdir() if f.is_dir()])

        for label in label_folders:
            song_type = SongTypeEnum.LABEL if not label.name.startswith("_") else SongTypeEnum.GENERIC
            print(label)
            self.parse_folder(label, song_type)

    def _parse_channel_folders(self, source_folder: str, song_type: SongTypeEnum):
        """
        Parses folders under a platform-specific directory like SoundCloud or YouTube.

        @param source_folder: Root subfolder under music_folder_path
        @param song_type: Enum describing the song origin
        """
        root = Path(s.music_folder_path) / source_folder
        if not root.exists():
            logging.warning(f"Folder '{root}' does not exist, skipping.")
            return

        for channel in sorted([f for f in root.iterdir() if f.is_dir()]):
            self.parse_folder(channel, song_type)

    def _parse_generic_folders(self):
        """
        Parses generic folders like Livesets, Podcasts, Top 100.
        """
        generic_folders = ["Livesets", "Podcasts", "Top 100", "Warm Up Mixes"]
        music_root = Path(s.music_folder_path)

        for folder_name in generic_folders:
            root_path = music_root / folder_name
            if not root_path.exists():
                continue
            for subfolder in [f for f in root_path.iterdir() if f.is_dir()]:
                self.parse_folder(subfolder, SongTypeEnum.GENERIC)

    def parse_folder(self, folder: Path, song_type: SongTypeEnum):
        """
        Recursively parses a folder and its subfolders for audio files to tag.

        @param folder: Path object to folder to scan
        @param song_type: Enum to define tag strategy
        """
        if "@eaDir" in str(folder):
            return

        extensions = {
            "mp3": parse_mp3,
            "flac": parse_flac,
            "wav": parse_wav,
            "m4a": parse_m4a,
            "aac": parse_aac
        }

        try:
            files = []
            for ext, enabled in extensions.items():
                if enabled:
                    files.extend(folder.glob(f"*.{ext}"))

            if self.parallel and files:
                with ThreadPoolExecutor(max_workers=16) as executor:
                    futures = [executor.submit(Tagger._parse_worker, str(file), song_type.name) for file in files]
                    for future in as_completed(futures):
                        path, status = future.result()
                        if status != "OK":
                            logging.warning(f"{path}: {status}")
            else:
                for file in files:
                    self._try_parse(file, song_type)

            for subfolder in [f for f in folder.iterdir() if f.is_dir() and not f.name.startswith("_")]:
                self.parse_folder(subfolder, song_type)

        except Exception as e:
            logging.error(f"Error parsing folder {folder}: {e}", exc_info=True)

    def _try_parse(self, file: Path, song_type: SongTypeEnum):
        try:
            self.parse_song(file, song_type)
        except KeyboardInterrupt:
            logging.info('KeyboardInterrupt')
            sys.exit(1)
        except (PermissionError, MutagenError, FileNotFoundError, ExtensionNotSupportedException) as e:
            logging.error(f"{type(e).__name__}: {e} -> {file}", exc_info=True)
            broken_song_helper.add(str(file), type(e).__name__)
        except Exception as e:
            logging.error(f"Parse_song failed: {e} -> {file}", exc_info=True)

    @staticmethod
    def parse_song(path: Path, song_type: SongTypeEnum, manual_tags: dict[str, str] | None = None):
        """
        Creates a Song instance to trigger tag parsing logic.

        @param path: Path object to the song
        @param song_type: Type of song source (LABEL, YOUTUBE, etc)
        """
        song = None
        if song_type == SongTypeEnum.LABEL:
            song = LabelSong(str(path))
        elif song_type == SongTypeEnum.YOUTUBE:
            song = YoutubeSong(str(path))
        elif song_type == SongTypeEnum.SOUNDCLOUD:
            song = SoundcloudSong(str(path))
        elif song_type == SongTypeEnum.TELEGRAM:
            song = TelegramSong(str(path))
        elif song_type == SongTypeEnum.GENERIC:
            song = GenericSong(str(path))
        if song:
            song.parse()
            if manual_tags:
                for tag, value in manual_tags.items():
                    song.tag_collection.add(tag, value)
                song.save_file()
        #for artist in song.artists():
        #    for genre in song.genres():
        #        a.submit(artist, genre)

    @staticmethod
    def _parse_worker(file: str, song_type_str: str, manual_tags: dict[str, str] | None = None):
        try:
            song_type = SongTypeEnum[song_type_str]
            Tagger.parse_song(Path(file), song_type, manual_tags)
            return file, "OK"
        except Exception as e:
            return file, f"{type(e).__name__}: {e}"
