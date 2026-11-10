"""The local viewer. Binds to 127.0.0.1 only: this is your message history.

It reads everything and writes two things: your own marks on items (done, not needed, still on,
snooze) and which chats are muted (a bot or an assistant, not a person).

`/` is the app (app.html: Today, People, All, Sources); `/viewer` is the older desktop viewer.
"""
from __future__ import annotations

import json
import re
import time
from functools import partial
from urllib.parse import urlsplit
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import linkedin_export, linkedin_live, nudge, priority
from .store import Store

INDEX = Path(__file__).with_name("viewer.html")
APP = Path(__file__).with_name("app.html")
# Why an item closed without the chat saying so (the app asks after "Not needed"). Run 6 found most
# promises close off the chat; these are its buckets, so the answers can be counted the same way.
REASONS = {"off_chat": "done off the chat", "not_needed": "no longer needed",
           "let_go": "let it go", "misread": "not a real promise"}
# app.html is written as a page body (so the same file publishes as a demo); the server adds the document.
APP_HEAD = (b'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            b'<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"></head><body>')


def _networks(store) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {}
    for pid, net in store.conn.execute("SELECT DISTINCT person_id, network FROM handle ORDER BY network"):
        out.setdefault(pid, []).append(net)
    return out


def _tag(items: list[dict], nets: dict[int, list[str]]) -> list[dict]:
    for c in items:
        c["networks"] = nets.get(c.get("person_id", c.get("id")), [])
    return items


def person(store, pid: int) -> dict | None:
    p = next((x for x in store.people() if x["id"] == pid), None)
    if not p:
        return None
    items = [c for c in nudge.assess(store) if c["person_id"] == pid]
    live = {(c["source_message_id"], c["owner"]): c for c in items}
    for c in p["commitments"]:  # open ones carry Today's view of them: live or quiet, and why
        c.update({k: live[(c["source_message_id"], c["owner"])][k] for k in ("live", "reasons")}
                 if (c["source_message_id"], c["owner"]) in live else {"live": False, "reasons": []})
    p["handles"] = [dict(r) for r in store.conn.execute(
        "SELECT network, address FROM handle WHERE person_id = ? ORDER BY network", (pid,))]
    p["attributes"] = [dict(r) for r in store.conn.execute(
        "SELECT key, value, source FROM attribute WHERE person_id = ? AND key != 'muted' ORDER BY key", (pid,))]
    p["muted"] = pid in store.muted()
    p["networks"] = sorted({h["network"] for h in p["handles"]})
    return p


def status(store, telegram_config: Path) -> dict:
    nets = [dict(network=n, messages=c, last=t) for n, c, t in store.conn.execute(
        "SELECT network, COUNT(*), MAX(ts) FROM message GROUP BY network ORDER BY MAX(ts) DESC")]
    groups = [dict(source=s, lines=c, last=t) for s, c, t in store.conn.execute(
        "SELECT substr(source, 1, instr(source, ':') - 1), COUNT(*), MAX(ts) FROM evidence"
        " WHERE source LIKE '%-group:%' GROUP BY 1")]
    try:
        tg = json.loads(telegram_config.read_text()) if telegram_config.exists() else {}
    except ValueError:
        tg = {}
    ran = store.conn.execute("SELECT MAX(ran_at) FROM extraction_run").fetchone()[0]
    muted = [dict(id=i, name=n) for i, n in store.conn.execute(
        "SELECT p.id, p.display_name FROM person p JOIN attribute a ON a.person_id = p.id AND a.key = 'muted'")]
    return dict(networks=nets, groups=groups, telegram=bool(tg.get("chat_id")), last_read=ran,
                disclosures=store.disclosures(), muted=muted)


def insight(store, now: float | None = None, days: int = 30) -> dict:
    """What closed in the last `days`, and why, for Today's weekly insight. Numbers only; the app writes the words."""
    since = (now or time.time()) - days * 86400
    rows = store.conn.execute(
        "SELECT state, decided_by, evidence FROM resolution WHERE at >= ? AND state IN ('done', 'dismissed')", (since,)).fetchall()
    why = {k: 0 for k in REASONS}
    labels = {f"you: {v}": k for k, v in REASONS.items()}
    closed = {"by_you": 0, "by_signal": 0}
    for state, by, evidence in rows:
        closed["by_you" if by == "you" else "by_signal"] += 1
        if evidence in labels:
            why[labels[evidence]] += 1
    return {"days": days, "closed": closed, "why": why}


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
            return self._send(APP_HEAD + APP.read_bytes() + b"</body></html>", "text/html; charset=utf-8")
        if path == "/viewer":
            return self._send(INDEX.read_bytes(), "text/html; charset=utf-8")
        store = Store(self.db)
        try:
            nets = _networks(store)
            if path == "/api/people":
                return self._json(_tag(store.people(), nets))
            if path == "/api/today":
                s = nudge.summary(store)
                s["today"] = _tag(s["today"], nets)
                return self._json(s)
            if path == "/api/all":  # every open item: live ones first, each with whether it's live and why
                items = nudge.assess(store)
                return self._json(_tag(priority._spread([c for c in items if c["live"]])
                                       + priority._spread([c for c in items if not c["live"]]), nets))
            if path == "/api/insight":
                return self._json(insight(store))
            if path == "/api/status":
                from .telegram import config_path
                return self._json(status(store, config_path(self.db)))
            m = re.fullmatch(r"/api/person/(\d+)", path)
            if m:
                p = person(store, int(m.group(1)))
                return self._json(p) if p else self._send(b"no such person", "text/plain", 404)
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
        if urlsplit(self.path).path == "/api/linkedin/sync":
            return self._linkedin_sync()
        origin = self.headers.get("Origin")
        if origin is not None and origin != f"http://{host}":
            return self._send(b"forbidden origin", "text/plain", 403)
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            return self._send(b"json only", "text/plain", 415)
        route = urlsplit(self.path).path
        if route not in ("/api/mark", "/api/mute"):
            return self._send(b"not found", "text/plain", 404)
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if not 0 < length <= 4096:
            return self._send(b"bad length", "text/plain", 400)
        if route == "/api/mute":
            return self._mute(length)
        try:
            req = json.loads(self.rfile.read(length))
            pid, src, owner, state = (req["person_id"], req["source_message_id"], req["owner"], req["state"])
            if not (isinstance(pid, int) and isinstance(src, int) and owner in ("me", "them")
                    and state in ("done", "dismissed", "snoozed", "open", "clear")):
                raise ValueError
            days = req.get("days", 3)
            reason = req.get("reason")  # optional, after "Not needed": why it closed without the chat saying so
            if reason is not None and reason not in REASONS:
                raise ValueError
            if reason == "off_chat":
                state = "done"  # it was done, just not where soloyolo could see
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
                store.resolve(pid, src, owner, state, "you", until=until,
                              evidence=f"you: {REASONS[reason]}" if reason else None)
            return self._json({"ok": True})
        finally:
            store.close()

    def _mute(self, length: int) -> None:
        try:
            req = json.loads(self.rfile.read(length))
            pid, on = req["person_id"], req["mute"]
            if not (isinstance(pid, int) and isinstance(on, bool)):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            return self._send(b"bad request", "text/plain", 400)
        store = Store(self.db)
        try:
            if not store.conn.execute("SELECT 1 FROM person WHERE id = ?", (pid,)).fetchone():
                return self._send(b"no such person", "text/plain", 404)
            store.mute(pid, "muted in the app") if on else store.unmute(pid)
            return self._json({"ok": True})
        finally:
            store.close()

    def _linkedin_sync(self) -> None:
        # From the Chrome extension, so the Origin is chrome-extension://. The pairing token stands in for the
        # same-origin check: a web page can't send an Authorization header here without a preflight we never answer.
        if not linkedin_live.authorized(self.db, self.headers.get("Authorization")):
            return self._send(b"not paired: run python -m spike linkedin-token", "text/plain", 401)
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            return self._send(b"json only", "text/plain", 415)
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if not 0 < length <= linkedin_live.MAX_BODY:
            return self._send(b"bad length", "text/plain", 400)
        try:
            body = json.loads(self.rfile.read(length))
            if body == {"ping": True}:  # the extension checks it's paired before spending LinkedIn requests
                return self._json({"ok": True})
            res = linkedin_live.parse(body)
        except ValueError as err:
            return self._send(str(err).encode(), "text/plain", 400)
        store = Store(self.db)
        try:
            summary = linkedin_export.save(store, res)
        finally:
            store.close()
        self._json({"ok": True, "summary": summary, "notes": res.notes})

    def _json(self, data) -> None:
        self._send(json.dumps(data).encode(), "application/json")


def serve(db: str, port: int = 8765) -> None:
    httpd = ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, db=db, port=port))
    print(f"soloyolo viewer on http://127.0.0.1:{port}  (Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
