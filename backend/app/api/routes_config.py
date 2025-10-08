from __future__ import annotations

from fastapi import APIRouter, Depends

from ..db.adapter import DatabaseAdapter
from ..schemas.config import ConfigResponse, ConfigUpdate, ALLOWED_CONFIG_KEYS
from .deps import get_adapter, verify_api_key

router = APIRouter(prefix="/config", tags=["config"], dependencies=[Depends(verify_api_key)])


@router.get("", response_model=ConfigResponse)
async def get_config(adapter: DatabaseAdapter = Depends(get_adapter)):
    """Return configuration values limited to the exposed allowlist."""

    values = await adapter.get_config()
    filtered = {k: v for k, v in values.items() if k in ALLOWED_CONFIG_KEYS}
    return ConfigResponse(values=filtered)


@router.put("", response_model=ConfigResponse)
async def update_config(payload: ConfigUpdate, adapter: DatabaseAdapter = Depends(get_adapter)):
    """Persist allowed configuration keys and return the updated snapshot."""

    data = payload.data
    if data:
        await adapter.update_config(data)
    values = await adapter.get_config()
    filtered = {k: v for k, v in values.items() if k in ALLOWED_CONFIG_KEYS}
    return ConfigResponse(values=filtered)
