"""Utilities to build deterministic track identifiers."""

from __future__ import annotations

import hashlib

from .normalizer import duration_bucket, normalize_tokens

__all__ = ["make_track_uid"]


def make_track_uid(
    artist: str | None,
    title: str | None,
    album: str | None = None,
    duration: int | None = None,
) -> str:
    """Return a deterministic SHA1 hash based on normalised metadata."""

    normalized = "|".join(
        [
            normalize_tokens([artist]),
            normalize_tokens([title]),
            normalize_tokens([album]),
            duration_bucket(duration),
        ]
    )
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()
