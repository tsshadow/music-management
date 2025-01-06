from data.settings import Settings
from postprocessing.Song.BaseSong import BaseSong
from postprocessing.constants import ALBUM_ARTIST, PUBLISHER, CATALOG_NUMBER, GENRE, ARTIST, COPYRIGHT, FormatEnum, \
    TITLE

s = Settings()


class SoundcloudSong(BaseSong):
    def __init__(self, path):
        super().__init__(path)
        paths = path.rsplit(s.delimiter, 2)
        if not self.album_artist():
            self.update_tag(ALBUM_ARTIST, str(paths[1]))
        if not self.copyright():
            self.update_tag(COPYRIGHT, self.calculate_copyright())
        self._publisher = "Soundcloud"
        self.update_song(str(paths[1]))
        self.update_tag(PUBLISHER, self._publisher)
        self.get_genre_from_artist()
        self.get_genre_from_subgenres()
        self.sort_genres()
        self.parse_tags()

    def calculate_copyright(self):
        album_artist = self.album_artist()
        date = self.date()
        year = str(date)[0:4]
        if album_artist:
            if date:
                return album_artist + " (" + year + ")"
            return self.publisher()
        return None

    def update_title(self):
        title = self.title()
        # if title is not None and len(title) > 0:
        #     if title.find(" - ") > 0:
        #         print("\nupdate title", self.artist(),
        #               " new artist:",
        #               title.split(" - ")[0],
        #               " title:",
        #               title.split(" - ")[1])

    def update_song(self, folder):
        ignored_artists = ['Sapher', 'C418', 'T78', 'Basher']
        if folder in ignored_artists:
            return
        if self.artist() == self.album_artist() and self.artist() == folder:
            if self.title().find(" - ") != -1:
                parts = self.title().split(" - ", 1)
                self.tag_collection.add(ARTIST, parts[0])
                self.tag_collection.set_item(TITLE, parts[1])

    def load_folders(self, file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                return {line.strip() for line in file if line.strip()}
        except FileNotFoundError:
            return set()  # Return an empty set if the file doesn't exist
