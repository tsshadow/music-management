import os
import subprocess
import time
import logging
from data.settings import Settings

s = Settings()

class Converter:
    def __init__(self, max_age_hours: int = 24):
        """
        Initializes the Converter using the music folder from settings.

        Args:
            max_age_hours (int): Max age (in hours) to keep temp files.
        """
        self.folder = s.music_folder_path
        self.max_age_hours = max_age_hours

    def run(self):
        """
        Runs both conversion and cleanup steps.
        """
        logging.info("Starting Conversion Step")
        self.scan_folder(self.folder)

    def scan_folder(self, folder):
        items = os.listdir(folder)
        files = [f for f in items if os.path.isfile(os.path.join(folder, f))]
        sub_folders = [f for f in items if os.path.isdir(os.path.join(folder, f))]

        for file in files:
            self.handle_file(folder, file)

        for sub_folder in sub_folders:
            if '@eaDir' not in sub_folder:
                self.scan_folder(os.path.join(folder, sub_folder))

    def handle_file(self, folder, file):
        full_path = os.path.join(folder, file)

        if file.lower().endswith(".aac"):
            self.convert_file(full_path)
        elif file.endswith(".temp.m4a"):
            self.cleanup_temp_file(full_path)

    def convert_file(self, src):
        dst = os.path.splitext(src)[0] + ".m4a"
        if os.path.exists(dst):
            os.remove(src)
            logging.info(f"Deleted {src} since .m4a already exists")
            return

        try:
            logging.info(f"Converting {src} to {dst}")
            subprocess.run(["ffmpeg", "-y", "-i", src, "-c", "copy", dst], check=True)
            if os.path.exists(dst):
                os.remove(src)
                logging.info(f"Deleted original .aac file after conversion: {src}")
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to convert {src} to .m4a: {e}")

    def cleanup_temp_file(self, full_path):
        now = time.time()
        try:
            age = now - os.path.getmtime(full_path)
            if age > self.max_age_hours * 3600:
                os.remove(full_path)
                logging.info(f"Deleted old temp file: {full_path}")
        except Exception as e:
            logging.warning(f"Could not remove temp file {full_path}: {e}")

