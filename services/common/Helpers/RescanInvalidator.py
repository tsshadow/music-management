import logging

from services.common.Helpers.DatabaseConnector import DatabaseConnector
from services.common.Helpers.ProcessedFilesHelper import ProcessedFilesHelper


class RescanInvalidator:
    """Turns a changed rule into the set of files that rule touches.

    A rule is written as a name -- an artist, a label, a genre -- but the tagger works
    on paths, so something has to bridge the two. The match is deliberately wide: a
    name counts as a hit when it is the track's artist, or when it appears anywhere in
    the title or the path. That also catches the rules that infer an artist out of a
    title, which no join could find.

    The width has one guard. A term shorter than MIN_TERM_LENGTH skips the substring
    half and matches on the artist name alone, because an artist called 'D' would
    otherwise drag in most of the library.

    Files the scanner has never indexed are not in library_media_files and are
    therefore invisible here. That is what invalidate_all is for.
    """

    MIN_TERM_LENGTH = 3

    def __init__(self, processed_files_helper: ProcessedFilesHelper | None=None):
        self.db_connector = DatabaseConnector()
        self.processed_files_helper = processed_files_helper or ProcessedFilesHelper()

    @staticmethod
    def _escape_like(term: str) -> str:
        """Make a user-typed term literal inside a LIKE pattern.

        A label really called '50% Off' would otherwise match every path in the
        library, because '%' is the wildcard.
        """
        return term.replace('\\', '\\\\').replace('%', r'\%').replace('_', r'\_')

    def _select_paths(self, query: str, args: tuple) -> list[str]:
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, args)
                return [str(row[0]) for row in cursor.fetchall() if row and row[0]]
        except Exception as e:
            logging.error(f'Failed to resolve files for a rescan: {e}')
            return []
        finally:
            connection.close()

    def invalidate_by_term(self, term: str, reason: str) -> int:
        """Mark every file the term touches. Returns how many were marked."""
        term = (term or '').strip()
        if not term:
            return 0
        base = '\n            SELECT DISTINCT mf.file_path\n            FROM library_media_files mf\n            LEFT JOIN library_tracks t         ON t.id = mf.track_id\n            LEFT JOIN library_track_artists ta ON ta.track_id = t.id\n            LEFT JOIN library_artists a        ON a.id = ta.artist_id\n        '
        if len(term) >= self.MIN_TERM_LENGTH:
            like = f'%{self._escape_like(term)}%'
            query = base + ' WHERE a.name = %s OR t.title LIKE %s OR mf.file_path LIKE %s'
            args = (term, like, like)
        else:
            query = base + ' WHERE a.name = %s'
            args = (term,)
        return self.invalidate_paths(self._select_paths(query, args), reason)

    def invalidate_paths(self, paths: list[str], reason: str) -> int:
        """Mark an explicit set of paths. Returns how many were marked."""
        if not paths:
            return 0
        return self.processed_files_helper.mark_paths_for_rescan(paths, reason)

    def invalidate_by_genre_id(self, genre_id: int, genre_name: str, reason: str) -> int:
        """Mark the tracks linked to this genre, plus anything the name matches.

        The link table is the precise half: those tracks carry the genre today. The
        name match catches files whose tag still says the genre but which the scanner
        has not linked, and files where the genre only shows up in a path.
        """
        linked = self._select_paths('\n            SELECT DISTINCT mf.file_path\n            FROM library_media_files mf\n            JOIN library_track_genres tg ON tg.track_id = mf.track_id\n            WHERE tg.genre_id = %s\n        ', (genre_id,))
        count = self.invalidate_paths(linked, reason)
        return count + self.invalidate_by_term(genre_name, reason)

    def invalidate_all(self, reason: str='fallback') -> int:
        """Mark the whole table.

        Returns -1 rather than a count: the underlying UPDATE has no bounded result to
        report and the caller shows no number for a fallback.
        """
        self.processed_files_helper.mark_for_rescan(None, reason=reason)
        return -1


rescan_invalidator = RescanInvalidator()
