"""services/common/audio_less_folder.py: which release folders hold no audio, and the guarded delete.

GitLab issue #167. The mover deletes a queue folder that holds only scene files. Everything here
checks the rule leans towards keeping: audio at any depth, an archive not yet extracted, an unknown
file, a link, an empty or unreadable folder, and anything outside the import queue all stay.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from services.common import audio_less_folder as alf
from services.common.import_queue import ImportQueue


def make(root: Path, *names: str) -> Path:
    """`root` with each relative file name in `names` created (directories as needed)."""
    root.mkdir(parents=True, exist_ok=True)
    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'x')
    return root


@pytest.fixture
def queue(tmp_path) -> ImportQueue:
    path = tmp_path / 'EPs' / '__TODO'
    path.mkdir(parents=True)
    return ImportQueue(str(path))


class InspectTest:
    def test_only_scene_files_is_audio_less(self, tmp_path):
        folder = make(tmp_path / 'R', '00-r.m3u', '00-r.jpg', '00-r.nfo', '00-r.sfv')

        verdict = alf.inspect(str(folder))

        assert verdict.audio_less
        assert verdict.files == ('00-r.jpg', '00-r.m3u', '00-r.nfo', '00-r.sfv')

    def test_os_housekeeping_and_synology_thumbnails_count_as_companions(self, tmp_path):
        folder = make(tmp_path / 'R', '00-r.nfo', 'Thumbs.db', '.DS_Store', '@eaDir/00-r.jpg/SYNOFILE_THUMB_M.jpg')

        verdict = alf.inspect(str(folder))

        assert verdict.audio_less
        assert '@eaDir/00-r.jpg/SYNOFILE_THUMB_M.jpg' not in verdict.files

    @pytest.mark.parametrize(
        'track', ['01-a.mp3', '01-a.FLAC', '01-a.m4a', '01-a.wav', '01-a.ogg', '01-a.opus', '01-a.aiff']
    )
    def test_any_audio_file_keeps_the_folder(self, tmp_path, track):
        folder = make(tmp_path / 'R', '00-r.m3u', track)

        assert alf.inspect(str(folder)).kind == alf.HOLDS_AUDIO

    def test_audio_in_a_disc_sub_folder_keeps_the_folder(self, tmp_path):
        folder = make(tmp_path / 'R', '00-r.nfo', 'CD1/00-cd1.m3u', 'CD2/deeper/01-a.flac')

        verdict = alf.inspect(str(folder))

        assert verdict.kind == alf.HOLDS_AUDIO
        assert verdict.detail == os.path.join('CD2', 'deeper', '01-a.flac')

    @pytest.mark.parametrize('archive', ['r.zip', 'r.rar', 'r.part1.rar', 'r.r00', 'r.7z', 'r.tar.gz'])
    def test_an_archive_not_yet_extracted_keeps_the_folder(self, tmp_path, archive):
        folder = make(tmp_path / 'R', '00-r.nfo', archive)

        assert alf.inspect(str(folder)).kind == alf.HOLDS_ARCHIVE

    def test_an_archive_in_a_sub_folder_keeps_the_folder(self, tmp_path):
        folder = make(tmp_path / 'R', '00-r.nfo', 'CD1/cd1.rar')

        assert alf.inspect(str(folder)).kind == alf.HOLDS_ARCHIVE

    @pytest.mark.parametrize('other', ['clip.mkv', '02-a.mp3.part', 'unknown.xyz'])
    def test_an_unknown_file_keeps_the_folder(self, tmp_path, other):
        folder = make(tmp_path / 'R', '00-r.nfo', other)

        verdict = alf.inspect(str(folder))

        assert verdict.kind == alf.HOLDS_OTHER
        assert verdict.detail == other

    def test_an_empty_folder_is_not_judged_audio_less(self, tmp_path):
        folder = make(tmp_path / 'R')
        (folder / 'empty-sub').mkdir()

        assert alf.inspect(str(folder)).kind == alf.EMPTY

    def test_a_missing_folder_is_unreadable_not_audio_less(self, tmp_path):
        assert alf.inspect(str(tmp_path / 'nowhere')).kind == alf.UNREADABLE

    def test_a_linked_sub_folder_keeps_the_folder(self, tmp_path):
        elsewhere = make(tmp_path / 'elsewhere', '01-a.mp3')
        folder = make(tmp_path / 'R', '00-r.nfo')
        (folder / 'CD1').symlink_to(elsewhere, target_is_directory=True)

        assert alf.inspect(str(folder)).kind == alf.HOLDS_LINK

    def test_a_linked_file_keeps_the_folder(self, tmp_path):
        target = make(tmp_path / 'elsewhere', 'x.nfo') / 'x.nfo'
        folder = make(tmp_path / 'R', '00-r.nfo')
        (folder / 'link.nfo').symlink_to(target)

        assert alf.inspect(str(folder)).kind == alf.HOLDS_LINK

    def test_the_folder_itself_as_a_link_is_kept(self, tmp_path):
        real = make(tmp_path / 'real', '00-r.nfo')
        (tmp_path / 'R').symlink_to(real, target_is_directory=True)

        assert alf.inspect(str(tmp_path / 'R')).kind == alf.HOLDS_LINK


class DeleteFromQueueTest:
    def test_an_audio_less_folder_in_the_queue_is_deleted(self, queue):
        folder = make(Path(queue.path) / 'HCL116 - Release', '00-r.m3u', '00-r.jpg')

        verdict = alf.delete_from_queue(queue, str(folder))

        assert verdict is not None and verdict.audio_less
        assert not folder.exists()

    def test_a_folder_with_audio_is_kept(self, queue):
        folder = make(Path(queue.path) / 'R', '00-r.m3u', '01-a.mp3')

        assert alf.delete_from_queue(queue, str(folder)) is None
        assert folder.exists()

    def test_a_folder_with_audio_in_a_sub_folder_is_kept(self, queue):
        folder = make(Path(queue.path) / 'R', '00-r.m3u', 'CD1/01-a.mp3')

        assert alf.delete_from_queue(queue, str(folder)) is None
        assert (folder / 'CD1' / '01-a.mp3').exists()

    def test_a_folder_with_an_unextracted_archive_is_kept(self, queue):
        folder = make(Path(queue.path) / 'R', '00-r.nfo', 'r.rar')

        assert alf.delete_from_queue(queue, str(folder)) is None
        assert folder.exists()

    def test_a_label_tree_folder_is_never_deleted(self, queue):
        label_release = make(Path(queue.path).parent / 'Scantraxx' / 'SCAN123 - R', '00-r.nfo')

        assert alf.delete_from_queue(queue, str(label_release)) is None
        assert label_release.exists()

    def test_a_folder_nested_deeper_in_the_queue_is_not_a_release_of_it(self, queue):
        nested = make(Path(queue.path) / 'Pack' / 'R', '00-r.nfo')

        assert alf.delete_from_queue(queue, str(nested)) is None
        assert nested.exists()

    def test_the_queue_itself_is_never_deleted(self, queue):
        make(Path(queue.path), '00-stray.nfo')

        assert alf.delete_from_queue(queue, queue.path) is None
        assert os.path.isdir(queue.path)

    def test_a_dot_dot_path_cannot_leave_the_queue(self, queue):
        outside = make(Path(queue.path).parent / 'Outside', '00-r.nfo')

        assert alf.delete_from_queue(queue, os.path.join(queue.path, '..', 'Outside')) is None
        assert outside.exists()

    def test_a_link_in_the_queue_to_a_folder_elsewhere_is_never_followed(self, queue, tmp_path):
        outside = make(tmp_path / 'elsewhere', '00-r.nfo')
        link = Path(queue.path) / 'R'
        link.symlink_to(outside, target_is_directory=True)

        assert alf.delete_from_queue(queue, str(link)) is None
        assert (outside / '00-r.nfo').exists()

    def test_without_a_queue_nothing_is_deleted(self, tmp_path):
        folder = make(tmp_path / 'R', '00-r.nfo')

        assert alf.delete_from_queue(ImportQueue(''), str(folder)) is None
        assert folder.exists()


def test_the_extractor_names_the_same_companion_kinds():
    """The extractor's warnings and this rule share one list of images and documents."""
    from services.importer import extractor

    assert extractor.IMAGE_EXTENSIONS is alf.IMAGE_EXTENSIONS
    assert extractor.DOCUMENT_EXTENSIONS is alf.DOCUMENT_EXTENSIONS
    assert extractor.IGNORED_NAMES is alf.IGNORED_NAMES
    suffixes = {suffix for suffix, _signature in extractor.ARCHIVE_SIGNATURES}
    assert all(name.endswith(alf.ARCHIVE_EXTENSIONS) for name in suffixes)
