from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings
from pydantic import ConfigDict


class AppSettings(BaseSettings):
    """Runtime configuration loaded from environment variables or .env."""

    model_config = ConfigDict(env_file=".env", env_file_encoding="utf-8", populate_by_name=True)
    app_name: str = "Scrobbler"
    api_prefix: str = "/api/v1"
    db_dsn: str = Field(default="sqlite+aiosqlite:///./scrobbler.db", alias="SCROBBLER_DB_DSN")
    api_key: str | None = Field(default=None, alias="SCROBBLER_API_KEY")
    log_level: str = Field(default="INFO", alias="SCROBBLER_LOG_LEVEL")
    cors_origins: List[str] = Field(default_factory=list, alias="SCROBBLER_CORS_ORIGINS")
    listenbrainz_base_url: str = Field(
        default="https://api.listenbrainz.org/1",
        alias="SCROBBLER_LISTENBRAINZ_BASE_URL",
    )


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Return a cached settings instance for application-wide use."""

    return AppSettings()
