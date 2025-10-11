"""Filesystem scanner that registers media files in the library."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Iterable

from analyzer.services.library_service import LibraryService

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".mp3", ".flac", ".m4a", ".ogg", ".wav", ".opus"}


async def scan_paths(
    library: LibraryService,
    paths: Iterable[str],
    *,
    force: bool = False,
) -> list[int]:
    """Scan filesystem paths and register media files."""

    registered: list[int] = []
    loop = asyncio.get_running_loop()
    for root in paths:
        base = Path(root)
        if not base.exists():
            logger.warning("Path %s does not exist", root)
            continue
        for file_path in base.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            stat_result = await loop.run_in_executor(None, file_path.stat)
            metadata = {
                "size": stat_result.st_size,
                "mtime": stat_result.st_mtime,
            }
            media_id = await library.register_media_file(
                file_path=str(file_path),
                file_size=stat_result.st_size,
                file_mtime=datetime.fromtimestamp(stat_result.st_mtime),
                audio_hash=None,
                duration=None,
                metadata=metadata,
            )
            registered.append(media_id)
    return registered
