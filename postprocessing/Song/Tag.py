import logging
import re

from postprocessing.Song.UniqueTagHandler import custom_title
from postprocessing.constants import ARTIST_REGEX


class ArtistHelper:
    artist_cache = None

    @staticmethod
    def load_artist_cache(file_path='./data/artists.txt'):
        if ArtistHelper.artist_cache is None:
            ArtistHelper.artist_cache = {}
            with open(file_path, 'r', encoding="utf-8") as f:
                for line in f:
                    artist = line.strip()
                    ArtistHelper.artist_cache[artist.lower()] = artist  # Store lowercase for case-insensitive lookup

    @staticmethod
    def recapitalize(name):
        ArtistHelper.load_artist_cache()
        return ArtistHelper.artist_cache.get(name.lower(), name)


# class ArtistHelper2:
#     artist_cache = None
#
#     @staticmethod
#     def load_artist_cache(file_path='./data/artists.txt'):
#         if ArtistHelper.artist_cache is None:
#             ArtistHelper.artist_cache = {}
#             with open(file_path, 'r',  encoding="utf-8") as f:
#                 for line in f:
#                     artist = line.strip()
#                     ArtistHelper.artist_cache[artist.lower()] = artist  # Store lowercase for case-insensitive lookup
#
#     @staticmethod
#     def recapitalize(name):
#         ArtistHelper.load_artist_cache()
#         return ArtistHelper.artist_cache.get(name.lower(), name)

class Tag:
    def __init__(self, tag, value):
        self.tag: str = tag
        if isinstance(value, str):
            self.value = value.split(";")
        elif isinstance(value, list):
            self.value = list(value)
            try:
                self.resplit()
            except AttributeError:
                logging.info("AttributeError")
                pass
            except TypeError:
                logging.info("TypeError")
                pass
        self.changed = False

    def resplit(self):
        self.value = [item for sublist in self.value for item in sublist.split(';')]
        self.value = [item for sublist in self.value for item in sublist.split('/')]

    def to_array(self):
        return self.value

    def to_string(self):
        return ";".join(self.value)

    def sort(self):
        old_value = self.value[:]
        self.value.sort()
        if old_value != self.value:
            logging.info(self.tag, "changed (sort) from %s to %s", old_value, self.value)
            self.changed = True

    def deduplicate(self):
        old_value = self.value[:]
        self.value = list(dict.fromkeys(self.value))
        if old_value != self.value:
            logging.info(self.tag, "changed (deduplicate) from %s to %s", old_value, self.value)
            self.changed = True

    def add(self, item):
        if item not in self.value:
            old_value = self.value[:]
            self.value.append(item)
            logging.info(self.tag, "changed (add) from %s to %s", old_value, self.value)
            self.changed = True

    def remove(self, val):
        old_value = self.value[:]
        if val in self.value:
            self.value.remove(val)
            logging.info(self.tag, "changed (remove) from %s to %s", old_value, self.value)
            self.changed = True

    def recapitalize(self):
        old_value = self.value[:]
        self.value = [element.title() for element in self.value]
        if old_value != self.value:
            logging.info(self.tag, "changed (recapitalize) from %s to %s", old_value, self.value)
            self.changed = True

    def strip(self):
        old_value = self.value[:]
        self.value = [element.strip() for element in self.value]
        if old_value != self.value:
            logging.info(self.tag, "changed (strip) from %s to %s", old_value, self.value)
            self.changed = True

    # def filter(self, input, output):
    #     old_value = self.value[:]
    #     self.value = [element.strip() for element in self.value]
    #     if old_value != self.value:
    #         logging.info("\n",self.tag,"changed (filter) from %s to %s", old_value, self.value)
    #         self.changed = True

    def regex(self):
        old_value = self.value[:]
        self.value = [re.sub(ARTIST_REGEX, ";", elem) for elem in self.value]
        if old_value != self.value:
            self.changed = True
            self.resplit()
            logging.info(self.tag, "changed (regex from %s to %s", old_value, self.value)

    def has_changes(self):
        return self.changed

    # def has_capitalization_error(self):
    # return self.has_changes() and (";".join(self.initial_value).lower() == ";".join(self.value).lower())

    def log(self):
        logging.info("%s %s",self.tag, self.to_string())
        pass

    def special_recapitalize(self):
        old_value = self.value[:]
        self.value = [ArtistHelper.recapitalize(name) for name in self.value]
        if old_value != self.value:
            self.changed = True
            logging.info(self.tag, "changed (special_recapitalize) from %s to %s", old_value, self.value)

    def set(self, value):
        old_value = self.value[:]
        if isinstance(value, str):
            self.value = value.split(";")
        elif isinstance(value, list):
            self.value = list(value)
            try:
                self.resplit()
            except AttributeError:
                logging.info('AttributeError')
                pass
            except TypeError:
                logging.info('TypeError')
                pass
        if old_value != self.value:
            logging.info(self.tag, "changed (set) from %s to %s", old_value, self.value)
            self.changed = True

