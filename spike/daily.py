"""The morning message: the 1-3 things for today, plain and short, plus a line when the plumbing broke.

What to show comes from spike/nudge.py (`today(store, now)`) when it exists, else from
spike/_nudge_stub.py (the top 3 of the ranking). This module only formats. It never sends:
the Telegram part builds the Bot API payload and reads back button taps, and the network call
is left to a sender that doesn't exist yet (docs/RUNNING-DAILY.md).

A silent failure is the worst one here: if sync stopped on Tuesday, Wednesday's "nothing today"
is a lie. So the message also says when the newest WhatsApp message is old, or when changed chats
have been waiting a long time to be read (a Claude usage limit, a lapsed login).
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import time
from datetime import datetime
from pathlib import Path

HOUR = 3600
STALE_SYNC_HOURS = 12   # a quiet night is ~8h; past 12 the sync has likely stopped
UNREAD_HOURS = 6        # changed chats unread this long: extraction is failing, not just slow
MIN_MESSAGES = 4        # same default as `watch`: shorter chats are never read, so never "waiting"


def _today_fn():
    try:
        from .nudge import today
    except ModuleNotFoundError as err:
        if err.name not in ("spike.nudge", f"{__package__}.nudge"):
            raise  # nudge.py exists but something it imports is missing: say so, don't hide it
        from ._nudge_stub import today
    return today


def today_items(store, now: float | None = None) -> list[dict]:
    return list(_today_fn()(store, now or time.time()))[:3]


# --- health --------------------------------------------------------------------------------

def health(store, now: float | None = None, stale_hours: float = STALE_SYNC_HOURS,
           unread_hours: float = UNREAD_HOURS, min_messages: int = MIN_MESSAGES) -> list[str]:
    """Plain-language warnings, empty when all is well. Reads the store only."""
    now = now or time.time()
    out = []
    conn = store.conn
    has_accounts = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'account'").fetchone()
    networks = [r[0] for r in conn.execute(
        "SELECT DISTINCT network FROM account WHERE remote_user IS NOT NULL")] if has_accounts else []
    for net in networks:  # only live-linked networks: an import-only store is old by design
        label = {"whatsapp": "WhatsApp", "imessage": "iMessage"}.get(net, net.capitalize())
        newest = conn.execute("SELECT MAX(ts) FROM message WHERE network = ?", (net,)).fetchone()[0] or 0
        groups = conn.execute("SELECT MAX(ts) FROM evidence WHERE source LIKE ?", (f"{net}-group:%",)).fetchone()[0]
        newest = max(newest, groups or 0)
        age = (now - newest) / HOUR
        if not newest:
            out.append(f"{label} is linked but no messages have arrived. See ~/.soloyolo/logs/connectord.log")
        elif age > stale_hours:
            out.append(f"{label} sync may have stopped: newest message {_hours(age)} old. "
                       f"See ~/.soloyolo/logs/connectord.log")
    counts = dict(conn.execute("SELECT person_id, COUNT(*) FROM message GROUP BY person_id").fetchall())
    pending = [pid for pid in store.changed_ids() if counts.get(pid, 0) >= min_messages]
    if pending:
        last = conn.execute("SELECT MAX(ran_at) FROM extraction_run WHERE extractor NOT LIKE 'none:%'").fetchone()[0]
        if last is None or (now - last) / HOUR > unread_hours:
            since = "never read" if last is None else f"nothing read for {_hours((now - last) / HOUR)}"
            n = len(pending)
            out.append(f"{n} changed chat{'s' if n > 1 else ''} waiting, {since}: a Claude usage limit or login? "
                       f"See ~/.soloyolo/logs/watch.log")
    return out


def _hours(h: float) -> str:
    return f"{int(h)}h" if h < 48 else f"{int(h // 24)} days"


# --- the message -----------------------------------------------------------------------------

def line(item: dict) -> str:
    """One item as one line. Names are added only when the action doesn't already say who."""
    action, name = item["action"].strip().rstrip("."), (item.get("name") or "").strip()
    first = name.split()[0].lower() if name else ""
    if item["owner"] == "me":
        text = action if not first or first in action.lower() else f"{action} ({name})"
    else:
        text = f"Waiting on {name}: {action[:1].lower()}{action[1:]}" if name else f"Waiting on them: {action}"
    why = ", ".join((item.get("reasons") or [])[:2])
    return f"{text} · {why}" if why else text


def render(items: list[dict], warnings: list[str] = (), now: float | None = None) -> str:
    d = datetime.fromtimestamp(now or time.time())
    head = f"soloyolo · {d:%a} {d.day} {d:%b}"
    if items:
        n = len(items)
        body = [f"{n} thing{'s' if n > 1 else ''} for today:"] + [f"{k}. {line(c)}" for k, c in enumerate(items, 1)]
    else:
        body = ["Nothing for today."]
    tail = [f"! {w}" for w in warnings]
    return "\n".join([head, *body, *([""] + tail if tail else [])])


# --- Telegram (formatting only; nothing here touches the network) ------------------------------
#
# Each item gets a row of buttons. A tap comes back to the bot as a callback_query carrying
# `callback_data` (at most 64 bytes), which names the item and the answer, so the sender keeps
# no state of its own: it applies the tap to the store and edits that row to show what was done.

BUTTONS = (("d", "Done"), ("x", "Not needed"), ("o", "Still on"))
STATES = {"d": "done", "x": "dismissed", "o": "open"}  # "open" by you: an explicit "not done yet"
_CB = re.compile(r"sy1:([dxo]):(\d{1,12}):(\d{1,15}):([mt])")


def callback_data(code: str, item: dict) -> str:
    data = f"sy1:{code}:{item['person_id']}:{item['source_message_id']}:{item['owner'][0]}"
    assert len(data.encode()) <= 64, data  # Telegram's limit
    return data


def telegram_message(items: list[dict], warnings: list[str] = (), now: float | None = None) -> dict:
    """A sendMessage body without chat_id. Plain text (no parse_mode), so names need no escaping."""
    text = render(items, warnings, now)
    if items:
        text += "\n\nTap one per line. No tap = done."
    body = {"text": text, "disable_web_page_preview": True}
    if items:
        body["reply_markup"] = {"inline_keyboard": [
            [{"text": f"{k} {label}", "callback_data": callback_data(code, c)} for code, label in BUTTONS]
            for k, c in enumerate(items, 1)]}
    return body


def parse_callback(data: str) -> tuple[str, int, int, str]:
    """(state, person_id, source_message_id, owner) from a button's callback_data, or ValueError."""
    m = _CB.fullmatch(data or "")
    if not m:
        raise ValueError(f"not a soloyolo button: {data!r}")
    code, pid, src, owner = m.groups()
    return STATES[code], int(pid), int(src), "me" if owner == "m" else "them"


def apply_callback(store, data: str) -> str:
    """Record a tap as your own mark. Returns the state. ValueError for junk or an item that's gone."""
    state, pid, src, owner = parse_callback(data)
    if not store.has_item(pid, src, owner):
        raise ValueError("no such item (re-read since?)")
    store.resolve(pid, src, owner, state, "you")
    return state


def tapped(markup: dict, data: str) -> dict:
    """The keyboard after a tap: that item's row collapses to one inert button saying what you chose."""
    state = parse_callback(data)[0]
    label = {"done": "done", "dismissed": "not needed", "open": "still on"}[state]
    rows = []
    for row in markup["inline_keyboard"]:
        if any(b.get("callback_data") == data for b in row):
            n = row[0]["text"].split()[0]
            rows.append([{"text": f"{n}: {label}", "callback_data": "sy1:noop"}])
        else:
            rows.append(row)
    return {"inline_keyboard": rows}


# --- output ----------------------------------------------------------------------------------

def write_private(path: Path, text: str) -> None:
    """Atomic, and readable by you only: the message names people and what you owe them."""
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".digest-")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text if text.endswith("\n") else text + "\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def digest(store, fmt: str = "text", now: float | None = None, stale_hours: float = STALE_SYNC_HOURS) -> str:
    now = now or time.time()
    items, warnings = today_items(store, now), health(store, now, stale_hours)
    if fmt == "telegram":
        return json.dumps(telegram_message(items, warnings, now), ensure_ascii=False, indent=1)
    return render(items, warnings, now)
