from __future__ import annotations

from pydantic import BaseModel, Field, RootModel


ALLOWED_CONFIG_KEYS = {
    "default_user",
    "api_key",
    "lms_source_name",
}


class ConfigUpdate(RootModel[dict[str, str | None]]):
    @property
    def data(self) -> dict[str, str]:
        return {
            k: v
            for k, v in (self.root or {}).items()
            if k in ALLOWED_CONFIG_KEYS and v is not None
        }


class ConfigResponse(BaseModel):
    values: dict[str, str]
