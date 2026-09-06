import logging
import re
import unicodedata
from contextlib import closing
from dataclasses import dataclass

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
    canonical_id: int | None


@dataclass
class GenreDecision:
    """Outcome of resolving one raw genre string.

    `values` is what should end up in the tag: empty when the genre is dropped,
    one entry for a plain keep or a rename, several when the genre is a
    contraction that expands ('Upterror' becomes 'Uptempo Hardcore' + 'Terror').
    """

    state: str
    values: list[str]


class GenreRulesHelper:
    """Curation state of every genre the library has ever seen.

    A genre is white (keep), black (drop) or unknown (awaiting a human decision).
    `canonical_id` turns either decided state into a rewrite, so 'uptempo' can be
    saved as 'Uptempo Hardcore' while 'Arts' is dropped outright.

    Unknown genres are recorded but never applied: they stay in the tag untouched
    until somebody decides, instead of silently counting as approved.

    A rewrite has one target in the usual case and several for a contraction
    ('Upterror' becomes 'Uptempo Hardcore' + 'Terror'), so targets live in
    `rules_genre_expansions` rather than in the single `canonical_id` column,
    which stays only for the tools that still read it.
    """

    table_name = 'rules_genres'
    expansion_table = 'rules_genre_expansions'

    def __init__(
        self, preload: bool = True, rows: list[GenreRow] | None = None, expansions: dict[int, list[int]] | None = None
    ):
        self.db_connector = DatabaseConnector()
        self._rows: dict[str, GenreRow] = {}
        self._by_id: dict[int, GenreRow] = {}
        self._expansions: dict[int, list[int]] = {}
        self._loaded = False
        if rows is not None:
            self._index(rows, expansions)
        elif preload:
            self._preload()

    @staticmethod
    def normalize(name: str) -> str:
        """Casing-, accent- and punctuation-insensitive key for a genre name."""
        decomposed = unicodedata.normalize('NFKD', name or '')
        without_accents = ''.join(c for c in decomposed if not unicodedata.combining(c))
        return re.sub('[^a-z0-9]+', ' ', without_accents.lower()).strip()

    def _index(self, rows: list[GenreRow], expansions: dict[int, list[int]] | None = None) -> None:
        self._rows = {row.normalized_name: row for row in rows}
        self._by_id = {row.id: row for row in rows}
        self._expansions = dict(expansions or {})
        self._loaded = True

    def set_rows(self, rows: list[GenreRow], expansions: dict[int, list[int]] | None = None) -> None:
        """Replace the cached rules, e.g. after a curation decision."""
        self._index(rows, expansions)

    def reload(self) -> None:
        self._preload()

    def is_loaded(self) -> bool:
        """True once a query for the rules has actually succeeded.

        A caller that *writes* what it resolved needs this: `_preload` logs its failures
        and returns, so an unreachable database is indistinguishable from a collection
        with no curated genres, and resolving against that empty map deletes genre links
        rather than leaving them alone.
        """
        return self._loaded

    def _preload(self) -> None:
        query = f'SELECT id, name, normalized_name, state, canonical_id FROM {self.table_name}'
        expansion_query = (
            f'SELECT genre_id, target_id FROM {self.expansion_table} ORDER BY genre_id, position, target_id'
        )
        try:
            with closing(self.db_connector.connect()) as connection, connection.cursor() as cursor:
                cursor.execute(query)
                rows = [
                    GenreRow(id=row[0], name=row[1], normalized_name=row[2], state=row[3], canonical_id=row[4])
                    for row in cursor.fetchall()
                ]
                expansions: dict[int, list[int]] = {}
                cursor.execute(expansion_query)
                for genre_id, target_id in cursor.fetchall():
                    expansions.setdefault(genre_id, []).append(target_id)
                self._index(rows, expansions)
        except Exception as e:
            logging.error(f'[{self.table_name}] Failed to preload genre rules: {e}')

    def get_row(self, name: str) -> GenreRow | None:
        return self._rows.get(self.normalize(name))

    def is_decided(self, name: str) -> bool:
        """Whether a human or the migration has ruled on this exact string."""
        row = self._rows.get(self.normalize(name))
        return row is not None and row.state != UNKNOWN

    def split_composite(self, name: str) -> list[str]:
        """Split 'Hardstyle/Hardcore' into two genres.

        A slash between genres is a separator, not part of a name: the tag
        pipeline already splits on ';' and on ' & ', but never on '/', so these
        arrived as a single genre and filled the curation queue with
        combinations that never repeat.

        A genre that has been decided is never split, so approving a name that
        genuinely contains a slash protects it permanently. That is also why
        this lives on the genre helper and not in `Tag.resplit`: artists really
        do contain slashes (AC/DC) and must keep them.
        """
        if not name or self.is_decided(name):
            return [name]
        parts = [part.strip() for part in name.split('/')]
        parts = [part for part in parts if part]
        if not parts:
            return [name]
        # One surviving part still means a stray slash was dropped ('Hardcore/'),
        # which is worth cleaning rather than queueing for curation as-is.
        return parts

    def resolve(self, name: str) -> GenreDecision:
        """Decide what to do with a raw genre string."""
        key = self.normalize(name)
        if not key:
            return GenreDecision(BLACK, [])
        row = self._rows.get(key)
        if row is None or row.state == UNKNOWN:
            return GenreDecision(UNKNOWN, [name.strip()])
        targets = [
            self._by_id[target_id]
            for target_id in self._expansions.get(row.id, [])
            if target_id in self._by_id and target_id != row.id
        ]
        if targets:
            return GenreDecision(row.state, [target.name for target in targets])
        if row.state == BLACK:
            return GenreDecision(BLACK, [])
        return GenreDecision(WHITE, [row.name])

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
