import re

from mutagen.mp3 import MP3
from mutagen.easyid3 import EasyID3
import glob

from data.settings import Settings


class Song:
    def __init__(self, mp3file):
        # self.genre = re.split(';|,/', str(mp3file.get("GENRE")))
        self.artist = re.split(';|,/', str(mp3file.get("ARTIST")))
        self.genre = mp3file.get("GENRE")

    def print(self):
        print("genre ", self.genre)
        print("artist ", self.artist)


class Tagger:
    def __init__(self):
        self.settings = Settings()

    def tag(self):
        print("tagging")
        files = glob.glob(self.settings.music_folder_path+"\Art of creation\*\*.mp3")
        for song in files:

            # turn it into an mp3 object using the mutagen library
            parsed_song = Song(MP3(song, ID3=EasyID3))
            parsed_song.print()
