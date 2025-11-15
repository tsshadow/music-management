"""Backward compatible module exposing the combined API app."""

from __future__ import annotations

from apps.api.main import app

__all__ = ["app"]
