import asyncio
import contextvars
import uuid
from collections import deque, defaultdict
from typing import Any, Dict, List
try:
    from fastapi import APIRouter, WebSocket, WebSocketDisconnect
except Exception:

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

        def websocket(self, *args: Any, **kwargs: Any):

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
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self.connections: Dict[str, List[WebSocket]] = defaultdict(list)
        self.history: deque[str] = deque(maxlen=50)
        self.results: Dict[str, Dict[str, Any]] = {}

    async def run(self, job_id: str, steps: List[Any], selected_steps: List[str]) -> None:
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

    def create_job(self, steps: List[Any], selected_steps: List[str]) -> str:
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

    async def _notify(self, job_id: str, payload: Dict[str, Any] | None=None) -> None:
        data = payload or self.jobs.get(job_id)
        for ws in list(self.connections.get(job_id, [])):
            try:
                await ws.send_json(data)
            except WebSocketDisconnect:
                self.disconnect(job_id, ws)

    def publish(self, payload: Dict[str, Any]) -> None:
        job_id = current_job_id.get()
        if not job_id:
            return
        loop = asyncio.get_running_loop()
        loop.create_task(self._notify(job_id, payload))

    def recent(self) -> List[Dict[str, Any]]:
        return [self.results[jid] for jid in self.history]
job_manager = JobManager()
router = APIRouter()

@router.websocket('/ws/jobs/{job_id}')
async def job_updates(websocket: WebSocket, job_id: str):
    await job_manager.connect(job_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        job_manager.disconnect(job_id, websocket)