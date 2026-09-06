import os
import tempfile
import unittest
from pathlib import Path

from services.common.Helpers.ReleaseFolder import CONFLICT, DUPLICATE, MOVED, is_same_release, move_release_folder


def _release(root: str, name: str, files: dict[str, str]) -> str:
    folder = Path(root) / name
    folder.mkdir(parents=True)
    for filename, content in files.items():
        (folder / filename).write_text(content)
    return str(folder)


class MoveReleaseFolderTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__('shutil').rmtree(self.root, ignore_errors=True))
        os.makedirs(os.path.join(self.root, 'eps'))

    def test_a_free_destination_is_a_plain_move(self):
        src = _release(os.path.join(self.root, 'import'), 'REL001', {'01.flac': 'aa'})
        dst = os.path.join(self.root, 'eps', 'REL001')

        self.assertEqual(move_release_folder(src, dst), MOVED)
        self.assertTrue(os.path.exists(os.path.join(dst, '01.flac')))
        self.assertFalse(os.path.exists(src))

    def test_an_occupied_destination_is_never_moved_into(self):
        """This is the whole point: shutil.move would put src *inside* dst.

        It does not raise while doing it, so the release ends up at dst/REL001/ and the
        next scan indexes it twice. 552 folders on production contain themselves.
        """
        src = _release(os.path.join(self.root, 'import'), 'REL001', {'01.flac': 'aa'})
        dst = _release(os.path.join(self.root, 'eps'), 'REL001', {'01.flac': 'aa'})

        result = move_release_folder(src, dst)

        self.assertEqual(result, DUPLICATE)
        self.assertFalse(os.path.exists(os.path.join(dst, 'REL001')))
        self.assertTrue(os.path.exists(src), 'the caller decides whether a duplicate may go')

    def test_a_destination_holding_something_else_is_a_conflict(self):
        src = _release(os.path.join(self.root, 'import'), 'REL001', {'01.flac': 'aa'})
        dst = _release(os.path.join(self.root, 'eps'), 'REL001', {'01.flac': 'a different track'})

        self.assertEqual(move_release_folder(src, dst), CONFLICT)
        self.assertFalse(os.path.exists(os.path.join(dst, 'REL001')))
        self.assertTrue(os.path.exists(src))

    def test_the_same_names_with_different_sizes_are_different_releases(self):
        src = _release(os.path.join(self.root, 'a'), 'REL', {'01.flac': 'aa'})
        dst = _release(os.path.join(self.root, 'b'), 'REL', {'01.flac': 'aaaa'})

        self.assertFalse(is_same_release(src, dst))

    def test_an_unreadable_folder_counts_as_different(self):
        src = _release(os.path.join(self.root, 'a'), 'REL', {'01.flac': 'aa'})

        self.assertFalse(is_same_release(src, os.path.join(self.root, 'does-not-exist')))


if __name__ == '__main__':
    unittest.main()
