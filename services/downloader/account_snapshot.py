"""How complete an account is, as of the end of one deep pass.

Its own module and not part of `deep_sweep` for one reason: `deep_sweep` imports yt-dlp at
the top, and the manager container -- which reads these snapshots for the Coverage page
-- does not ship yt-dlp. The page answered "No module named 'yt_dlp'" the first evening it
was live. Nothing here needs the downloader; it is a record and its three states.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

SNAPSHOT_COMPLETE = 'complete'
SNAPSHOT_CAPPED = 'capped'
SNAPSHOT_PARKED = 'parked'


@dataclass(frozen=True)
class AccountSnapshot:
    """A partition of the listing, not the report's running totals.

    Every listed id is in exactly one of held, excluded and remaining, so the
    three add up to listed and a percentage read off them means something. The
    report's `held` is the archive before the pass and its `written_off` counts
    expired decisions too; neither survives being stored and read back a month
    later.
    """

    listed: int
    held: int
    excluded: int
    remaining: int
    state: str
    taken_at: datetime

    @property
    def coverage(self) -> float | None:
        if self.listed <= 0:
            return None
        return self.held / self.listed
