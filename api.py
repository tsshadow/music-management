import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
import threading

from job_manager import job_manager


class JobAPIHandler(BaseHTTPRequestHandler):
    def _send(self, code=200, body=None):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if body is not None:
            self.wfile.write(json.dumps(body).encode())

    def do_GET(self):
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


def start_api_server(host="localhost", port=0):
    server = HTTPServer((host, port), JobAPIHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
