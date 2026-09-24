"""A retag of an already-tagged file must write nothing, proved against real mutagen.

`services/tests/mock_base.py` replaces `mutagen` for every test under `services/`, so no test
there can see what actually lands on disk -- which is exactly where these defects lived:

- mutagen writes a bare m4a atom name as exactly 4 bytes, so `REMIXER` and `ORIGINAL_TITLE`
  landed as `REMI`/`ORIG` and were never read back; every m4a with a remixer was rewritten on
  every retag, and title inference re-ran on the already-cleaned title.
- `ALBUM_ARTIST` went to `TALB` (an ID3 frame name) and `ALBUM` to a freeform atom, so LMS saw
  neither on an m4a the tagger wrote.
- `Tag` split every value on '/', turning 'AC/DC' into two artists and a title into three values.
- `CheckArtistRule` mutated the artist list it iterated, moving a corrected first artist to
  the end -- a new primary artist, and a new order again on the next pass.

As in `test_artwork_embedding.py`, the work runs in a child interpreter: whether the mutagen stub
is installed depends on collection order, and a child has a clean `sys.modules`.
"""

import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MP3_FIXTURE = ROOT / 'tests' / 'fixtures' / 'music' / 'ci-test-track-001.mp3'
M4A_FIXTURE = Path(__file__).resolve().parent / 'fixtures' / 'tone.m4a'

PRELUDE = """
import os
import shutil
import sys
import tempfile

os.environ.setdefault('delimiter', '/')
sys.path.insert(0, {root!r})
sys.path.insert(1, {services!r})

from mutagen.id3 import ID3
from mutagen.mp4 import MP4, MP4FreeForm

from services.tagger.constants import (
    ALBUM, ALBUM_ARTIST, ARTIST, ORIGINAL_TITLE, REMIXER, TITLE,
)
from services.tagger.Song.BaseSong import BaseSong
from services.tagger.Song.rules.CheckArtistRule import CheckArtistRule

MP3_FIXTURE = {mp3!r}
M4A_FIXTURE = {m4a!r}

WRITTEN = {{
    ARTIST: ['ANGERFIST', 'outsiders', 'Dj Mad Dog'],
    TITLE: ['AC/DC Tribute (Live 24/7)'],
    REMIXER: ['Dj Mad Dog'],
    ORIGINAL_TITLE: ['Angerfist - AC/DC Tribute (Live 24/7)'],
    ALBUM: ['Thunderdome 2025/2026'],
    ALBUM_ARTIST: ['Various Artists'],
}}
CANONICAL_ARTISTS = ['Angerfist', 'Outsiders', 'Dj Mad Dog']


class CasingTable:
    # A library_artists stand-in that canonicalises casing, like the real table does.
    names = {{name.lower(): name for name in CANONICAL_ARTISTS}}

    def exists(self, name):
        return name.lower() in self.names

    def get(self, name):
        return self.names[name.lower()]


class NothingIgnored:
    # A rules_ignored_artists stand-in with no entries.
    def get_corrected(self, _name):
        return None

    def exists(self, _name):
        return False


def copy_fixture(source):
    directory = tempfile.mkdtemp()
    target = os.path.join(directory, 'track' + os.path.splitext(source)[1])
    shutil.copy(source, target)
    return target


def read_back(path):
    tags = BaseSong(path).tag_collection
    return {{key: list(tags.get_item_as_array(key)) for key in WRITTEN}}


def write_initial(path):
    song = BaseSong(path)
    for key, value in WRITTEN.items():
        song.tag_collection.add(key, ';'.join(value))
    assert song.save_file(), 'the initial write must write'


def retag(path):
    song = BaseSong(path)
    CheckArtistRule(CasingTable(), NothingIgnored()).apply(song)
    return song.save_file()


def snapshot(path):
    with open(path, 'rb') as handle:
        return handle.read()


def check_idempotent(path):
    write_initial(path)
    assert read_back(path) == WRITTEN, read_back(path)
    assert retag(path), 'the first retag canonicalises the casing, so it writes'
    expected = dict(WRITTEN, **{{ARTIST: CANONICAL_ARTISTS}})
    assert read_back(path) == expected, read_back(path)
    before = snapshot(path)
    assert not retag(path), 'the second retag must not write'
    assert snapshot(path) == before, 'the second retag changed the bytes on disk'
    assert read_back(path) == expected, read_back(path)
"""


def run_with_real_mutagen(body: str) -> str:
    """Run `body` after PRELUDE in a child interpreter; fail the test on a crash."""
    script = PRELUDE.format(
        root=str(ROOT),
        services=str(ROOT / 'services'),
        mp3=str(MP3_FIXTURE),
        m4a=str(M4A_FIXTURE),
    ) + textwrap.dedent(body)
    result = subprocess.run(  # noqa: S603 - a fixed interpreter and a literal script
        [sys.executable, '-c', script],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        # A scratch working directory, so a stray broken-files.log never lands in the checkout.
        cwd=tempfile.mkdtemp(),
    )
    assert result.returncode == 0, f'child failed:\n{result.stdout}\n{result.stderr}'
    return result.stdout.strip()


def test_an_mp3_retag_is_idempotent_and_keeps_order_and_slashes():
    output = run_with_real_mutagen(
        """
        path = copy_fixture(MP3_FIXTURE)
        check_idempotent(path)
        # The ID3 side is unchanged by this fix: the custom names stay TXXX frames.
        frames = ID3(path)
        print(sorted(key for key in frames.keys() if key.startswith('TXXX:')))
        print(frames['TPE1'].text, frames['TIT2'].text, frames['TALB'].text, frames['TPE2'].text)
        """
    )
    txxx, text = output.splitlines()
    # The fixture carries its own TXXX:MUSIC_MANAGEMENT_ID beside these.
    assert "'TXXX:original_title', 'TXXX:remixer'" in txxx
    assert text == (
        "['Angerfist;Outsiders;Dj Mad Dog'] ['AC/DC Tribute (Live 24/7)'] ['Thunderdome 2025/2026'] ['Various Artists']"
    )


def test_an_m4a_retag_is_idempotent_and_uses_the_right_atoms():
    output = run_with_real_mutagen(
        """
        path = copy_fixture(M4A_FIXTURE)
        check_idempotent(path)
        atoms = MP4(path).tags
        for key in sorted(atoms.keys()):
            value = atoms[key][0]
            print(key, '=', value.decode() if isinstance(value, bytes) else value)
        """
    )
    atoms = dict(line.split(' = ', 1) for line in output.splitlines())
    assert atoms['©ART'] == 'Angerfist;Outsiders;Dj Mad Dog'
    assert atoms['©nam'] == 'AC/DC Tribute (Live 24/7)'
    assert atoms['©alb'] == 'Thunderdome 2025/2026'
    assert atoms['aART'] == 'Various Artists'
    assert atoms['----:com.apple.iTunes:REMIXER'] == 'Dj Mad Dog'
    assert atoms['----:com.apple.iTunes:ORIGINAL_TITLE'] == 'Angerfist - AC/DC Tribute (Live 24/7)'
    for truncated in ('REMI', 'ORIG', 'TALB', '----:com.apple.iTunes:ALBUM'):
        assert truncated not in atoms, truncated


def test_legacy_m4a_atoms_migrate_on_the_next_retag_and_then_stay_put():
    output = run_with_real_mutagen(
        """
        path = copy_fixture(M4A_FIXTURE)
        # What earlier versions left on disk: mutagen truncates the bare names itself.
        audio = MP4(path)
        if audio.tags is None:
            audio.add_tags()
        audio.tags['\\u00a9ART'] = 'Angerfist'
        audio.tags['REMIXER'] = 'Dj Mad Dog'
        audio.tags['ORIGINAL_TITLE'] = 'Angerfist - Raise Your Fist'
        audio.tags['TALB'] = 'Various Artists'
        audio.tags['----:com.apple.iTunes:ALBUM'] = [MP4FreeForm(b'Youtube (Masters of Hardcore)')]
        audio.save()
        assert {'REMI', 'ORIG', 'TALB'} <= set(MP4(path).tags.keys()), MP4(path).tags.keys()

        legacy = read_back(path)
        assert legacy[REMIXER] == ['Dj Mad Dog'], legacy
        assert legacy[ORIGINAL_TITLE] == ['Angerfist - Raise Your Fist'], legacy
        assert legacy[ALBUM_ARTIST] == ['Various Artists'], legacy
        assert legacy[ALBUM] == ['Youtube (Masters of Hardcore)'], legacy

        assert retag(path), 'the migration is a write'
        assert read_back(path) == legacy, read_back(path)
        before = snapshot(path)
        assert not retag(path), 'a migrated file must not be written again'
        assert snapshot(path) == before
        print(sorted(MP4(path).tags.keys()))
        """
    )
    assert output == str(
        sorted(
            [
                '©ART',
                '©alb',
                'aART',
                '----:com.apple.iTunes:ORIGINAL_TITLE',
                '----:com.apple.iTunes:REMIXER',
            ]
        )
    )
