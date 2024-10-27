from mutagen.easyid3 import EasyID3
from mutagen.flac import VCFLACDict
from mutagen.mp4 import MP4Tags
from mutagen.wave import _WaveID3

from postprocessing.Song.Tag import Tag


# {'TALB': TALB(encoding= < Encoding.UTF16: 1 >, text = ['Rescue Me (Back To The Roots Edit)']), 'TPE1': TPE1(
#     encoding= < Encoding.UTF16: 1 >, text = ['Headhunterz', 'Sound Rush', 'Eurielle']), 'TCON': TCON(
#     encoding= < Encoding.UTF16: 1 >, text = ['Hardstyle\ufeff;Mainstream Hardstyle']), 'TIT2': TIT2(
#     encoding= < Encoding.UTF16: 1 >, text = ['Rescue Me (Back To The Roots Edit) (Extended Mix)']), 'TDRC': TDRC(
#     encoding= < Encoding.LATIN1: 0 >, text = ['2021'])}

class TagCollection:
    def __init__(self, tags):
        self.tags: dict[str, Tag] = {}

        # FLAC
        if isinstance(tags, VCFLACDict):
            for tag in tags:
                self.tags[tag] = Tag(tag[0], tag[1])
        # MP3
        elif isinstance(tags, EasyID3):
            for tag in tags:
                self.tags[tag] = Tag(tag, tags[tag])
        # Wav
        elif isinstance(tags, _WaveID3):
            for tag in tags:
                self.tags[tag] = Tag(tag, tags[tag])
        elif isinstance(tags, MP4Tags):
            for tag in tags:
                self.tags[tag] = Tag(tag, tags[tag])
        else:
            print("TagCollection not supporting this file extension")
            print(type(tags))

    def add(self, mp3tag, value):
        if value is not None:
            self.tags[mp3tag] = Tag(mp3tag, value)
        else:
            print("Error adding tag(" + mp3tag + "), value is none")

    def print(self):
        for tag in self.tags.values():
            tag.print()

    def has_item(self, tag):
        return tag in self.tags

    def get_item(self, tag):
        return self.tags[tag]

    def get_item_as_string(self, tag):
        try:
            return self.tags[tag].to_string()
        except:
            return ""

    def get_item_as_array(self, tag):
        try:
            return self.tags[tag].to_array()
        except:
            return []

    def get(self):
        return self.tags
