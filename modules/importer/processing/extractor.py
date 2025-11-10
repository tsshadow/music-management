import logging
import os
from os import listdir
from os.path import join, isfile
import patoolib
from data.settings import Settings


class Extractor:
    def __init__(self):
        self.settings = Settings()

    def run(self):
        logging.info("Starting Extract Step")

        try:
            # List all files in the import folder
            only_files = [f for f in listdir(self.settings.import_folder_path) if
                          isfile(join(self.settings.import_folder_path, f))]
            logging.info(f"Found {len(only_files)} files: {only_files}")
        except Exception as e:
            logging.error(f"Failed to list files: {e}")
            return

        for idx, file in enumerate(only_files, start=1):
            try:
                file_with_path = join(self.settings.import_folder_path, file)
                logging.info(f"[{idx}/{len(only_files)}] Extracting: {file_with_path}")
                patoolib.extract_archive(file_with_path, outdir=self.settings.import_folder_path, interactive=False)

                logging.info(f"[{idx}/{len(only_files)}] Removing: {file_with_path}")
                os.remove(file_with_path)
            except patoolib.util.PatoolError as e:
                logging.error(f"Extraction failed for {file_with_path}: {e}")
            except OSError as e:
                logging.error(f"Failed to delete {file_with_path}: {e}")
            except Exception as e:
                logging.error(f"Unexpected error with {file_with_path}: {e}")

        logging.info("Extraction step completed.")
