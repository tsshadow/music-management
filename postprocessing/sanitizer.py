from pathlib import Path
import logging

from data.settings import Settings

s = Settings()

class Sanitizer:
    """
    Handles the sanitization of filenames and folder names in the music directory.
    Replaces invalid characters with safe alternatives recursively.
    """

    def __init__(self):
        self.replacements = {
            "/": "-",
            "|": "-",
            ":": "-",
            "／": "-",   # Full-width slash
            " ⧸": "-",   # Unusual Unicode slash
        }

    def sanitize(self):
        """
        Starts the recursive sanitization process from the root music folder.
        """
        logging.info("Starting Sanitization Step")
        base_folder = Path(s.music_folder_path)
        if base_folder.exists():
            self.sanitize_folder(base_folder)

    def sanitize_folder(self, folder: Path):
        """
        Recursively sanitizes file and folder names in a given directory.

        @param folder: Path object of the folder to sanitize
        """
        if "@eaDir" in str(folder):
            return

        try:
            for item in folder.iterdir():
                if item.is_file():
                    self.sanitize_file(item)
                elif item.is_dir():
                    self.sanitize_folder(item)
        except FileNotFoundError as e:
            logging.warning(f"Folder not found: {folder} — {e}")
        except PermissionError as e:
            logging.warning(f"Permission denied: {folder} — {e}")

    def sanitize_file(self, file_path: Path):
        """
        Renames a file if it contains invalid characters.

        @param file_path: Path object pointing to the file
        """
        sanitized_name = self.replace_invalid_characters(file_path.name)

        if file_path.name != sanitized_name:
            new_path = file_path.with_name(sanitized_name)
            try:
                file_path.rename(new_path)
                logging.info(f"Renamed: {file_path.name} -> {sanitized_name}")
            except Exception as e:
                logging.error(f"Error renaming {file_path.name}: {e}")

    def replace_invalid_characters(self, name: str) -> str:
        """
        Replaces all defined invalid characters in a filename.

        @param name: The original file or folder name
        @return: A sanitized version of the name
        """
        sanitized = name
        for invalid_char, replacement in self.replacements.items():
            if invalid_char in sanitized:
                logging.debug(f"Replacing '{invalid_char}' in: {sanitized}")
            sanitized = sanitized.replace(invalid_char, replacement)
        return sanitized
