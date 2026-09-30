import logging
import threading
import time
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from services.common.config_store import ConfigStore
from services.common.Helpers.LmsScanTrigger import lms_scan_trigger
from services.common.Helpers.ProcessedFilesHelper import ProcessedFilesHelper
from services.music_manager.bpm.tag_writeback import BpmTagWriteback
from services.music_manager.rbac import require_admin
from services.music_manager.routers.users import verify_api_key
from services.music_manager.thread_registry import default_stale_after, run_forever
from services.tagger.deep_run import deep_run_tick
from services.tagger.tagger import TAGGER_BATCH_PAUSE, Tagger, TagSingleFile
from services.tagger.walk_schedule import WalkSchedule

router = APIRouter(tags=['tagger'])
logger = logging.getLogger('music-manager.tagger')


class TaggerManager:
    def __init__(self):
        self.tagger = Tagger()
        self._lock = threading.Lock()
        #: Created on first use, so importing this router reads no settings.
        self.bpm_tags: BpmTagWriteback | None = None

    def run_full(self, walk: bool | None = None):
        """One round: the queue, and the folder walk when asked or when it is due.

        `walk=None` leaves it to the schedule (`tagger_walk_interval_hours`), which is what
        the loop does; the endpoints say what they mean.
        """
        if self._lock.locked():
            logger.warning('Tagging already in progress, skipping full run')
            return
        with self._lock:
            schedule = WalkSchedule(ConfigStore().get('tagger_walk_interval_hours'))
            if walk is None:
                walk = schedule.due()
            logger.info('Starting tagging round (walk: %s)', walk)
            self.tagger.run(walk=walk)
            if walk and not self.tagger.stop_requested:
                schedule.record()
            if not self.tagger.stop_requested:
                self._write_bpm_tags()
            logger.info('Tagging round completed (interrupted: %s)', self.tagger.stop_requested)

    def _write_bpm_tags(self):
        """The round's last step: a capped slice of measured tempos into the files' BPM tags.

        After the queue and the walk, so every retag reason -- decisions, new files, bulk -- is
        served first; inside the lock, so no tagger thread writes the same file meanwhile. A
        failure is logged and never ends the round (issue #139, docs/designs/bpm-tag-writeback/).
        """
        try:
            if getattr(self, 'bpm_tags', None) is None:
                self.bpm_tags = BpmTagWriteback(pause_seconds=TAGGER_BATCH_PAUSE)
            self.bpm_tags.run_round(should_stop=lambda: self.tagger.stop_requested)
        except Exception as e:  # pylint: disable=broad-except  # the tagger round must go on
            logger.error('BPM tag writeback failed: %s', e)

    def stop(self):
        logger.info('Requesting to stop tagging operation')
        self.tagger.stop_requested = True

    @property
    def stopping(self) -> bool:
        return self._lock.locked() and self.tagger.stop_requested

    #: How long restart() waits for the running round to let go. A stop lands within one
    #: folder's thread pool, so this is far more than it needs; it only keeps a stuck NFS
    #: mount from parking the background task forever.
    RESTART_WAIT_SECONDS = 900

    def restart(self):
        """Cut the running round short and start a fresh one from the front.

        A round does the retag queue before it walks a single folder, so this is how the
        decisions made just now get their files tagged without waiting for a walk that may
        take hours. The wait is for the lock, not for a thread: if the five-minute loop
        wakes first and takes it, that round is the fresh one and run_full simply skips.
        """
        self.stop()
        deadline = time.monotonic() + self.RESTART_WAIT_SECONDS
        while self._lock.locked():
            if time.monotonic() > deadline:
                logger.warning('Tagger did not stop within %ds, not restarting', self.RESTART_WAIT_SECONDS)
                return
            time.sleep(0.5)
        self.run_full(walk=False)

    def tag_single(self, path: str | Path, extra_info=None):
        with self._lock:
            logger.info('Processing single file tag request: %s', path)
            result = TagSingleFile(path, extra_info=extra_info)
        # Outside the lock: a slow or unreachable LMS must not hold up the tagger. This
        # is the path behind rerun-parse, where the correction is expected in the app
        # straight away -- so LMS is told the file's folder, which it reads in seconds,
        # rather than asked for a library-wide scan it would still be busy with an hour
        # from now (bug report 120). `notify` never blocks.
        lms_scan_trigger.notify([str(Path(path).parent)])
        return result


tagger_manager = TaggerManager()


@router.get('/health')
async def health():
    return {'status': 'OK', 'busy': tagger_manager._lock.locked()}


@router.post('/tag/all')
async def api_tag_all(background_tasks: BackgroundTasks, _auth: dict = Depends(verify_api_key)):
    if tagger_manager._lock.locked():
        raise HTTPException(status_code=409, detail='A tagging operation is already in progress')
    background_tasks.add_task(tagger_manager.run_full, True)
    return {'message': 'Full tagging run started in background'}


@router.post('/tag/stop')
async def api_tag_stop(_auth: dict = Depends(verify_api_key)):
    if not tagger_manager._lock.locked():
        return {'message': 'No tagging operation in progress'}
    tagger_manager.stop()
    return {'message': 'Stop request sent to tagger'}


@router.post('/tag/file')
def api_tag_file(path: str = Query(...), _auth: dict = Depends(verify_api_key)):
    # Plain `def`: tag_single waits for the tagger lock, which a running round can hold for
    # a long time, and an `async def` waiting on a threading.Lock stalls every other request.
    tagger_manager.tag_single(path)
    return {'message': f'Tagging for {path} completed'}


@router.get('/retag/pending')
async def api_retag_pending(_auth: dict = Depends(verify_api_key)):
    """How many files a rule change has queued up, and which change did it.

    Carries the tagger's state as well, so the page that polls this can tell a pile that
    is being worked off from one that is waiting for a walk to finish.
    """
    summary = ProcessedFilesHelper().pending_summary()
    summary['busy'] = tagger_manager._lock.locked()
    summary['stopping'] = tagger_manager.stopping
    return summary


def run_retag():
    """Tag the marked files, index the result, then let LMS catch up.

    The queue only, no folder walk: a retag is what a decision queued, and the walk
    is a daily safety net with nothing to do with it. A round cut short by a restart
    resumes with what is left. The five-minute loop serves the same queue; this
    endpoint exists for not wanting to wait for it.
    """
    tagger_manager.run_full(walk=False)
    from services.music_manager.routers.scanner import scanner_manager

    scanner_manager.run_full()


@router.post('/retag/run')
async def api_retag_run(background_tasks: BackgroundTasks, _auth: dict = Depends(verify_api_key)):
    if tagger_manager._lock.locked():
        raise HTTPException(status_code=409, detail='Tagging already in progress')
    background_tasks.add_task(run_retag)
    return {'status': 'ok', 'message': 'Retag started'}


def restart_retag():
    """run_retag, but first cutting short whatever round is running."""
    tagger_manager.restart()
    from services.music_manager.routers.scanner import scanner_manager

    scanner_manager.run_full()


@router.post('/retag/restart')
async def api_retag_restart(background_tasks: BackgroundTasks, _auth: dict = Depends(verify_api_key)):
    """Stop the running round and start over from the front, queue first.

    Unlike /retag/run this is never refused: being busy is the reason to call it.
    """
    background_tasks.add_task(restart_retag)
    return {'status': 'ok', 'message': 'Retag restart requested'}


def _todo_label_repair_page(after: str, limit: int, apply: bool) -> dict:
    """One page of the `__TODO` label repair; see services/tagger/todo_label_repair.py."""
    from services.tagger.todo_label_repair import TodoLabelRepair

    return TodoLabelRepair().run_page(after=after, limit=limit, apply=apply)


@router.get('/todo-label-repair')
def api_todo_label_repair_dry_run(
    after: str = Query('', description='Cursor: next_after of the previous page'),
    limit: int = Query(300, ge=1, le=2000),
    _auth: dict = Depends(require_admin()),
):
    """Dry run: which files on this page still carry `__TODO` as their label, and what it should be.

    Reads tags, writes nothing. Plain `def`: it reads a page of files from the share, which
    must not happen on the event loop. Bug report 087.
    """
    return _todo_label_repair_page(after, limit, apply=False)


@router.post('/todo-label-repair')
def api_todo_label_repair_apply(
    after: str = Query('', description='Cursor: next_after of the previous page'),
    limit: int = Query(300, ge=1, le=2000),
    _auth: dict = Depends(require_admin()),
):
    """Apply: queue this page's poisoned files for the tagger with reason `todo_label_repair`.

    Never retags inline -- the tagger round does the writing. Re-runnable.
    """
    return _todo_label_repair_page(after, limit, apply=True)


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


# A round may include the daily walk over the whole library, which on the CIFS share takes
# far longer than the five-minute interval. A day without one completed round is stuck.
TAGGER_STALE_AFTER_SECONDS = 24 * 3600


def _tagger_tick() -> None:
    """One round: queue a slice of the deep run, then tag what is pending."""
    _queue_deep_run()
    tagger_manager.run_full()


def run_tagger_loop(sleeptime: int = 300, stop: threading.Event | None = None):
    """The `tagger` thread: a round on start, then one every `sleeptime` seconds, for good.

    Runs through thread_registry.run_forever, so a round that raises (MariaDB restarting, a
    share that drops mid-walk) is logged and retried instead of ending the loop. `stop` ends
    the loop when set (tests use it to run an exact number of rounds).
    """
    logger.info('Starting background tagger loop with sleeptime %d', sleeptime)
    run_forever(
        'tagger',
        _tagger_tick,
        sleeptime,
        stale_after=max(TAGGER_STALE_AFTER_SECONDS, default_stale_after(sleeptime)),
        stop=stop,
    )
