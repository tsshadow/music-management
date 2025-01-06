import os
from os import listdir
from os.path import join, isfile

import patoolib
from data.settings import Settings


class Extractor:
    def __init__(self):
        self.settings = Settings()

    def extract(self):
        print("Starting Extract Step")
        only_files = [f for f in listdir(self.settings.import_folder_path) if
                      isfile(join(self.settings.import_folder_path, f))]
        print(only_files)
        for file in only_files:
            try:
                file_with_path = self.settings.import_folder_path + self.settings.delimiter + file
                print('extracting ' + file_with_path)
                patoolib.extract_archive(file_with_path, outdir=self.settings.import_folder_path, interactive=False)
                print('removing ' + file_with_path)
                os.remove(file_with_path)
            except Exception as e:
                print(e)
