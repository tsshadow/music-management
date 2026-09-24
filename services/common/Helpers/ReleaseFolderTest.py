import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from services.common.Helpers import ReleaseFolder
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


def _lengths(by_name: dict[str, float | None]):
    """A stand-in for `mutagen.File` that knows each file's length by its content."""

    def read(path):
        with open(path, encoding='utf-8') as handle:
            length = by_name.get(handle.read())
        if length is None:
            return None
        return SimpleNamespace(info=SimpleNamespace(length=length))

    return read


class SameReleaseByTrackLengthTest(unittest.TestCase):
    """Two copies of a release are compared on their track lists and track lengths, not on bytes.

    The copy already in the library has been retagged by `LabelSong` since it was moved
    there, so its files grew or shrank as soon as the new tags stopped fitting the old
    padding. A second download of the same release never matched it by size, and the
    mover logged "contents differ ... manual intervention" about it on every cycle.
    """

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__('shutil').rmtree(self.root, ignore_errors=True))
        # File contents stand for recordings: 'take-a' and its retagged copy are the same
        # 180 s; 'take-b' is a different, longer edit; 'broken' cannot be read at all.
        reader = _lengths({'take-a': 180.0, 'take-a retagged': 180.4, 'take-b': 240.0, 'broken': None})
        patcher = patch.object(ReleaseFolder.mutagen, 'File', reader, create=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def pair(self, src_files, dst_files):
        src = _release(os.path.join(self.root, 'import'), 'REL', src_files)
        dst = _release(os.path.join(self.root, 'eps'), 'REL', dst_files)
        return src, dst

    def test_a_retagged_library_copy_is_the_same_release(self):
        src, dst = self.pair({'01.mp3': 'take-a'}, {'01.mp3': 'take-a retagged'})
        self.assertNotEqual(os.path.getsize(os.path.join(src, '01.mp3')), os.path.getsize(os.path.join(dst, '01.mp3')))
        self.assertTrue(is_same_release(src, dst))
        self.assertEqual(move_release_folder(src, dst), DUPLICATE)

    def test_a_different_length_is_a_different_release(self):
        src, dst = self.pair({'01.mp3': 'take-a'}, {'01.mp3': 'take-b'})
        self.assertFalse(is_same_release(src, dst))

    def test_a_missing_track_is_a_different_release(self):
        src, dst = self.pair({'01.mp3': 'take-a'}, {'01.mp3': 'take-a', '02.mp3': 'take-b'})
        self.assertFalse(is_same_release(src, dst))

    def test_files_that_are_not_tracks_do_not_count(self):
        src, dst = self.pair(
            {'01.mp3': 'take-a', '00-release.nfo': 'scene nfo'},
            {'01.mp3': 'take-a retagged', 'folder.jpg': 'cover the artwork backfill added'},
        )
        self.assertTrue(is_same_release(src, dst))

    def test_one_readable_and_one_unreadable_track_are_different(self):
        src, dst = self.pair({'01.mp3': 'take-a'}, {'01.mp3': 'broken'})
        self.assertFalse(is_same_release(src, dst))

    def test_audio_length_is_none_for_a_reader_that_raises(self):
        with patch.object(ReleaseFolder.mutagen, 'File', side_effect=ValueError('bad header'), create=True):
            self.assertIsNone(ReleaseFolder.audio_length(os.path.join(self.root, 'anything.mp3')))


if __name__ == '__main__':
    unittest.main()
