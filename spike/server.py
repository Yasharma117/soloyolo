"""A read-only local viewer. Binds to 127.0.0.1 only: this is your message history."""
from __future__ import annotations

import json
import re
from functools import partial
from urllib.parse import urlsplit
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .store import Store

INDEX = Path(__file__).with_name("viewer.html")


class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, db: str, port: int, **kwargs):
        self.db = db
        # Binding to 127.0.0.1 isn't enough: a web page can rebind its own domain to 127.0.0.1 and read
        # this server as same-origin. Only answer requests addressed to the loopback names.
        self.allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
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
        if self.headers.get("Host", "") not in self.allowed_hosts:
            return self._send(b"forbidden host", "text/plain", 403)
        path = urlsplit(self.path).path
        if path in ("/", "/index.html"):
            return self._send(INDEX.read_bytes(), "text/html; charset=utf-8")
        store = Store(self.db)
        try:
            if path == "/api/people":
                return self._json(store.people())
            if path == "/api/disclosures":
                return self._json(store.disclosures())
            m = re.fullmatch(r"/api/thread/(\d+)", path)
            if m:
                return self._json([dict(r) for r in store.thread(int(m.group(1)))])
            self._send(b"not found", "text/plain", 404)
        finally:
            store.close()

    def _json(self, data) -> None:
        self._send(json.dumps(data).encode(), "application/json")


def serve(db: str, port: int = 8765) -> None:
    httpd = ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, db=db, port=port))
    print(f"soloyolo viewer on http://127.0.0.1:{port}  (Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
