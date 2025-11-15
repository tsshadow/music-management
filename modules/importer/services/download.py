"""Download service orchestrating downloader classes."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from data.settings import Settings
from downloader.soundcloud import SoundcloudDownloader
from downloader.telegram import TelegramDownloader
from downloader.youtube import YoutubeDownloader
from postprocessing.constants import SongTypeEnum


@dataclass(frozen=True)
class DownloadItem:
    """Metadata describing downloaded content for downstream processing."""

    source: str
    target_dir: Optional[Path]
    song_type: Optional[SongTypeEnum]
    identifier: Optional[str] = None
    extra: Dict[str, str] = field(default_factory=dict)


@dataclass
class DownloadBatchResult:
    """Container for one or multiple :class:`DownloadItem` instances."""

    items: List[DownloadItem] = field(default_factory=list)

    def merge(self, other: "DownloadBatchResult | None") -> None:
        if not other:
            return
        self.items.extend(other.items)

    def as_dict(self) -> List[Dict[str, str]]:
        """Return a serialisable representation used for API responses."""

        serialised: List[Dict[str, str]] = []
        for item in self.items:
            payload: Dict[str, str] = {
                "source": item.source,
            }
            if item.identifier:
                payload["identifier"] = item.identifier
            if item.target_dir:
                payload["target"] = str(item.target_dir)
            if item.song_type:
                payload["song_type"] = item.song_type.name
            payload.update(item.extra)
            serialised.append(payload)
        return serialised


class DownloadService:
    """Facade providing higher level download workflows with metadata."""

    def __init__(
        self,
        youtube: YoutubeDownloader,
        soundcloud: SoundcloudDownloader,
        telegram: TelegramDownloader,
        settings: Optional[Settings] = None,
    ) -> None:
        self._youtube = youtube
        self._soundcloud = soundcloud
        self._telegram = telegram
        self._settings = settings or Settings()

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def download_youtube(
        self,
        *,
        account: Optional[str] = None,
        url: Optional[str] = None,
        break_on_existing: Optional[bool] = None,
        redownload: bool = False,
    ) -> DownloadBatchResult:
        """Download YouTube content and describe target folders."""

        if url:
            self._youtube.manual_download(url, break_on_existing, redownload=redownload)
            return DownloadBatchResult(
                [
                    DownloadItem(
                        source="youtube",
                        identifier=url,
                        target_dir=self._youtube_target_dir(),
                        song_type=SongTypeEnum.YOUTUBE,
                    )
                ]
            )

        if account:
            self._youtube.manual_account_download(account, redownload=redownload)
            return DownloadBatchResult(
                [
                    DownloadItem(
                        source="youtube",
                        identifier=account,
                        target_dir=self._youtube_target_dir(account),
                        song_type=SongTypeEnum.YOUTUBE,
                    )
                ]
            )

        self._youtube.run()
        return DownloadBatchResult(
            [
                DownloadItem(
                    source="youtube",
                    identifier=None,
                    target_dir=self._youtube_target_dir(),
                    song_type=SongTypeEnum.YOUTUBE,
                )
            ]
        )

    def download_soundcloud(
        self,
        *,
        account: Optional[str] = None,
        break_on_existing: Optional[bool] = None,
        redownload: bool = False,
    ) -> DownloadBatchResult:
        """Download SoundCloud tracks and surface affected folders."""

        account_value = account or ""
        self._soundcloud.run(
            account=account_value,
            breakOnExisting=break_on_existing,
            redownload=redownload,
        )

        target = self._soundcloud_target_dir(account if account else None)
        identifier = account if account else None
        return DownloadBatchResult(
            [
                DownloadItem(
                    source="soundcloud",
                    identifier=identifier,
                    target_dir=target,
                    song_type=SongTypeEnum.SOUNDCLOUD,
                )
            ]
        )

    def download_telegram(
        self,
        *,
        channel: str,
        limit: Optional[int] = None,
    ) -> DownloadBatchResult:
        """Download audio messages from Telegram channels."""

        self._telegram.run(channel, limit)
        return DownloadBatchResult(
            [
                DownloadItem(
                    source="telegram",
                    identifier=channel,
                    target_dir=self._telegram_target_dir(channel),
                    song_type=SongTypeEnum.TELEGRAM,
                )
            ]
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _youtube_target_dir(self, account: Optional[str] = None) -> Optional[Path]:
        base = self._youtube.output_folder or self._music_root() / "Youtube"
        path = Path(base)
        return path / account if account else path

    def _soundcloud_target_dir(self, account: Optional[str] = None) -> Optional[Path]:
        base = self._soundcloud.output_folder or self._music_root() / "Soundcloud"
        path = Path(base)
        return path / account if account else path

    def _telegram_target_dir(self, channel: Optional[str] = None) -> Optional[Path]:
        base = self._telegram.output_folder if getattr(self._telegram, "output_folder", None) else self._music_root() / "Telegram"
        path = Path(base)
        return path / channel if channel else path

    def _music_root(self) -> Path:
        return Path(self._settings.music_folder_path)
