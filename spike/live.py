"""Live sync: what the soloyolo Chrome extension (extension/) posts to `/api/live/sync`.

An export is a snapshot you have to keep re-requesting. The extension instead reads your inbox through the
session already open in Chrome, the way Kondo does for LinkedIn, and sends new messages here. It only reads
and never sends. It covers LinkedIn, Instagram and X, and each network's payload is turned into the same
Result its export importer builds and stored by that importer's save(), so a person has one handle either
way and a message both paths have seen is stored once.

The extension authenticates with one pairing token for every network: `python -m spike linkedin-token`
prints it, you paste it into the extension's options. Payload (every field but the ids may be missing;
anything malformed is skipped):

    {"network": "linkedin" | "instagram" | "x",
     "me": {"id": "...", "name": "You", "username": "you"},
     "conversations": [{"id": "...", "title": "", "group": false,
                        "participants": [{"id": "...", "name": "Dana Kim", "username": "dana"}],
                        "messages": [{"id": "...", "ts": 1762000000000, "sender": "<participant id>",
                                      "text": "...", "media": ["photo"], "link": "https://..."}]}]}

What an id is depends on the network. LinkedIn: the profile URL (`url` is accepted in place of `id`, and
`subject` and `attachment` are read, as the first version of the extension sent them). Instagram: the
messaging id of a user, with the thread's own key in the conversation's `key`. X: the numeric user id.
`media` holds any of photo, video, voice, document, call, attachment; `ts` is in milliseconds.
"""
from __future__ import annotations

import hashlib
import hmac
import html
import json
import os
import secrets
import threading
import time
from collections import Counter
from pathlib import Path

from . import instagram_export, linkedin_export, x_export
from .linkedin_export import ATTACHMENT, SPONSORED, clean, normalize_url

MAX_BODY = 8 << 20  # a first sync of a busy inbox; the server refuses anything bigger
NETWORKS = ("linkedin", "instagram", "x")
SAME_MESSAGE_WINDOW = 2.0  # seconds: an export and the live sync name the same message differently


# --- pairing ----------------------------------------------------------------------------------
def token_path(db: str | Path) -> Path:
    # The name is from when LinkedIn was the only network; kept so a paired extension stays paired.
    return Path(db).expanduser().resolve().parent / "linkedin-extension-token"


def token(db: str | Path, create: bool = False) -> str | None:
    """The extension's pairing token, made on first use. Readable only by you, like the store next to it."""
    path = token_path(db)
    if path.exists():
        return path.read_text().strip() or None
    if not create:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    value = secrets.token_urlsafe(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(value + "\n")
    return value


def authorized(db: str | Path, header: str | None) -> bool:
    expected = token(db)
    given = (header or "").removeprefix("Bearer ").strip()
    return bool(expected and given) and hmac.compare_digest(expected, given)


# --- sync state, for the app's screens ----------------------------------------------------------
_STATE_LOCK = threading.Lock()
STATE_FIELDS = {"enabled": bool, "error": (str, type(None)), "you": str}  # what the extension may report


def state_path(db: str | Path) -> Path:
    return Path(db).expanduser().resolve().parent / "live-sync.json"


def _read_state(db: str | Path) -> dict:
    try:
        data = json.loads(state_path(db).read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def record(db: str | Path, network: str, **fields) -> None:
    """Remembers how a network's sync is going: what the server stored, or what the extension reported."""
    if network not in NETWORKS:
        raise ValueError(f"unknown network {network!r}")
    with _STATE_LOCK:
        data = _read_state(db)
        data[network] = {**(data.get(network) if isinstance(data.get(network), dict) else {}), **fields}
        path = state_path(db)
        tmp = path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
        os.replace(tmp, path)


def report(db: str | Path, payload: dict) -> None:
    """The extension's own view of one network: switched on or off, and the error that stopped it (or null)."""
    if not isinstance(payload, dict) or payload.get("network") not in NETWORKS:
        raise ValueError("payload has no known 'network'")
    fields = {k: payload[k] for k, kind in STATE_FIELDS.items() if k in payload and isinstance(payload[k], kind)}
    if isinstance(fields.get("error"), str):
        fields["error"] = fields["error"][:500]
        fields["failed"] = time.time()
    record(db, payload["network"], **fields)


def status(db: str | Path) -> dict:
    """{"paired": bool, "networks": {name: {"enabled", "ok", "summary", "you", "error", "failed"}}}. Times are
    epoch seconds; a field is null until something has set it."""
    data = _read_state(db)
    keys = ("enabled", "ok", "summary", "you", "error", "failed")
    return {"paired": token(db) is not None,
            "networks": {n: {k: (data.get(n) or {}).get(k) for k in keys} for n in NETWORKS}}


# --- parsing ------------------------------------------------------------------------------------
def _str(v) -> str:
    return v if isinstance(v, str) else ""


def _list(v) -> list:
    return v if isinstance(v, list) else []


def _guid(key: str) -> str:
    return "live:" + hashlib.sha256(key.encode()).hexdigest()[:40]


def _ts(m: dict) -> float | None:
    ts = m.get("ts")
    return ts / 1000 if isinstance(ts, (int, float)) and not isinstance(ts, bool) and ts > 0 else None


def _media(m: dict) -> list[str]:
    return [k for k in _list(m.get("media")) if isinstance(k, str)]


def _conversations(payload: dict, skipped: Counter):
    for conv in _list(payload.get("conversations")):
        if not isinstance(conv, dict) or not _str(conv.get("id")):
            skipped["malformed conversations"] += 1
            continue
        yield conv, [m for m in _list(conv.get("messages")) if isinstance(m, dict)]


def _me(payload) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    return payload.get("me") if isinstance(payload.get("me"), dict) else {}


def _linkedin_text(m: dict) -> str:
    text = clean(_str(m.get("text")))
    subject = clean(_str(m.get("subject")))
    if subject and subject.casefold() not in text.casefold():  # same rule as the export: InMail's ask is in the subject
        text = f"{subject}\n{text}".strip()
    if not text and (m.get("attachment") is True or _media(m)):
        text = ATTACHMENT
    return text


def parse_linkedin(payload: dict) -> linkedin_export.Result:
    """Turns the extension's payload into the export's Result. Raises ValueError when it can't tell who you are."""
    me_obj = _me(payload)
    me = normalize_url(_str(me_obj.get("id")) or _str(me_obj.get("url")))
    if not me:
        raise ValueError("payload has no 'me' profile URL")
    res = linkedin_export.Result(me=me)
    skipped: Counter = Counter()
    for conv, msgs in _conversations(payload, skipped):
        names: dict[str, str] = {}
        for p in _list(conv.get("participants")):
            url = normalize_url(_str(p.get("id")) or _str(p.get("url"))) if isinstance(p, dict) else None
            if url and url != me:
                names[url] = clean(_str(p.get("name"))) or url
        if conv.get("group") is True or len(names) > 1:
            title = clean(_str(conv.get("title"))) or ", ".join(sorted(names.values())) or "unnamed"
            lines = res.groups.setdefault(title, [])
            for m in msgs:
                ts, text = _ts(m), _linkedin_text(m)
                if ts is None or not _str(m.get("id")) or not text:
                    continue
                sender = normalize_url(_str(m.get("sender")))
                lines.append(linkedin_export.GroupLine(_guid(m["id"]), ts, "me" if sender == me else names.get(sender or "", "?"), text))
            continue
        if not names:  # a company page, a sponsored message, or a deleted member: no person to key by
            skipped["threads with no member on the other side"] += 1
            continue
        other, name = next(iter(names.items()))
        added = False
        for m in msgs:
            ts, text, sender = _ts(m), _linkedin_text(m), normalize_url(_str(m.get("sender")))
            if ts is None or not _str(m.get("id")) or not text or sender not in (me, other):
                skipped["messages with no id, time, text or known sender"] += 1
                continue
            if SPONSORED.search(_str(m.get("text"))):
                skipped["sponsored"] += 1
                continue
            res.messages.append(linkedin_export.Message(_guid(m["id"]), other, ts, sender == me, text))
            added = True
        if added:
            res.names[other] = name
    res.notes = [f"skipped {n} {why}" for why, n in skipped.items()]
    return res


IG_MARKS = {"photo": instagram_export.PHOTO, "video": instagram_export.VIDEO, "voice": instagram_export.VOICE,
            "document": instagram_export.DOCUMENT}


def _instagram_text(m: dict) -> str | None:
    """The same text the export importer's body() stores: media and shares as markers, then what was typed."""
    media = _media(m)
    if "call" in media:
        return instagram_export.CALL
    content = _str(m.get("text")).strip()
    marks = [IG_MARKS[k] for k in dict.fromkeys(media) if k in IG_MARKS]
    link = _str(m.get("link")).strip()
    if link and link not in content:
        marks.append(f"{instagram_export.LINK} {link}")
    return " ".join(marks + ([content] if content else [])).strip() or None


def parse_instagram(payload: dict) -> instagram_export.Result:
    """1:1 threads become messages keyed 'thread:<key>', as the export importer keys them; groups become evidence."""
    me_obj = _me(payload)
    me = _str(me_obj.get("id"))
    if not me:
        raise ValueError("payload has no 'me' id")
    res = instagram_export.Result(me=_str(me_obj.get("name")) or _str(me_obj.get("username")) or me)
    skipped: Counter = Counter()
    for conv, msgs in _conversations(payload, skipped):
        others: dict[str, dict] = {}
        for p in _list(conv.get("participants")):
            if isinstance(p, dict) and _str(p.get("id")) and p["id"] != me:
                others[p["id"]] = p
        names = {uid: _str(p.get("name")).strip() or _str(p.get("username")) or "Instagram user" for uid, p in others.items()}
        key = _str(conv.get("key")) or conv["id"]
        rows, seen = [], Counter()
        for m in sorted(msgs, key=lambda m: _ts(m) or 0):
            ts, text = _ts(m), _instagram_text(m)
            if ts is None or not _str(m.get("id")) or not text or not _str(m.get("sender")):
                skipped["messages with no id, time, text or sender"] += 1
                continue
            # The export importer's own id (instagram_export._guid), so a message both have seen is one row
            # whichever arrives first. It holds when the thread key, the time, the name and the text all agree.
            sender = res.me if m["sender"] == me else names.get(m["sender"], "")
            k = f"ig|{key}|{int(m['ts'])}|{sender}|{text}"
            seen[k] += 1
            rows.append((hashlib.sha256(f"{k}|{seen[k]}".encode()).hexdigest()[:40], ts, m["sender"], text))
        if conv.get("group") is True or len(others) > 1:
            title = _str(conv.get("title")).strip() or ", ".join(sorted(names.values())) or "unnamed"
            lines = res.groups.setdefault(title, [])
            lines += [instagram_export.GroupLine(guid, ts, "me" if sender == me else names.get(sender, "?"), text)
                      for guid, ts, sender, text in rows if text != instagram_export.CALL]
            continue
        if not others:
            skipped["threads with only you in them"] += 1
            continue
        other = next(iter(others))
        handle = f"thread:{key}"
        kept = [instagram_export.Message(guid, handle, ts, sender == me, text)
                for guid, ts, sender, text in rows if sender in (me, other)]
        if not kept:
            continue
        res.messages += kept
        res.names[handle] = names[other]
        if _str(others[other].get("username")):  # the live API names the account, so no need to confirm it
            res.usernames[handle] = others[other]["username"]
    res.notes = [f"skipped {n} {why}" for why, n in skipped.items()]
    return res


X_MARKS = {"photo": x_export.PHOTO, "video": x_export.VIDEO, "voice": x_export.VOICE}


def _x_text(m: dict) -> str | None:
    marks = [X_MARKS[k] for k in dict.fromkeys(_media(m)) if k in X_MARKS]
    return " ".join(marks + [html.unescape(_str(m.get("text"))).strip()]).strip() or None


def parse_x(payload: dict) -> x_export.Result:
    """1:1 conversations become messages keyed 'id:<user id>' with the DM's own id, exactly as the archive
    importer stores them, so a DM in both is one row. Groups become evidence."""
    me = _str(_me(payload).get("id"))
    if not me.isdigit():
        raise ValueError("payload has no numeric 'me' id")
    res = x_export.Result(me=me)
    skipped: Counter = Counter()
    for conv, msgs in _conversations(payload, skipped):
        others: dict[str, dict] = {}
        for p in _list(conv.get("participants")):
            if isinstance(p, dict) and _str(p.get("id")).isdigit() and p["id"] != me:
                others[p["id"]] = p

        def name(uid: str) -> str | None:
            p = others.get(uid) or {}
            return _str(p.get("name")).strip() or (f"@{p['username']}" if _str(p.get("username")) else None)

        rows = []
        for m in msgs:
            ts, text, sender = _ts(m), _x_text(m), _str(m.get("sender"))
            if ts is None or not _str(m.get("id")).isdigit() or not text or not sender:
                skipped["DMs with nothing to keep (a GIF alone, or no date or id)"] += 1
                continue
            rows.append((m["id"], ts, sender, text))
        if conv.get("group") is True or len(others) > 1:
            lines = res.groups.setdefault(conv["id"], [])
            lines += [x_export.GroupLine(mid, ts, "me" if sender == me else name(sender) or f"X user {sender}", text)
                      for mid, ts, sender, text in rows]
            continue
        if len(others) != 1:
            skipped["1:1 conversations that don't name you and one other person"] += 1
            continue
        other = next(iter(others))
        handle = f"id:{other}"
        kept = [x_export.Message(mid, handle, ts, sender == me, text) for mid, ts, sender, text in rows if sender in (me, other)]
        if not kept:
            continue
        res.messages += kept
        res.people[handle] = {"x_id": other, "x": _str(others[other].get("username"))}
        if name(other):
            res.names[handle] = name(other)
    res.notes = [f"skipped {n} {why}" for why, n in skipped.items()]
    return res


PARSERS = {"linkedin": parse_linkedin, "instagram": parse_instagram, "x": parse_x}


def parse(payload: dict, network: str | None = None):
    """(network, that network's export Result). `network` is the default for a payload that doesn't say."""
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    network = payload.get("network", network)
    if network not in PARSERS:
        raise ValueError(f"payload has no known 'network' (one of {', '.join(NETWORKS)})")
    return network, PARSERS[network](payload)


# --- writing ------------------------------------------------------------------------------------
def _unseen(store, network: str, messages: list) -> list:
    """Messages not already stored under another id. Instagram's export gives messages no id of their own; when
    the id built in parse_instagram doesn't line up with the export's (a changed display name, say), one the
    export already stored is matched by person, direction, time and text, as linkedin_export.save does."""
    out = []
    for m in messages:
        row = store.conn.execute(
            "SELECT 1 FROM message m JOIN handle h ON h.person_id = m.person_id AND h.network = ? AND h.address = ?"
            " WHERE m.network = ? AND m.remote_id != ? AND m.from_me = ? AND m.text = ? AND m.ts BETWEEN ? AND ?",
            (network, m.handle, network, m.guid, int(m.from_me), m.text,
             m.ts - SAME_MESSAGE_WINDOW, m.ts + SAME_MESSAGE_WINDOW)).fetchone()
        if not row:
            out.append(m)
    return out


def save(store, network: str, res) -> str:
    """Stores res through the network's export importer. Returns its one-line summary."""
    if network == "linkedin":
        return linkedin_export.save(store, res)  # does its own cross-path check
    if network == "instagram":
        res.messages = _unseen(store, "instagram", res.messages)
        return instagram_export.save(store, res)
    if network == "x":
        return x_export.save(store, res)  # the DM's own id dedupes
    raise ValueError(f"unknown network {network!r}")
