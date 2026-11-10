"""Live LinkedIn sync: what the soloyolo Chrome extension (extension/) posts to `/api/linkedin/sync`.

The export (linkedin_export.py) is a snapshot you have to keep re-requesting. The extension instead reads your
inbox through the LinkedIn session already open in Chrome, the way Kondo does, and sends new messages here. It
only reads and never sends. Both paths build the same Result and go through linkedin_export.save, so a person's
handle is their profile URL either way, and a message seen by both is stored once (see save's content check).

The extension authenticates with a pairing token: `python -m spike linkedin-token` prints it, you paste it into
the extension's options. Payload (every field but the ids may be missing; anything malformed is skipped):

    {"me": {"url": "https://www.linkedin.com/in/you", "name": "You"},
     "conversations": [{"id": "urn:li:msg_conversation:...", "title": "", "group": false,
                        "participants": [{"url": "...", "name": "Dana Kim"}],
                        "messages": [{"id": "urn:li:msg_message:...", "ts": 1762000000000, "sender": "<profile url>",
                                      "text": "...", "subject": "", "attachment": false}]}]}
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from collections import Counter
from pathlib import Path

from .linkedin_export import ATTACHMENT, SPONSORED, GroupLine, Message, Result, clean, normalize_url

MAX_BODY = 8 << 20  # a first sync of a busy inbox; the server refuses anything bigger


def token_path(db: str | Path) -> Path:
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


def _str(v) -> str:
    return v if isinstance(v, str) else ""


def _guid(urn: str) -> str:
    return "live:" + hashlib.sha256(urn.encode()).hexdigest()[:40]


def _text(m: dict) -> str:
    text = clean(_str(m.get("text")))
    subject = clean(_str(m.get("subject")))
    if subject and subject.casefold() not in text.casefold():  # same rule as the export: InMail's ask is in the subject
        text = f"{subject}\n{text}".strip()
    if not text and m.get("attachment") is True:
        text = ATTACHMENT
    return text


def parse(payload: dict) -> Result:
    """Turns the extension's payload into the export's Result. Raises ValueError when it can't tell who you are."""
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    me_obj = payload.get("me") if isinstance(payload.get("me"), dict) else {}
    me = normalize_url(_str(me_obj.get("url")))
    if not me:
        raise ValueError("payload has no 'me' profile URL")
    res = Result(me=me)
    skipped: Counter = Counter()
    convs = payload.get("conversations")
    for conv in convs if isinstance(convs, list) else []:
        if not isinstance(conv, dict) or not _str(conv.get("id")):
            skipped["malformed conversations"] += 1
            continue
        names: dict[str, str] = {}
        for p in conv.get("participants") if isinstance(conv.get("participants"), list) else []:
            url = normalize_url(_str(p.get("url"))) if isinstance(p, dict) else None
            if url and url != me:
                names[url] = clean(_str(p.get("name"))) or url
        msgs = [m for m in conv.get("messages") or [] if isinstance(m, dict)] if isinstance(conv.get("messages"), list) else []
        if conv.get("group") is True or len(names) > 1:
            title = clean(_str(conv.get("title"))) or ", ".join(sorted(names.values())) or "unnamed"
            lines = res.groups.setdefault(title, [])
            for m in msgs:
                ts, text = m.get("ts"), _text(m)
                if not (isinstance(ts, (int, float)) and _str(m.get("id")) and text):
                    continue
                sender = normalize_url(_str(m.get("sender")))
                lines.append(GroupLine(_guid(m["id"]), ts / 1000, "me" if sender == me else names.get(sender or "", "?"), text))
            continue
        if not names:  # a company page, a sponsored message, or a deleted member: no person to key by
            skipped["threads with no member on the other side"] += 1
            continue
        other, name = next(iter(names.items()))
        added = False
        for m in msgs:
            ts, text, sender = m.get("ts"), _text(m), normalize_url(_str(m.get("sender")))
            if not (isinstance(ts, (int, float)) and _str(m.get("id")) and text) or sender not in (me, other):
                skipped["messages with no id, time, text or known sender"] += 1
                continue
            if SPONSORED.search(_str(m.get("text"))):
                skipped["sponsored"] += 1
                continue
            res.messages.append(Message(_guid(m["id"]), other, ts / 1000, sender == me, text))
            added = True
        if added:
            res.names[other] = name
    res.notes = [f"skipped {n} {why}" for why, n in skipped.items()]
    return res
