from services.common.config_store import ConfigStore as Settings
from services.tagger.constants import ALBUM, ALBUM_ARTIST, ARTIST, CATALOG_NUMBER, COPYRIGHT, PUBLISHER
from services.tagger.Song import rule_stack
from services.tagger.Song.BaseSong import BaseSong

s = Settings()


class YoutubeSong(BaseSong):
    """A track downloaded from a YouTube channel.

    Runs the same rule stack as SoundcloudSong. What used to sit here instead was
    a single hand-written title split guarded on the artist tag still being equal
    to the channel folder; the moment yt-dlp supplied an artist of its own -- which
    it does whenever YouTube shows a music-credit panel -- the guard stopped
    matching and the artists were left sitting in the title.

    What stays YouTube-specific is the album (`Youtube (<channel>)`), the
    publisher, the festival inference, and the channel-to-genre lookup: for a
    channel that is really a label, the channel name is the only genre signal
    there is.
    """

    def __init__(self, path, extra_info=None):
        super().__init__(path, extra_info)
        self._catalog_number = None
        paths = path.rsplit(s.delimiter, 2)
        self._album_artist_from_path = str(paths[1])
        self._publisher = 'Youtube'
        channel = None
        if extra_info:
            channel = (
                extra_info.get('uploader')
                or extra_info.get('channel')
                or extra_info.get('uploader_id')
                or extra_info.get('channel_id')
            )
        self._channel_for_album = channel or self._album_artist_from_path
        self._album = f'{self._publisher} ({self._channel_for_album})'

    def parse(self):
        if not self.album_artist():
            self.tag_collection.set_item(ALBUM_ARTIST, self._album_artist_from_path)
        if not self.artist():
            self.tag_collection.set_item(ARTIST, self._channel_for_album)
        if not self.album():
            self.tag_collection.set_item(ALBUM, self._album)
        if not self.copyright() and self.calculate_copyright():
            self.tag_collection.set_item(COPYRIGHT, self.calculate_copyright())
        self.tag_collection.set_item(PUBLISHER, self._publisher)
        if self._catalog_number:
            self.tag_collection.set_item(CATALOG_NUMBER, self._catalog_number)
        # Built once per tagging round, not per file; see rule_stack.
        self.rules.extend(rule_stack.rules_for(rule_stack.YOUTUBE))
        super().parse()

    def calculate_copyright(self):
        album_artist = self.album_artist()
        date = self.date()
        year = str(date)[0:4]
        if album_artist:
            if date:
                return album_artist + ' (' + year + ')'
            return self.publisher()
        return None

    def load_folders(self, file_path):
        try:
            with open(file_path, encoding='utf-8') as file:
                return {line.strip() for line in file if line.strip()}
        except FileNotFoundError:
            return set()
