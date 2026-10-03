import os
import unittest
from unittest.mock import MagicMock, patch

from tools.fix_nested_ep_dirs import (
    DELETE_DUP,
    MOVE_UP,
    PARTIAL,
    Case,
    DbCleaner,
    Executor,
    auto_answer,
    classify,
    find_cases,
    list_files,
)


def write(path, name, content='x'):
    os.makedirs(path, exist_ok=True)
    full = os.path.join(path, name)
    with open(full, 'w', encoding='utf-8') as handle:
        handle.write(content)
    return full


class ListFilesTest(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.tmp = tempfile.mkdtemp()

    def test_lists_plain_files_sorted(self):
        write(self.tmp, 'b.mp3')
        write(self.tmp, 'a.mp3')
        self.assertEqual(list_files(self.tmp), ['a.mp3', 'b.mp3'])

    def test_skips_directories(self):
        write(self.tmp, 'a.mp3')
        os.makedirs(os.path.join(self.tmp, 'sub'))
        self.assertEqual(list_files(self.tmp), ['a.mp3'])

    def test_skips_eadir(self):
        write(os.path.join(self.tmp, '@eaDir'), 'thumb.jpg')
        write(self.tmp, 'a.mp3')
        self.assertEqual(list_files(self.tmp), ['a.mp3'])

    def test_missing_dir_returns_empty(self):
        self.assertEqual(list_files(os.path.join(self.tmp, 'nope')), [])


class ClassifyTest(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.tmp = tempfile.mkdtemp()
        self.outer = os.path.join(self.tmp, 'SCAN123 EP')
        self.inner = os.path.join(self.outer, 'SCAN123 EP')
        os.makedirs(self.inner)

    def test_move_up_when_outer_has_no_audio(self):
        write(self.outer, 'cover.jpg')
        write(self.inner, '01.mp3')
        self.assertEqual(classify(self.outer, self.inner).action, MOVE_UP)

    def test_move_up_when_outer_completely_empty(self):
        write(self.inner, '01.mp3')
        self.assertEqual(classify(self.outer, self.inner).action, MOVE_UP)

    def test_delete_dup_when_inner_is_subset(self):
        write(self.outer, '01.mp3')
        write(self.outer, '02.mp3')
        write(self.inner, '01.mp3')
        write(self.inner, '02.mp3')
        self.assertEqual(classify(self.outer, self.inner).action, DELETE_DUP)

    def test_partial_when_inner_has_unique_files(self):
        write(self.outer, '01.mp3')
        write(self.inner, '01.mp3')
        write(self.inner, '02.mp3')
        case = classify(self.outer, self.inner)
        self.assertEqual(case.action, PARTIAL)
        self.assertEqual(case.unique_inner_files, ['02.mp3'])

    def test_inner_files_include_nested_subdirs(self):
        write(self.outer, '01.mp3')
        write(os.path.join(self.inner, 'Disc 1'), '02.mp3')
        case = classify(self.outer, self.inner)
        self.assertEqual(case.inner_files, [os.path.join('Disc 1', '02.mp3')])
        self.assertEqual(case.action, PARTIAL)

    def test_outer_listing_excludes_the_inner_dir(self):
        write(self.outer, '01.mp3')
        write(self.inner, '99.mp3')
        self.assertEqual(classify(self.outer, self.inner).outer_files, ['01.mp3'])

    def test_empty_inner_dir_is_delete_dup(self):
        write(self.outer, '01.mp3')
        self.assertEqual(classify(self.outer, self.inner).action, DELETE_DUP)

    def test_flac_counts_as_audio(self):
        write(self.outer, '01.flac')
        write(self.inner, '01.mp3')
        self.assertEqual(classify(self.outer, self.inner).action, PARTIAL)


class FindCasesTest(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.root = tempfile.mkdtemp()

    def make(self, label, ep, inner_name=None):
        outer = os.path.join(self.root, label, ep)
        os.makedirs(outer, exist_ok=True)
        if inner_name:
            os.makedirs(os.path.join(outer, inner_name), exist_ok=True)
        return outer

    def test_finds_identically_named_inner_dir(self):
        self.make('Scantraxx', 'SCAN123 EP', 'SCAN123 EP')
        cases, oddities = find_cases(self.root)
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0].outer, os.path.join(self.root, 'Scantraxx', 'SCAN123 EP'))
        self.assertEqual(oddities, [])

    def test_ignores_ep_without_subdir(self):
        self.make('Scantraxx', 'SCAN123 EP')
        cases, oddities = find_cases(self.root)
        self.assertEqual(cases, [])
        self.assertEqual(oddities, [])

    def test_reports_differently_named_subdir_as_oddity(self):
        self.make('Sealand', 'SEA017 - The Sound', 'The Sound')
        cases, oddities = find_cases(self.root)
        self.assertEqual(cases, [])
        self.assertEqual(len(oddities), 1)
        self.assertIn('The Sound', oddities[0])

    def test_identical_and_odd_subdir_side_by_side(self):
        outer = self.make('Sealand', 'SEA017', 'SEA017')
        os.makedirs(os.path.join(outer, 'Other'))
        cases, oddities = find_cases(self.root)
        self.assertEqual(len(cases), 1)
        self.assertEqual(len(oddities), 1)

    def test_label_filter_limits_scan(self):
        self.make('Scantraxx', 'SCAN123', 'SCAN123')
        self.make('Sealand', 'SEA017', 'SEA017')
        cases, _ = find_cases(self.root, label='Sealand')
        self.assertEqual(len(cases), 1)
        self.assertIn('Sealand', cases[0].outer)

    def test_reports_each_case_while_scanning(self):
        """A slow mount takes minutes to walk; hits must show up before the walk ends."""
        self.make('Scantraxx', 'SCAN123', 'SCAN123')
        self.make('Sealand', 'SEA017', 'SEA017')
        seen = []
        find_cases(self.root, on_case=lambda case: seen.append((case.outer, len(seen))))
        self.assertEqual(
            [outer for outer, _ in seen],
            [
                os.path.join(self.root, 'Scantraxx', 'SCAN123'),
                os.path.join(self.root, 'Sealand', 'SEA017'),
            ],
        )

    def test_skips_eadir_at_both_levels(self):
        os.makedirs(os.path.join(self.root, '@eaDir'))
        outer = self.make('Scantraxx', 'SCAN123')
        os.makedirs(os.path.join(outer, '@eaDir'))
        cases, oddities = find_cases(self.root)
        self.assertEqual(cases, [])
        self.assertEqual(oddities, [])


class ExecutorTest(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.tmp = tempfile.mkdtemp()
        self.outer = os.path.join(self.tmp, 'SCAN123 EP')
        self.inner = os.path.join(self.outer, 'SCAN123 EP')
        os.makedirs(self.inner)
        self.db = MagicMock()
        self.executor = Executor(self.db)

    def case(self):
        return classify(self.outer, self.inner)

    def test_move_up_moves_files_and_removes_inner(self):
        write(self.inner, '01.mp3')
        write(self.inner, 'cover.jpg')
        old = os.path.join(self.inner, '01.mp3')
        result = self.executor.move_up(self.case())
        self.assertTrue(os.path.isfile(os.path.join(self.outer, '01.mp3')))
        self.assertTrue(os.path.isfile(os.path.join(self.outer, 'cover.jpg')))
        self.assertFalse(os.path.exists(self.inner))
        self.assertEqual(result.clashes, [])
        self.db.delete_paths.assert_called_once()
        self.assertIn(old, self.db.delete_paths.call_args[0][0])

    def test_move_up_never_overwrites_and_keeps_inner(self):
        write(self.outer, 'cover.jpg', 'outer')
        write(self.inner, 'cover.jpg', 'inner')
        write(self.inner, '01.mp3')
        result = self.executor.move_up(self.case())
        with open(os.path.join(self.outer, 'cover.jpg'), encoding='utf-8') as handle:
            self.assertEqual(handle.read(), 'outer')
        self.assertTrue(os.path.isfile(os.path.join(self.inner, 'cover.jpg')))
        self.assertEqual(result.clashes, ['cover.jpg'])
        self.assertTrue(os.path.isdir(self.inner))
        self.assertEqual(self.db.delete_paths.call_args[0][0], [os.path.join(self.inner, '01.mp3')])

    def test_move_up_removes_inner_holding_only_eadir(self):
        write(self.inner, '01.mp3')
        write(os.path.join(self.inner, '@eaDir'), 'thumb.jpg')
        self.executor.move_up(self.case())
        self.assertFalse(os.path.exists(self.inner))

    def test_delete_inner_removes_tree_and_cleans_db(self):
        write(self.outer, '01.mp3')
        write(self.inner, '01.mp3')
        old = os.path.join(self.inner, '01.mp3')
        self.executor.delete_inner(self.case())
        self.assertFalse(os.path.exists(self.inner))
        self.assertTrue(os.path.isfile(os.path.join(self.outer, '01.mp3')))
        self.assertEqual(self.db.delete_paths.call_args[0][0], [old])

    def test_merge_unique_moves_only_unique_then_deletes_rest(self):
        write(self.outer, '01.mp3', 'outer')
        write(self.inner, '01.mp3', 'inner')
        write(self.inner, '02.mp3')
        old_unique = os.path.join(self.inner, '02.mp3')
        old_dup = os.path.join(self.inner, '01.mp3')
        self.executor.merge_unique(self.case())
        self.assertTrue(os.path.isfile(os.path.join(self.outer, '02.mp3')))
        with open(os.path.join(self.outer, '01.mp3'), encoding='utf-8') as handle:
            self.assertEqual(handle.read(), 'outer')
        self.assertFalse(os.path.exists(self.inner))
        deleted = self.db.delete_paths.call_args[0][0]
        self.assertIn(old_unique, deleted)
        self.assertIn(old_dup, deleted)

    def test_dry_run_touches_nothing(self):
        write(self.inner, '01.mp3')
        executor = Executor(self.db, dry_run=True)
        executor.move_up(self.case())
        self.assertTrue(os.path.isfile(os.path.join(self.inner, '01.mp3')))
        self.assertFalse(os.path.exists(os.path.join(self.outer, '01.mp3')))
        self.db.delete_paths.assert_not_called()

    def test_move_up_preserves_nested_structure(self):
        write(os.path.join(self.inner, 'Disc 1'), '02.mp3')
        self.executor.move_up(self.case())
        self.assertTrue(os.path.isfile(os.path.join(self.outer, 'Disc 1', '02.mp3')))
        self.assertFalse(os.path.exists(self.inner))

    def test_vanished_paths_include_nested_subdir_files(self):
        write(self.outer, '01.mp3')
        nested = os.path.join(self.inner, 'Disc 1')
        write(nested, '02.mp3')
        self.executor.delete_inner(self.case())
        self.assertEqual(self.db.delete_paths.call_args[0][0], [os.path.join(nested, '02.mp3')])


class DbCleanerTest(unittest.TestCase):
    def setUp(self):
        patcher = patch('tools.fix_nested_ep_dirs.DatabaseConnector')
        self.addCleanup(patcher.stop)
        self.mock_connector_cls = patcher.start()
        self.mock_connection = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_connection.cursor.return_value.__enter__.return_value = self.mock_cursor
        self.mock_connector_cls.return_value.connect.return_value = self.mock_connection
        self.cleaner = DbCleaner()

    def test_deletes_from_all_three_tables(self):
        self.mock_cursor.rowcount = 1
        self.cleaner.delete_paths(['/mnt/music/EPs/L/EP/EP/01.mp3'])
        statements = [call[0][0] for call in self.mock_cursor.execute.call_args_list]
        self.assertTrue(any('library_media_files' in s for s in statements))
        self.assertTrue(any('library_track_audio_features' in s for s in statements))
        self.assertTrue(any('tagger_processed_files' in s for s in statements))
        self.mock_connection.commit.assert_called_once()
        self.mock_connection.close.assert_called_once()

    def test_media_files_deleted_by_sha256_of_path(self):
        import hashlib

        path = '/mnt/music/EPs/L/EP/EP/01.mp3'
        expected = hashlib.sha256(path.encode('utf-8')).hexdigest()
        self.cleaner.delete_paths([path])
        media_call = [c for c in self.mock_cursor.execute.call_args_list if 'library_media_files' in c[0][0]][0]
        self.assertEqual(media_call[0][1], (expected,))

    def test_empty_path_list_does_not_connect(self):
        self.cleaner.delete_paths([])
        self.mock_connector_cls.return_value.connect.assert_not_called()

    def test_connect_failure_reports_minus_one(self):
        self.mock_connector_cls.return_value.connect.side_effect = RuntimeError('no config')
        self.assertEqual(self.cleaner.delete_paths(['/some/path.mp3']), -1)

    def test_failure_rolls_back_and_closes(self):
        self.mock_cursor.execute.side_effect = Exception('DB Error')
        self.assertEqual(self.cleaner.delete_paths(['/some/path.mp3']), -1)
        self.mock_connection.rollback.assert_called_once()
        self.mock_connection.close.assert_called_once()


class CaseRenderTest(unittest.TestCase):
    def test_describe_marks_unique_inner_files(self):
        case = Case(
            outer='/EPs/L/EP',
            inner='/EPs/L/EP/EP',
            outer_files=['01.mp3'],
            inner_files=['01.mp3', '02.mp3'],
            action=PARTIAL,
        )
        text = case.describe()
        self.assertIn('/EPs/L/EP', text)
        self.assertIn('* 02.mp3', text)
        self.assertIn(PARTIAL, text)


class AutoAnswerTest(unittest.TestCase):
    """The rule a human run always ended up applying: delete when the inner folder adds
    nothing, otherwise lift the files it does add and drop the rest."""

    @staticmethod
    def case(action, outer_files, inner_files):
        return Case(
            outer='/EPs/L/EP',
            inner='/EPs/L/EP/EP',
            outer_files=outer_files,
            inner_files=inner_files,
            action=action,
        )

    def test_deletes_when_inner_holds_nothing_new(self):
        case = self.case(DELETE_DUP, ['01.mp3'], ['01.mp3'])
        self.assertEqual(auto_answer(case), 'd')

    def test_merges_partial_because_the_duplicates_would_clash(self):
        case = self.case(PARTIAL, ['01.mp3'], ['01.mp3', '02.mp3'])
        self.assertEqual(auto_answer(case), 'm')

    def test_merges_move_up_case(self):
        case = self.case(MOVE_UP, ['cover.jpg'], ['01.mp3'])
        self.assertEqual(auto_answer(case), 'm')


if __name__ == '__main__':
    unittest.main()
