from services.tagger.Song.BaseSong import BaseSong


class ReadonlySong(BaseSong):
    """
    A readonly version of BaseSong that prevents any changes from being saved to the file.
    Used for scanning metadata into the database without modifying the files.
    """

    # Read by BaseSong.__init__: it is what keeps loading a file from deleting an
    # unparseable m4a or rewriting a FLAC's tag keys. Overriding save_file() alone is not
    # enough -- both of those happen before __init__ returns, through os.remove and
    # mutagen's own save().
    readonly = True

    def __init__(self, path, extra_info=None):
        super().__init__(path, extra_info)
        self.rules = []

    def save_file(self):
        """Override save_file to do nothing."""

    def __del__(self):
        """Override __del__ to prevent saving."""
