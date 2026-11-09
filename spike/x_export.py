"""Import an X (Twitter) archive ("Download an archive of your data") into the store. Format notes: docs/INSTAGRAM-X.md.

Reading DMs live needs a paid API tier, so read X's own archive instead. On x.com: More → Settings and
privacy → Your account → Download an archive of your data → confirm your password and a code →
Request archive. X emails when the zip is ready (a day or more); download it from the same page.

    python -m spike import-x ~/Downloads/twitter-2026-11-07-*.zip

What it reads (anywhere in the zip or folder; other files are ignored):

    data/direct-messages.js        1:1 conversations become messages on network 'x', keyed by the other
                                   person's numeric user id. Each file is `window.YTD.<feed>.partN = [...]`.
    data/direct-messages-group.js  group conversations become evidence ('x-group:<conversationId>').
    data/account.js                your user id, so the right side of every conversation is you.
    data/tweets.js (or tweet.js)   names and handles for user ids: DMs carry only numbers, but your
                                   tweets' mentions and replies name the people in them.

Each person gets an x_id attribute, and an x (handle) attribute when the archive names them.
Re-importing the same or a newer archive adds only what's new: every DM has its own id.
"""
from __future__ import annotations

import html
import json
import re
import time
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .identity import add_attribute, normalize_handle

NETWORK = "x"
SOURCE = "x-export"  # attribute.source
ATTRIBUTE_DDL = ("CREATE TABLE IF NOT EXISTS attribute (person_id INTEGER NOT NULL REFERENCES person(id),"
                 " key TEXT NOT NULL, value TEXT NOT NULL, source TEXT NOT NULL, ts REAL NOT NULL,"
                 " PRIMARY KEY (person_id, key, value, source));")

# data/direct-messages.js, data/direct-messages-part1.js, data/direct-messages-group.js, data/tweets-part2.js
FEED = re.compile(r"(?:^|/)(direct-messages(?:-group)?|account|tweets?)(?:-part\d+)?\.js$", re.I)
PREFIX = re.compile(r"^\s*window\.YTD\.[\w]+\.part\d+\s*=\s*")
PHOTO, VIDEO, VOICE = "[photo]", "[video]", "[voice note]"
MEDIA_LINK = re.compile(r"(twitter|x)\.com/messages/media/\d+", re.I)


def read_js(raw: bytes, where: str):
    """The JSON array inside `window.YTD.direct_messages.part0 = [...]`."""
    text = raw.decode("utf-8-sig")
    m = PREFIX.match(text)
    if not m:
        raise ValueError(f"{where}: no window.YTD.<feed>.partN = prefix; not an X archive file")
    return json.loads(text[m.end():])


@dataclass(frozen=True)
class Message:
    guid: str
    handle: str  # 'id:<numeric user id>': handles change, ids don't
    ts: float
    from_me: bool
    text: str


@dataclass(frozen=True)
class GroupLine:
    remote_id: str
    ts: float
    sender: str  # 'me' for you
    text: str


@dataclass
class Result:
    me: str  # your numeric user id
    messages: list[Message] = field(default_factory=list)
    names: dict[str, str] = field(default_factory=dict)  # handle -> display name, only when the archive has one
    people: dict[str, dict] = field(default_factory=dict)  # handle -> {'x_id', 'x'}
    groups: dict[str, list[GroupLine]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


# --- reading ------------------------------------------------------------------------------
def _entries(path: Path):
    if path.is_dir():
        for p in sorted(path.rglob("*.js")):
            yield p.relative_to(path).as_posix(), p.read_bytes
    elif path.suffix.lower() == ".zip":
        z = zipfile.ZipFile(path)
        for n in sorted(z.namelist()):
            yield n, (lambda n=n: z.read(n))
    elif path.suffix.lower() == ".js":
        yield path.as_posix(), path.read_bytes
    else:
        raise ValueError(f"{path}: not an X archive (expected a .zip, a folder or data/direct-messages.js)")


def read(paths: list[Path]) -> tuple[dict[str, list], list[str]]:
    """{'direct-messages': [...], 'direct-messages-group': [...], 'account': [...], 'tweets': [...]}, notes."""
    feeds: dict[str, list] = {"direct-messages": [], "direct-messages-group": [], "account": [], "tweets": []}
    notes: list[str] = []
    for path in map(Path, paths):
        for name, load in _entries(path):
            m = FEED.search(name)
            if not m or "/assets/" in name:  # the archive's own viewer ships .js files too
                continue
            feed = m[1].lower()
            feed = "tweets" if feed == "tweet" else feed
            try:
                data = read_js(load(), name)
            except ValueError as err:
                notes.append(f"{name}: skipped ({str(err)[:120]})")
                continue
            feeds[feed] += data if isinstance(data, list) else []
    return feeds, notes


def directory(tweets: list) -> dict[str, tuple[str, str]]:
    """user id -> (display name, handle) from your tweets' mentions and replies. The archive has no user table."""
    out: dict[str, tuple[str, str]] = {}
    for item in tweets:
        t = item.get("tweet", item) if isinstance(item, dict) else {}
        for u in (t.get("entities") or {}).get("user_mentions") or []:
            if u.get("id_str") and u.get("screen_name"):
                out[u["id_str"]] = (u.get("name") or "", u["screen_name"])
        rid, rname = t.get("in_reply_to_user_id_str"), t.get("in_reply_to_screen_name")
        if rid and rname and rid not in out:
            out[rid] = ("", rname)
    return out


def infer_me(feeds: dict[str, list], me: str | None = None) -> str:
    """Your id: --me (an id or @handle), else account.js, else the one id in every 1:1 conversation."""
    account = next((a.get("account", a) for a in feeds["account"] if isinstance(a, dict)), {})
    if me:
        if me.lstrip("@").isdigit():
            return me.lstrip("@")
        if normalize_handle("x", me) == normalize_handle("x", account.get("username") or "") and account.get("accountId"):
            return str(account["accountId"])
        raise ValueError("--me takes your numeric user id (data/account.js: accountId)")
    if account.get("accountId"):
        return str(account["accountId"])
    ids = [set(c.get("dmConversation", {}).get("conversationId", "").split("-")) for c in feeds["direct-messages"]]
    ids = [s for s in ids if len(s) == 2]
    common = set.intersection(*ids) if len(ids) >= 2 else set()
    if len(common) == 1:
        return common.pop()
    raise ValueError("can't tell which account is you: data/account.js is missing; pass --me <your user id>")


def _ts(created: str) -> float | None:
    try:
        return datetime.fromisoformat(created.replace("Z", "+00:00")).timestamp()  # '2026-10-05T02:30:00.123Z'
    except (AttributeError, ValueError):
        return None


def media_mark(url: str) -> str | None:
    """A DM attachment's URL -> marker. GIFs say nothing, like stickers."""
    u = url.lower().split("?")[0]
    if "dm_gif" in u or "tweet_video" in u:
        return None
    if re.search(r"\.(m4a|aac|mp3|opus|ogg|wav)$", u) or "dm_audio" in u or "/audio/" in u:
        return VOICE
    if "dm_video" in u or u.endswith((".mp4", ".mov", ".m3u8")):
        return VIDEO
    return PHOTO


def body(mc: dict) -> str | None:
    """The stored text for one messageCreate, or None to skip it. t.co links are expanded and the
    attachment's own link becomes a marker."""
    text = html.unescape(mc.get("text") or "")
    for u in mc.get("urls") or []:
        short, expanded = u.get("url") or "", u.get("expanded") or ""
        if short and short in text:
            text = text.replace(short, "" if MEDIA_LINK.search(expanded) else expanded)
    marks: list[str] = []
    for url in mc.get("mediaUrls") or []:
        mark = media_mark(url)
        if mark and mark not in marks:
            marks.append(mark)
    if mc.get("mediaUrls"):  # the attachment's own t.co link, when urls didn't list it
        text = re.sub(r"\s*https://t\.co/\w+\s*$", "", text)
    text = " ".join(marks + [text.strip()]).strip()
    return text or None


def load(paths: list[Path], me: str | None = None) -> Result:
    feeds, notes = read(paths)
    if not feeds["direct-messages"] and not feeds["direct-messages-group"]:
        raise ValueError("no data/direct-messages.js found: is this an X archive?")
    res = Result(infer_me(feeds, me), notes=notes)
    people = directory(feeds["tweets"])
    skipped: Counter = Counter()

    def name(uid: str) -> str | None:
        disp, handle = people.get(uid, ("", ""))
        return disp or (f"@{handle}" if handle else None)

    for conv in feeds["direct-messages"]:
        dm = conv.get("dmConversation") or {}
        ids = [i for i in (dm.get("conversationId") or "").split("-") if i]
        others = [i for i in ids if i != res.me]
        if len(ids) != 2 or len(others) != 1:
            skipped["1:1 conversations whose id doesn't name you and one other person"] += 1
            continue
        other = others[0]
        handle = f"id:{other}"
        res.people[handle] = {"x_id": other, "x": people.get(other, ("", ""))[1]}
        if name(other):
            res.names[handle] = name(other)
        for m in dm.get("messages") or []:
            mc = m.get("messageCreate")
            if not mc:
                continue  # reactions and other events; reactions sit inside messageCreate when present
            text, ts, sender = body(mc), _ts(mc.get("createdAt")), str(mc.get("senderId") or "")
            if not text or ts is None or not mc.get("id") or sender not in (res.me, other):
                skipped["DMs with nothing to keep (a GIF alone, or no date or id)"] += 1
                continue
            res.messages.append(Message(str(mc["id"]), handle, ts, sender == res.me, text))
    for conv in feeds["direct-messages-group"]:
        dm = conv.get("dmConversation") or {}
        cid = dm.get("conversationId") or ""
        if not cid:
            continue
        out = res.groups.setdefault(cid, [])
        for m in dm.get("messages") or []:
            mc = m.get("messageCreate")
            if not mc:
                continue  # joins, leaves, renames
            text, ts, sender = body(mc), _ts(mc.get("createdAt")), str(mc.get("senderId") or "")
            if not text or ts is None or not mc.get("id"):
                continue
            who = "me" if sender == res.me else name(sender) or f"X user {sender}"
            out.append(GroupLine(str(mc["id"]), ts, who, text))
    for why, n in skipped.items():
        res.notes.append(f"skipped {n} {why}")
    unnamed = sum(1 for h in res.people if h not in res.names)
    res.notes.append(f"you are id {res.me}; {len(res.messages)} messages in {len(res.people)} 1:1 conversations"
                     f" ({unnamed} with no name in the archive: shown as 'X user <id>'); "
                     f"{sum(map(len, res.groups.values()))} lines in {len(res.groups)} groups kept as evidence "
                     "(closes items, never creates them)")
    return res


# --- writing --------------------------------------------------------------------------------
def save(store, res: Result) -> str:
    """Writes res into the store. Returns a one-line summary. Safe to run again: adds only what's new."""
    conn = store.conn
    conn.execute(ATTRIBUTE_DDL)  # for stores whose core.sql predates the attribute table
    with conn:
        for handle, p in res.people.items():
            if handle not in res.names:  # a placeholder name only for a new card; never over a real one
                if not conn.execute("SELECT 1 FROM handle WHERE network = ? AND address = ?", (NETWORK, handle)).fetchone():
                    store.person_for(NETWORK, handle, f"X user {p['x_id']}")
    added = store.add_messages(NETWORK, res.messages, res.names)
    attrs = 0
    with conn:
        for handle, p in res.people.items():
            pid = store.person_for(NETWORK, handle, res.names.get(handle))
            for key in ("x_id", "x"):
                if p.get(key):
                    attrs += add_attribute(conn, pid, key, p[key], SOURCE, time.time())
    lines = sum(store.add_evidence(f"x-group:{cid}", rows) for cid, rows in res.groups.items())
    return (f"{added} new messages from {len(res.people)} conversations, {lines} new group lines, "
            f"{attrs} new attributes")
