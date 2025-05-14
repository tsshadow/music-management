import logging
import os
from pathlib import Path
import shutil
from concurrent.futures import ThreadPoolExecutor

from data.settings import Settings


class EpsFlattener:
    def __init__(self, dry_run: bool = True):
        self.settings = Settings()
        self.eps_root = Path(self.settings.eps_folder_path)
        self.dry_run = dry_run

    def flatten_folder(self, dirpath: str, dirname: str):
        subdir = Path(dirpath) / dirname
        parent = Path(dirpath)

        try:
            if subdir.is_dir():
                files_moved = 0
                files_skipped = 0

                for file in subdir.iterdir():
                    destination = parent / file.name
                    if not destination.exists():
                        logging.info(f"[{'DRY' if self.dry_run else 'MOVE'}] {file} → {destination}")
                        if not self.dry_run:
                            shutil.move(str(file), str(destination))
                        files_moved += 1
                    else:
                        logging.warning(f"File already exists: {file} → {destination}, skipping")
                        files_skipped += 1

                # Check if subdir has the same name as parent
                if subdir.name == parent.name:
                    logging.info(f"[{'DRY' if self.dry_run else 'RMTREE'}] Force removing folder: {subdir}")
                    if not self.dry_run:
                        shutil.rmtree(subdir)
                else:
                    remaining_files = list(subdir.iterdir())
                    if not remaining_files:
                        logging.info(f"[{'DRY' if self.dry_run else 'REMOVE'}] Empty folder: {subdir}")
                        if not self.dry_run:
                            subdir.rmdir()
                    else:
                        logging.info(f"Not empty, not removed: {subdir} ({len(remaining_files)} remaining)")

        except Exception as e:
            logging.error(f"Error while processing {subdir}: {e}")

    def run(self):
        logging.info("Starting EPS flattener..." + (" (dry run)" if self.dry_run else ""))
        work = []

        for dirpath, dirnames, filenames in os.walk(self.eps_root):
            # Ignore Synology thumbnail folders
            dirnames[:] = [d for d in dirnames if d.lower() != "@eadir"]
            if len(dirnames) == 1:
                work.append((dirpath, dirnames[0]))

        if not work:
            logging.info("No nested folders found to flatten.")
            return

        with ThreadPoolExecutor(max_workers=1) as executor:
            executor.map(lambda args: self.flatten_folder(*args), work)

        logging.info("Finished flattening EPS directory.")
