from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services.common.config_store import ConfigStore
from services.music_manager.rbac import require_permission

router = APIRouter(tags=['config'])
config_store = ConfigStore()

# Reading is as privileged as writing here: the response carries every runtime
# setting, and until this gate existed any logged-in session could fetch the
# database credentials and the third-party tokens in the clear. Secrets are masked
# as well (see ConfigStore.SECRET_SENTINEL) -- the two are belt and braces, because
# the non-secret half still describes the whole deployment.
MANAGE = Depends(require_permission('config.manage'))


class ConfigUpdatePayload(BaseModel):
    updates: dict[str, Any] = Field(default_factory=dict)


@router.get('/')
def get_config(_auth: dict = MANAGE):
    return {'config': config_store.all_configs(), 'groups': config_store.groups()}


@router.post('/')
def update_config(payload: ConfigUpdatePayload, _auth: dict = MANAGE):
    try:
        updated = config_store.update(payload.updates)
        return {'status': 'success', 'config': updated}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get('/fields')
def get_fields(_auth: dict = MANAGE):
    return config_store.fields()
