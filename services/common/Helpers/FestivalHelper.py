import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date

from services.common.Helpers.DatabaseConnector import DatabaseConnector

YEAR_PATTERN = re.compile(r'\b(19[89]\d|20[0-4]\d)\b')


@dataclass
class Festival:
    """One festival, the spellings it is known by, and the editions we have a date for."""

    name: str
    aliases: list[str] = field(default_factory=list)
    editions: dict[int, date] = field(default_factory=dict)


class FestivalHelper:
    """
    Recognises a festival in a title, a filename or a path.

    The names live in three tables: `rules_festivals` holds the canonical name,
    `rules_festival_aliases` the spellings that occur in the wild, and
    `rules_festival_editions` the date per year. Splitting them means a festival
    only has to be entered once to be recognised -- an edition row adds the date,
    but is never needed for the label itself.

    Matching is done on normalised text (accent-free, lower case, punctuation
    collapsed to single spaces) padded with a space on both sides, so an alias
    only matches on word boundaries: "Rise" does not match "Sunrise". When more
    than one alias hits, the longest one wins, which is what makes
    "Intents Karnaval Festival" resolve to Karnaval Festival rather than Intents.
    """

    def __init__(self, preload: bool = True):
        self.db_connector = DatabaseConnector()
        self._festivals: list[Festival] = []
        # Longest alias first, so the first hit is always the most specific one.
        self._index: list[tuple[str, Festival]] = []
        if preload:
            self.reload()

    # -- data ------------------------------------------------------------

    def set_festivals(self, festivals: list[Festival]) -> None:
        self._festivals = festivals
        index = []
        for festival in festivals:
            for alias in festival.aliases or [festival.name]:
                normalized = self.normalize(alias)
                if normalized.strip():
                    index.append((normalized, festival))
        index.sort(key=lambda pair: len(pair[0]), reverse=True)
        self._index = index

    def reload(self) -> None:
        self.set_festivals(self._load())

    def _load(self) -> list[Festival]:
        try:
            connection = self.db_connector.connect()
        except Exception as e:
            logging.error('[FestivalHelper] Failed to connect: %s', e)
            return []
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT id, name FROM rules_festivals WHERE active = 1')
                by_id = {row[0]: Festival(name=row[1]) for row in cursor.fetchall()}

                cursor.execute('SELECT festival_id, alias FROM rules_festival_aliases')
                for festival_id, alias in cursor.fetchall():
                    if festival_id in by_id and alias:
                        by_id[festival_id].aliases.append(alias)

                cursor.execute('SELECT festival_id, year, date FROM rules_festival_editions')
                for festival_id, year, edition_date in cursor.fetchall():
                    if festival_id in by_id and year and edition_date:
                        by_id[festival_id].editions[int(year)] = edition_date

                for festival in by_id.values():
                    if not festival.aliases:
                        festival.aliases = [festival.name]
                return list(by_id.values())
        except Exception as e:
            logging.error('[FestivalHelper] Failed to load festivals: %s', e)
            return []
        finally:
            connection.close()

    # -- matching --------------------------------------------------------

    @staticmethod
    def normalize(text: str) -> str:
        """Accent-free, lower case, punctuation as single spaces, padded on both sides."""
        decomposed = unicodedata.normalize('NFKD', text or '')
        stripped = ''.join(c for c in decomposed if not unicodedata.combining(c))
        collapsed = re.sub(r'[^a-z0-9]+', ' ', stripped.lower()).strip()
        return f' {collapsed} '

    @staticmethod
    def extract_year(text: str) -> int | None:
        """The last plausible year in the text, so a path's own year beats the album's."""
        matches = YEAR_PATTERN.findall(text or '')
        return int(matches[-1]) if matches else None

    def get(self, input_string: str, require_year: bool = False) -> dict | None:
        """
        Returns `{festival, year?, date?}` for the most specific festival recognised
        in the text, or None. With `require_year` the text must carry a year to match
        at all -- used for paths, where a bare folder name is too weak on its own.
        """
        results = self.get_all(input_string, require_year=require_year)
        return results[0] if results else None

    def get_all(self, input_string: str, require_year: bool = False) -> list[dict]:
        """
        Every festival recognised in the text, most specific first.

        A title can name two events at once -- "Reverze 2023 - Reverze Flashback"
        is a Flashback set played at Reverze -- and both belong on the file. What
        must not happen is one name being counted twice because a shorter alias sits
        inside a longer one: "Intents Karnaval Festival" is Karnaval Festival, not
        also Intents. So a match is kept only when its position in the text is not
        already covered by a longer match that was accepted before it. Overlap is
        not enough to reject -- neighbouring aliases share the space between them.
        """
        if not input_string:
            return []
        year = self.extract_year(input_string)
        if require_year and year is None:
            return []
        normalized = self.normalize(input_string)
        accepted: list[tuple[int, int]] = []
        results: list[dict] = []
        seen: set[str] = set()
        for alias, festival in self._index:
            span = self._first_free_span(normalized, alias, accepted)
            if span is None:
                continue
            accepted.append(span)
            if festival.name in seen:
                continue
            seen.add(festival.name)
            result: dict = {'festival': festival.name}
            if year is not None:
                result['year'] = year
                edition = festival.editions.get(year)
                if edition:
                    result['date'] = edition.isoformat()
            results.append(result)
        return results

    @staticmethod
    def _first_free_span(normalized: str, alias: str, accepted: list[tuple[int, int]]) -> tuple[int, int] | None:
        """The first occurrence of `alias` that no accepted span already contains."""
        start = normalized.find(alias)
        while start != -1:
            end = start + len(alias)
            if not any(low <= start and end <= high for low, high in accepted):
                return (start, end)
            start = normalized.find(alias, start + 1)
        return None
