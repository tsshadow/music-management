import sys
import unittest
from unittest.mock import MagicMock

for _mod_name in ('dbutils', 'dbutils.pooled_db', 'pymysql', 'mutagen', 'mutagen.easyid3', 'markdown'):
    sys.modules.setdefault(_mod_name, MagicMock())

from services.common.Helpers.GenreRulesHelper import GenreRow, GenreRulesHelper
from services.music_manager.routers.scanner import ScannerManager
from services.tagger.Song.BaseSong import BaseSong


def helper_with(rows, expansions=None):
    """A GenreRulesHelper backed by explicit rows instead of the database."""
    return GenreRulesHelper(preload=False, rows=rows, expansions=expansions or {})


class TaggedSong:
    """A song stub with only the genre API BaseSong really has.

    Deliberately not a MagicMock: a mock answers to any method name, so it
    happily accepted a call that does not exist on BaseSong and the scanner
    blew up on every file in production instead. Anything the scanner reaches
    for beyond rules_genres() must fail here.
    """

    def __init__(self, tags):
        self._tags = tags

    def rules_genres(self):
        return self._tags


def row(id_, name, state, normalized=None):
    return GenreRow(
        id=id_,
        name=name,
        normalized_name=normalized or GenreRulesHelper.normalize(name),
        state=state,
        canonical_id=None,
    )


class ScannerGenreResolutionTest(unittest.TestCase):
    def setUp(self):
        self.manager = ScannerManager()

    def _resolve(self, tags, rows, expansions=None):
        self.manager.genre_helper = helper_with(rows, expansions)
        return self.manager._resolve_genre_ids(TaggedSong(tags))

    def test_the_stub_matches_the_genre_api_real_songs_expose(self):
        """Guards the stub above against drifting away from production."""
        self.assertTrue(callable(BaseSong.rules_genres))

    def test_white_genre_resolves_to_its_own_id(self):
        rows = [row(7, 'Uptempo Hardcore', 'white')]
        self.assertEqual(self._resolve(['Uptempo Hardcore'], rows), [7])

    def test_white_genre_is_matched_case_insensitively(self):
        rows = [row(7, 'Uptempo Hardcore', 'white')]
        self.assertEqual(self._resolve(['uptempo hardcore'], rows), [7])

    def test_black_genre_is_dropped(self):
        rows = [row(9, 'Arts', 'black')]
        self.assertEqual(self._resolve(['Arts'], rows), [])

    def test_unknown_genre_is_indexed_under_its_raw_name(self):
        rows = [row(11, 'Zaagtempo', 'unknown')]
        self.assertEqual(self._resolve(['Zaagtempo'], rows), [11])

    def test_genre_absent_from_rules_is_skipped(self):
        self.assertEqual(self._resolve(['Never Seen'], []), [])

    def test_expansion_yields_every_target(self):
        rows = [
            row(1, 'Upterror', 'white'),
            row(2, 'Uptempo Hardcore', 'white'),
            row(3, 'Terror', 'white'),
        ]
        result = self._resolve(['Upterror'], rows, expansions={1: [2, 3]})
        self.assertEqual(sorted(result), [2, 3])

    def test_composite_slash_splits_when_undecided(self):
        rows = [
            row(2, 'Hardstyle', 'white'),
            row(3, 'Hardcore', 'white'),
        ]
        result = self._resolve(['Hardstyle/Hardcore'], rows)
        self.assertEqual(sorted(result), [2, 3])

    def test_decided_genre_containing_slash_is_not_split(self):
        rows = [row(5, 'Drum/Bass', 'white')]
        self.assertEqual(self._resolve(['Drum/Bass'], rows), [5])

    def test_several_tag_genres_all_resolve(self):
        rows = [
            row(2, 'Hardstyle', 'white'),
            row(4, 'Raw Hardstyle', 'white'),
        ]
        result = self._resolve(['Hardstyle', 'Raw Hardstyle'], rows)
        self.assertEqual(sorted(result), [2, 4])

    def test_duplicate_genres_are_deduplicated(self):
        rows = [row(2, 'Hardstyle', 'white')]
        self.assertEqual(self._resolve(['Hardstyle', 'hardstyle'], rows), [2])

    def test_no_genre_tag_yields_nothing(self):
        rows = [row(2, 'Hardstyle', 'white')]
        self.assertEqual(self._resolve([], rows), [])
        self.assertEqual(self._resolve(None, rows), [])


class ScannerGenreWriteTest(unittest.TestCase):
    def setUp(self):
        self.manager = ScannerManager()
        self.manager.genre_helper = helper_with([row(2, 'Hardstyle', 'white')])

    def test_write_replaces_previous_rows_then_inserts(self):
        cursor = MagicMock()
        self.manager._write_genres(cursor, track_id=42, genre_ids=[2, 5])

        executed = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertIn('DELETE FROM library_track_genres WHERE track_id = %s', executed[0])
        self.assertEqual(
            executed.count('INSERT IGNORE INTO library_track_genres (track_id, genre_id) VALUES (%s, %s)'), 2
        )
        cursor.execute.assert_any_call(
            'INSERT IGNORE INTO library_track_genres (track_id, genre_id) VALUES (%s, %s)', (42, 2)
        )

    def test_write_with_no_genres_still_clears_stale_rows(self):
        cursor = MagicMock()
        self.manager._write_genres(cursor, track_id=42, genre_ids=[])
        cursor.execute.assert_called_once_with('DELETE FROM library_track_genres WHERE track_id = %s', (42,))

    def test_nothing_is_written_when_the_rules_never_loaded(self):
        """A failed rules query leaves an empty map that resolves every genre to nothing.
        Deleting on that reading would strip the genre links of every file a scan touches,
        which is the same damage the empty cache used to do on a single scan."""
        self.manager.genre_helper = GenreRulesHelper(preload=False)
        cursor = MagicMock()
        self.manager._write_genres(cursor, track_id=42, genre_ids=[])
        cursor.execute.assert_not_called()


if __name__ == '__main__':
    unittest.main()
