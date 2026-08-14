"""Asking SoundCloud one question: what is this account's newest track?

A full check pages an account's entire catalogue before it can conclude there is
nothing new -- 28 API requests for an account with five thousand tracks, whether
or not anything changed. This asks for a single flat entry instead, which costs
one request whatever the size of the account, and that is enough to answer
"anything new?" in the case where the answer is almost always no.

A flat entry carries an id, a title and a url and nothing else: the SoundCloud
extractor yields a bare ``url_result`` for a user's tracks page and never builds
the full info dict, so there is no upload timestamp to be had here. The date
comes from the full run instead.
"""
from __future__ import annotations

from dataclasses import dataclass

from yt_dlp import YoutubeDL

# Read exactly one entry, and resolve none of it.
_PROBE_OPTS = {
    'extract_flat': 'in_playlist',
    'lazy_playlist': True,
    'playlistend': 1,
    'skip_download': True,
    'simulate': True,
    'quiet': True,
}

# Options that would hide the very thing we are looking for. `break_on_existing`
# raises as soon as it meets an archived track, which is the expected case here,
# and `download_archive` makes yt-dlp skip the entry outright. The rest only
# matter to a real download.
_DROPPED_OPTS = ('download_archive', 'break_on_existing', 'match_filter',
                 'outtmpl', 'format')


@dataclass(frozen=True)
class ProbeResult:
    """The newest track of one account, as far as a flat listing can tell."""
    track_id: str
    title: str | None
    url: str | None


def newest_track(account: str, base_opts: dict, ydl_factory=YoutubeDL) -> ProbeResult | None:
    """The account's newest track, or None when it has none we can see.

    Errors are raised rather than swallowed: only the caller knows whether a 403
    should park the source or simply fall through to a full run.
    """
    opts = {key: value for key, value in base_opts.items() if key not in _DROPPED_OPTS}
    opts.update(_PROBE_OPTS)
    url = f'https://soundcloud.com/{account}/tracks'
    with ydl_factory(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    entries = (info or {}).get('entries') or []
    if not entries:
        return None
    entry = entries[0] or {}
    track_id = entry.get('id')
    if track_id is None:
        return None
    return ProbeResult(str(track_id), entry.get('title'), entry.get('url'))
