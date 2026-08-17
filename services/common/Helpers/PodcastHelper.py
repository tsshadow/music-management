import logging
import re
import unicodedata

from services.common.Helpers.DatabaseConnector import DatabaseConnector

# The markers that introduce an episode number, in the spellings the library actually
# uses: "#150", "Episode #73", "ep. 12", "Podcast 140", "week 023", "Podcast_130",
# "afl 12". Anchored on the marker rather than on any number, so a year or a bitrate
# never reads as an episode. The separator class includes '_' and '-' because scene
# releases join every word with them.
# The marker is preceded by a lookbehind rather than \b because '_' is a word character:
# \b never fires in 'Twisted_Darkside_Podcast_130', which is how half the ripped
# episodes in the library are named.
EPISODE_PATTERN = re.compile('(?<![a-z])(?:episode|podcast|afl|ep|week)\\.?[\\s_-]*#?[\\s_-]*(\\d{1,4})\\b|#\\s*(\\d{1,4})\\b', re.IGNORECASE)

# "Podcast" is regularly part of a show's own name -- The Uptempo Tribe Podcast,
# Monstercat Podcast, Twisted Darkside Podcast -- so it is kept when the series key is
# cut, unlike "episode" or "week", which never are.
NAME_MARKERS = ('podcast',)


def normalize(name: str | None) -> str:
    """
    Casing-, accent- and punctuation-insensitive key for a show name.

    Deliberately the same rule as `GenreRulesHelper.normalize` and `normalizeGenre` in
    the webui, so a curator, the tagger and the detector all group names identically.
    """
    decomposed = unicodedata.normalize('NFKD', name or '')
    without_accents = ''.join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub('[^a-z0-9]+', ' ', without_accents.lower()).strip()


def series_cut(text: str | None) -> int | None:
    """
    Where the show name ends and the episode begins, or None without a marker.

    A marker that is part of the name ("… Tribe Podcast #44") is kept on the name side
    of the cut; every other marker is dropped with the rest.
    """
    match = EPISODE_PATTERN.search(text or '')
    if not match:
        return None
    tail = (text or '')[match.start():].lower()
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

    Only shows a human approved (`state = 'white'`) are matched, so a hit is trusted on
    the strength of that decision: an episode number is welcome but not required. The
    lookup is loaded once and kept, because the tagger builds one helper per run and the
    table is small.
    """

    def __init__(self, table_name: str='rules_podcasts', alias_table_name: str='rules_podcast_aliases'):
        self.table_name = table_name
        self.alias_table_name = alias_table_name
        self.db_connector = DatabaseConnector()
        self._aliases: dict[str, str] | None = None

    def get(self, text: str | None) -> dict | None:
        """
        Looks up the show for a title, a path, or both concatenated.

        Returns:
            dict or None: `{'podcast': canonical name, 'episode': number or None}`, or
                None when no approved show matches.
        """
        haystack = normalize(text)
        if not haystack:
            return None
        aliases = self._load()
        if not aliases:
            return None
        # Longest alias first: "Hardstyle Sessions Yearmix" is its own series and must
        # not be resolved to the "Hardstyle Sessions" it contains.
        matches = [alias for alias in aliases if alias and alias in haystack]
        if not matches:
            return None
        best = max(matches, key=len)
        return {'podcast': aliases[best], 'episode': find_episode(text)}

    def reload(self) -> None:
        """Drops the cached lookup, so the next `get` sees fresh curation decisions."""
        self._aliases = None

    def _load(self) -> dict[str, str]:
        """
        Normalized alias -> canonical show name, for approved shows only.

        A show's own name counts as an alias, which is what makes a freshly approved
        show match before anyone has recorded a spelling for it.
        """
        if self._aliases is not None:
            return self._aliases
        query = f'\n            SELECT p.name, a.alias\n            FROM {self.table_name} p\n            LEFT JOIN {self.alias_table_name} a ON a.podcast_id = p.id\n            WHERE p.state = %s\n        '
        aliases: dict[str, str] = {}
        try:
            connection = self.db_connector.connect()
        except Exception as e:
            logging.error(f'[PodcastHelper] Could not connect: {e}')
            return {}
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, ('white',))
                for row in cursor.fetchall():
                    name, alias = (row['name'], row['alias']) if isinstance(row, dict) else (row[0], row[1])
                    aliases[normalize(name)] = name
                    if alias:
                        aliases[normalize(alias)] = name
        except Exception as e:
            logging.error(f'[PodcastHelper] Error querying {self.table_name}: {e}')
            return {}
        finally:
            connection.close()
        aliases.pop('', None)
        self._aliases = aliases
        return aliases
