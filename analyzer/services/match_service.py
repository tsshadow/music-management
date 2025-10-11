"""Match listens against known tracks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator, Sequence

from analyzer.db.repo import AnalyzerRepository
from analyzer.matching.uid import make_track_uid

__all__ = ["MatchResult", "MatchCandidate", "MatchService"]


@dataclass(slots=True)
class MatchCandidate:
    track_id: int
    confidence: int


@dataclass(slots=True)
class MatchResult:
    status: str
    track_id: int | None
    confidence: int | None
    candidates: Sequence[MatchCandidate]


class MatchService:
    """Provide deterministic and fuzzy listen matching."""

    def __init__(self, repo: AnalyzerRepository) -> None:
        self.repo = repo

    async def deterministic_match(
        self,
        *,
        artist: str | None,
        title: str | None,
        album: str | None,
        duration: int | None,
    ) -> MatchResult:
        uid = make_track_uid(artist=artist, title=title, album=album, duration=duration)
        track = await self.repo.find_track_by_uid(uid)
        if track:
            return MatchResult(status="matched", track_id=track["id"], confidence=100, candidates=[])
        return MatchResult(status="unmatched", track_id=None, confidence=None, candidates=[])

    async def find_candidates(
        self,
        *,
        artist: str | None,
        title: str | None,
        duration: int | None,
        limit: int = 5,
    ) -> AsyncIterator[MatchCandidate]:
        results = await self.repo.search_tracks_by_metadata(
            artist=artist, title=title, duration=duration, limit=limit
        )
        for track_id, confidence in results:
            yield MatchCandidate(track_id=track_id, confidence=confidence)
