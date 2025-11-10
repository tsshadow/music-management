import logging

from mutagen.easyid3 import EasyID3
from mutagen.flac import VCFLACDict
from mutagen.mp4 import MP4Tags, MP4FreeForm
from mutagen.wave import _WaveID3

from postprocessing.Song.Tag import Tag
from postprocessing.constants import MP3Tags, reversed_FLACTags, reversed_MP3Tags, reversed_MP4Tags, reversed_WAVTags, \
    reversed_AACTags

missing_tags_flac = []
missing_aac_tags = []
missing_tags_mp3 = []
missing_tags_wav = []
missing_tags_m4a = []

class UnsupportedExtension(Exception):
    """Raised when an unsupported file extension is encountered."""
    def __init__(self, extension: str):
        super().__init__(f"Unsupported file extension: {extension}")
        self.extension = extension


class TagCollection:
    """
    Represents a collection of standardized audio metadata tags,
    extracted from various audio file formats using Mutagen.

    Attributes:
        tags (dict[str, Tag]): Dictionary mapping standard tag keys to Tag objects.
    """

    def __init__(self, tags):
        """
        Initializes a TagCollection from a tag dictionary (format-specific).

        Supports FLAC, MP3, WAV, and M4A formats.

        Args:
            tags (dict): The format-specific tag dictionary.
        """
        self.tags: dict[str, Tag] = {}
        if tags is None:
            logging.info('no tags for tagcollection')

        elif isinstance(tags, VCFLACDict):  # FLAC
            for tag in tags:
                if tag[0] == tag[0].lower():
                    logging.info('error in tag %s', tag)
                try:
                    self.tags[reversed_FLACTags[tag[0]]] = Tag(reversed_FLACTags[tag[0]], tag[1])
                except KeyError:
                    if tag[0] not in missing_tags_flac:
                        missing_tags_flac.append(tag[0])

        elif isinstance(tags, EasyID3):  # MP3
            for tag in tags:
                try:
                    self.tags[reversed_MP3Tags[tag]] = Tag(reversed_MP3Tags[tag], tags[tag])
                except KeyError:
                    if tag not in missing_tags_mp3:
                        missing_tags_mp3.append(tag)

        elif isinstance(tags, _WaveID3):  # WAV
            for tag in tags:
                try:
                    id3_frame = tags[tag]
                    if hasattr(id3_frame, "text"):
                        value = id3_frame.text  # This is usually a list like ["Test Artist"]
                    else:
                        value = id3_frame
                    self.tags[reversed_WAVTags[tag]] = Tag(reversed_WAVTags[tag], value)
                except KeyError:
                    if tag not in missing_tags_wav:
                        missing_tags_wav.append(tag)

        elif isinstance(tags, MP4Tags):  # M4A / AAC
            for tag_key, value in tags.items():
                # Known mapped tag
                standard_key = reversed_MP4Tags.get(tag_key)
                if standard_key:
                    self.tags[standard_key] = Tag(standard_key, value)
                elif tag_key.startswith("----:com.apple.iTunes:"):
                    # fallback voor LMS-style custom tags
                    custom_name = tag_key.split(":")[-1].lower()
                    val = value[0]
                    if isinstance(val, MP4FreeForm):
                        decoded_val = val.decode("utf-8", "ignore")
                    elif isinstance(val, bytes):
                        decoded_val = val.decode("utf-8", "ignore")
                    else:
                        decoded_val = str(val)
                    self.tags[custom_name] = Tag(custom_name, decoded_val)
                else:
                    if tag_key not in missing_tags_m4a:
                        missing_tags_m4a.append(tag_key)
        else:
            logging.info("TagCollection not supporting this file extension")
            logging.info(type(tags))
            raise UnsupportedExtension(str(type(tags)))


    def __str__(self):
        """
        Returns a readable string representation of the tag collection.

        Returns:
            str: A string showing all tag keys and their values.
        """
        return '\n'.join(f"{key}: {tag.to_string()}" for key, tag in self.tags.items())

    def __eq__(self, other):
        """
        Compares this TagCollection with another for equality.

        Args:
            other (TagCollection): The other collection to compare with.

        Returns:
            bool: True if both collections contain the same tags and values.
        """
        if not isinstance(other, TagCollection):
            return False
        return self.tags == other.tags

    def __len__(self):
        """
        Returns the number of tags in the collection.

        Returns:
            int: Number of tags.
        """
        return len(self.tags)

    def __iter__(self):
        """
        Iterates over the Tag objects in the collection.

        Yields:
            Tag: Each Tag object in the collection.
        """
        return iter(self.tags.values())

    def copy(self):
        """
        Creates a shallow copy of the tag collection.

        Returns:
            TagCollection: A new TagCollection with the same tags.
        """
        copied = TagCollection(None)
        copied.tags = {key: tag.copy() for key, tag in self.tags.items()}
        return copied

    def add(self, mp3tag, value):
        """
        Adds or updates a tag in the collection.

        Args:
            mp3tag (str): The standardized tag name.
            value (Any): The new value to assign to the tag.
        """
        if value is not None:
            if self.tags.get(mp3tag):
                self.tags[mp3tag].set(value)
            else:
                self.tags[mp3tag] = Tag(mp3tag, "")
                self.tags[mp3tag].set(value)
        else:
            logging.info("Error adding tag(%s), value is none", mp3tag)

    def log(self):
        """
        Logs all tags in the collection using each Tag's internal log method.
        """
        for tag in self.tags.values():
            tag.log()

    def has_item(self, tag):
        """
        Checks if a tag is present in the collection.

        Args:
            tag (str): The tag name to check.

        Returns:
            bool: True if the tag exists, False otherwise.
        """
        return tag in self.tags

    def get_item(self, tag):
        """
        Retrieves a Tag object from the collection.

        Args:
            tag (str): The tag name to retrieve.

        Returns:
            Tag: The corresponding Tag object.
        """
        if tag not in self.tags:
            self.tags[tag] = Tag(tag, "")
        return self.tags[tag]

    def set_item(self, tag, value):
        """
        Sets a new value on an existing tag.
        It tag does not exist, create a new tag

        Args:
            tag (str): The tag name.
            value (Any): The value to set.
        """
        if self.has_item(tag):
            tag = self.get_item(tag)
            tag.set(value)
        else:
            self.add(tag, value)

    def get_item_as_string(self, tag):
        """
        Retrieves the tag value as a string.

        Args:
            tag (str): The tag name.

        Returns:
            str: The string representation of the tag value, or "" on error.
        """
        try:
            return self.tags[tag].to_string()
        except Exception:
            return ""

    def get_item_as_array(self, tag) -> list[str|None]:
        """
        Retrieves the tag value as an array.

        Args:
            tag (str): The tag name.

        Returns:
            list: The array representation of the tag value, or [] on error.
        """
        try:
            return self.tags[tag].to_array()
        except Exception:
            return []

    def get(self):
        """
        Returns the internal dictionary of tags.

        Returns:
            dict[str, Tag]: All tags in the collection.
        """
        return self.tags
