"""The SoundCloud post-processor chain against real yt-dlp, ffmpeg and mutagen (bug report 088).

The SoundCloud downloader runs FFmpegMetadata and then EmbedThumbnail. For an mp3 the
latter remuxes the file with `-id3v2_version 3`; ffmpeg keeps month and day through that
only for a `YYYY-MM-DD` date, so yt-dlp's undelimited `upload_date` (`20260831`) came out
as `2026`. Nothing mocked can show that -- it lives in ffmpeg's ID3 writer -- so this runs
the real post-processors on a generated mp3 in a child interpreter (the same reason
test_artwork_embedding.py does) and reads the date back the way the tagger does.

Skips when ffmpeg or yt-dlp is absent; the tooling image backend:unit runs in has both.
"""

import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.skipif(shutil.which('ffmpeg') is None, reason='needs ffmpeg')

CHAIN = """
import os, subprocess, sys, tempfile
sys.path.insert(0, {root!r})
try:
    from yt_dlp import YoutubeDL
    from yt_dlp.postprocessor import EmbedThumbnailPP, FFmpegMetadataPP
except ImportError:
    print('no-yt-dlp')
    raise SystemExit(0)
from mutagen.easyid3 import EasyID3
from services.downloader.metadata_date import IsoUploadDatePP

work = tempfile.mkdtemp()
mp3 = os.path.join(work, 'track.mp3')
jpg = os.path.join(work, 'track.jpg')
quiet = ['ffmpeg', '-loglevel', 'error', '-y']
subprocess.run(quiet + ['-f', 'lavfi', '-i', 'sine=frequency=440:duration=1', '-c:a', 'libmp3lame', mp3], check=True)
subprocess.run(quiet + ['-f', 'lavfi', '-i', 'color=c=red:s=64x64:d=1', '-frames:v', '1', jpg], check=True)

info = {{
    'id': '1', 'title': 'Track', 'ext': 'mp3', 'filepath': mp3, 'upload_date': '20260831',
    'thumbnails': [{{'id': '0', 'filepath': jpg}}], '__files_to_move': {{}},
}}
ydl = YoutubeDL({{'quiet': True, 'noprogress': True}})
if {with_fix}:
    _, info = IsoUploadDatePP(ydl).run(info)
for pp in (FFmpegMetadataPP(ydl), EmbedThumbnailPP(ydl)):
    _, info = pp.run(info)
print(EasyID3(mp3).get('date', [''])[0])
"""


def chain_date(with_fix: bool) -> str:
    """The DATE the tagger would read after the downloader's post-processors ran."""
    script = textwrap.dedent(CHAIN).format(root=str(ROOT), with_fix=with_fix)
    result = subprocess.run(  # noqa: S603 - a fixed interpreter and a literal script
        [sys.executable, '-c', script],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, f'child failed:\n{result.stdout}\n{result.stderr}'
    output = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ''
    if output == 'no-yt-dlp':
        pytest.skip('needs yt-dlp')
    return output


def test_the_undelimited_upload_date_is_cut_to_the_year_by_the_thumbnail_step():
    """The defect itself, kept so a yt-dlp or ffmpeg change that removes it is noticed."""
    assert chain_date(with_fix=False) == '2026'


def test_the_full_date_survives_the_chain_with_the_delimited_upload_date():
    assert chain_date(with_fix=True) == '2026-08-31'
