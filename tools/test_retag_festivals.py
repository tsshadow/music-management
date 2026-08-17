import unittest
from unittest.mock import MagicMock, patch

from tools import retag_festivals


def fake_connection(rowcount=0, count=0):
    cursor = MagicMock()
    cursor.fetchone.return_value = (count,)
    cursor.rowcount = rowcount
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    return connection, cursor


class CountCandidatesTest(unittest.TestCase):

    def test_counts_per_prefix_and_ignores_rows_already_queued(self):
        connection, cursor = fake_connection(count=7)
        counts = retag_festivals.count_candidates(connection, ('/mnt/music/Livesets',))
        self.assertEqual(counts, {'/mnt/music/Livesets': 7})
        query, params = cursor.execute.call_args.args
        self.assertIn('needs_rescan = 0', query)
        self.assertEqual(params, ('/mnt/music/Livesets%',))


class MarkForRescanTest(unittest.TestCase):

    def test_flags_the_rows_and_commits(self):
        connection, cursor = fake_connection(rowcount=3)
        marked = retag_festivals.mark_for_rescan(connection, ('/a', '/b'))
        self.assertEqual(marked, 6)
        self.assertIn('SET needs_rescan = 1', cursor.execute.call_args.args[0])
        connection.commit.assert_called_once()


class StripLegacyAtomTest(unittest.TestCase):

    def setUp(self):
        patcher = patch.object(retag_festivals, 'MP4')
        self.mp4 = patcher.start()
        self.addCleanup(patcher.stop)

    def _audio_with(self, tags):
        audio = MagicMock()
        audio.tags = tags
        self.mp4.return_value = audio
        return audio

    def test_removes_only_the_legacy_atom(self):
        tags = {retag_festivals.LEGACY_ATOM: ['Defqon 2024'],
                retag_festivals.CURRENT_ATOM: ['Defqon']}
        audio = self._audio_with(tags)
        self.assertTrue(retag_festivals.strip_legacy_atom('/x.m4a'))
        self.assertEqual(list(tags), [retag_festivals.CURRENT_ATOM])
        audio.save.assert_called_once()

    def test_leaves_a_file_without_the_legacy_atom_alone(self):
        audio = self._audio_with({retag_festivals.CURRENT_ATOM: ['Defqon']})
        self.assertFalse(retag_festivals.strip_legacy_atom('/x.m4a'))
        audio.save.assert_not_called()


class MainTest(unittest.TestCase):

    def setUp(self):
        self.connection, _ = fake_connection(rowcount=2, count=5)
        connector = MagicMock()
        connector.connection.return_value.__enter__.return_value = self.connection
        patcher = patch.object(retag_festivals, 'DatabaseConnector', return_value=connector)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_dry_run_writes_nothing(self):
        with patch.object(retag_festivals, 'mark_for_rescan') as mark:
            retag_festivals.main([])
        mark.assert_not_called()

    def test_apply_marks_the_rows(self):
        with patch.object(retag_festivals, 'mark_for_rescan', return_value=2) as mark:
            retag_festivals.main(['--apply'])
        mark.assert_called_once()

    def test_a_prefix_narrows_the_scope(self):
        with patch.object(retag_festivals, 'count_candidates', return_value={}) as count:
            retag_festivals.main(['--prefix', '/mnt/music/Livesets'])
        self.assertEqual(count.call_args.args[1], ('/mnt/music/Livesets',))

    def test_the_legacy_atom_is_only_touched_when_asked(self):
        with patch.object(retag_festivals, 'find_legacy_atoms', return_value=['/x.m4a']) as find, \
             patch.object(retag_festivals, 'strip_legacy_atom') as strip:
            retag_festivals.main(['--apply'])
        find.assert_not_called()
        strip.assert_not_called()

    def test_the_legacy_atom_is_reported_before_it_is_cleared(self):
        with patch.object(retag_festivals, 'find_legacy_atoms', return_value=['/x.m4a']), \
             patch.object(retag_festivals, 'strip_legacy_atom') as strip:
            retag_festivals.main(['--strip-legacy-atom'])
        strip.assert_not_called()


if __name__ == '__main__':
    unittest.main()
