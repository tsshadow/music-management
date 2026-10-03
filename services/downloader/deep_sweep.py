"""Finding the tracks an account lists and the archive does not hold.

The ordinary sweep stops at the first track it already has, which is what keeps
it cheap and what makes a gap permanent: a run cut short by a 429 leaves the rest
of that account behind, and every later run stops above the hole.

A deep pass asks a different question. It lists the account flat -- ids only, 200
per request, nothing resolved -- subtracts what the archive already holds and what
has been deliberately written off, and resolves only what is left. The cost then
follows the size of the gap rather than the size of the account, which is the
whole reason this can run at all: without the break, the same answer used to cost
one full metadata request per track on the account, on every single run.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime

from yt_dlp import YoutubeDL

from services.downloader.account_report import detect_http_status
from services.downloader.account_snapshot import (  # noqa: F401 - re-exported for the passes and their tests
    SNAPSHOT_CAPPED,
    SNAPSHOT_COMPLETE,
    SNAPSHOT_PARKED,
    AccountSnapshot,
)
from services.downloader.write_offs import WriteOff, still_written_off

# Read the listing, resolve none of it. A flat entry carries an id, a title and a
# url and nothing else -- the extractor yields a bare url_result and never builds
# the full info dict -- which is exactly what makes this affordable.
FLAT_OPTS = {
    'extract_flat': 'in_playlist',
    'lazy_playlist': True,
    'skip_download': True,
    'simulate': True,
    'quiet': True,
}

# Options that would hide the very entries we are counting. `break_on_existing`
# raises at the first archived track, which is the expected case here, and
# `download_archive` makes yt-dlp skip such an entry outright. The rest only
# matter to a real download. Everything else -- the cookies, the user agent, the
# proxy -- is kept, because a listing has to present the same client a download
# would, or the anti-bot layer answers it differently.
_DROPPED_OPTS = (
    'download_archive',
    'break_on_existing',
    'match_filter',
    'outtmpl',
    'format',
    'playlistend',
    'postprocessors',
)


@dataclass(frozen=True)
class FlatTrack:
    """One entry of a flat listing: everything the API page gives us."""

    track_id: str
    url: str
    title: str | None = None


@dataclass(frozen=True)
class DeepSweepReport:
    """What one account's deep pass found, and whether it finished.

    The numbers are the audit. An account is complete when every track it lists
    is either held or written off, and this says so in arithmetic rather than in
    hope.
    """

    listed: int
    held: int
    written_off: int
    wanted: int
    downloaded: int = 0
    capped: bool = False
    parked: bool = False

    @property
    def complete(self) -> bool:
        """Whether nothing is left to fetch for this account."""
        if self.capped or self.parked:
            return False
        return self.downloaded >= self.wanted

    def summary(self) -> str:
        return (
            f'{self.listed} listed, {self.held} held, '
            f'{self.written_off} written off, {self.wanted} wanted, '
            f'{self.downloaded} fetched'
        )


def snapshot_state(report: DeepSweepReport, interrupted: bool = False) -> str:
    """How far the pass got: parked and interrupted both mean "not to the end".

    A stop request is not a rate limit -- the settle still charges the track it
    was on -- but for the count it is the same thing: the tail was not reached.
    """
    if report.parked or interrupted:
        return SNAPSHOT_PARKED
    if report.capped:
        return SNAPSHOT_CAPPED
    return SNAPSHOT_COMPLETE


def take_snapshot(
    listing: Iterable[FlatTrack],
    held: set[str],
    arrived: set[str],
    write_offs: Mapping[str, WriteOff],
    retry_days: int,
    now: datetime,
    bounds: tuple[int, int] | None,
    state: str,
) -> AccountSnapshot:
    """Partition the listing after the pass: held, excluded, or still to fetch.

    `held` is the archive as it was before the pass and may carry ids from the
    text archive that the listing never mentioned; only listed ids count. What
    `arrived` names is held now. `write_offs` must be re-read after the pass so
    the failures it recorded are in it -- an id that is both held and written off
    is held, which is what `wanted_tracks` decides too.
    """
    # One entry per id: a listing that repeats an id would otherwise make the
    # three parts add up to more than the ids there are.
    first_by_id: dict[str, FlatTrack] = {}
    for entry in listing:
        first_by_id.setdefault(entry.track_id, entry)
    listing = list(first_by_id.values())
    held_now = {entry.track_id for entry in listing if entry.track_id in held or entry.track_id in arrived}
    remaining = wanted_tracks(listing, held_now, write_offs, retry_days, now, bounds)
    listed = len(listing)
    return AccountSnapshot(
        listed=listed,
        held=len(held_now),
        excluded=listed - len(held_now) - len(remaining),
        remaining=len(remaining),
        state=state,
        taken_at=now,
    )


def wanted_tracks(
    listing: Iterable[FlatTrack],
    held: set[str],
    write_offs: Mapping[str, WriteOff],
    retry_days: int,
    now: datetime,
    bounds: tuple[int, int] | None,
) -> list[FlatTrack]:
    """The listed tracks that are neither held nor still written off.

    Listing order is kept, which means newest first: a pass that is cut short
    gets through the recent end before the tail, and the tail is what the next
    pass resumes on.
    """
    wanted = []
    for entry in listing:
        if entry.track_id in held:
            continue
        recorded = write_offs.get(entry.track_id)
        if recorded is not None and still_written_off(recorded, retry_days, now, bounds):
            continue
        wanted.append(entry)
    return wanted


class ListingFailed(Exception):
    """A flat listing that did not come back, as opposed to one that came back empty.

    The two used to look identical. yt-dlp ran with the caller's ``ignoreerrors``,
    turned a 403 on the listing into a line on stderr and returned ``None``; the
    pass read that as "nothing listed", counted zero wanted and zero fetched, and
    marked the account deep-swept for another ``deep_sweep_days``. ``status`` is
    the HTTP status yt-dlp's own text reports (403, 429), or None when it reports
    none -- read from the reason alone, so an account whose name happens to
    contain "403" cannot park the source.
    """

    def __init__(self, url: str, reason: str) -> None:
        super().__init__(f'Could not list {url}: {reason}')
        self.url = url
        self.reason = reason
        self.status = detect_http_status(reason)


def list_flat(url: str, base_opts: dict, limit: int | None = None, ydl_factory=YoutubeDL) -> list[FlatTrack]:
    """Every track the URL lists, as ids and permalinks.

    Raises `ListingFailed` when the listing itself did not come back; only the
    caller knows whether that should park the source or fall through to the
    ordinary run. ``ignoreerrors`` is forced off for this one call, whatever the
    caller's options say: under it yt-dlp reports a refused page on stderr and
    returns nothing, which is indistinguishable from an account with no tracks.
    """
    opts = {key: value for key, value in base_opts.items() if key not in _DROPPED_OPTS}
    opts.update(FLAT_OPTS)
    opts['ignoreerrors'] = False
    if limit is not None:
        opts['playlistend'] = limit
    try:
        with ydl_factory(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:
        raise ListingFailed(url, str(exc)) from exc
    if info is None:
        raise ListingFailed(url, 'yt-dlp returned no listing')
    tracks = []
    for entry in info.get('entries') or []:
        entry = entry or {}
        track_id = entry.get('id')
        if track_id is None:
            continue
        tracks.append(FlatTrack(str(track_id), entry.get('url') or '', entry.get('title')))
    return tracks


def ids_in_text_archive(path: str | None) -> set[str]:
    """The ids in a yt-dlp download archive file.

    yt-dlp consults this file itself, so a track listed here is one it will
    silently refuse to download again. Leaving it out of the known set would
    queue such a track on every pass and never see it downloaded and never see it
    rejected -- an account that can never be finished.
    """
    if not path or not os.path.isfile(path):
        return set()
    found = set()
    try:
        with open(path, encoding='utf-8') as handle:
            for line in handle:
                parts = line.split()
                if parts:
                    found.add(parts[-1])
    except OSError as exc:
        logging.warning('Could not read the download archive %s: %s', path, exc)
    return found
