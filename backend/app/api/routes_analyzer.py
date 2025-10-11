"""Expose analyzer API routes within the backend application."""

from analyzer.api.router import router  # noqa: F401

__all__ = ["router"]
