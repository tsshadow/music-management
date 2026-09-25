import logging
import re
from dataclasses import dataclass, field

from services.common.Helpers.DatabaseConnector import DatabaseConnector
from services.common.text_normalize import ascii_name_key, padded_ascii_name_key

# The markers that introduce an episode number, in the spellings the library actually
# uses: "#150", "Episode #73", "ep. 12", "Podcast 140", "week 023", "Podcast_130",
# "afl 12". Anchored on the marker rather than on any number, so a year or a bitrate
# never reads as an episode. The separator class includes '_' and '-' because scene
# releases join every word with them, and the marker is preceded by a lookbehind rather
# than \b because '_' is a word character: \b never fires in 'Twisted_Darkside_Podcast_130'.
EPISODE_PATTERN = re.compile(
    '(?<![a-z])(?:episode|podcast|afl|ep|week)\\.?[\\s_-]*#?[\\s_-]*(\\d{1,4})\\b|#\\s*(\\d{1,4})\\b', re.IGNORECASE
)

# "Podcast" is regularly part of a show's own name -- The Uptempo Tribe Podcast,
# Monstercat Podcast, Twisted Darkside Podcast -- so it is kept when the series key is
# cut, unlike "episode" or "week", which never are.
NAME_MARKERS = ('podcast',)


@dataclass
class Show:
    """One radio show or podcast series, and the spellings it is known by."""

    name: str
    aliases: list[str] = field(default_factory=list)


def normalize(name: str | None) -> str:
    """
    Casing-, accent- and punctuation-insensitive key for a show name.

    Deliberately the same rule as `GenreRulesHelper.normalize` and `normalizeGenre` in
    the webui (`services.common.text_normalize.ascii_name_key`), so a curator, the
    tagger and the detector all group names identically. Unpadded, because this is
    also the key stored in `normalized_name`; matching pads both sides itself.
    """
    return ascii_name_key(name)


def padded(name: str | None) -> str:
    """Normalized and wrapped in spaces, so an alias only matches on word boundaries."""
    return padded_ascii_name_key(name)


def series_cut(text: str | None) -> int | None:
    """
    Where the show name ends and the episode begins, or None without a marker.

    A marker that is part of the name ("… Tribe Podcast #44") is kept on the name side
    of the cut; every other marker is dropped with the rest.
    """
    match = EPISODE_PATTERN.search(text or '')
    if not match:
        return None
    tail = (text or '')[match.start() :].lower()
    for marker in NAME_MARKERS:
        if tail.startswith(marker):
            return match.start() + len(marker)
    return match.start()


def strip_episode_and_guest(text: str | None) -> str:
    """
    Normalized series key: everything up to the episode marker.

    The remainder of an episode title is what varies per episode -- the number, the
    guest, the month -- so cutting at the marker is what collapses "Hardcore Italia
    #151 mixed by Art of Fighters" and "Hardcore Italia - Episode 140 - hosted by Nico
    & Tetta" onto one key.

    A title with no marker is left whole. Cutting a trailing "- something" off those
    too would eat half of every ordinary release name ("Nitrogenetics - Inside Your
    Head").
    """
    cut = series_cut(text)
    if cut is None:
        return normalize(text)
    return normalize((text or '')[:cut])


def find_episode(text: str | None) -> str | None:
    """The episode number as it was written, or None when the text carries no marker."""
    match = EPISODE_PATTERN.search(text or '')
    if not match:
        return None
    return match.group(1) or match.group(2)


class PodcastHelper:
    """
    Identifies the radio show or podcast series a recording belongs to.

    The names live in two tables: `rules_podcasts` holds the canonical name and the
    curation state, `rules_podcast_aliases` the spellings that occur in the wild. Only
    shows a human approved (`state = 'white'`) are matched, so a hit is trusted on the
    strength of that decision: an episode number is welcome but not required.

    Matching works on normalised text padded with a space on both sides, so an alias
    only matches on word boundaries -- "Louder" does not match "Loudness". When more
    than one alias hits, the longest one wins, which is what makes "Isaac's Hardstyle
    Sessions Yearmix" resolve to the yearmix series rather than to the show it contains.
    """

    def __init__(
        self, preload: bool = True, table_name: str = 'rules_podcasts', alias_table_name: str = 'rules_podcast_aliases'
    ):
        self.table_name = table_name
        self.alias_table_name = alias_table_name
        self.db_connector = DatabaseConnector()
        self._shows: list[Show] = []
        # Longest alias first, so the first hit is always the most specific one.
        self._index: list[tuple[str, Show]] = []
        if preload:
            self.reload()

    # -- data ------------------------------------------------------------

    def set_shows(self, shows: list[Show]) -> None:
        """Replace the show list and rebuild the alias index the matcher searches."""
        self._shows = shows
        index = []
        for show in shows:
            for alias in show.aliases or [show.name]:
                key = padded(alias)
                if key.strip():
                    index.append((key, show))
        index.sort(key=lambda pair: len(pair[0]), reverse=True)
        self._index = index

    def reload(self) -> None:
        """Reloads the approved shows, e.g. after a curation decision."""
        self.set_shows(self._load())

    def _load(self) -> list[Show]:
        """
        The approved shows and their spellings.

        A show's own name counts as an alias, which is what makes a freshly approved
        show match before anyone has recorded a spelling for it.
        """
        query = f'\n            SELECT p.id, p.name, a.alias\n            FROM {self.table_name} p\n            LEFT JOIN {self.alias_table_name} a ON a.podcast_id = p.id\n            WHERE p.state = %s\n        '
        try:
            connection = self.db_connector.connect()
        except Exception as e:
            logging.error('[PodcastHelper] Failed to connect: %s', e)
            return []
        try:
            by_id: dict[int, Show] = {}
            with connection.cursor() as cursor:
                cursor.execute(query, ('white',))
                for row in cursor.fetchall():
                    show_id, name, alias = (
                        (row['id'], row['name'], row['alias']) if isinstance(row, dict) else (row[0], row[1], row[2])
                    )
                    show = by_id.setdefault(show_id, Show(name=name, aliases=[name]))
                    if alias and alias not in show.aliases:
                        show.aliases.append(alias)
            return list(by_id.values())
        except Exception as e:
            logging.error('[PodcastHelper] Failed to load shows from %s: %s', self.table_name, e)
            return []
        finally:
            connection.close()

    # -- matching --------------------------------------------------------

    def get(self, text: str | None) -> dict | None:
        """
        Looks up the show for a title, a path, or both concatenated.

        Returns:
            dict or None: `{'podcast': canonical name, 'episode': number or None}`, or
                None when no approved show matches.
        """
        if not text:
            return None
        haystack = padded(text)
        if not haystack.strip():
            return None
        for alias, show in self._index:
            if alias in haystack:
                return {'podcast': show.name, 'episode': find_episode(text)}
        return None
