from __future__ import annotations

from functools import lru_cache
from typing import List

import json

from pydantic import ConfigDict, Field, model_validator
from pydantic_settings import BaseSettings


class AppSettings(BaseSettings):
    """Runtime configuration loaded from environment variables or .env."""

    model_config = ConfigDict(env_file=".env", env_file_encoding="utf-8", populate_by_name=True)
    app_name: str = "Scrobbler"
    api_prefix: str = "/api/v1"
    db_dsn: str = Field(default="sqlite+aiosqlite:///./scrobbler.db", alias="SCROBBLER_DB_DSN")
    api_key: str | None = Field(default=None, alias="SCROBBLER_API_KEY")
    log_level: str = Field(default="INFO", alias="SCROBBLER_LOG_LEVEL")
    cors_origins: List[str] = Field(default_factory=list, alias="SCROBBLER_CORS_ORIGINS")
    redis_url: str = Field(default="redis://redis:6379/0", alias="SCROBBLER_REDIS_URL")
    analyzer_queue_name: str = Field(default="scrobbler-analyzer", alias="SCROBBLER_ANALYZER_QUEUE")
    analyzer_default_paths: List[str] = Field(
        default_factory=list, alias="SCROBBLER_ANALYZER_PATHS"
    )
    listenbrainz_base_url: str = Field(
        default="https://api.listenbrainz.org/1",
        alias="SCROBBLER_LISTENBRAINZ_BASE_URL",
    )
    musicbrainz_base_url: str = Field(
        default="https://musicbrainz.org/ws/2",
        alias="SCROBBLER_MUSICBRAINZ_BASE_URL",
    )
    musicbrainz_user_agent: str = Field(
        default="scrobbler/1.0 (+https://github.com/)",
        alias="SCROBBLER_MUSICBRAINZ_USER_AGENT",
    )

    @model_validator(mode="before")
    @classmethod
    def _coerce_analyzer_paths(cls, data: dict) -> dict:
        value = data.get("SCROBBLER_ANALYZER_PATHS") or data.get("analyzer_default_paths")
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    data["analyzer_default_paths"] = parsed
                    return data
            except json.JSONDecodeError:
                pass
            paths = [part.strip() for part in value.split(",") if part.strip()]
            data["analyzer_default_paths"] = paths
        return data


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Return a cached settings instance for application-wide use."""

    return AppSettings()
