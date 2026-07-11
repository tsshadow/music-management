import logging
from services.tagger.Song.BaseSong import BaseSong

class ReadonlySong(BaseSong):
    """
    A readonly version of BaseSong that prevents any changes from being saved to the file.
    Used for scanning metadata into the database without modifying the files.
    """

    def __init__(self, path, extra_info=None):
        super().__init__(path, extra_info)
        self.rules = []

    def save_file(self):
        """Override save_file to do nothing."""
        pass

    def __del__(self):
        """Override __del__ to prevent saving."""
        pass