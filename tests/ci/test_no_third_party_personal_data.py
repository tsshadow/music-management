"""No tracked file names a private person who is not the owner (issue #189, step 7).

The banned words are stored as sha256 digests so this file does not contain them. Every
tracked text file is split into lowercase words ([a-z0-9]+); a word whose digest is on the
list fails the test. Add a digest here when a new person's name or account turns up in the
repository.
"""

import hashlib
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

BANNED_SHA256 = {
    '25becee34cc33552d364365b7f5e698b1831ab6b2c57f33a286098f916085be3',
    '3b9e72334ed1a154b98fb44db70a003593a298a0132ec0f8658cd776963cd404',
}

WORD = re.compile(r'[a-z0-9]+')


def _tracked_files() -> list[str]:
    """Return the tracked file paths of the checkout."""
    out = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, check=True, capture_output=True).stdout
    return [p for p in out.decode().split('\0') if p]


def test_no_banned_word_in_tracked_files():
    """Fail on any tracked text file that holds a word from the banned digest list."""
    hits = []
    for rel in _tracked_files():
        path = ROOT / rel
        if not path.is_file():
            continue
        data = path.read_bytes()
        if b'\0' in data[:4096]:
            continue
        text = data.decode('utf-8', 'ignore').lower()
        for word in set(WORD.findall(text)):
            if hashlib.sha256(word.encode()).hexdigest() in BANNED_SHA256:
                hits.append(rel)
                break
    assert not hits, f'personal data of a third person in: {hits}'
