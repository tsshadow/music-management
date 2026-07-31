import logging
import threading
import time
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, Query, HTTPException, Header, Depends
from services.tagger.tagger import Tagger, TagSingleFile
router = APIRouter(tags=['tagger'])
logger = logging.getLogger('music-manager.tagger')

async def verify_api_key(x_api_key: Optional[str]=Header(None)):
    """Same system-or-user API key check the other routers use.

    Delegates rather than re-implementing it (as library.py/management.py do) so there is one
    place where "what counts as a valid key" is defined. Imported lazily because users.py is
    itself a router module that main.py imports alongside this one.
    """
    from services.music_manager.routers.users import verify_api_key as _verify
    return await _verify(x_api_key)

class TaggerManager:

    def __init__(self):
        self.tagger = Tagger()
        self._lock = threading.Lock()

    def run_full(self):
        if self._lock.locked():
            logger.warning('Tagging already in progress, skipping full run')
            return
        with self._lock:
            logger.info('Starting full tagging run')
            self.tagger.run()
            logger.info('Full tagging run completed (interrupted: %s)', self.tagger.stop_requested)

    def stop(self):
        logger.info('Requesting to stop tagging operation')
        self.tagger.stop_requested = True

    def tag_single(self, path: str | Path, extra_info=None):
        with self._lock:
            logger.info('Processing single file tag request: %s', path)
            return TagSingleFile(path, extra_info=extra_info)
tagger_manager = TaggerManager()

@router.get('/health')
async def health():
    return {'status': 'OK', 'busy': tagger_manager._lock.locked()}

@router.post('/tag/all')
async def api_tag_all(background_tasks: BackgroundTasks, _auth: dict=Depends(verify_api_key)):
    if tagger_manager._lock.locked():
        raise HTTPException(status_code=409, detail='A tagging operation is already in progress')
    background_tasks.add_task(tagger_manager.run_full)
    return {'message': 'Full tagging run started in background'}

@router.post('/tag/stop')
async def api_tag_stop(_auth: dict=Depends(verify_api_key)):
    if not tagger_manager._lock.locked():
        return {'message': 'No tagging operation in progress'}
    tagger_manager.stop()
    return {'message': 'Stop request sent to tagger'}

@router.post('/tag/file')
async def api_tag_file(path: str=Query(...), _auth: dict=Depends(verify_api_key)):
    tagger_manager.tag_single(path)
    return {'message': f'Tagging for {path} completed'}

def run_tagger_loop(sleeptime: int=300):
    logger.info('Starting background tagger loop with sleeptime %d', sleeptime)
    tagger_manager.run_full()
    while True:
        time.sleep(sleeptime)
        tagger_manager.run_full()