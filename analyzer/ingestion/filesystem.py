"""Filesystem scanner that registers media files in the library."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from mutagen import File as MutagenFile
from mutagen.easyid3 import EasyID3  # type: ignore

from analyzer.services.library_service import LibraryService

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".mp3", ".flac", ".m4a", ".ogg", ".wav", ".opus"}

for key, frame in (
    ("label", "TPUB"),
    ("publisher", "TPUB"),
    ("catalogusnumber", "TXXX:CATALOGUSNUMBER"),
    ("festival", "TXXX:FESTIVAL"),
):
    try:
        EasyID3.RegisterTextKey(key, frame)
    except KeyError:
        # Key already registered by mutagen; safe to ignore.
        pass


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
            metadata = await loop.run_in_executor(None, _collect_file_metadata, file_path)
            try:
                track_id = await _register_track_from_metadata(library, metadata, file_path)
            except Exception as exc:  # pragma: no cover - defensive guard for ingest failures
                logger.exception("Failed to upsert track metadata for %s: %s", file_path, exc)
                track_id = None
            payload = dict(metadata)
            if track_id is not None:
                payload["linked_track_id"] = track_id
            payload["size"] = stat_result.st_size
            payload["mtime"] = stat_result.st_mtime
            media_id = await library.register_media_file(
                file_path=str(file_path),
                file_size=stat_result.st_size,
                file_mtime=datetime.fromtimestamp(stat_result.st_mtime),
                audio_hash=None,
                duration=metadata.get("duration"),
                metadata=payload,
            )
            registered.append(media_id)
    return registered


def _collect_file_metadata(file_path: Path) -> dict[str, Any]:
    """Return normalized metadata extracted from the audio file."""

    metadata: dict[str, Any] = {}
    tags: dict[str, list[str]] = {}
    try:
        easy_audio = MutagenFile(file_path, easy=True)
    except Exception:
        easy_audio = None
    if easy_audio and getattr(easy_audio, "tags", None):
        for raw_key, raw_values in easy_audio.tags.items():
            values = raw_values if isinstance(raw_values, list) else [raw_values]
            cleaned = [str(value).strip() for value in values if str(value).strip()]
            if cleaned:
                tags[raw_key.lower()] = cleaned

    def first(key: str) -> str | None:
        values = tags.get(key.lower())
        return values[0] if values else None

    def multi(key: str) -> list[str]:
        values = tags.get(key.lower(), [])
        return _unique(_split_multi(values))

    metadata["title"] = first("title")
    metadata["album"] = first("album")
    metadata["album_artist"] = first("albumartist") or first("album artist")
    metadata["artists"] = multi("artist")
    metadata["genres"] = multi("genre")
    metadata["track_number"] = _parse_number(first("tracknumber"))
    metadata["disc_number"] = _parse_number(first("discnumber"))
    metadata["year"] = _parse_year(first("date") or first("originaldate") or first("year"))
    labels = multi("label") + multi("publisher") + multi("organization")
    metadata["labels"] = _unique(labels)
    metadata["catalog_number"] = first("catalogusnumber")
    metadata["festival"] = first("festival")

    try:
        detailed_audio = MutagenFile(file_path)
    except Exception:
        detailed_audio = None

    if metadata.get("catalog_number") is None:
        metadata["catalog_number"] = _extract_custom_tag(
            getattr(detailed_audio, "tags", None),
            "CATALOGUSNUMBER",
        )
    if metadata.get("festival") is None:
        metadata["festival"] = _extract_custom_tag(
            getattr(detailed_audio, "tags", None),
            "FESTIVAL",
        )
    if not metadata["labels"]:
        custom_label = _extract_custom_tag(getattr(detailed_audio, "tags", None), "PUBLISHER")
        if custom_label:
            metadata["labels"] = [custom_label]

    duration = None
    for source in (easy_audio, detailed_audio):
        length = getattr(getattr(source, "info", None), "length", None)
        if length:
            duration = int(round(length))
            break
    metadata["duration"] = duration
    return {key: value for key, value in metadata.items() if value not in (None, [], "")}


async def _register_track_from_metadata(
    library: LibraryService,
    metadata: dict[str, Any],
    file_path: Path,
) -> int | None:
    """Create or update normalized track metadata based on extracted tags."""

    title = metadata.get("title") or file_path.stem
    artists = metadata.get("artists", [])
    album_artist = metadata.get("album_artist")
    primary_artist_name = album_artist or (artists[0] if artists else None) or "Unknown Artist"
    primary_artist_id = await library.upsert_artist(primary_artist_name)

    album_id = None
    album_title = metadata.get("album")
    if album_title:
        album_artist_name = album_artist or primary_artist_name
        album_artist_id = await library.upsert_artist(album_artist_name)
        album_id = await library.upsert_album(
            title=album_title,
            artist_id=album_artist_id,
            year=metadata.get("year"),
        )

    track_id = await library.upsert_track(
        title=title,
        primary_artist_id=primary_artist_id,
        duration=metadata.get("duration"),
        album_id=album_id,
        mbid=None,
        isrc=None,
        acoustid=None,
        track_uid=None,
    )

    artist_relations = []
    seen_ids: set[int] = set()
    artist_relations.append((primary_artist_id, "primary"))
    seen_ids.add(primary_artist_id)
    for index, name in enumerate(artists):
        artist_id = await library.upsert_artist(name)
        if artist_id in seen_ids:
            continue
        role = "primary" if index == 0 and artist_id == primary_artist_id else "featured"
        artist_relations.append((artist_id, role))
        seen_ids.add(artist_id)
    if artist_relations:
        await library.link_track_artists(track_id, artist_relations)

    genres = metadata.get("genres", [])
    if genres:
        genre_ids = [await library.upsert_genre(name) for name in genres]
        if genre_ids:
            await library.link_track_genres(track_id, genre_ids)

    labels = metadata.get("labels", [])
    if labels:
        label_ids = [await library.upsert_label(name) for name in labels]
        if label_ids:
            await library.link_track_labels(track_id, label_ids)

    catalog_number = metadata.get("catalog_number")
    if catalog_number:
        await library.set_track_attribute(
            track_id,
            key="catalog_number",
            value=catalog_number,
            source="analyzer_scan",
        )

    festival = metadata.get("festival")
    if festival:
        await library.set_track_attribute(
            track_id,
            key="festival",
            value=festival,
            source="analyzer_scan",
        )

    return track_id


def _split_multi(values: list[str]) -> list[str]:
    parts: list[str] = []
    for value in values:
        tokens = re.split(r"[;,]", value)
        for token in tokens:
            text = token.strip()
            if text:
                parts.append(text)
    return parts


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _parse_number(value: str | None) -> int | None:
    if not value:
        return None
    match = re.match(r"(\d+)", value)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _parse_year(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"(\d{4})", value)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _extract_custom_tag(tags: Any, key: str) -> str | None:
    if not tags:
        return None
    upper_key = key.upper()
    if hasattr(tags, "getall"):
        if upper_key == "PUBLISHER":
            frame = tags.get("TPUB")
            if frame is not None:
                for text in getattr(frame, "text", []) or []:
                    value = str(text).strip()
                    if value:
                        return value
        try:
            frames = tags.getall("TXXX")
        except AttributeError:
            frames = []
        for frame in frames:
            desc = getattr(frame, "desc", "")
            if desc and desc.strip().upper() == upper_key:
                for text in getattr(frame, "text", []) or []:
                    value = str(text).strip()
                    if value:
                        return value
    if hasattr(tags, "items"):
        target = upper_key.lower()
        for raw_key, raw_value in tags.items():
            normalized = str(raw_key).strip().lower()
            if normalized != target:
                continue
            values = raw_value if isinstance(raw_value, (list, tuple)) else [raw_value]
            for text in values:
                value = str(text).strip()
                if value:
                    return value
    for candidate in {key, upper_key, key.lower()}:
        try:
            values = tags[candidate]
        except Exception:
            values = tags.get(candidate) if hasattr(tags, "get") else None
        if not values:
            continue
        if isinstance(values, (list, tuple)):
            for text in values:
                value = str(text).strip()
                if value:
                    return value
        else:
            value = str(values).strip()
            if value:
                return value
    return None
