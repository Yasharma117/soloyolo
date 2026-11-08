"""The local viewer. Binds to 127.0.0.1 only: this is your message history.

It reads everything and writes one thing: your own marks on items (done, not real, snooze).
"""
from __future__ import annotations

import json
import re
import time
from functools import partial
from urllib.parse import urlsplit
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import nudge, priority
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
            if path == "/api/today":
                return self._json(nudge.summary(store))
            if path == "/api/top":
                return self._json(priority.rank(store))
            if path == "/api/disclosures":
                return self._json(store.disclosures())
            m = re.fullmatch(r"/api/thread/(\d+)", path)
            if m:
                return self._json([dict(r) for r in store.thread(int(m.group(1)))])
            self._send(b"not found", "text/plain", 404)
        finally:
            store.close()

    def do_POST(self) -> None:
        # Same checks as GET, plus: a cross-site page can submit a form to localhost, but it can't send
        # application/json without a CORS preflight, which this server never answers. Origin, when the
        # browser sends one, must be this server.
        host = self.headers.get("Host", "")
        if host not in self.allowed_hosts:
            return self._send(b"forbidden host", "text/plain", 403)
        origin = self.headers.get("Origin")
        if origin is not None and origin != f"http://{host}":
            return self._send(b"forbidden origin", "text/plain", 403)
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            return self._send(b"json only", "text/plain", 415)
        if urlsplit(self.path).path != "/api/mark":
            return self._send(b"not found", "text/plain", 404)
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if not 0 < length <= 4096:
            return self._send(b"bad length", "text/plain", 400)
        try:
            req = json.loads(self.rfile.read(length))
            pid, src, owner, state = (req["person_id"], req["source_message_id"], req["owner"], req["state"])
            if not (isinstance(pid, int) and isinstance(src, int) and owner in ("me", "them")
                    and state in ("done", "dismissed", "snoozed", "open", "clear")):
                raise ValueError
            days = req.get("days", 3)
            if state == "snoozed" and not (isinstance(days, int) and 1 <= days <= 60):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            return self._send(b"bad request", "text/plain", 400)
        store = Store(self.db)
        try:
            if not store.has_item(pid, src, owner):
                return self._send(b"no such item", "text/plain", 404)
            if state == "clear":
                store.unresolve(pid, src, owner)
            else:
                until = time.time() + days * 86400 if state == "snoozed" else None
                store.resolve(pid, src, owner, state, "you", until=until)
            return self._json({"ok": True})
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
