from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from services.common.config_store import ConfigStore
from services.music_manager.api_key import is_system_api_key
from services.music_manager.rbac import require_permission

router = APIRouter(tags=['config'])
config_store = ConfigStore()

# Reading is as privileged as writing here: the response carries every runtime
# setting, and until this gate existed any logged-in session could fetch the
# database credentials and the third-party tokens in the clear. Secrets are masked
# as well (see ConfigStore.SECRET_SENTINEL) -- the two are belt and braces, because
# the non-secret half still describes the whole deployment.
MANAGE = Depends(require_permission('config.manage'))

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
def get_config(_auth: dict=MANAGE):
    return {'config': config_store.all_configs(), 'groups': config_store.groups()}

@router.post('/')
def update_config(payload: ConfigUpdatePayload, _auth: dict=MANAGE):
    try:
        updated = config_store.update(payload.updates)
        return {'status': 'success', 'config': updated}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

@router.get('/fields')
def get_fields(_auth: dict=MANAGE):
    return config_store.fields()