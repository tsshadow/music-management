import asyncio
import contextvars
import uuid
from collections import defaultdict, deque
from typing import Any

try:
    from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

    from services.music_manager.routers.users import verify_api_key
except Exception:

    def Depends(_dependency: Any) -> None:  # noqa: N802 - mirrors the FastAPI name
        return None

    def verify_api_key() -> None:
        return None

    class WebSocket:
        async def accept(self) -> None:
            pass

        async def send_json(self, data: Any) -> None:
            pass

        async def receive_text(self) -> str:
            await asyncio.sleep(0)
            return ''

    class WebSocketDisconnect(Exception):
        pass

    class APIRouter:
        def websocket(self, *_args: Any, **_kwargs: Any):

            def decorator(func):
                return func

            return decorator


current_job_id = contextvars.ContextVar('current_job_id', default=None)


class JobManager:
    """Simple in-memory job manager for Step based pipelines.

    Jobs are executed asynchronously. Progress for every job is
    tracked and pushed to all WebSocket listeners. Recent job
    results are stored in memory so that the UI can retrieve them
    even after the job has finished.
    """

    def __init__(self) -> None:
        self.jobs: dict[str, dict[str, Any]] = {}
        self.connections: dict[str, list[WebSocket]] = defaultdict(list)
        self.history: deque[str] = deque(maxlen=50)
        self.results: dict[str, dict[str, Any]] = {}

    async def run(self, job_id: str, steps: list[Any], selected_steps: list[str]) -> None:
        total = len(steps)
        state = {'status': 'running', 'current': None, 'progress': 0, 'total': total}
        self.jobs[job_id] = state
        await self._notify(job_id)
        for index, step in enumerate(steps, start=1):
            state['current'] = step.name
            state['progress'] = index - 1
            await self._notify(job_id)
            token = current_job_id.set(job_id)
            try:
                await asyncio.to_thread(step.run, selected_steps)
            finally:
                current_job_id.reset(token)
            state['progress'] = index
            await self._notify(job_id)
        state['status'] = 'finished'
        await self._notify(job_id)
        self.results[job_id] = state.copy()
        self.history.appendleft(job_id)

    def create_job(self, steps: list[Any], selected_steps: list[str]) -> str:
        job_id = str(uuid.uuid4())
        asyncio.create_task(self.run(job_id, steps, selected_steps))
        return job_id

    async def connect(self, job_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections[job_id].append(websocket)
        if job_id in self.jobs:
            await websocket.send_json(self.jobs[job_id])

    def disconnect(self, job_id: str, websocket: WebSocket) -> None:
        if job_id in self.connections:
            self.connections[job_id].remove(websocket)

    async def _notify(self, job_id: str, payload: dict[str, Any] | None = None) -> None:
        data = payload or self.jobs.get(job_id)
        for ws in list(self.connections.get(job_id, [])):
            try:
                await ws.send_json(data)
            except WebSocketDisconnect:
                self.disconnect(job_id, ws)

    def publish(self, payload: dict[str, Any]) -> None:
        job_id = current_job_id.get()
        if not job_id:
            return
        loop = asyncio.get_running_loop()
        loop.create_task(self._notify(job_id, payload))

    def recent(self) -> list[dict[str, Any]]:
        return [self.results[jid] for jid in self.history]


job_manager = JobManager()
router = APIRouter(tags=['jobs'])


@router.websocket('/ws/jobs/{job_id}')
async def job_updates(websocket: WebSocket, job_id: str):
    await job_manager.connect(job_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        job_manager.disconnect(job_id, websocket)


# The three HTTP routes take a key. The workers that register here already
# send one (services/common/job_manager.py), and the reverse proxy now hands
# /muma/api/ to MuMa without LMS's own credential check in front of it, so
# an open route here would be open to the internet.
@router.post("/register/{job_id}")
async def register_external_job(job_id: str, payload: dict[str, Any], _auth: dict = Depends(verify_api_key)):
    """Allow external workers to register their job status."""
    job_manager.jobs[job_id] = payload
    if payload.get('status') in ('finished', 'completed', 'done', 'failed', 'error'):
        job_manager.results[job_id] = payload
        if job_id not in job_manager.history:
            job_manager.history.appendleft(job_id)
    await job_manager._notify(job_id)
    return {"status": "ok"}


@router.get("/active")
async def list_active_jobs(_auth: dict = Depends(verify_api_key)):
    return {"jobs": job_manager.jobs}


@router.get("/history")
async def list_job_history(_auth: dict = Depends(verify_api_key)):
    return {"history": job_manager.recent()}
