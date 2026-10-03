"""List the video files that never should have ended up in the audio tree.

`/mnt/music/Youtube` is the audio target: every download there runs through
FFmpegExtractAudio and comes out as m4a. The mp4/webm/mkv files that are sitting
in it are what stayed behind when that extraction failed, plus the `.fNNN`
fragments of downloads whose video and audio streams were never merged. All of
them are 640x360, because that is the one progressive stream YouTube still
serves and what yt-dlp falls back to when it cannot merge.

This only reports. Deleting is a separate decision and a separate command; the
listing tells you which files and how many bytes are involved.

Usage:
    python -m tools.list_youtube_video_residue [--folder /mnt/music/Youtube]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from typing import cast

VIDEO_EXTENSIONS = ('.mp4', '.webm', '.mkv', '.flv')

# yt-dlp names an unmerged stream after its format id, e.g. "Track.f616.mp4".
FRAGMENT_RE = re.compile(r'\.f\d+\.[a-z0-9]+$', re.IGNORECASE)

# yt-dlp's placeholder when title extraction failed, e.g. "youtube video #abc123".
PLACEHOLDER_TITLE_RE = re.compile(r'.+ video #[0-9A-Za-z_-]+$')


def probe_resolution(path: str) -> str:
    """Return "WIDTHxHEIGHT", or "?" when ffprobe cannot say."""
    try:
        result = subprocess.run(
            [
                'ffprobe',
                '-v',
                'error',
                '-select_streams',
                'v:0',
                '-show_entries',
                'stream=width,height',
                '-of',
                'json',
                path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        streams = json.loads(result.stdout).get('streams') or []
        if not streams:
            return '?'
        return f"{streams[0].get('width', '?')}x{streams[0].get('height', '?')}"
    except Exception:
        return '?'


def scan(folder: str, probe: bool = True) -> list[dict]:
    findings = []
    for root, _dirs, files in os.walk(folder):
        for name in files:
            if not name.lower().endswith(VIDEO_EXTENSIONS):
                continue
            path = os.path.join(root, name)
            try:
                size = os.path.getsize(path)
            except OSError:
                size = 0
            stem = os.path.splitext(name)[0]
            findings.append(
                {
                    'path': path,
                    'size': size,
                    'fragment': bool(FRAGMENT_RE.search(name)),
                    'placeholder_title': bool(PLACEHOLDER_TITLE_RE.match(stem)),
                    'resolution': probe_resolution(path) if probe else '-',
                }
            )
    findings.sort(key=lambda entry: cast(str, entry['path']))
    return findings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--folder',
        default=os.environ.get('youtube_folder', '/mnt/music/Youtube'),
        help='The audio download tree to scan.',
    )
    parser.add_argument('--no-probe', action='store_true', help='Skip ffprobe; much faster, but no resolutions.')
    args = parser.parse_args()

    findings = scan(args.folder, probe=not args.no_probe)
    if not findings:
        print(f'No stray video files under {args.folder}.')
        return

    total = 0
    for entry in findings:
        total += entry['size']
        flags = []
        if entry['fragment']:
            flags.append('unmerged fragment')
        if entry['placeholder_title']:
            flags.append('placeholder title')
        suffix = f"  [{', '.join(flags)}]" if flags else ''
        print(f"{entry['resolution']:>10}  {entry['size'] / 1024 / 1024:8.1f} MB  {entry['path']}{suffix}")

    fragments = sum(1 for entry in findings if entry['fragment'])
    print(
        f'\n{len(findings)} stray video files, {fragments} of them unmerged fragments, '
        f'{total / 1024 / 1024 / 1024:.2f} GB in total.'
    )
    print('Nothing was deleted. Remove what you do not want by hand.')


if __name__ == '__main__':
    main()
