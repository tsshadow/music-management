from pathlib import Path
import logging
import sys

from mutagen import MutagenError
from mutagen.easyid3 import EasyID3
from mutagen.easymp4 import EasyMP4Tags

from data.settings import Settings
from postprocessing.Song.BaseSong import ExtensionNotSupportedException
from postprocessing.Song.GenericSong import GenericSong
from postprocessing.Song.LabelSong import LabelSong
from postprocessing.Song.SoundcloudSong import SoundcloudSong
from postprocessing.Song.YoutubeSong import YoutubeSong
from postprocessing.constants import SongTypeEnum

# global vars
EasyID3.RegisterTextKey('publisher_old', 'TPUB')
EasyID3.RegisterTXXXKey('publisher', 'publisher')
EasyID3.RegisterTXXXKey('parsed', 'parsed')
EasyID3.RegisterTXXXKey('festival', 'festival')
EasyMP4Tags.RegisterTextKey("publisher", "publisher")
EasyMP4Tags.RegisterTextKey("parsed", "parsed")
EasyMP4Tags.RegisterTextKey("festival", "festival")

s = Settings()

parse_labels = True
parse_youtube = True
parse_soundcloud = True
parse_generic = True

parse_mp3 = True
parse_flac = True
parse_m4a = True
parse_wav = False  # WAV is currently bugged
parse_aac = False  # AAC has no tags, downloads changed to M4A


class Tagger:
    """
    Handles automatic tagging of music files using Mutagen,
    based on their source (Label, SoundCloud, YouTube, etc).
    """

    def __init__(self):
        pass

    def run(self):
        """
        Entrypoint for the tagging process.
        Scans various music directories (labels, YouTube, SoundCloud, generic) and applies appropriate tag parsing.
        """
        logging.info("Starting Tag Step")

        if parse_labels:
            self._parse_label_folders()

        if parse_soundcloud:
            self._parse_channel_folders("Soundcloud", SongTypeEnum.SOUNDCLOUD)

        if parse_youtube:
            self._parse_channel_folders("Youtube", SongTypeEnum.YOUTUBE)

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
            self.parse_folder(label, song_type)

    def _parse_channel_folders(self, source_folder: str, song_type: SongTypeEnum):
        """
        Parses folders under a platform-specific directory like SoundCloud or YouTube.

        @param source_folder: Root subfolder under music_folder_path
        @param song_type: Enum describing the song origin
        """
        root = Path(s.music_folder_path) / source_folder
        if not root.exists():
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
            for ext, enabled in extensions.items():
                if enabled:
                    for file in folder.glob(f"*.{ext}"):
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
        except Exception as e:
            logging.error(f"Parse_song failed: {e} -> {file}", exc_info=True)

    @staticmethod
    def parse_song(path: Path, song_type: SongTypeEnum):
        """
        Creates a Song instance to trigger tag parsing logic.

        @param path: Path object to the song
        @param song_type: Type of song source (LABEL, YOUTUBE, etc)
        """
        if song_type == SongTypeEnum.LABEL:
            LabelSong(str(path))
        elif song_type == SongTypeEnum.YOUTUBE:
            YoutubeSong(str(path))
        elif song_type == SongTypeEnum.SOUNDCLOUD:
            SoundcloudSong(str(path))
        elif song_type == SongTypeEnum.GENERIC:
            GenericSong(str(path))
