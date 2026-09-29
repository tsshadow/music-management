"""The effective BPM of every track that has one, held in memory for the browse API.

docs/designs/bpm-browse/technical.md, "The index". The effective BPM folds a tag or tempo
into the band of the track's genres -- a rule in Python (`effective.resolve`), not an SQL
expression -- so filtering on it in SQL would mean repeating that rule in SQL. Instead the
inputs are read once (one query, ~90k rows on production, about a second), resolved here, and
kept sorted by tempo; a request then filters and pages in memory and asks the database only for
the details of the one page it returns.

The index is rebuilt at most every `REFRESH_SECONDS`. A request that finds it stale is still
answered from the old one while a background thread rebuilds it (stale-while-revalidate); only
the very first request after a start waits for a build.
"""

from __future__ import annotations

import bisect
import logging
import threading
import time
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from services.music_manager.bpm.effective import CONFIDENCE_RANK, DEFAULT_RELIABLE_CONFIDENCE, resolve

logger = logging.getLogger('music-manager.bpm')

REFRESH_SECONDS = 600.0
#: Separator for the genre names GROUP_CONCAT joins; no curated genre name holds one.
GENRE_SEPARATOR = '|'

#: Every track that is a track (not a set or podcast: a two-hour mix has no one tempo) and has
#: at least one BPM source, with its genres. MAX() because a track can carry more than one
#: audio-features row after a relink.
INDEX_SQL = """
    SELECT t.id AS track_id,
           MAX(af.bpm_tag) AS bpm_tag,
           MAX(af.tempo) AS tempo,
           MAX(m.bpm) AS measured,
           MAX(m.confidence) AS measured_confidence,
           MAX(m.octave_corrected) AS measured_folded,
           GROUP_CONCAT(DISTINCT g.name SEPARATOR '|') AS genres
    FROM library_tracks t
    LEFT JOIN library_track_audio_features af ON af.internal_track_id = t.id
    LEFT JOIN library_track_bpm m ON m.track_uid = t.track_uid AND m.status = 'ok' AND m.bpm IS NOT NULL
    LEFT JOIN library_track_genres tg ON tg.track_id = t.id
    LEFT JOIN rules_genres g ON g.id = tg.genre_id
    WHERE (t.form = 'track' OR t.form IS NULL)
      AND (af.internal_track_id IS NOT NULL OR m.track_uid IS NOT NULL)
    GROUP BY t.id
"""


@dataclass(frozen=True)
class Entry:
    """One track in the index."""

    track_id: int
    bpm: float
    source: str
    confidence: str
    folded: bool
    approximate: bool
    genres: tuple[str, ...]

    def has_genre(self, genre_key: str) -> bool:
        """True when one of the track's genres is `genre_key` (lower-cased)."""
        return any(g.lower() == genre_key for g in self.genres)


class BpmIndex:
    """The entries sorted by tempo, with the filters and counts the API asks for."""

    def __init__(self, entries: Iterable[Entry], built_at: float | None = None):
        self.entries: list[Entry] = sorted(entries, key=lambda e: (e.bpm, e.track_id))
        self._bpms = [e.bpm for e in self.entries]
        self.built_at = time.monotonic() if built_at is None else built_at

    @classmethod
    def from_rows(cls, rows: Iterable[dict], reliable_confidence: float = DEFAULT_RELIABLE_CONFIDENCE) -> BpmIndex:
        """Resolve every row of INDEX_SQL; rows without a usable tempo are left out."""
        entries = []
        for row in rows:
            genres = tuple(g for g in (row.get('genres') or '').split(GENRE_SEPARATOR) if g)
            found = resolve(
                measured=row.get('measured'),
                measured_confidence=row.get('measured_confidence'),
                measured_folded=bool(row.get('measured_folded')),
                tag=row.get('bpm_tag'),
                tempo=row.get('tempo'),
                genres=genres,
                reliable_confidence=reliable_confidence,
            )
            if found is None:
                continue
            entries.append(
                Entry(
                    track_id=int(row['track_id']),
                    bpm=found.bpm,
                    source=found.source,
                    confidence=found.confidence,
                    folded=found.folded,
                    approximate=found.approximate,
                    genres=genres,
                )
            )
        return cls(entries)

    def select(
        self,
        bpm_from: float,
        bpm_to: float,
        *,
        min_confidence: str = 'low',
        genre: str | None = None,
        center: float | None = None,
    ) -> list[Entry]:
        """The entries from `bpm_from` to `bpm_to` inclusive that pass the filters, sorted.

        With a `center` (a picked tempo) the nearest come first, then the more trusted, so the
        exact 150s lead a 148-152 window; without one (a range) they are in tempo order.
        """
        low = bisect.bisect_left(self._bpms, bpm_from)
        high = bisect.bisect_right(self._bpms, bpm_to)
        rank = CONFIDENCE_RANK.get(min_confidence, 0)
        genre_key = genre.strip().lower() if genre and genre.strip() else None
        chosen = [
            e
            for e in self.entries[low:high]
            if CONFIDENCE_RANK[e.confidence] >= rank and (genre_key is None or e.has_genre(genre_key))
        ]
        if center is not None:
            chosen.sort(key=lambda e: (abs(e.bpm - center), -CONFIDENCE_RANK[e.confidence], e.track_id))
        return chosen

    def histogram(
        self, *, min_confidence: str = 'low', genre: str | None = None, low: float = 60.0, high: float = 300.0
    ) -> list[dict]:
        """Track counts per whole BPM from `low` to `high`, split by confidence."""
        rank = CONFIDENCE_RANK.get(min_confidence, 0)
        genre_key = genre.strip().lower() if genre and genre.strip() else None
        bins: dict[int, Counter] = {}
        for e in self.entries[bisect.bisect_left(self._bpms, low) : bisect.bisect_right(self._bpms, high)]:
            if CONFIDENCE_RANK[e.confidence] < rank or (genre_key is not None and not e.has_genre(genre_key)):
                continue
            bins.setdefault(int(round(e.bpm)), Counter())[e.confidence] += 1
        return [
            {'bpm': bpm, 'count': sum(c.values()), 'high': c['high'], 'medium': c['medium'], 'low': c['low']}
            for bpm, c in sorted(bins.items())
        ]

    def genre_counts(self, *, min_confidence: str = 'low', limit: int = 40) -> list[dict]:
        """The genres with the most tracks in the index, for the page's genre picker."""
        rank = CONFIDENCE_RANK.get(min_confidence, 0)
        counts: Counter = Counter()
        for e in self.entries:
            if CONFIDENCE_RANK[e.confidence] >= rank:
                counts.update(set(e.genres))
        return [{'name': name, 'count': count} for name, count in counts.most_common(limit)]

    def summary(self) -> dict[str, Any]:
        """How many tracks the index holds, per source and per confidence."""
        return {
            'tracks': len(self.entries),
            'by_source': dict(Counter(e.source for e in self.entries)),
            'by_confidence': dict(Counter(e.confidence for e in self.entries)),
        }


class IndexCache:
    """One BpmIndex per process, rebuilt in the background once older than `refresh_seconds`."""

    def __init__(
        self,
        load: Callable[[], BpmIndex],
        refresh_seconds: float = REFRESH_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._load = load
        self._refresh_seconds = refresh_seconds
        self._clock = clock
        self._index: BpmIndex | None = None
        self._built_at = 0.0
        self._build_lock = threading.Lock()
        self._refreshing = False

    def get(self) -> BpmIndex:
        """The index: built now when there is none, the old one (refreshing behind it) when stale."""
        index = self._index
        if index is None:
            with self._build_lock:
                if self._index is None:
                    self._store(self._load())
                return self._index  # type: ignore[return-value]
        if self._clock() - self._built_at > self._refresh_seconds and not self._refreshing:
            self._refreshing = True
            threading.Thread(target=self._refresh, name='bpm-index-refresh', daemon=True).start()
        return index

    def _store(self, index: BpmIndex) -> None:
        self._index = index
        self._built_at = self._clock()

    def _refresh(self) -> None:
        """Rebuild behind the current index; a failure keeps the old one and retries next time."""
        try:
            with self._build_lock:
                self._store(self._load())
        except Exception:  # pylint: disable=broad-except  # a failed refresh must not lose the index
            logger.exception('bpm: rebuilding the browse index failed; serving the previous one')
        finally:
            self._refreshing = False

    def invalidate(self) -> None:
        """Forget the index; the next request builds a fresh one. Tests use this."""
        self._index = None
        self._built_at = 0.0
