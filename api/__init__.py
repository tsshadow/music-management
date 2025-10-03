"""API utilities and FastAPI application entry point.

This module exposes two main things:

``start_api_server`` – a small HTTP server used in the tests for
job tracking.
``app`` – the FastAPI application which can be served via ``uvicorn``.

Having these definitions in ``api/__init__.py`` avoids conflicts with the
previous standalone ``api.py`` module and allows ``uvicorn api:app`` to
work as expected.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from api.job_manager import job_manager

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
try:  # pragma: no cover - FastAPI is optional in the execution environment
    from .server import app  # re-export for ``uvicorn api:app``
except Exception:  # pragma: no cover - provide a fallback when FastAPI is missing
    app = None  # type: ignore


# ---------------------------------------------------------------------------
# Lightweight HTTP server for tests
# ---------------------------------------------------------------------------
class JobAPIHandler(BaseHTTPRequestHandler):
    """Serve basic job information over HTTP."""

    def _send(self, code: int = 200, body: Any | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if body is not None:
            self.wfile.write(json.dumps(body).encode())

    def do_GET(self) -> None:  # pragma: no cover - exercised via tests
        parsed = urlparse(self.path)
        if parsed.path == "/jobs":
            jobs = job_manager.list_active()
            self._send(200, jobs)
        elif parsed.path == "/status":
            params = parse_qs(parsed.query)
            job_id = params.get("job_id", [None])[0]
            job = job_manager.get(job_id)
            if job:
                self._send(200, {"job_id": job_id, **job})
            else:
                self._send(404, {"error": "Job not found"})
        else:
            self._send(404, {"error": "Not found"})


def start_api_server(host: str = "localhost", port: int = 0) -> HTTPServer:
    """Start the lightweight HTTP server in a background thread."""

    server = HTTPServer((host, port), JobAPIHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


__all__ = ["app", "start_api_server"]
