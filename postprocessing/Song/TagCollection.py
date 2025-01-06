import mutagen
from mutagen.apev2 import APEv2
from mutagen.easyid3 import EasyID3
from mutagen.flac import VCFLACDict
from mutagen.mp4 import MP4Tags
from mutagen.wave import _WaveID3

from postprocessing.Song.Tag import Tag
from postprocessing.constants import MP3Tags, reversed_FLACTags, reversed_MP3Tags, reversed_MP4Tags, reversed_WAVTags, \
    reversed_AACTags

missing_tags_flac = []
missing_aac_tags = []
missing_tags_mp3 = []
missing_tags_wav = []
missing_tags_m4a = []


class TagCollection:
    def __init__(self, tags):
        self.tags: dict[str, Tag] = {}
        if tags is None:
            print('no tags for tagcollection')

        # FLAC
        elif isinstance(tags, VCFLACDict):
            for tag in tags:
                if tag[0] == tag[0].lower():
                    print('error in tag', tag)
                try:
                    self.tags[reversed_FLACTags[tag[0]]] = Tag(reversed_FLACTags[tag[0]], tag[1])
                except KeyError:
                    if tag[0] not in missing_tags_flac:
                        missing_tags_flac.append(tag[0])
        # AAC
        # elif isinstance(tags, APEv2):
        #     for tag in tags:
        #         try:
        #             self.tags[reversed_AACTags[tag]] = Tag(reversed_AACTags[tag], tags[tag])
        #         except KeyError:
        #             if tag not in missing_aac_tags:
        #                 missing_aac_tags.append(tag)
        #                 print(missing_aac_tags)

        # MP3
        elif isinstance(tags, EasyID3):
            for tag in tags:
                try:
                    self.tags[reversed_MP3Tags[tag]] = Tag(reversed_MP3Tags[tag], tags[tag])
                except KeyError:
                    if tag not in missing_tags_mp3:
                        missing_tags_mp3.append(tag)

        # WAV
        elif isinstance(tags, _WaveID3):
            for tag in tags:
                try:
                    self.tags[reversed_WAVTags[tag]] = Tag(reversed_WAVTags[tag], tags[tag])
                except KeyError:
                    if tag not in missing_tags_wav:
                        missing_tags_wav.append(missing_tags_wav)

        # M4A
        elif isinstance(tags, MP4Tags):
            for tag in tags:
                try:
                    self.tags[reversed_MP4Tags[tag]] = Tag(reversed_MP4Tags[tag], tags[tag])
                except KeyError:
                    if tag not in missing_tags_m4a:
                        missing_tags_m4a.append(tag)

        else:
            print("TagCollection not supporting this file extension")
            print(type(tags))
            exit(1)

    def add(self, mp3tag, value):
        if value is not None:
            if self.tags.get(mp3tag):
                self.tags[mp3tag].set(value)
            else:
                self.tags[mp3tag] = Tag(mp3tag, "")
                self.tags[mp3tag].set(value)
        else:
            print("Error adding tag(" + mp3tag + "), value is none")

    def print(self):
        for tag in self.tags.values():
            tag.print()

    def has_item(self, tag):
        return tag in self.tags

    def get_item(self, tag):
        return self.tags[tag]

    def set_item(self, tag, value):
        tag = self.get_item(tag)
        tag.set(value)

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
