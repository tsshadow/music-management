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

What "flat" means lives in `services.downloader.deep_sweep`, which the deep pass
uses to read the same listing without a limit. One definition, two questions.
"""
from __future__ import annotations

from dataclasses import dataclass

from yt_dlp import YoutubeDL

from services.downloader.deep_sweep import list_flat


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
    url = f'https://soundcloud.com/{account}/tracks'
    tracks = list_flat(url, base_opts, limit=1, ydl_factory=ydl_factory)
    if not tracks:
        return None
    first = tracks[0]
    return ProbeResult(first.track_id, first.title, first.url)
