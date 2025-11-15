"""Job management utilities shared across importer services."""

from __future__ import annotations

import asyncio
import contextvars
from collections import defaultdict, deque
from typing import Any, Deque, Dict, Iterable, List, MutableMapping, Optional
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

current_job_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_job_id", default=None
)


class JobManager:
    """In-memory coordination hub for background importer jobs."""

    def __init__(self) -> None:
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self.connections: MutableMapping[str, List[WebSocket]] = defaultdict(list)
        self.history: Deque[str] = deque(maxlen=50)
        self.results: Dict[str, Dict[str, Any]] = {}

    async def run(self, job_id: str, steps: Iterable[Any]) -> None:
        state = self.jobs[job_id]
        total = len(list(steps))
        state.update({"status": "running", "progress": 0, "total": total})
        await self._notify(job_id)

        for index, step in enumerate(steps, start=1):
            state["current"] = getattr(step, "name", str(step))
            await self._notify(job_id)
            token = current_job_id.set(job_id)
            try:
                await asyncio.to_thread(step)
            finally:
                current_job_id.reset(token)
            state["progress"] = index
            await self._notify(job_id)

        state["status"] = "finished"
        await self._notify(job_id)
        self.results[job_id] = state.copy()
        self.history.appendleft(job_id)

    def create(self, job_id: str, payload: Dict[str, Any]) -> None:
        self.jobs[job_id] = payload

    def register(self, step_name: str) -> str:
        job_id = str(uuid4())
        self.jobs[job_id] = {"step": step_name, "status": "running"}
        return job_id

    def update(self, job_id: str, status: str, error: Optional[str] = None) -> None:
        job = self.jobs.get(job_id)
        if not job:
            return
        job["status"] = status
        if error:
            job["error"] = error

    def list_active(self) -> List[Dict[str, Any]]:
        return [
            {"job_id": job_id, "step": data.get("step", "")}
            for job_id, data in self.jobs.items()
            if data.get("status") == "running"
        ]

    def get(self, job_id: Optional[str]) -> Optional[Dict[str, Any]]:
        if not job_id:
            return None
        return self.jobs.get(job_id)

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

    def publish(self, payload: Dict[str, Any]) -> None:
        job_id = current_job_id.get()
        if not job_id:
            return
        loop = asyncio.get_running_loop()
        loop.create_task(self._notify(job_id, payload))

    def recent(self) -> List[Dict[str, Any]]:
        return [self.results[jid] for jid in self.history]


job_manager = JobManager()


def build_websocket_router(prefix: str = "") -> APIRouter:
    """Create a router that exposes job progress updates via WebSocket."""

    router = APIRouter()

    @router.websocket(f"{prefix}/jobs/{{job_id}}")
    async def job_updates(websocket: WebSocket, job_id: str) -> None:  # pragma: no cover - IO glue
        await job_manager.connect(job_id, websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            job_manager.disconnect(job_id, websocket)

    return router


__all__ = ["JobManager", "job_manager", "build_websocket_router", "current_job_id"]
