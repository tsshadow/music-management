import re

from postprocessing.constants import ARTIST_REGEX


class ArtistHelper:
    artist_cache = None

    @staticmethod
    def load_artist_cache(file_path='./data/artists.txt'):
        if ArtistHelper.artist_cache is None:
            ArtistHelper.artist_cache = {}
            with open(file_path, 'r') as f:
                for line in f:
                    artist = line.strip()
                    ArtistHelper.artist_cache[artist.lower()] = artist  # Store lowercase for case-insensitive lookup

    @staticmethod
    def recapitalize(name):
        ArtistHelper.load_artist_cache()
        return ArtistHelper.artist_cache.get(name.lower(), name)


class Tag:
    def __init__(self, tag, value):
        self.tag: str = tag
        if isinstance(value, str):
            self.value = value.split(";")
        elif isinstance(value, list):
            self.value = list(value)
        self.changed = False

    def to_array(self):
        return self.value

    def to_string(self):
        return ";".join(self.value)

    def sort(self):
        old_value = self.value[:]
        self.value.sort()
        if old_value != self.value:
            print("changed sort")
            self.changed = True

    def deduplicate(self):
        old_value = self.value[:]
        self.value = list(dict.fromkeys(self.value))
        if old_value != self.value:
            print("changed deduplicate")
            self.changed = True

    def add(self, item):
        if item not in self.value:
            self.value.append(item)
            print("changed add")
            self.changed = True

    def remove(self, val):
        if val in self.value:
            self.value.remove(val)
            print("changed remove")
            self.changed = True

    def recapitalize(self):
        old_value = self.value[:]
        self.value = [element.title() for element in self.value]
        if old_value != self.value:
            print("changed recapitalize")
            self.changed = True

    def regex(self):
        old_value = self.value[:]
        self.value = [re.sub(ARTIST_REGEX, ";", elem) for elem in self.value]
        if old_value != self.value:
            self.changed = True
            print("changed regex")

    def has_changes(self):
        return self.changed

    # def has_capitalization_error(self):
    # return self.has_changes() and (";".join(self.initial_value).lower() == ";".join(self.value).lower())

    def print(self):
        print(self.tag, self.to_string())
        pass

    def special_recapitalize(self):
        old_value = self.value[:]
        self.value = [ArtistHelper.recapitalize(name) for name in self.value]
        if old_value != self.value:
            self.changed = True
            print("changed special_recapitalize")
