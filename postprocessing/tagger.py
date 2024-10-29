import glob
import os
import sys

from mutagen import MutagenError
from mutagen.easyid3 import EasyID3
from mutagen.easymp4 import EasyMP4Tags

from data.settings import Settings
from postprocessing.Song.BaseSong import ExtensionNotSupportedException
from postprocessing.Song.GenericSong import GenericSong
from postprocessing.Song.LabelSong import LabelSong
from postprocessing.Song.SoundcloudSong import SoundcloudSong
from postprocessing.Song.YoutubeSong import YoutubeSong
from postprocessing.constants import SongTypeEnum

# global vars
EasyID3.RegisterTextKey('publisher_old', 'TPUB')
EasyID3.RegisterTXXXKey('publisher', 'publisher')
EasyID3.RegisterTXXXKey('parsed', 'parsed')
EasyMP4Tags.RegisterTextKey("publisher", "publisher")
EasyMP4Tags.RegisterTextKey("parsed", "parsed")

s = Settings()


class Tagger:
    def __init__(self):
        self.rescan = None

    def tag(self):
        parse_labels = True
        parse_youtube = True
        parse_soundcloud = True
        parse_generic = True
        if parse_labels:
            label_folders = [f for f in os.listdir(s.eps_folder_path) if
                             not os.path.isfile(os.path.join(s.eps_folder_path, f))]
            label_folders.sort()
            for label in label_folders:
                # Skip free/none and todofolder
                if label[0] != "_":
                    self.parse_folder(s.eps_folder_path + s.delimiter + label, SongTypeEnum.LABEL)

        if parse_soundcloud:
            soundcloud_folder = s.music_folder_path + s.delimiter + "Soundcloud"
            soundcloud_channel_folders = [f for f in os.listdir(soundcloud_folder) if
                                          not os.path.isfile(os.path.join(soundcloud_folder, f))]
            soundcloud_channel_folders.sort()
            for soundcloud_channel_folder in soundcloud_channel_folders:
                self.parse_folder(
                    s.music_folder_path + s.delimiter + "Soundcloud" + s.delimiter + soundcloud_channel_folder,
                    SongTypeEnum.SOUNDCLOUD)

        if parse_youtube:
            youtube_folder = s.music_folder_path + s.delimiter + "Youtube"
            youtube_channel_folders = [f for f in os.listdir(youtube_folder) if
                                       not os.path.isfile(os.path.join(youtube_folder, f))]
            youtube_channel_folders.sort()
            for youtube_channel_folder in youtube_channel_folders:
                self.parse_folder(
                    s.music_folder_path + s.delimiter + "Youtube" + s.delimiter + youtube_channel_folder,
                    SongTypeEnum.YOUTUBE)

        if parse_generic:
            folders = ["Livesets", "Podcasts", "Top 100", "Warm Up Mixes"]
            for folder in folders:
                generic_music_folders = [f for f in os.listdir(s.music_folder_path + s.delimiter + folder) if
                                         not os.path.isfile(
                                             os.path.join(s.music_folder_path + s.delimiter + folder, f))]
                for generic_music_folder in generic_music_folders:
                    self.parse_folder(
                        s.music_folder_path + s.delimiter + folder + s.delimiter + generic_music_folder,
                        SongTypeEnum.GENERIC)

    def parse_folder(self, folder, song_type):
        print("\r", folder, end="")
        folders = [f for f in os.listdir(folder) if
                   not os.path.isfile(os.path.join(folder, f))]
        files = glob.glob(
            folder + s.delimiter + "*.mp3") + glob.glob(
            folder + s.delimiter + "*.wav") + glob.glob(
            folder + s.delimiter + "*.flac") + glob.glob(
            folder + s.delimiter + "*.m4a")
        for file in files:
            try:
                self.parse_song(file, song_type)
            except KeyboardInterrupt:
                print('KeyboardInterrupt')
                sys.exit(1)
            except PermissionError as e:
                print(f"PermissionError: {e}")
                pass
            except MutagenError as e:
                print(f"MutagenError: {e}")
                pass
            except FileNotFoundError as e:
                print(f"FileNotFoundError: {e}")
                pass
            except ExtensionNotSupportedException as e:
                print(f"ExtensionNotSupportedException: {e}")
                pass
            except SystemExit:
                sys.exit(2)
        for sub_folder in folders:
            if sub_folder[0] != '_':
                self.parse_folder(folder + s.delimiter + sub_folder, song_type)

    @staticmethod
    def parse_song(path, song_type):
        print("\r", path, end="")
        if song_type == SongTypeEnum.LABEL:
            LabelSong(path)
        if song_type == SongTypeEnum.YOUTUBE:
            YoutubeSong(path)
        if song_type == SongTypeEnum.SOUNDCLOUD:
            SoundcloudSong(path)
        if song_type == SongTypeEnum.GENERIC:
            GenericSong(path)
