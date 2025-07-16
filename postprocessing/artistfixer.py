import logging
from pathlib import Path

from mutagen import MutagenError

from data.settings import Settings
from postprocessing.Song.BaseSong import BaseSong, ExtensionNotSupportedException
from postprocessing.Song.Helpers.Cache import databaseHelpers
from postprocessing.Song.rules.VerifyArtistRule import VerifyArtistRule
from postprocessing.Song.rules.TagResult import TagResultType


class ArtistFixer:
    """Iterate over all songs and fix the ARTIST tag using VerifyArtistRule."""

    def __init__(self):
        self.settings = Settings()
        self.artist_db = databaseHelpers["artists"]
        self.rule = VerifyArtistRule(self.artist_db)
        self.extensions = {
            "mp3": True,
            "flac": True,
            "wav": False,
            "m4a": True,
            "aac": False,
        }

    def run(self):
        logging.info("Starting Artist Fixer Step")
        root = Path(self.settings.music_folder_path)
        if root.exists():
            self._parse_folder(root)

    def _parse_folder(self, folder: Path):
        if "@eaDir" in str(folder):
            return
        try:
            files: list[Path] = []
            for ext, enabled in self.extensions.items():
                if enabled:
                    files.extend(folder.glob(f"*.{ext}"))
            for file in files:
                self._fix_file(file)
            for sub in [f for f in folder.iterdir() if f.is_dir() and not f.name.startswith("_")]:
                self._parse_folder(sub)
        except Exception as e:
            logging.error(f"Error processing folder {folder}: {e}", exc_info=True)

    def _fix_file(self, path: Path):
        try:
            song = BaseSong(str(path))
            original = song.artist()
            was_known = self.artist_db.exists(original) if original else True
            result = self.rule.apply(song)
            song.save_file()

            if result.result_type == TagResultType.VALID and not was_known:
                print(f"✅ added '{original}' to artists table")
            elif result.result_type == TagResultType.UPDATED:
                print(f"✏️ updated '{original}' -> '{result.value}'")
            elif result.result_type == TagResultType.IGNORED:
                print(f"🗑️ removed invalid artist '{original}'")
        except (PermissionError, MutagenError, FileNotFoundError, ExtensionNotSupportedException) as e:
            logging.warning(f"{type(e).__name__}: {e} -> {path}")
        except Exception as e:
            logging.error(f"Artist fix failed: {e} -> {path}", exc_info=True)
