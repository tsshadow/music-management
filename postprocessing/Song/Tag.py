import re

from postprocessing.Song.Helpers.ArtistHelper import ArtistHelper
from postprocessing.constants import ARTIST_REGEX

import logging

class Tag:
    """
    Represents a single audio metadata tag that may contain multiple values.

    Attributes:
        tag (str): The tag name (e.g., "artist", "genre").
        value (list[str]): The list of tag values.
        changed (bool): Whether the tag has been modified since initialization.
    """

    def __init__(self, tag, value):
        """
        Initializes a Tag with a tag name and a string or list of values.

        Args:
            tag (str): The tag name.
            value (str or list[str]): The tag value(s).
        """
        self.tag: str = tag
        if isinstance(value, str):
            self.value = value.split(";")
        elif isinstance(value, list):
            self.value = list(value)
            try:
                self.resplit()
            except (AttributeError, TypeError):
                logging.info("Error during resplit")
        self.changed = False


    def __str__(self):
        """
        Returns a string representation of the tag.

        Returns:
            str: Tag name and joined value string.
        """
        return f"{self.tag}: {self.to_string()}"

    def __eq__(self, other):
        """
        Compares two tags by name and value.

        Args:
            other (Tag): Another tag.

        Returns:
            bool: True if both tags have the same name and values.
        """
        return isinstance(other, Tag) and self.tag == other.tag and self.value == other.value

    def __len__(self):
        """
        Returns the number of values in this tag.

        Returns:
            int: Value count.
        """
        return len(self.value)

    def __iter__(self):
        """
        Iterates through the tag's values.

        Yields:
            str: Each tag value.
        """
        return iter(self.value)

    def resplit(self):
        """
        Further splits values by ';' and '/' delimiters.
        """
        self.value = [item for sublist in self.value for item in sublist.split(';')]
        self.value = [item for sublist in self.value for item in sublist.split('/')]

    def to_array(self):
        """
        Returns the tag values as a list.

        Returns:
            list[str]: The list of values.
        """
        return self.value

    def to_string(self):
        """
        Returns the tag values as a single string.

        Returns:
            str: The values joined by ';'.
        """
        return ";".join(self.value)

    def sort(self):
        """
        Sorts the tag values alphabetically and marks as changed if modified.
        """
        old_value = self.value[:]
        self.value.sort()
        if old_value != self.value:
            logging.info(f"{self.tag} changed(sort) from {old_value} to {self.value}")
            self.changed = True

    def deduplicate(self):
        """
        Removes duplicate entries and marks as changed if modified.
        """
        old_value = self.value[:]
        self.value = list(dict.fromkeys(self.value))
        if old_value != self.value:
            logging.info(f"{self.tag} changed(deduplicate) from {old_value} to {self.value}")
            self.changed = True

    def add(self, item):
        """
        Adds a new value if not already present.

        Args:
            item (str): The value to add.
        """
        if item not in self.value:
            old_value = self.value[:]
            self.value.append(item)
            logging.info(f"{self.tag} changed(add) from {old_value} to {self.value}")
            self.changed = True

    def remove(self, val):
        """
        Removes a value if it exists.

        Args:
            val (str): The value to remove.
        """
        old_value = self.value[:]
        if val in self.value:
            self.value.remove(val)
            logging.info(f"{self.tag} changed(remove) from {old_value} to {self.value}")
            self.changed = True

    def recapitalize(self):
        """
        Title-cases all values (e.g., "my artist" -> "My Artist").
        """
        old_value = self.value[:]
        self.value = [element.title() for element in self.value]
        if old_value != self.value:
            logging.info(f"{self.tag} changed(recapitalize) from {old_value} to {self.value}")
            self.changed = True

    def strip(self):
        """
        Removes leading/trailing spaces from all values.
        """
        old_value = self.value[:]
        self.value = [element.strip() for element in self.value]
        if old_value != self.value:
            logging.info(f"{self.tag} changed(strip) from {old_value} to {self.value}")
            self.changed = True

    def regex(self):
        """
        Applies a regex split on each value using `ARTIST_REGEX` and resplits.
        """
        old_value = self.value[:]
        self.value = [re.sub(ARTIST_REGEX, ";", elem) for elem in self.value]
        if old_value != self.value:
            self.resplit()
            logging.info(f"{self.tag} changed(regex) from {old_value} to {self.value}")
            self.changed = True

    def special_recapitalize(self):
        """
        Recapitalizes names using database matches (via ArtistHelper).
        """
        old_value = self.value[:]
        self.value = [ArtistHelper.recapitalize(name) for name in self.value]
        if old_value != self.value:
            logging.info(f"{self.tag} changed(special_recapitalize) from {old_value} to {self.value}")
            self.changed = True

    def set(self, value):
        """
        Sets a new value list, splitting strings on semicolons.

        Args:
            value (str or list[str]): The new tag value(s).
        """
        old_value = self.value[:]
        if isinstance(value, str):
            self.value = value.split(";")
        elif isinstance(value, list):
            self.value = list(value)
            try:
                self.resplit()
            except (AttributeError, TypeError):
                logging.info("Error during set->resplit")
        if old_value != self.value:
            logging.info(f"{self.tag} changed(set) from {old_value} to {self.value}")
            self.changed = True

    def has_changes(self):
        """
        Returns whether the tag was modified since initialization.

        Returns:
            bool: True if modified.
        """
        return self.changed

    def log(self):
        """
        Logs the tag and its current value.
        """
        logging.info("%s %s", self.tag, self.to_string())

    def copy(self):
        """
        Returns a copy of this Tag object.

        Returns:
            Tag: A new Tag instance with the same data.
        """
        return Tag(self.tag, self.value[:])

