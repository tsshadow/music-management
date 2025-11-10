import asyncio
import contextvars
import uuid
from collections import deque, defaultdict
from typing import Any, Dict, List

try:  # pragma: no cover - used only when FastAPI is available
    from fastapi import APIRouter, WebSocket, WebSocketDisconnect
except Exception:  # pragma: no cover - allow running tests without FastAPI
    class WebSocket:  # type: ignore
        async def accept(self) -> None:
            pass

        async def send_json(self, data: Any) -> None:  # noqa: ANN401
            pass

        async def receive_text(self) -> str:  # noqa: ANN401
            await asyncio.sleep(0)
            return ""

    class WebSocketDisconnect(Exception):
        pass

    class APIRouter:  # minimal stub
        def websocket(self, *args: Any, **kwargs: Any):  # noqa: ANN401
            def decorator(func):
                return func

            return decorator


current_job_id = contextvars.ContextVar("current_job_id", default=None)

class JobManager:
    """Simple in-memory job manager for Step based pipelines.

    Jobs are executed asynchronously. Progress for every job is
    tracked and pushed to all WebSocket listeners. Recent job
    results are stored in memory so that the UI can retrieve them
    even after the job has finished.
    """

    def __init__(self) -> None:
        # job_id -> state
        self.jobs: Dict[str, Dict[str, Any]] = {}
        # job_id -> websocket connections
        self.connections: Dict[str, List[WebSocket]] = defaultdict(list)
        # recently finished jobs
        self.history: deque[str] = deque(maxlen=50)
        self.results: Dict[str, Dict[str, Any]] = {}

    # -----------------------------------------------------
    # job execution
    # -----------------------------------------------------
    async def run(self, job_id: str, steps: List[Any], selected_steps: List[str]) -> None:
        total = len(steps)
        state = {"status": "running", "current": None, "progress": 0, "total": total}
        self.jobs[job_id] = state
        await self._notify(job_id)

        for index, step in enumerate(steps, start=1):
            state["current"] = step.name
            state["progress"] = index - 1
            await self._notify(job_id)

            token = current_job_id.set(job_id)
            try:
                await asyncio.to_thread(step.run, selected_steps)
            finally:
                current_job_id.reset(token)

            state["progress"] = index
            await self._notify(job_id)

        state["status"] = "finished"
        await self._notify(job_id)

        # store result for later retrieval
        self.results[job_id] = state.copy()
        self.history.appendleft(job_id)

    def create_job(self, steps: List[Any], selected_steps: List[str]) -> str:
        job_id = str(uuid.uuid4())
        asyncio.create_task(self.run(job_id, steps, selected_steps))
        return job_id

    # -----------------------------------------------------
    # websocket handling
    # -----------------------------------------------------
    async def connect(self, job_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections[job_id].append(websocket)
        if job_id in self.jobs:
            await websocket.send_json(self.jobs[job_id])

    def disconnect(self, job_id: str, websocket: WebSocket) -> None:
        if job_id in self.connections:
            self.connections[job_id].remove(websocket)

    async def _notify(self, job_id: str, payload: Dict[str, Any] | None = None) -> None:
        data = payload or self.jobs.get(job_id)
        for ws in list(self.connections.get(job_id, [])):
            try:
                await ws.send_json(data)
            except WebSocketDisconnect:
                self.disconnect(job_id, ws)

    # -----------------------------------------------------
    # external progress publishing (e.g. from downloaders)
    # -----------------------------------------------------
    def publish(self, payload: Dict[str, Any]) -> None:
        job_id = current_job_id.get()
        if not job_id:
            return
        loop = asyncio.get_running_loop()
        loop.create_task(self._notify(job_id, payload))

    # -----------------------------------------------------
    # querying
    # -----------------------------------------------------
    def recent(self) -> List[Dict[str, Any]]:
        return [self.results[jid] for jid in self.history]


# create global manager instance
job_manager = JobManager()

router = APIRouter()

@router.websocket("/ws/jobs/{job_id}")
async def job_updates(websocket: WebSocket, job_id: str):
    await job_manager.connect(job_id, websocket)
    try:
        while True:
            # keep connection open; we don't expect messages
            await websocket.receive_text()
    except WebSocketDisconnect:
        job_manager.disconnect(job_id, websocket)
