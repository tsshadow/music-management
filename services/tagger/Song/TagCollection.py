import logging

from mutagen.easyid3 import EasyID3
from mutagen.flac import VCFLACDict
from mutagen.mp4 import MP4FreeForm, MP4Tags
from mutagen.oggopus import OggOpusVComment
from mutagen.wave import _WaveID3

from services.tagger.constants import (
    LEGACY_MP4_ATOMS,
    MP4_FREEFORM_PREFIX,
    reversed_FLACTags,
    reversed_MP3Tags,
    reversed_MP4Tags,
    reversed_OPUSTags,
    reversed_WAVTags,
)
from services.tagger.Song.Tag import Tag

missing_tags_flac = []
missing_tags_opus = []
missing_aac_tags = []
missing_tags_mp3 = []
missing_tags_wav = []
missing_tags_m4a = []


def _canonical_m4a_key(tag_key: str) -> str:
    """The spelling this tagger writes for an m4a key: freeform names upper-cased, others as-is."""
    if tag_key.startswith(MP4_FREEFORM_PREFIX):
        return MP4_FREEFORM_PREFIX + tag_key[len(MP4_FREEFORM_PREFIX) :].upper()
    return tag_key


def _decode_m4a_value(value) -> str:
    """One m4a atom value as text: a freeform atom holds bytes, a standard one a str."""
    if isinstance(value, (MP4FreeForm, bytes)):
        return value.decode('utf-8', 'ignore')
    return str(value)


def _decode_m4a_values(values) -> list[str]:
    """Every value of an m4a atom as text, so a freeform atom reads back as it was written."""
    if isinstance(values, (str, bytes)):
        values = [values]
    return [_decode_m4a_value(value) for value in values]


def _id3_frame_text(frame):
    """An ID3 frame's values as text, the way EasyID3 hands them to _parse_mp3.

    The time frames (TDRC, TDOR, ...) hold ID3TimeStamp objects rather than str. Handed to Tag
    as they were, the ';' split failed on every one of them -- ~270 "Could not split date value
    ['2023']" warnings in 2 h on production (bug report 118) -- and the date stayed an object
    no rule could compare. str() of an ID3TimeStamp is its text, so this is lossless.
    """
    if not hasattr(frame, 'text'):
        return frame
    return [value if isinstance(value, str) else str(value) for value in frame.text]


class UnsupportedExtension(Exception):
    """Raised when an unsupported file extension is encountered."""

    def __init__(self, extension: str):
        super().__init__(f'Unsupported file extension: {extension}')
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
        elif isinstance(tags, VCFLACDict):
            self._parse_flac(tags)
        elif isinstance(tags, OggOpusVComment):
            self._parse_opus(tags)
        elif isinstance(tags, EasyID3):
            self._parse_mp3(tags)
        elif isinstance(tags, _WaveID3):
            self._parse_wav(tags)
        elif isinstance(tags, MP4Tags):
            self._parse_m4a(tags)
        else:
            logging.info('TagCollection not supporting this file extension: %s', type(tags))
            raise UnsupportedExtension(str(type(tags)))

    def _parse_flac(self, tags):
        for tag in tags:
            if tag[0] == tag[0].lower():
                logging.info('error in tag %s', tag)
            try:
                self.tags[reversed_FLACTags[tag[0].upper()]] = Tag(reversed_FLACTags[tag[0].upper()], tag[1])
            except KeyError:
                if tag[0] not in missing_tags_flac:
                    missing_tags_flac.append(tag[0])

    def _parse_opus(self, tags):
        for tag in tags:
            try:
                self.tags[reversed_OPUSTags[tag[0].upper()]] = Tag(reversed_OPUSTags[tag[0].upper()], tag[1])
            except KeyError:
                if tag[0] not in missing_tags_opus:
                    missing_tags_opus.append(tag[0])

    def _parse_mp3(self, tags):
        for tag in tags:
            try:
                self.tags[reversed_MP3Tags[tag]] = Tag(reversed_MP3Tags[tag], tags[tag])
            except KeyError:
                if tag not in missing_tags_mp3:
                    missing_tags_mp3.append(tag)

    def _parse_wav(self, tags):
        for tag in tags:
            try:
                id3_frame = tags[tag]
                value = _id3_frame_text(id3_frame)
                self.tags[reversed_WAVTags[tag]] = Tag(reversed_WAVTags[tag], value)
            except KeyError:
                if tag not in missing_tags_wav:
                    missing_tags_wav.append(tag)

    def _parse_m4a(self, tags):
        """Read m4a atoms; a correct atom always wins over a legacy or differently-cased one."""
        legacy: dict[str, list] = {}
        for tag_key, value in tags.items():
            legacy_key = LEGACY_MP4_ATOMS.get(_canonical_m4a_key(tag_key))
            if legacy_key:
                legacy.setdefault(legacy_key, value)
                continue
            standard_key = reversed_MP4Tags.get(tag_key)
            if standard_key:
                self.tags[standard_key] = Tag(standard_key, _decode_m4a_values(value))
            elif tag_key.startswith(MP4_FREEFORM_PREFIX):
                custom_name = tag_key.split(':')[-1].lower()
                if custom_name in self.tags and tag_key != _canonical_m4a_key(tag_key):
                    # A lower- or mixed-case twin of an atom already read: the upper-case
                    # one is what this tagger writes, so it holds the current value.
                    continue
                self.tags[custom_name] = Tag(custom_name, _decode_m4a_value(value[0]) if value else '')
            elif tag_key not in missing_tags_m4a:
                missing_tags_m4a.append(tag_key)
        for standard_key, value in legacy.items():
            if standard_key in self.tags:
                continue
            tag = Tag(standard_key, _decode_m4a_values(value))
            # Read from where no later read will look, so it has to be written to the real atom.
            tag.mark_unsaved()
            self.tags[standard_key] = tag

    def __str__(self):
        """
        Returns a readable string representation of the tag collection.

        Returns:
            str: A string showing all tag keys and their values.
        """
        return '\n'.join((f'{key}: {tag.to_string()}' for key, tag in self.tags.items()))

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
            # `in`, not truthiness: an existing Tag with no values is falsy through __len__,
            # and replacing it loses the baseline has_changes compares against.
            if mp3tag in self.tags:
                self.tags[mp3tag].set(value)
            else:
                self.tags[mp3tag] = Tag(mp3tag, '')
                self.tags[mp3tag].set(value)
        else:
            logging.info('Error adding tag(%s), value is none', mp3tag)

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
            self.tags[tag] = Tag(tag, '')
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
            return ''

    def get_item_as_array(self, tag) -> list[str | None]:
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
