import glob
import os
import sys

from mutagen.easyid3 import EasyID3
from mutagen.easymp4 import EasyMP4Tags

from data.settings import Settings
from postprocessing.Song.GenericSong import GenericBaseSong
from postprocessing.Song.LabelSong import LabelBaseSong
from postprocessing.Song.SoundcloudSong import SoundcloudBaseSong
from postprocessing.Song.YoutubeSong import YoutubeBaseSong
from postprocessing.constants import SongTypeEnum

# global vars
EasyID3.RegisterTextKey('publisher_old', 'TPUB')
EasyID3.RegisterTXXXKey('publisher', 'publisher')
EasyID3.RegisterTXXXKey('parsed', 'parsed')
EasyMP4Tags.RegisterTextKey("publisher", "publisher")
EasyMP4Tags.RegisterTextKey("parsed", "parsed")

print_new_line = False

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
            generic_music_folders = [f for f in os.listdir(s.music_folder_path + s.delimiter + "Livesets") if
                                     not os.path.isfile(
                                         os.path.join(s.music_folder_path + s.delimiter + "Livesets", f))]
            for generic_music_folder in generic_music_folders:
                self.parse_folder(
                    s.music_folder_path + s.delimiter + "Livesets" + s.delimiter + generic_music_folder,
                    SongTypeEnum.GENERIC)
            generic_music_folders = [f for f in os.listdir(s.music_folder_path + s.delimiter + "Podcasts") if
                                     not os.path.isfile(
                                         os.path.join(s.music_folder_path + s.delimiter + "Podcasts", f))]
            for generic_music_folder in generic_music_folders:
                self.parse_folder(
                    s.music_folder_path + s.delimiter + "Podcasts" + s.delimiter + generic_music_folder,
                    SongTypeEnum.GENERIC)
            generic_music_folders = [f for f in os.listdir(s.music_folder_path + s.delimiter + "Top 100") if
                                     not os.path.isfile(os.path.join(s.music_folder_path + s.delimiter + "Top 100", f))]
            for generic_music_folder in generic_music_folders:
                self.parse_folder(
                    s.music_folder_path + s.delimiter + "Top 100" + s.delimiter + generic_music_folder,
                    SongTypeEnum.GENERIC)
            generic_music_folders = [f for f in os.listdir(s.music_folder_path + s.delimiter + "Warm Up Mixes") if
                                     not os.path.isfile(
                                         os.path.join(s.music_folder_path + s.delimiter + "Warm Up Mixes", f))]
            for generic_music_folder in generic_music_folders:
                self.parse_folder(
                    s.music_folder_path + s.delimiter + "Warm Up Mixes" + s.delimiter + generic_music_folder,
                    SongTypeEnum.GENERIC)

    def parse_folder(self, folder, song_type):
        print("\r", folder, end="")
        global print_new_line
        print_new_line = True
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
            except SystemExit:
                sys.exit(2)
            except Exception as e:
                print('Failed to parse song ' + file + ' ' + str(e))
        for sub_folder in folders:
            # Testcode for finding and fixing multi-level deep folders
            # a = folder + s.delimiter + sub_folder
            # if len(a.split("\\")) > 7:
            #     fs = glob.glob(a.rsplit("\\", 1)[0] + s.delimiter + "*.mp3") + glob.glob(
            #         a.rsplit("\\", 1)[0] + s.delimiter + "*.wav") + glob.glob(
            #         a.rsplit("\\", 1)[0] + s.delimiter + "*.flac") + glob.glob(
            #         a.rsplit("\\", 1)[0] + s.delimiter + "*.m4a")
            #     if len(fs) != 0:
            #         shutil.rmtree(a)
            #         print("deleting", a, "# files", len(fs))
            #     else:
            #         fs2 = glob.glob(a + s.delimiter + "*.*")
            #         if len(fs2) != 0:
            #             print("moving ", a, "to", a.rsplit("\\", 1)[0])
            #             for fs22 in fs2:
            #                 shutil.move(fs22, str(a.rsplit("\\", 1)[0]))
            #             shutil.rmtree(a)
            #         else:
            #             print("MISSING", a)
            if sub_folder[0] != '_':
                try:
                    self.parse_folder(folder + s.delimiter + sub_folder, song_type)
                except KeyboardInterrupt:
                    print('KeyboardInterrupt')
                    sys.exit(1)
                except SystemExit:
                    sys.exit(2)
                except Exception as e:
                    print('Failed to parse folder ' + sub_folder + ' ' + str(e))

    @staticmethod
    def parse_song(path, song_type):
        print("\r", path, end="")

        if song_type == SongTypeEnum.LABEL:
            song = LabelBaseSong(path)
        if song_type == SongTypeEnum.YOUTUBE:
            song = YoutubeBaseSong(path)
        if song_type == SongTypeEnum.SOUNDCLOUD:
            song = SoundcloudBaseSong(path)
        if song_type == SongTypeEnum.GENERIC:
            song = GenericBaseSong(path)
