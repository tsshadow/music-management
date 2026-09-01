"""One row of `downloads_youtube_accounts`.

The table's primary key is (name, download_type), so a channel can appear twice:
once as an audio source and once as a video source. Passing plain strings around
loses that distinction, which is how the downloader ended up sweeping seven
channels twice as audio and never as video.
"""

from __future__ import annotations

from dataclasses import dataclass

AUDIO = 'audio'
VIDEO = 'video'

# What _match_filter hardcoded before the column was read.
DEFAULT_MIN_DURATION = 60


@dataclass(frozen=True)
class YoutubeAccount:
    name: str
    download_type: str = AUDIO
    min_duration: int = DEFAULT_MIN_DURATION
    active: bool = True

    @property
    def is_video(self) -> bool:
        return self.download_type == VIDEO

    @property
    def schedule_key(self) -> str:
        """The key the sweep schedule stores this row's last check under.

        Audio keeps the bare name so existing schedule rows stay valid. Video
        needs its own key, otherwise the audio pass of a dual channel would mark
        it as checked and the video pass would skip it for the whole cooldown.
        """
        return f'{self.name}#video' if self.is_video else self.name

    @classmethod
    def from_row(cls, row) -> YoutubeAccount:
        """Build an account from a (name, download_type, min_duration, active) row.

        Databases that predate migrate_v6 may hand back short rows or NULLs, so
        every field past the name falls back to the old hardcoded behaviour.
        """
        name = row[0]
        download_type = (row[1] if len(row) > 1 else None) or AUDIO
        if download_type not in (AUDIO, VIDEO):
            download_type = AUDIO
        raw_duration = row[2] if len(row) > 2 else None
        min_duration = DEFAULT_MIN_DURATION if raw_duration is None else int(raw_duration)
        raw_active = row[3] if len(row) > 3 else None
        active = True if raw_active is None else bool(raw_active)
        return cls(name=name, download_type=download_type, min_duration=min_duration, active=active)
