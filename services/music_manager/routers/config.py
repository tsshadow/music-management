from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from services.common.config_store import ConfigStore
from services.music_manager.api_key import is_system_api_key

router = APIRouter(tags=['config'])
config_store = ConfigStore()

def verify_api_key(x_api_key: str | None=Header(None)):
    if not x_api_key:
        raise HTTPException(status_code=401, detail='Missing API Key')
    if is_system_api_key(x_api_key):
        return {'type': 'system'}
    from services.music_manager.routers.users import verify_token
    try:
        res = verify_token(x_api_key)
        if res.get('status') == 'ok':
            return res
    except Exception:
        pass
    raise HTTPException(status_code=401, detail='Invalid API key')

class ConfigUpdatePayload(BaseModel):
    updates: dict[str, Any] = Field(default_factory=dict)

@router.get('/')
def get_config(_auth: dict=Depends(verify_api_key)):
    return {'config': config_store.all_configs(), 'groups': config_store.groups()}

@router.post('/')
def update_config(payload: ConfigUpdatePayload, _auth: dict=Depends(verify_api_key)):
    try:
        updated = config_store.update(payload.updates)
        return {'status': 'success', 'config': updated}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

@router.get('/fields')
def get_fields(_auth: dict=Depends(verify_api_key)):
    return config_store.fields()