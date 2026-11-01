"""A read-only local viewer. Binds to 127.0.0.1 only: this is your message history."""
from __future__ import annotations

import json
import re
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .store import Store

INDEX = Path(__file__).with_name("viewer.html")


class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, db: str, **kwargs):
        self.db = db
        super().__init__(*args, **kwargs)

    def log_message(self, *_):  # keep message text out of the terminal log
        pass

    def _send(self, body: bytes, ctype: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        store = Store(self.db)
        try:
            if self.path in ("/", "/index.html"):
                return self._send(INDEX.read_bytes(), "text/html; charset=utf-8")
            if self.path == "/api/people":
                return self._json(store.people())
            m = re.fullmatch(r"/api/thread/(\d+)", self.path)
            if m:
                return self._json([dict(r) for r in store.thread(int(m.group(1)))])
            self._send(b"not found", "text/plain", 404)
        finally:
            store.close()

    def _json(self, data) -> None:
        self._send(json.dumps(data).encode(), "application/json")


def serve(db: str, port: int = 8765) -> None:
    httpd = ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, db=db))
    print(f"soloyolo viewer on http://127.0.0.1:{port}  (Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
