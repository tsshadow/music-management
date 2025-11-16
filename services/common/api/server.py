import asyncio
import logging
import os
import uuid
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from fastapi import Depends, FastAPI, HTTPException, Header, WebSocket, WebSocketDisconnect, Body
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from services.common.Helpers.DatabaseConnector import DatabaseConnector
from .config_store import ConfigStore
from .db_init import ensure_tables_exist
from .steps import step_map, steps_to_run
app = FastAPI()
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', force=True)
current_job_id: ContextVar[Optional[str]] = ContextVar('current_job_id', default=None)
_default_logger = logging.LoggerAdapter(logging.getLogger(), {})
current_logger: ContextVar[logging.LoggerAdapter] = ContextVar('current_logger', default=_default_logger)

def ensure_yt_dlp_is_updated():
    if os.getenv('SKIP_YT_DLP_UPDATE'):
        return
    import subprocess
    try:
        subprocess.run(['pip', 'install', '--upgrade', 'yt-dlp', '--break-system-packages'], check=True)
    except subprocess.CalledProcessError as e:
        logging.error(f'Failed to install yt-dlp: {e}')

@app.on_event('startup')
def _startup() -> None:
    ensure_yt_dlp_is_updated()
    print('starting up...')
    ensure_tables_exist()

class JobLogFilter(logging.Filter):

    def __init__(self, job_id: str):
        super().__init__()
        self.job_id = job_id

    def filter(self, record: logging.LogRecord) -> bool:
        active = current_job_id.get()
        return getattr(record, 'job_id', None) == self.job_id and active == self.job_id

def _log(level, msg, *args, **kwargs):
    logger = current_logger.get()
    logger.log(level, msg, *args, **kwargs)

def _exception(msg, *args, exc_info=True, **kwargs):
    _log(logging.ERROR, msg, *args, exc_info=exc_info, **kwargs)
logging.log = _log
logging.debug = lambda msg, *a, **k: _log(logging.DEBUG, msg, *a, **k)
logging.info = lambda msg, *a, **k: _log(logging.INFO, msg, *a, **k)
logging.warning = lambda msg, *a, **k: _log(logging.WARNING, msg, *a, **k)
logging.error = lambda msg, *a, **k: _log(logging.ERROR, msg, *a, **k)
logging.exception = _exception
API_KEY = os.getenv('API_KEY')

def verify_api_key(x_api_key: Optional[str]=Header(default=None)) -> None:
    """Simple optional API key check."""
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail='Invalid API key')
default_origins = 'http://192.168.1.4:8001,https://music-importer.teunschriks.nl'
trusted_origins = os.getenv('CORS_ORIGINS', default_origins).split(',')
app.add_middleware(CORSMiddleware, allow_origins=[origin.strip() for origin in trusted_origins if origin.strip()], allow_credentials=True, allow_methods=['*'], allow_headers=['*'])
jobs: Dict[str, Dict] = {}
clients: Set[WebSocket] = set()

class ConfigUpdatePayload(BaseModel):
    updates: Dict[str, Any] = Field(default_factory=dict)

    @field_validator('updates')
    @classmethod
    def _validate_updates(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        if not value:
            raise ValueError('updates must contain at least one entry')
        return value

async def broadcast(job: Dict) -> None:
    """Send a minimal job update to all connected WebSocket clients."""
    message = {'id': job['id'], 'step': job['step'], 'status': job['status']}
    disconnected: Set[WebSocket] = set()
    for connection in clients:
        try:
            await connection.send_json(message)
        except Exception:
            disconnected.add(connection)
    for connection in disconnected:
        clients.discard(connection)

def _public_job(job: Dict) -> Dict:
    return {k: v for k, v in job.items() if k not in {'task', 'stop_event'}}

def _load_accounts(table: str) -> List[str]:
    """Fetch account names from the given table, logging errors on failure."""
    try:
        conn = DatabaseConnector().connect()
    except Exception as exc:
        logging.error('Failed to connect to database for %s accounts: %s', table, exc)
        return []
    try:
        with conn.cursor() as cursor:
            cursor.execute(f'SELECT name FROM {table}')
            accounts = [row[0] for row in cursor.fetchall()]
    except Exception as exc:
        logging.error('Failed to fetch %s accounts: %s', table, exc)
        return []
    finally:
        conn.close()
    return sorted(accounts)

@app.get('/health')
async def health() -> Dict[str, str]:
    """Basic health check endpoint.

    Optionally verifies database connectivity for additional assurance.
    """
    try:
        from services.common.Helpers.DatabaseConnector import DatabaseConnector

        def _check_db() -> None:
            conn = DatabaseConnector().connect()
            conn.close()
        await run_in_threadpool(_check_db)
    except Exception as exc:
        raise HTTPException(status_code=500, detail='Database connection failed') from exc
    return {'status': 'ok'}

@app.get('/api/steps')
async def list_steps(_: None=Depends(verify_api_key)):
    """Return available step keys for dropdowns."""
    return {'steps': sorted(step_map.keys())}

@app.get('/api/accounts')
async def list_accounts(_: None=Depends(verify_api_key)) -> Dict[str, List[str]]:
    """Return SoundCloud and YouTube account names for UI dropdowns."""
    return {'soundcloud': _load_accounts('soundcloud_accounts'), 'youtube': _load_accounts('youtube_accounts')}

@app.get('/api/config')
async def get_config(_: None=Depends(verify_api_key)) -> Dict[str, Any]:
    """Return the configuration schema and current values."""
    store = ConfigStore()
    return {'fields': store.describe()}

@app.patch('/api/config')
async def update_config(payload: ConfigUpdatePayload, _: None=Depends(verify_api_key)) -> Dict[str, Any]:
    """Persist configuration updates and notify registered listeners."""
    store = ConfigStore()
    try:
        updated = store.update(payload.updates)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {'values': updated}

@app.get('/api/jobs')
async def list_jobs(_: None=Depends(verify_api_key)):
    """Return jobs including completed ones."""
    return {'jobs': [_public_job(job) for job in jobs.values()]}

class JobLogHandler(logging.Handler):

    def __init__(self, job_id: str):
        super().__init__()
        self.job_id = job_id

    def emit(self, record: logging.LogRecord) -> None:
        jobs[self.job_id]['log'].append(self.format(record))

async def execute_step(step_name: str, job_id: str, repeat: bool, interval: float, stop_event: asyncio.Event, args: Dict[str, Any]):
    job = jobs[job_id]
    if step_name not in step_map:
        job['status'] = 'error'
        job['log'] = job.get('log', []) + [f'Unknown step: {step_name}']
        await broadcast(job)
        return
    step_keys = {step_name}
    steps_sequence = [s for s in steps_to_run if s.should_run(step_keys)]
    if not steps_sequence:
        job['status'] = 'error'
        job['log'].append(f'No executable steps found for: {step_name}')
        await broadcast(job)
        return
    handler = JobLogHandler(job_id)
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    handler.addFilter(JobLogFilter(job_id))
    job_logger = logging.getLogger(f'job.{job_id}')
    job_logger.setLevel(logging.INFO)
    job_logger.propagate = False
    job_logger.addHandler(handler)
    token_id = current_job_id.set(job_id)
    adapter = logging.LoggerAdapter(job_logger, {'job_id': job_id})
    token_logger = current_logger.set(adapter)
    try:
        job['status'] = 'running'
        await broadcast(job)
        while True:
            for current_step in steps_sequence:
                await run_in_threadpool(current_step.run, step_keys, **args)
            if stop_event.is_set() or not repeat:
                job['status'] = 'done' if not stop_event.is_set() else 'stopped'
                break
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue
        if stop_event.is_set():
            job['status'] = 'stopped'
    except asyncio.CancelledError:
        job['status'] = 'stopped'
        raise
    except Exception as e:
        job['status'] = 'error'
        job['log'].append(str(e))
    finally:
        job['ended'] = datetime.utcnow().isoformat()
        await broadcast(job)
        job_logger.removeHandler(handler)
        current_logger.reset(token_logger)
        current_job_id.reset(token_id)
        job.pop('task', None)
        job.pop('stop_event', None)

@app.post('/api/run/{step_name}')
async def run_step_endpoint(step_name: str, options: Dict[str, Any]=Body(default={}), _: None=Depends(verify_api_key)):
    if step_name not in step_map:
        raise HTTPException(status_code=404, detail='Unknown step')
    if step_name == 'manual-youtube' and (not options.get('url')):
        raise HTTPException(status_code=400, detail='Missing url')
    repeat = bool(options.pop('repeat', False))
    interval = float(options.pop('interval', 0))
    args = options
    job_id = str(uuid.uuid4())
    stop_event = asyncio.Event()
    jobs[job_id] = {'id': job_id, 'step': step_name, 'status': 'queued', 'log': [], 'stop_event': stop_event, 'started': datetime.utcnow().isoformat()}
    await broadcast(jobs[job_id])
    task = asyncio.create_task(execute_step(step_name, job_id, repeat, interval, stop_event, args))
    jobs[job_id]['task'] = task
    return _public_job(jobs[job_id])

@app.get('/api/job/{job_id}')
async def get_job(job_id: str, _: None=Depends(verify_api_key)):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail='Job not found')
    return _public_job(job)

@app.post('/api/job/{job_id}/stop')
async def stop_job(job_id: str, _: None=Depends(verify_api_key)):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail='Job not found')
    stop_event: Optional[asyncio.Event] = job.get('stop_event')
    task: Optional[asyncio.Task] = job.get('task')
    if stop_event:
        stop_event.set()
    if task and (not task.done()):
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    job['status'] = 'stopped'
    await broadcast(job)
    return _public_job(job)

@app.websocket('/ws/jobs')
async def jobs_ws(ws: WebSocket):
    token = ws.query_params.get('api_key')
    if API_KEY and token != API_KEY:
        await ws.close(code=1008)
        return
    await ws.accept()
    clients.add(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        clients.discard(ws)
frontend_dir = Path('frontend/dist')
if frontend_dir.exists():
    app.mount('/', StaticFiles(directory=str(frontend_dir), html=True), name='frontend')
else:
    logging.warning('Frontend build directory not found; static files will not be served.')