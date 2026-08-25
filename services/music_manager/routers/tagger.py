import logging
import threading
import time
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query

from services.common.Helpers.LmsScanTrigger import lms_scan_trigger
from services.common.Helpers.ProcessedFilesHelper import ProcessedFilesHelper
from services.tagger.deep_run import deep_run_tick
from services.tagger.tagger import Tagger, TagSingleFile

router = APIRouter(tags=['tagger'])
logger = logging.getLogger('music-manager.tagger')

async def verify_api_key(x_api_key: str | None=Header(None)):
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
            result = TagSingleFile(path, extra_info=extra_info)
        # Outside the lock: a slow or unreachable LMS must not hold up the tagger. This
        # is the path behind rerun-parse, where the correction is expected in the app
        # straight away, so a per-file trigger is worth it here.
        lms_scan_trigger.trigger()
        return result
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

@router.get('/retag/pending')
async def api_retag_pending(_auth: dict=Depends(verify_api_key)):
    """How many files a rule change has queued up, and which change did it."""
    return ProcessedFilesHelper().pending_summary()

def run_retag():
    """Tag the marked files, index the result, then let LMS catch up.

    No dedicated execution path is needed: Tagger.run walks the folders and asks
    needs_processing per file, so the marked files are picked up and the rest is
    skipped. Walking is cheap; tagging is not.
    """
    tagger_manager.run_full()
    from services.music_manager.routers.scanner import scanner_manager
    scanner_manager.run_full()

@router.post('/retag/run')
async def api_retag_run(background_tasks: BackgroundTasks, _auth: dict=Depends(verify_api_key)):
    if tagger_manager._lock.locked():
        raise HTTPException(status_code=409, detail='Tagging already in progress')
    background_tasks.add_task(run_retag)
    return {'status': 'ok', 'message': 'Retag started'}

def _queue_deep_run():
    """Hand the next slice of the deep run to the round that is about to start.

    Wrapped rather than called directly: deep_run_tick already swallows its own database
    errors, and this second net keeps anything unforeseen there from ending the loop --
    the deep run is a nicety, the five-minute round is not.
    """
    try:
        deep_run_tick()
    except Exception as e:
        logger.error('Deep run tick failed: %s', e)

def run_tagger_loop(sleeptime: int=300):
    logger.info('Starting background tagger loop with sleeptime %d', sleeptime)
    _queue_deep_run()
    tagger_manager.run_full()
    while True:
        time.sleep(sleeptime)
        _queue_deep_run()
        tagger_manager.run_full()