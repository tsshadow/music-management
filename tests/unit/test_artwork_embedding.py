"""The artwork backfill against real mutagen, in a subprocess.

`services/tests/mock_base.py` replaces `mutagen` with a bare module for every test under
`services/`, which is right for the tagger and fatal here: `embed_artwork` dispatches on
`isinstance(audio, FLAC | MP4 | ID3FileType)`, and against stubs every branch misses and the
"no way to carry a picture" fallback would pass for every format. Whether the stub is in place
depends on collection order, so importing real mutagen at the top of this file is not enough.

A child interpreter has a clean `sys.modules`, which is the same reason
`services/downloader/tests/test_account_snapshot.py` reads a row in one. What is proved here
is the part a mocked test cannot reach: a picture put in by `embed_artwork` comes back out of
`has_artwork`, per container, and a file that already has one is recognised.
"""

import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run_with_real_mutagen(body: str):
    """Run `body` in a child interpreter and return its stdout, failing the test on a crash."""
    script = textwrap.dedent(
        """
        import sys
        sys.path.insert(0, {root!r})
        from services.downloader.artwork import embed_artwork, has_artwork, mime_type
        from mutagen.flac import FLAC, Picture
        from mutagen.id3 import APIC, ID3
        from mutagen.mp3 import MP3
        from mutagen.mp4 import MP4, MP4Cover

        JPEG = b'\\xff\\xd8\\xff' + b'\\x00' * 4000
        PNG = b'\\x89PNG\\r\\n\\x1a\\n' + b'\\x00' * 4000

        def empty(cls):
            # A FLAC that never parsed a file has no `metadata_blocks`, and `pictures` walks it.
            audio = cls()
            if cls is FLAC:
                audio.metadata_blocks = []
            return audio
        """
    ).format(root=str(ROOT)) + textwrap.dedent(body)
    result = subprocess.run(  # noqa: S603 - a fixed interpreter and a literal script
        [sys.executable, '-c', script],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, f'child failed:\n{result.stdout}\n{result.stderr}'
    return result.stdout.strip()


def test_every_container_takes_a_picture_and_reports_it_back():
    output = run_with_real_mutagen(
        """
        for cls in (FLAC, MP4, MP3):
            audio = empty(cls)
            assert not has_artwork(audio), cls.__name__ + ' started with artwork'
            assert embed_artwork(audio, JPEG), cls.__name__ + ' refused a picture'
            assert has_artwork(audio), cls.__name__ + ' did not report the picture back'
        print('ok')
        """
    )
    assert output == 'ok'


def test_the_bytes_and_the_cover_type_survive_per_container():
    output = run_with_real_mutagen(
        """
        flac = empty(FLAC)
        embed_artwork(flac, PNG)
        picture = flac.pictures[0]
        assert picture.data == PNG and picture.mime == 'image/png' and picture.type == 3

        mp4 = empty(MP4)
        embed_artwork(mp4, PNG)
        cover = mp4.tags['covr'][0]
        assert bytes(cover) == PNG and cover.imageformat == MP4Cover.FORMAT_PNG

        mp3 = empty(MP3)
        embed_artwork(mp3, JPEG)
        frame = mp3.tags.getall('APIC')[0]
        assert frame.data == JPEG and frame.mime == 'image/jpeg' and frame.type == 3
        print('ok')
        """
    )
    assert output == 'ok'


def test_a_file_that_already_has_a_cover_is_recognised_per_container():
    output = run_with_real_mutagen(
        """
        flac = empty(FLAC)
        picture = Picture()
        picture.type, picture.mime, picture.data = 3, 'image/jpeg', JPEG
        flac.add_picture(picture)
        assert has_artwork(flac)

        mp4 = empty(MP4)
        mp4.add_tags()
        mp4.tags['covr'] = [MP4Cover(JPEG, imageformat=MP4Cover.FORMAT_JPEG)]
        assert has_artwork(mp4)

        mp3 = empty(MP3)
        mp3.tags = ID3()
        mp3.tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=JPEG))
        assert has_artwork(mp3)
        print('ok')
        """
    )
    assert output == 'ok'


def test_an_unknown_container_is_left_alone_rather_than_written_to():
    output = run_with_real_mutagen(
        """
        class Unknown:
            tags = None

        # "It has one" is the safe answer: a container this module cannot describe is skipped
        # by the backfill instead of being written to on a guess.
        assert has_artwork(Unknown())
        assert not embed_artwork(Unknown(), JPEG)
        assert mime_type(JPEG) == 'image/jpeg' and mime_type(PNG) == 'image/png'
        print('ok')
        """
    )
    assert output == 'ok'
