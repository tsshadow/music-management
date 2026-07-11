import os
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Header, Body, Depends
from pydantic import BaseModel, Field
from services.common.config_store import ConfigStore
router = APIRouter(tags=['config'])
config_store = ConfigStore()
API_KEY = os.getenv('API_KEY') or os.getenv('MUMA_API_KEY') or '453ecd33-3cb2-4ca4-a531-1677330bbaee'

def verify_api_key(x_api_key: Optional[str]=Header(None)):
    if not x_api_key:
        raise HTTPException(status_code=401, detail='Missing API Key')
    if API_KEY and x_api_key == API_KEY:
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
    updates: Dict[str, Any] = Field(default_factory=dict)

@router.get('/')
def get_config(_auth: dict=Depends(verify_api_key)):
    return {'config': config_store.all_configs(), 'groups': config_store.groups()}

@router.post('/')
def update_config(payload: ConfigUpdatePayload, _auth: dict=Depends(verify_api_key)):
    try:
        config_store.update_many(payload.updates)
        return {'status': 'success'}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get('/fields')
def get_fields(_auth: dict=Depends(verify_api_key)):
    return config_store.fields()