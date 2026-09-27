import logging
import os

from mutagen.easyid3 import EasyID3
from mutagen.flac import FLAC
from mutagen.id3 import TXXX, TextFrame
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4FreeForm, MP4StreamInfoError
from mutagen.oggopus import OggOpus
from mutagen.wave import WAVE

from services.common.config_store import ConfigStore as Settings
from services.common.Helpers import Quarantine
from services.tagger.constants import (
    ALBUM,
    ALBUM_ARTIST,
    ARTIST,
    BPM,
    CATALOG_NUMBER,
    COPYRIGHT,
    DATE,
    FESTIVAL,
    GENRE,
    LEGACY_MP4_ATOMS,
    MP4_FREEFORM_PREFIX,
    ORIGINAL_ARTIST,
    ORIGINAL_DATE,
    PARSED,
    PUBLISHER,
    RATING,
    REMIXER,
    TITLE,
    TRACK_NUMBER,
    FLACTags,
    MP4Tags,
    MusicFileType,
    OPUSTags,
    WAVTags,
)
from services.tagger.Song.ReleaseDate import completed_date, format_release_date, preferred_release_date
from services.tagger.Song.rules.AnalyzeBpmRule import AnalyzeBpmRule
from services.tagger.Song.rules.CleanTitleRule import CleanTitleRule
from services.tagger.Song.rules.CollapseRepeatedValuesRule import CollapseRepeatedValuesRule
from services.tagger.Song.rules.NormalizeFlacTagsRule import NormalizeFlacTagsRule
from services.tagger.Song.rules.TagRule import TagRule
from services.tagger.Song.Tag import Tag
from services.tagger.Song.TagCollection import TagCollection
from services.tagger.tag_registration import register_custom_tag_keys

LOG_FILE = 'broken-files.log'
s = Settings()
register_custom_tag_keys()


class ExtensionNotSupportedException(Exception):
    """Raised when an unsupported music file extension is encountered."""


def log_broken_file(pad: str):
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(pad + '\n')


class BaseSong:
    """
    Represents a single audio file and its associated metadata.

    Supports MP3, FLAC, WAV, M4A, and AAC (partial).
    Provides methods to read, clean, update, and save tags.
    """

    # Loading a file is not passive by default: an unparseable m4a is deleted and a FLAC
    # with lower-case tag keys is rewritten, both from __init__. Subclasses that only read
    # -- the scanner's ReadonlySong -- set this, and then merely opening a file changes
    # nothing on disk.
    readonly = False

    # Whether a year-only DATE is completed from the info dict's `upload_date` of the same
    # year. Only the SoundCloud path wrote a full date that an ID3v2.3 rewrite cut to the
    # year (bug report 088); a year-only DATE from any other source is what that source
    # stated and stays as it is.
    completes_year_only_date = False

    def __init__(self, path, extra_info=None):
        """
        Initializes the BaseSong object by loading the file and its tags.

        Args:
            path (str): Path to the audio file.
        """
        self.rules: list[TagRule] = []
        #: The artist credit as a download's title stated it, offered by
        #: InferArtistFromTitleRule and written -- or discarded -- by
        #: CaptureDisplayArtistRule once the artist list has settled.
        self.display_artist_candidate: str | None = None
        #: Whether parse() wrote the file. Read by the tagger to decide if LMS has to look.
        self.saved: bool = False
        paths = path.rsplit(s.delimiter, 2)
        self._path: str = path
        self._filename = str(paths[-1])
        self._extension = os.path.splitext(self._filename)[1].lower()
        music_file_classes = {
            '.mp3': lambda p: (MP3(p, ID3=EasyID3), MusicFileType.MP3),
            '.flac': lambda p: (FLAC(p), MusicFileType.FLAC),
            '.wav': lambda p: (WAVE(p), MusicFileType.WAV),
            '.m4a': lambda p: (MP4(p), MusicFileType.M4A),
            '.opus': lambda p: (OggOpus(p), MusicFileType.OPUS),
        }
        try:
            self.music_file, self.type = music_file_classes[self._extension](path)
        except KeyError as exc:
            raise ExtensionNotSupportedException(f'{self._extension} is not supported') from exc
        except MP4StreamInfoError:
            print('MP4StreamInfoError' + path)
            if self.readonly:
                # A reader reports the broken file and leaves it alone; deciding to delete
                # it belongs to the tagger, which is the component that owns writing.
                log_broken_file(path)
                return
            # Parked, not deleted. "mutagen cannot read this" is not the same claim as
            # "there is no audio in here": a truncated download and a container mutagen
            # has no parser for look identical from here, and only one of them is worth
            # throwing away. Quarantine.sweep removes it once the retention window closes.
            log_broken_file(path)
            if not Quarantine.put(path, Quarantine.UNREADABLE_FILE):
                # Nowhere to park it, or a read-only volume. The file stays where it is
                # and stays unreadable, which the broken-song log already records.
                print('Kon bestand niet in quarantaine zetten: ' + path)
            # Returning here is what keeps the rest of __init__ from reading self.type,
            # which the failed load never got to set.
            return
        # An m4a needs this for the same reason a wav does: mutagen reports `tags` as None
        # when the container carries no metadata atom at all, and `_set_m4a_tag` then writes
        # into None. A yt-dlp format fragment that never got merged (`....f140.m4a`) is
        # exactly such a file, and it is the tagger -- not the reader -- that has to put the
        # atom there before the first tag is written.
        if self.type in (MusicFileType.WAV, MusicFileType.M4A) and self.music_file.tags is None:
            self.music_file.add_tags()
        self.tag_collection = TagCollection(self.music_file.tags if self.type != MusicFileType.AAC else self.music_file)
        if extra_info:
            self._apply_extra_info(extra_info)
        if self.type == MusicFileType.FLAC and not self.readonly:
            # The rule saves the file when it changes a key's case. TagCollection._parse_flac
            # upper-cases on read anyway, so a reader loses nothing by skipping it.
            NormalizeFlacTagsRule().apply(self)
        # First, so every rule after it reads a title that is one value again (bug report 117).
        self.rules.append(CollapseRepeatedValuesRule())
        self.rules.append(CleanTitleRule())
        if s.analyze_bpm:
            self.rules.append(AnalyzeBpmRule())

    def parse(self) -> bool:
        """Run all rules and persist any changes. True when the file on disk was written."""
        self.run_all_rules()
        self.saved = self.save_file()
        return self.saved

    def delete_tag(self, tag):
        """Removes a tag from both the tag collection and file if present."""
        if self.music_file and self.music_file.get(tag):
            self.music_file.pop(tag)
        if getattr(self, 'type', None) == MusicFileType.M4A and self.music_file is not None:
            # An m4a keeps a tag under its atom name, not the tag name, so the pop above
            # never matched: an emptied remixer stayed on the file and came back next read.
            atoms = getattr(self.music_file, 'tags', None)
            if atoms is not None and self._m4a_key(tag) in atoms:
                del atoms[self._m4a_key(tag)]
        if tag in self.tag_collection.get():
            del self.tag_collection.get()[tag]

    def sort_genres(self):
        """Sorts the genre tag array alphabetically if the tag exists."""
        if self.tag_collection.has_item(GENRE):
            rules_genres = self.tag_collection.get_item(GENRE)
            rules_genres.sort()

    def normalize_custom_atoms(self) -> bool:
        """Folds differently-cased freeform atoms into the one this tagger writes.

        m4a has two spellings of the same tag living side by side: `_set_m4a_tag` upper-cases
        the name, while the EasyMP4 registrations map to the lower-case atom, and older
        rounds wrote `Festival` with a capital. Reading is case-insensitive
        (`TagCollection._parse_m4a` lower-cases the key), so muma never noticed -- but LMS
        reads both atoms and makes two clusters out of one festival. Worse, a new value goes
        to the upper-case atom only, which would leave the stale one behind with the old text.

        The canonical atom wins when both exist: it is what this tagger writes, so it holds
        the value the rules just produced.

        Returns True when the file was altered and therefore has to be saved.
        """
        if getattr(self, 'type', None) != MusicFileType.M4A or not getattr(self, 'music_file', None):
            return False
        tags = self.music_file.tags
        if tags is None:
            return False
        prefix = MP4_FREEFORM_PREFIX
        changed = False
        for key in [k for k in list(tags.keys()) if str(k).startswith(prefix)]:
            canonical = prefix + str(key)[len(prefix) :].upper()
            if str(key) == canonical:
                continue
            value = tags[key]
            del tags[key]
            if canonical not in tags:
                tags[canonical] = value
            changed = True
        return changed

    def save_file(self) -> bool:
        """Writes the file when a rule changed a tag. Returns whether it did.

        The caller needs the answer: the tagger tells LMS about a folder after tagging it,
        and a folder where nothing was written has nothing for LMS to re-read.
        """
        if not hasattr(self, 'tag_collection'):
            return False
        changes = self.normalize_custom_atoms()
        # After the case fold, so a lower-case legacy freeform atom is caught under its
        # canonical spelling too.
        changes = self.drop_legacy_m4a_atoms() or changes
        written: list[Tag] = []
        for tag in list(self.tag_collection.get().values()):
            if isinstance(tag, Tag) and tag.has_changes():
                try:
                    self.set_tag(tag)
                except (KeyError, ValueError) as e:
                    # A name the format will not take -- an unregistered ID3 key raises here.
                    # One such tag used to end the whole save, so every other change the rules
                    # had just made to this file was dropped with it. Losing the one tag is bad
                    # enough; losing the file's other tags without a word is what made the
                    # podcast rule look like it was never running.
                    logging.error(f'Could not write tag {tag.tag} on {self.path()}: {e}')
                    continue
                written.append(tag)
                changes = True
        if changes:
            # Logged after the write, not before it. A read-only file raises here, and announcing
            # the save first made a denied write read as a success: the backfill over the library
            # logged 17356 "File saved" lines for 8885 files it actually wrote.
            self.music_file.save()
            # Baselines move only once the bytes are on disk; a save that raised leaves every
            # tag still reporting its change, so the next attempt writes it again.
            for tag in written:
                tag.clear_changes()
            logging.info(f'File saved: {self.path()}')
        return changes

    def set_tag(self, tag: Tag):
        """Sets a tag on the underlying music file based on type."""
        logging.info(f'Set tag {tag.tag} to {tag.to_string()} (was: {self.music_file.get(tag.tag)})')
        value = tag.to_string()
        if not value.strip():
            self.delete_tag(tag.tag)
            return
        if self.type == MusicFileType.MP3:
            self.music_file[tag.tag] = value
        elif self.type == MusicFileType.FLAC:
            self._set_flac_tag(tag.tag, value)
        elif self.type == MusicFileType.OPUS:
            self._set_opus_tag(tag.tag, value)
        elif self.type == MusicFileType.WAV:
            self._set_wav_tag(tag.tag, value)
        elif self.type == MusicFileType.M4A:
            self._set_m4a_tag(tag.tag, value)

    def _set_flac_tag(self, tag_name, value):
        flac_key = FLACTags.get(tag_name)
        if flac_key:
            self.music_file[flac_key] = value

    def _set_opus_tag(self, tag_name, value):
        opus_key = OPUSTags.get(tag_name)
        if opus_key:
            self.music_file[opus_key] = value

    def _set_wav_tag(self, tag_name, value):
        wav_key = WAVTags.get(tag_name)
        if wav_key:
            if wav_key.startswith('TXXX:'):
                self.music_file.tags.add(TXXX(encoding=3, desc=wav_key[5:], text=[value]))
            else:
                self.music_file.tags[wav_key] = TextFrame(encoding=3, text=[value])

    def _set_m4a_tag(self, tag_name, value):
        """Write one tag to its m4a atom; freeform atoms carry UTF-8 bytes, standard ones text."""
        mp4_key = self._m4a_key(tag_name)
        if mp4_key.startswith(MP4_FREEFORM_PREFIX):
            self.music_file.tags[mp4_key] = [MP4FreeForm(value.encode('utf-8'))]
        else:
            self.music_file.tags[mp4_key] = value

    @staticmethod
    def _m4a_key(tag_name) -> str:
        """The m4a atom a tag is written to: its MP4Tags entry, else an upper-case freeform atom."""
        return MP4Tags.get(tag_name) or f'{MP4_FREEFORM_PREFIX}{tag_name.upper()}'

    def drop_legacy_m4a_atoms(self) -> bool:
        """Deletes the atoms earlier versions wrote under a wrong name (see LEGACY_MP4_ATOMS).

        TagCollection has already taken their value when the correct atom was missing, and
        marked it unsaved, so save_file writes it to the correct atom in the same pass.
        Returns True when an atom was removed and the file therefore has to be saved.
        """
        if getattr(self, 'type', None) != MusicFileType.M4A or not getattr(self, 'music_file', None):
            return False
        tags = self.music_file.tags
        if tags is None:
            return False
        changed = False
        for key in LEGACY_MP4_ATOMS:
            if key in tags:
                del tags[key]
                changed = True
        return changed

    def length(self):
        try:
            if hasattr(self.music_file, 'info') and hasattr(self.music_file.info, 'length'):
                return self.music_file.info.length
            logging.warning(f'Could not retrieve length for: {self.path()}')
        except Exception as e:
            logging.warning(f'Error retrieving length for {self.path()}: {e}')
        return None

    def _apply_extra_info(self, info):
        """
        Apply extra metadata from yt-dlp dump to tag collection.
        """
        artist = (
            info.get('library_artists', [None])[0]
            if isinstance(info.get('library_artists'), list)
            else info.get('artist')
        )
        if not artist:
            artist = info.get('uploader') or info.get('channel')
        if artist and (not self.tag_collection.get_item_as_string(ARTIST)):
            self.tag_collection.set_item(ARTIST, artist)
        title = info.get('title')
        if title and (not self.tag_collection.get_item_as_string(TITLE)):
            self.tag_collection.set_item(TITLE, title)
        genre = info.get('genre')
        if genre:
            self.tag_collection.get_item(GENRE).add(genre)
        if info.get('upload_date') and (not self.tag_collection.get_item_as_string(DATE)):
            self.tag_collection.set_item(DATE, info.get('upload_date'))
        elif self.completes_year_only_date:
            # A year-only DATE is what an ID3v2.3 rewrite leaves of the full date the
            # downloader wrote (bug report 088); the stored info dict still has the rest.
            full = completed_date(self.tag_collection.get_item_as_string(DATE), info.get('upload_date'))
            if full:
                self.tag_collection.set_item(DATE, full)

    def album(self):
        return self.tag_collection.get_item_as_string(ALBUM)

    def album_artist(self):
        return self.tag_collection.get_item_as_string(ALBUM_ARTIST)

    def artist(self):
        return self.tag_collection.get_item_as_string(ARTIST)

    def library_artists(self):
        return self.tag_collection.get_item_as_array(ARTIST)

    def original_artist(self):
        """The artist string as it read on disk before CleanTagsRule split it, or None."""
        return self.tag_collection.get_item_as_string(ORIGINAL_ARTIST) or None

    def bpm(self):
        return self.tag_collection.get_item_as_string(BPM)

    def catalog_number(self):
        return self.tag_collection.get_item_as_string(CATALOG_NUMBER)

    def copyright(self):
        return self.tag_collection.get_item_as_string(COPYRIGHT)

    def date(self):
        return self.tag_collection.get_item_as_string(DATE)

    def original_date(self):
        """The original release date, which is the one worth sorting and dating by."""
        return self.tag_collection.get_item_as_string(ORIGINAL_DATE)

    def release_date(self):
        """The single date worth showing: see services/tagger/Song/ReleaseDate.py."""
        return preferred_release_date(self.date(), self.original_date())

    def festival(self):
        return self.tag_collection.get_item_as_string(FESTIVAL)

    def genre(self):
        return self.tag_collection.get_item_as_string(GENRE)

    def rules_genres(self):
        return self.tag_collection.get_item_as_array(GENRE)

    def parsed(self):
        return self.tag_collection.get_item_as_string(PARSED)

    def rating(self):
        return self.tag_collection.get_item_as_string(RATING)

    def publisher(self):
        return self.tag_collection.get_item_as_string(PUBLISHER)

    def remixer(self):
        return self.tag_collection.get_item_as_string(REMIXER)

    def remixers(self):
        return self.tag_collection.get_item_as_array(REMIXER)

    def title(self):
        return self.tag_collection.get_item_as_string(TITLE)

    def track_number(self):
        return self.tag_collection.get_item_as_string(TRACK_NUMBER)

    def filename(self):
        return self._filename

    def path(self):
        return self._path

    def channel_stand_ins(self) -> list[str]:
        """Names that stand in for an artist only because the file came through a channel.

        Empty here; the download song types return the channel folder and the uploader, which
        they write into ARTIST when the title names nobody. ApplyChannelLinkRule replaces exactly
        those values with the artist the channel is linked to (docs/designs/channel-links).
        """
        return []

    def extension(self):
        return self._extension

    def run_all_rules(self):
        for rule in self.rules:
            rule.apply(self)

    def __str__(self):
        fields = [
            ('Title', self.title()),
            ('Artists', self.artist()),
            ('Album', self.album()),
            ('Released', format_release_date(self.release_date())),
            ('Genre', self.genre()),
            ('Publisher', self.publisher()),
            ('Path', self.path()),
        ]
        return '\n'.join([f'{label}={value}' for label, value in fields if value])
