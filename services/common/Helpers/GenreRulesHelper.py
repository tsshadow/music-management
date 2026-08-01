import logging
import re
import unicodedata
from contextlib import closing
from dataclasses import dataclass
from typing import Optional
from services.common.Helpers.DatabaseConnector import DatabaseConnector

WHITE = 'white'
BLACK = 'black'
UNKNOWN = 'unknown'
VALID_STATES = (WHITE, BLACK, UNKNOWN)


@dataclass
class GenreRow:
    id: int
    name: str
    normalized_name: str
    state: str
    canonical_id: Optional[int]


@dataclass
class GenreDecision:
    """Outcome of resolving one raw genre string.

    `value` is what should end up in the tag, or None when the genre is dropped.
    """
    state: str
    value: Optional[str]


class GenreRulesHelper:
    """Curation state of every genre the library has ever seen.

    A genre is white (keep), black (drop) or unknown (awaiting a human decision).
    `canonical_id` turns either decided state into a rewrite, so 'uptempo' can be
    saved as 'Uptempo Hardcore' while 'Arts' is dropped outright.

    Unknown genres are recorded but never applied: they stay in the tag untouched
    until somebody decides, instead of silently counting as approved.
    """
    table_name = 'rules_genres'

    def __init__(self, preload: bool=True, rows: Optional[list[GenreRow]]=None):
        self.db_connector = DatabaseConnector()
        self._rows: dict[str, GenreRow] = {}
        self._by_id: dict[int, GenreRow] = {}
        if rows is not None:
            self._index(rows)
        elif preload:
            self._preload()

    @staticmethod
    def normalize(name: str) -> str:
        """Casing-, accent- and punctuation-insensitive key for a genre name."""
        decomposed = unicodedata.normalize('NFKD', name or '')
        without_accents = ''.join((c for c in decomposed if not unicodedata.combining(c)))
        return re.sub('[^a-z0-9]+', ' ', without_accents.lower()).strip()

    def _index(self, rows: list[GenreRow]) -> None:
        self._rows = {row.normalized_name: row for row in rows}
        self._by_id = {row.id: row for row in rows}

    def set_rows(self, rows: list[GenreRow]) -> None:
        """Replace the cached rules, e.g. after a curation decision."""
        self._index(rows)

    def reload(self) -> None:
        self._preload()

    def _preload(self) -> None:
        query = f'SELECT id, name, normalized_name, state, canonical_id FROM {self.table_name}'
        try:
            with closing(self.db_connector.connect()) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(query)
                    rows = [GenreRow(id=row[0], name=row[1], normalized_name=row[2], state=row[3], canonical_id=row[4]) for row in cursor.fetchall()]
                    self._index(rows)
        except Exception as e:
            logging.error(f'[{self.table_name}] Failed to preload genre rules: {e}')

    def get_row(self, name: str) -> Optional[GenreRow]:
        return self._rows.get(self.normalize(name))

    def resolve(self, name: str) -> GenreDecision:
        """Decide what to do with a raw genre string."""
        key = self.normalize(name)
        if not key:
            return GenreDecision(BLACK, None)
        row = self._rows.get(key)
        if row is None or row.state == UNKNOWN:
            return GenreDecision(UNKNOWN, name.strip())
        canonical = self._by_id.get(row.canonical_id) if row.canonical_id else None
        if canonical and canonical.id != row.id:
            return GenreDecision(row.state, canonical.name)
        if row.state == BLACK:
            return GenreDecision(BLACK, None)
        return GenreDecision(WHITE, row.name)

    def record_unknown(self, name: str) -> None:
        """Register an undecided genre for curation, or bump its occurrence count."""
        key = self.normalize(name)
        if not key:
            return
        query = f'\n            INSERT INTO {self.table_name} (name, normalized_name, state, occurrences)\n            VALUES (%s, %s, %s, 1)\n            ON DUPLICATE KEY UPDATE occurrences = occurrences + 1\n        '
        try:
            with closing(self.db_connector.connect()) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(query, (name.strip(), key, UNKNOWN))
                connection.commit()
        except Exception as e:
            logging.error(f"[{self.table_name}] Failed to record unknown genre '{name}': {e}")
