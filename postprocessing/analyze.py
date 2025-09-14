import logging
from pathlib import Path

from data.settings import Settings
from postprocessing.Song.BaseSong import BaseSong, ExtensionNotSupportedException
from postprocessing.analyzer import Analyzer
from mutagen import MutagenError

class Analyze:
    def __init__(self):
        self.settings = Settings()
        try:
            self.analyzer = Analyzer()
        except Exception as e:
            logging.warning(f"Analyzer unavailable: {e}")
            class _DummyAnalyzer:
                def start(self):
                    pass
                def submit(self, *args, **kwargs):
                    pass
                def done(self):
                    pass
            self.analyzer = _DummyAnalyzer()
        self.extensions = {
            "mp3": True,
            "flac": True,
            "wav": False,
            "m4a": True,
            "aac": False,
        }

    def run(self):
        logging.info("Starting Analyze Step")
        self.analyzer.start()
        base = Path(self.settings.music_folder_path)
        if base.exists():
            self._parse_folder(base)
        self.analyzer.done()

    def _parse_folder(self, folder: Path):
        if "@eaDir" in str(folder):
            return
        try:
            files = []
            for ext, enabled in self.extensions.items():
                if enabled:
                    files.extend(folder.glob(f"*.{ext}"))
            for file in files:
                self._analyze_file(file)
            for sub in [f for f in folder.iterdir() if f.is_dir() and not f.name.startswith("_")]:
                self._parse_folder(sub)
        except Exception as e:
            logging.error(f"Error analyzing folder {folder}: {e}", exc_info=True)

    def _analyze_file(self, file: Path):
        try:
            song = BaseSong(str(file))
            for artist in song.artists():
                for genre in song.genres():
                    self.analyzer.submit(artist, genre)
        except (PermissionError, MutagenError, FileNotFoundError, ExtensionNotSupportedException) as e:
            logging.warning(f"{type(e).__name__}: {e} -> {file}")
        except Exception as e:
            logging.error(f"Analyze failed: {e} -> {file}", exc_info=True)
