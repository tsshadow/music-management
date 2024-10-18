import re

from postprocessing.constants import ARTIST_REGEX


class Tag:
    def __init__(self, tag, value):
        self.tag: str = tag
        if isinstance(value, str):
            self.value = value.split(";")
        if isinstance(value, list):
            self.value = []
            for item in value:
                self.value.append(item)
        self.initial_value = value

    def to_array(self):
        return self.value

    def to_string(self):
        return ";".join(self.value)

    def sort(self):
        self.value.sort()

    def deduplicate(self):
        self.value = list(set(self.value))

    def add(self, item):
        if item not in self.value:
            self.value.append(item)

    def remove(self, val):
        try:
            self.value.remove(val)
        except:
            pass

    def recapitalize(self):
        self.value = [element.title() for element in self.value]

    def regex(self):
        self.value = [re.sub(ARTIST_REGEX, ";", elem) for elem in self.value]

    def has_changes(self):
        return self.initial_value != self.value

    def has_capitalization_error(self):
        return self.has_changes() and (";".join(self.initial_value).lower() == ";".join(self.value).lower())

    def print(self):
        print(self.tag, self.to_string())
        pass
