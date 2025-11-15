"""Shared pipeline helpers used by CLI and API workflows."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set

from api.job_manager import job_manager

from .download import DownloadBatchResult, DownloadService
from .tagging import TaggingOptions, TaggingResult, TaggingService


@dataclass
class StepContext:
    download_service: DownloadService
    tagging_service: TaggingService
    extras: Dict[str, Any] = field(default_factory=dict)
    download_metadata: Optional[DownloadBatchResult] = None
    tagging_results: List[TaggingResult] = field(default_factory=list)

    def record_download(self, result: Optional[DownloadBatchResult]) -> None:
        if not result:
            return
        if self.download_metadata is None:
            self.download_metadata = DownloadBatchResult(list(result.items))
        else:
            self.download_metadata.merge(result)

    def record_tagging(self, result: Optional[TaggingResult]) -> None:
        if not result:
            return
        self.tagging_results.append(result)

    def serialise(self) -> Dict[str, Any]:
        return {
            "downloads": [] if not self.download_metadata else self.download_metadata.as_dict(),
            "tagging": [result.as_dict() for result in self.tagging_results],
        }


@dataclass
class StepDefinition:
    name: str
    selectors: Set[str]
    runner: Callable[[StepContext, Set[str], Dict[str, Any]], Optional[Any]]

    def matches(self, selection: Iterable[str]) -> bool:
        selected = {s.lower() for s in selection}
        return bool(self.selectors & selected) or "all" in selected


def execute_pipeline_step(
    step: StepDefinition,
    selection: Iterable[str],
    context: StepContext,
    options: Dict[str, Any],
) -> Optional[Any]:
    if not step.matches(selection):
        return None
    job_id = job_manager.register(step.name)
    try:
        result = step.runner(context, {s.lower() for s in selection}, options)
        logging.info("%s completed.", step.name)
        job_manager.update(job_id, "completed")
        return result
    except Exception as exc:  # pragma: no cover - defensive logging
        logging.error("%s failed: %s", step.name, exc, exc_info=True)
        job_manager.update(job_id, "failed", str(exc))
    return None


def create_default_steps(
    *,
    extractor,
    renamer,
    mover,
    converter,
    sanitizer,
    flattener,
    analyzer,
    artist_fixer,
    download_service: DownloadService,
    tagging_service: TaggingService,
) -> Sequence[StepDefinition]:
    """Build the default set of pipeline step definitions."""

    return [
        StepDefinition(
            "Extractor",
            {"import", "extract"},
            lambda ctx, _sel, _opts: extractor.run(),
        ),
        StepDefinition(
            "Renamer",
            {"import", "rename"},
            lambda ctx, _sel, _opts: renamer.run(),
        ),
        StepDefinition(
            "Mover",
            {"import", "move"},
            lambda ctx, _sel, _opts: mover.run(),
        ),
        StepDefinition(
            "Converter",
            {"convert"},
            lambda ctx, _sel, _opts: converter.run(),
        ),
        StepDefinition(
            "Sanitizer",
            {"sanitize"},
            lambda ctx, _sel, _opts: sanitizer.run(),
        ),
        StepDefinition(
            "Flattener",
            {"flatten"},
            lambda ctx, _sel, _opts: flattener.run(),
        ),
        StepDefinition(
            "YouTube Downloader",
            {"download", "download-youtube"},
            lambda ctx, _sel, opts: ctx.record_download(
                download_service.download_youtube(
                    account=opts.get("account"),
                    url=opts.get("url"),
                    break_on_existing=opts.get("break_on_existing"),
                    redownload=bool(opts.get("redownload", False)),
                )
            ),
        ),
        StepDefinition(
            "Manual YouTube Downloader",
            {"manual-youtube"},
            lambda ctx, _sel, opts: ctx.record_download(
                download_service.download_youtube(
                    account=opts.get("account"),
                    url=opts.get("url"),
                    break_on_existing=opts.get("break_on_existing"),
                    redownload=bool(opts.get("redownload", False)),
                )
            ),
        ),
        StepDefinition(
            "SoundCloud Downloader",
            {"download", "download-soundcloud"},
            lambda ctx, _sel, opts: ctx.record_download(
                download_service.download_soundcloud(
                    account=opts.get("account"),
                    break_on_existing=opts.get("break_on_existing"),
                    redownload=bool(opts.get("redownload", False)),
                )
            ),
        ),
        StepDefinition(
            "Telegram Downloader",
            {"download-telegram"},
            lambda ctx, _sel, opts: ctx.record_download(
                download_service.download_telegram(
                    channel=opts.get("account") or opts.get("channel", ""),
                    limit=opts.get("limit"),
                )
            ),
        ),
        StepDefinition(
            "Analyze",
            {"analyze"},
            lambda ctx, _sel, _opts: analyzer.run(),
        ),
        StepDefinition(
            "ArtistFixer",
            {"artistfixer"},
            lambda ctx, _sel, _opts: artist_fixer.run(),
        ),
        StepDefinition(
            "Tagger",
            {"tag", "tag-labels", "tag-soundcloud", "tag-youtube", "tag-generic", "tag-telegram"},
            lambda ctx, sel, opts: ctx.record_tagging(
                tagging_service.tag(
                    TaggingOptions.from_selection(sel),
                    metadata=ctx.download_metadata,
                    manual_tags=opts.get("manual_tags"),
                )
            ),
        ),
    ]
