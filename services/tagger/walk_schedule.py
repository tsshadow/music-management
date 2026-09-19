"""When the folder walk is due.

The five-minute round serves the queue; the walk -- every folder, every file, `stat` and
a table lookup each -- is the safety net for a file nobody announced, and it needs to run
once a day, not every round. The moment of the last walk is kept on disk rather than in
memory because the process restarts on every deploy, and five deploys in one night used
to mean five walks that each started over at EPs.
"""

import logging
import os
import time
from pathlib import Path

logger = logging.getLogger('music-manager.tagger')


class WalkSchedule:
    #: Where the timestamp lives. MUMA_SERVER_DB_ROOT is the container's persistent data
    #: directory (/app/data on the deployment); `data/` is where ConfigStore keeps its
    #: file when that is unset, so the two travel together.
    FILENAME = 'tagger_last_walk'

    def __init__(self, interval_hours: float, path: str | Path | None = None):
        self.interval_hours = float(interval_hours or 0)
        self.path = Path(path) if path else Path(os.getenv('MUMA_SERVER_DB_ROOT') or 'data') / self.FILENAME

    def last_walk_at(self) -> float | None:
        """Epoch seconds of the last completed walk, or None when there never was one."""
        try:
            return float(self.path.read_text(encoding='utf-8').strip())
        except (FileNotFoundError, ValueError):
            return None
        except OSError as e:
            logger.warning('Could not read %s: %s', self.path, e)
            return None

    def due(self, now: float | None = None) -> bool:
        """True when the walk should run this round.

        An interval of 0 is the old behaviour: every round. Otherwise the walk runs when
        the last one is older than the interval -- and *not* on a fresh install with no
        record, because on a first start the queue is the work and the walk would push it
        back by hours. `record` after the first queue-only round starts the clock.
        """
        if self.interval_hours <= 0:
            return True
        last = self.last_walk_at()
        if last is None:
            self.record(now)
            return False
        return (now if now is not None else time.time()) - last >= self.interval_hours * 3600

    def record(self, now: float | None = None) -> None:
        """Note that a walk finished (or, on first start, that the clock started) now."""
        stamp = now if now is not None else time.time()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(f'{stamp:.0f}\n', encoding='utf-8')
        except OSError as e:
            # Without a record the next round walks again; noisy, not fatal.
            logger.warning('Could not record the walk in %s: %s', self.path, e)
