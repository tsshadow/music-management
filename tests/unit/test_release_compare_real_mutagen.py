"""Duplicate-release detection against real mutagen and real audio, in a child interpreter.

`is_same_release` compares two copies of a release by track list and track length, because
the copy in the library has been retagged since it arrived and no longer matches a fresh
download byte for byte. Under `services/` mutagen is a stub (`services/tests/mock_base.py`)
with no `File` at all, so the length comparison there falls back to sizes and the part that
matters -- reading a real length out of a real, retagged file -- cannot be exercised. A child
interpreter has a clean `sys.modules`, the same reason `test_artwork_embedding.py` uses one.
"""

import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'tests' / 'fixtures' / 'music' / 'ci-test-track-001.mp3'


def run_with_real_mutagen(body: str) -> str:
    """Run `body` in a child interpreter with the helpers below, returning its stdout."""
    script = textwrap.dedent(
        """
        import os, shutil, sys, tempfile, wave
        sys.path.insert(0, {root!r})
        from mutagen.id3 import ID3, TXXX
        from services.common.Helpers import ReleaseFolder
        from services.common.Helpers.ReleaseFolder import is_same_release

        work = tempfile.mkdtemp()

        def release(name, files):
            folder = os.path.join(work, name, 'REL001 - Release')
            os.makedirs(folder)
            for filename, make in files.items():
                make(os.path.join(folder, filename))
            return folder

        def tone(seconds):
            def make(path):
                with wave.open(path, 'wb') as handle:
                    handle.setnchannels(1)
                    handle.setsampwidth(2)
                    handle.setframerate(8000)
                    handle.writeframes(bytes(2 * 8000 * seconds))
            return make

        def fixture(retagged=False):
            def make(path):
                shutil.copyfile({fixture!r}, path)
                if retagged:
                    # What LabelSong does after the move: more tags than the padding holds.
                    tags = ID3(path)
                    tags.add(TXXX(encoding=3, desc='COMMENT', text=['x' * 20000]))
                    tags.save(path)
            return make
        """
    ).format(root=str(ROOT), fixture=str(FIXTURE)) + textwrap.dedent(body)
    result = subprocess.run(  # noqa: S603 - a fixed interpreter and a literal script
        [sys.executable, '-c', script],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, f'child failed:\n{result.stdout}\n{result.stderr}'
    return result.stdout.strip()


def test_a_retagged_library_copy_of_an_mp3_release_is_the_same_release():
    output = run_with_real_mutagen(
        """
        src = release('import', {'01.mp3': fixture()})
        dst = release('library', {'01.mp3': fixture(retagged=True)})
        a, b = os.path.join(src, '01.mp3'), os.path.join(dst, '01.mp3')
        print(os.path.getsize(a) != os.path.getsize(b))
        print(ReleaseFolder.audio_length(a) is not None)
        print(is_same_release(src, dst))
        """
    )
    assert output.splitlines() == ['True', 'True', 'True']


def test_tracks_of_different_length_are_a_different_release():
    output = run_with_real_mutagen(
        """
        src = release('import', {'01.wav': tone(2)})
        dst = release('library', {'01.wav': tone(5)})
        print(round(ReleaseFolder.audio_length(os.path.join(src, '01.wav')), 1))
        print(is_same_release(src, dst))
        """
    )
    assert output.splitlines() == ['2.0', 'False']


def test_a_release_missing_a_track_is_a_different_release():
    output = run_with_real_mutagen(
        """
        src = release('import', {'01.wav': tone(2)})
        dst = release('library', {'01.wav': tone(2), '02.wav': tone(3)})
        print(is_same_release(src, dst))
        """
    )
    assert output == 'False'
