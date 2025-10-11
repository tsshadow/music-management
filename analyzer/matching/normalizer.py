"""String normalisation helpers used by the analyzer."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Iterable

from unidecode import unidecode

__all__ = ["normalize_text", "normalize_tokens", "duration_bucket"]

_WHITESPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[\u2018\u2019\u201c\u201d\-\u2014()]+")
_REMIX_RE = re.compile(r"\(([^)]*remix[^)]*)\)", re.IGNORECASE)
_FEAT_RE = re.compile(r"\bfeat(?:\.|uring)?\b", re.IGNORECASE)


@lru_cache(maxsize=4096)
def normalize_text(value: str | None) -> str:
    """Return a deterministic normalised string for identifier generation."""

    if not value:
        return ""
    stripped = value.strip().lower()
    ascii_only = unidecode(stripped)
    without_punct = _PUNCT_RE.sub(" ", ascii_only)
    collapsed = _WHITESPACE_RE.sub(" ", without_punct).strip()
    without_feat = _FEAT_RE.sub("feat", collapsed)
    without_remix = _REMIX_RE.sub("", without_feat).strip()
    return without_remix


def normalize_tokens(tokens: Iterable[str | None]) -> str:
    """Normalise and join multiple text tokens."""

    parts = [normalize_text(token) for token in tokens if token]
    return " ".join(part for part in parts if part)


def duration_bucket(duration: int | None, tolerance: int = 2) -> str:
    """Return a duration bucket string with a configurable tolerance."""

    if duration is None:
        return "na"
    if tolerance < 1:
        tolerance = 1
    bucket = round(duration / tolerance) * tolerance
    return str(int(bucket))
