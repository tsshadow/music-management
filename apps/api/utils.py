"""Shared helpers for the combined API application."""

from __future__ import annotations

import logging
import os
import subprocess


def ensure_yt_dlp_is_updated() -> None:
    """Update yt-dlp unless explicitly disabled.

    The importer depends on yt-dlp for YouTube downloads. Historically this
    update ran during application startup; we keep the behaviour but make it
    reusable for different entrypoints.
    """

    if os.getenv("SKIP_YT_DLP_UPDATE"):
        logging.info("Skipping yt-dlp update because SKIP_YT_DLP_UPDATE is set")
        return

    try:
        subprocess.run(
            ["pip", "install", "--upgrade", "yt-dlp", "--break-system-packages"],
            check=True,
        )
    except subprocess.CalledProcessError as exc:  # pragma: no cover - defensive
        logging.error("Failed to install yt-dlp: %s", exc)


__all__ = ["ensure_yt_dlp_is_updated"]
