import os
import logging

from data.settings import Settings

s = Settings()

class Sanitizer:
    def __init__(self):
        self.replacements = {
            "/": "-",
            "|": "-",
            ":": "-",
            "／": "-",  # Full-width slash
            " ⧸": "-",  # Toxic sickness slash
        }

    def sanitize(self):
        logging.info("Starting Sanitization Step")
        base_folder = s.music_folder_path
        self.sanitize_folder(base_folder)

    def sanitize_folder(self, folder):
        items = os.listdir(folder)
        files = [f for f in items if os.path.isfile(os.path.join(folder, f))]
        sub_folders = [f for f in items if os.path.isdir(os.path.join(folder, f))]

        # Process files
        for file in files:
            self.sanitize_file(folder, file)

        # Process subfolders recursively
        for sub_folder in sub_folders:
            if '@eaDir' in folder :
                pass
            else:
                self.sanitize_folder(os.path.join(folder, sub_folder))

    def sanitize_file(self, folder, file_name):
        sanitized_name = self.replace_invalid_characters(file_name)
        if file_name != sanitized_name:
            old_path = os.path.join(folder, file_name)
            new_path = os.path.join(folder, sanitized_name)
            try:
                os.rename(old_path, new_path)
                logging.info(f"Renamed: {file_name} -> {sanitized_name}")
            except Exception as e:
                logging.error(f"Error renaming {file_name}: {e}")

    def replace_invalid_characters(self, file_name):
        sanitized = file_name
        for invalid_char, replacement in self.replacements.items():
            logging.debug(f"Original file name: {file_name}")
            sanitized = sanitized.replace(invalid_char, replacement)
            logging.debug(f"Sanitized file name: {sanitized}")
        return sanitized