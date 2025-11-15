"""Router registration helpers for the shared API."""

from .importer import register_importer
from .scrobbler import register_scrobbler

__all__ = ["register_importer", "register_scrobbler"]
