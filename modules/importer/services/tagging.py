"""Tagging service integrating Tagger with download metadata."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from postprocessing.constants import SongTypeEnum
from postprocessing.tagger import Tagger

from .download import DownloadBatchResult


@dataclass
class TaggingOptions:
    parse_labels: bool = True
    parse_soundcloud: bool = True
    parse_youtube: bool = True
    parse_generic: bool = True
    parse_telegram: bool = True

    def should_parse(self, song_type: SongTypeEnum) -> bool:
        mapping = {
            SongTypeEnum.LABEL: self.parse_labels,
            SongTypeEnum.SOUNDCLOUD: self.parse_soundcloud,
            SongTypeEnum.YOUTUBE: self.parse_youtube,
            SongTypeEnum.TELEGRAM: self.parse_telegram,
            SongTypeEnum.GENERIC: self.parse_generic,
        }
        return mapping.get(song_type, True)

    @classmethod
    def from_selection(cls, selected: Iterable[str]) -> "TaggingOptions":
        selected_set = {step.lower() for step in selected}
        parse_all = "tag" in selected_set or "all" in selected_set
        return cls(
            parse_labels=parse_all or "tag-labels" in selected_set,
            parse_soundcloud=parse_all or "tag-soundcloud" in selected_set,
            parse_youtube=parse_all or "tag-youtube" in selected_set,
            parse_generic=parse_all or "tag-generic" in selected_set,
            parse_telegram=parse_all or "tag-telegram" in selected_set,
        )


@dataclass(frozen=True)
class TaggingRecord:
    song_type: SongTypeEnum
    target: Path
    manual_tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class TaggingResult:
    processed: List[TaggingRecord] = field(default_factory=list)
    used_metadata: bool = False

    def as_dict(self) -> Dict[str, List[Dict[str, str]]]:
        return {
            "processed": [
                {
                    "song_type": record.song_type.name,
                    "target": str(record.target),
                    **({} if not record.manual_tags else {"manual_tags": record.manual_tags}),
                }
                for record in self.processed
            ],
            "used_metadata": self.used_metadata,
        }


class TaggingService:
    """Higher level entry point for tagging operations."""

    def __init__(self, tagger: Tagger) -> None:
        self._tagger = tagger

    def tag(
        self,
        options: TaggingOptions,
        metadata: Optional[DownloadBatchResult] = None,
        manual_tags: Optional[Dict[str, str]] = None,
    ) -> TaggingResult:
        processed: List[TaggingRecord] = []
        used_metadata = False

        if metadata and metadata.items:
            used_metadata = True
            for item in metadata.items:
                if not item.song_type or not item.target_dir:
                    continue
                if not options.should_parse(item.song_type):
                    continue
                self._tagger.parse_folder(item.target_dir, item.song_type)
                processed.append(
                    TaggingRecord(
                        song_type=item.song_type,
                        target=item.target_dir,
                        manual_tags=manual_tags or {},
                    )
                )
            return TaggingResult(processed=processed, used_metadata=used_metadata)

        self._tagger.run(
            parse_labels=options.parse_labels,
            parse_soundcloud=options.parse_soundcloud,
            parse_youtube=options.parse_youtube,
            parse_generic=options.parse_generic,
            parse_telegram=options.parse_telegram,
        )
        return TaggingResult(processed=processed, used_metadata=used_metadata)
