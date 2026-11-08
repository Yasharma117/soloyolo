"""Import an Instagram "Download your information" export (JSON) into the store. Format notes: docs/INSTAGRAM-X.md.

Instagram's private API through cookies carries the highest ban risk of any network, so read Instagram's
own export instead. In the app: Accounts Center → Your information and permissions → Download your
information → Download or transfer information → Some of your information → Messages → Download to
device → Date range: All time, Format: JSON → Create files. Instagram emails a link when it's ready.

    python -m spike import-instagram ~/Downloads/instagram-yourname-2026-11-07-*.zip

What it reads (anywhere in the zip or folder; a big export split into several zips can be passed whole):

    messages/inbox/<thread>/message_N.json             1:1 threads become messages on network 'instagram';
    messages/message_requests/<thread>/message_N.json  group threads become evidence ('instagram-group:<title>').
                                                       Requests are kept only if you replied.
    personal_information.json                          your name, to tell which sender is you.
    following.json, followers_N.json                   usernames, to confirm a thread folder is named after one.

Meta writes the JSON's text as UTF-8 bytes escaped one per character (\\u00e0\\u00a4\\u00a8 for "न"); it's
repaired here. Re-importing the same or a newer export adds only what's new.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .identity import add_attribute, normalize_handle

NETWORK = "instagram"
SOURCE = "instagram-export"  # attribute.source
ATTRIBUTE_DDL = ("CREATE TABLE IF NOT EXISTS attribute (person_id INTEGER NOT NULL REFERENCES person(id),"
                 " key TEXT NOT NULL, value TEXT NOT NULL, source TEXT NOT NULL, ts REAL NOT NULL,"
                 " PRIMARY KEY (person_id, key, value, source));")

THREAD_FILE = re.compile(r"(?:^|/)messages/(inbox|message_requests)/([^/]+)/message_(\d+)\.(json|html)$", re.I)
CONNECTION_FILE = re.compile(r"(?:^|/)(following|followers(?:_\d+)?|close_friends)\.json$", re.I)
CALL, PHOTO, VIDEO, VOICE, DOCUMENT, LINK = "[call]", "[photo]", "[video]", "[voice note]", "[document]", "[link]"

# Content Instagram writes itself. Kept out: it's not something anyone said.
SYSTEM = re.compile(
    r"^(liked a message|.*\breacted .{1,12} to (your|a) message\b.*|.*\bunsent a message\b.*|message unavailable"
    r"|this message (is unavailable|was unsent).*|.*\b(created|named|left) the group\b.*|.*\bchanged the group (name|photo)\b.*"
    r"|.*\badded .+ to the group\b.*|.*\bremoved .+ from the group\b.*|.*\bset (the|your) nickname\b.*"
    r"|.*\bchanged the theme\b.*|.*\bset the quick reaction\b.*|messages and calls are (now )?secured.*"
    r"|.*\bturned (on|off) disappearing messages\b.*|.*\bmentioned you in (their|a) story\b.*)$", re.I)
# "You sent an attachment." / "Asha shared a reel." / "Asha sent a voice message.": a caption for media
ATTACHMENT_NOTE = re.compile(r"^.{0,60}\b(sent an attachment|sent a (photo|video|voice message|gif|sticker)"
                             r"|shared a (story|post|reel|link|profile)|sent a (post|reel|story))\.?$", re.I)
CALL_NOTE = re.compile(r"^.{0,60}\b((audio|video) (call|chat) ended|joined (an audio|a video) (call|chat))\b.*$", re.I)
CALL_START = re.compile(r"^.{0,60}\bstarted (an audio|a video) (call|chat)\b.*$", re.I)  # may never have connected
MISSED = re.compile(r"^.{0,60}\bmissed (an? )?(audio |video )?(call|chat)\b.*$", re.I)


def fix_mojibake(s: str) -> str:
    """Meta's 'ð\\x9f\\x91\\x8d' -> '👍'. Text that isn't mojibake (real Latin-1, or already fixed) is left alone."""
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def fix_all(v):
    if isinstance(v, str):
        return fix_mojibake(v)
    if isinstance(v, list):
        return [fix_all(x) for x in v]
    if isinstance(v, dict):
        return {k: fix_all(x) for k, x in v.items()}
    return v


@dataclass(frozen=True)
class Message:
    guid: str
    handle: str  # 'thread:<id>': display names aren't unique and the export has no user ids
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
class Thread:
    folder: str
    box: str  # inbox | message_requests
    title: str = ""
    participants: list[str] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)

    @property
    def key(self) -> str:
        """The thread id: the numeric tail of 'ashaverma_1234567890'. The name part changes if they rename."""
        head, _, tail = self.folder.rpartition("_")
        return tail if head and tail.isdigit() else self.folder

    @property
    def names(self) -> set[str]:
        return (set(self.participants) | {m.get("sender_name", "") for m in self.messages}) - {""}


@dataclass
class Result:
    me: str
    messages: list[Message] = field(default_factory=list)
    names: dict[str, str] = field(default_factory=dict)
    usernames: dict[str, str] = field(default_factory=dict)  # handle -> instagram username, when confirmed
    groups: dict[str, list[GroupLine]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


# --- reading ------------------------------------------------------------------------------
def _entries(path: Path):
    """(name inside the export, bytes loader) for every file in a zip or folder."""
    if path.is_dir():
        for p in sorted(path.rglob("*")):
            if p.is_file():
                yield p.relative_to(path).as_posix(), p.read_bytes
    elif path.suffix.lower() == ".zip":
        z = zipfile.ZipFile(path)
        for n in sorted(z.namelist()):
            yield n, (lambda n=n: z.read(n))
    elif path.suffix.lower() == ".json":
        yield path.as_posix(), path.read_bytes
    else:
        raise ValueError(f"{path}: not an Instagram export (expected a .zip, a folder or a message_N.json)")


def _values(v, label: str) -> list[str]:
    """Every value filed under `label`, in any of Meta's shapes: string_map_data {label: {value}},
    label_values [{label, value}], or plain {label: value}."""
    out: list[str] = []
    if isinstance(v, dict):
        if v.get("label") == label and isinstance(v.get("value"), str):
            out.append(v["value"])
        for k, x in v.items():
            if k == label and isinstance(x, dict) and isinstance(x.get("value"), str):
                out.append(x["value"])
            elif k == label and isinstance(x, str):
                out.append(x)
            else:
                out += _values(x, label)
    elif isinstance(v, list):
        for x in v:
            out += _values(x, label)
    return out


def _usernames(v) -> set[str]:
    """Usernames in following.json / followers_N.json. Each entry has string_list_data [{href, value, timestamp}];
    newer exports put the username in the entry's title and leave value out."""
    out: set[str] = set()
    if isinstance(v, dict):
        if isinstance(v.get("string_list_data"), list):
            raw = [v.get("title") or ""] + [x.get(k) or "" for x in v["string_list_data"] if isinstance(x, dict)
                                            for k in ("value", "href")]
            out |= {u for u in (normalize_handle("instagram", r.replace("/_u/", "/")) for r in raw if r) if u}
        for x in v.values():
            if isinstance(x, (dict, list)):
                out |= _usernames(x)
    elif isinstance(v, list):
        for x in v:
            out |= _usernames(x)
    return out


def read(paths: list[Path]) -> tuple[dict[str, Thread], dict[str, list[str]], set[str], list[str]]:
    """(threads by folder, your profile {'Name': [...], 'Username': [...]}, usernames you follow or who follow you, notes)."""
    threads: dict[str, Thread] = {}
    profile: dict[str, list[str]] = defaultdict(list)
    usernames: set[str] = set()
    html_only: set[str] = set()
    notes: list[str] = []
    for path in map(Path, paths):
        for name, load in _entries(path):
            m = THREAD_FILE.search(name)
            if m and m[4].lower() == "html":
                html_only.add(m[2])
                continue
            base = name.rsplit("/", 1)[-1].lower()
            if not m and base != "personal_information.json" and not CONNECTION_FILE.search(name):
                continue
            try:
                data = fix_all(json.loads(load().decode("utf-8-sig")))
            except (ValueError, UnicodeDecodeError) as err:
                notes.append(f"{name}: unreadable, skipped ({err})")
                continue
            if m:
                t = threads.setdefault(m[2], Thread(m[2], m[1].lower()))
                if m[1].lower() == "inbox":
                    t.box = "inbox"  # a request you accepted can be in both folders
                if not isinstance(data, dict) or not isinstance(data.get("messages"), list):
                    notes.append(f"{name}: no messages list, skipped")
                    continue
                t.title = t.title or data.get("title") or ""
                for p in data.get("participants") or []:
                    n = p.get("name") if isinstance(p, dict) else p
                    if isinstance(n, str) and n and n not in t.participants:
                        t.participants.append(n)
                t.messages += [x for x in data["messages"] if isinstance(x, dict)]
            elif base == "personal_information.json":
                for label in ("Name", "Username"):
                    profile[label] += [v for v in _values(data, label) if v]
            else:
                usernames |= _usernames(data)
    if html_only - set(threads):
        raise ValueError(f"this export is HTML ({len(html_only - set(threads))} threads as message_N.html): "
                         "request it again with Format: JSON (docs/INSTAGRAM-X.md)")
    return threads, profile, usernames, notes


def infer_me(threads: dict[str, Thread], profile: dict[str, list[str]], me: str | None = None) -> str:
    """You: --me, else your profile name if it's in a thread, else the one participant in every thread."""
    everyone = Counter(n for t in threads.values() for n in t.names)
    if me:
        if me not in everyone:
            raise ValueError(f"--me {me!r} isn't a sender in this export; senders include: "
                             + ", ".join(n for n, _ in everyone.most_common(8)))
        return me
    for n in profile.get("Name", []) + profile.get("Username", []):
        if n in everyone:
            return n
    if len(threads) >= 2:
        common = set.intersection(*(t.names for t in threads.values()))
        if len(common) == 1:
            return common.pop()
    raise ValueError("can't tell which sender is you: pass --me \"Your Name\" as Instagram shows it; "
                     "senders include: " + ", ".join(n for n, _ in everyone.most_common(8)))


def body(m: dict) -> str | None:
    """The stored text for one message, or None to skip it. Media, shares and calls become markers."""
    if m.get("is_unsent") or m.get("is_unsent_image_by_messenger_kid_parent"):
        return None
    content = (m.get("content") or "").strip()
    # A call that connected is what closes "I'll call you back"; a missed or unanswered one isn't.
    if "call_duration" in m:
        return CALL if (m.get("call_duration") or 0) > 0 else None
    if CALL_START.match(content) or MISSED.match(content):
        return None
    if m.get("type") == "Call" or CALL_NOTE.match(content):
        return CALL
    if SYSTEM.match(content):
        return None
    if ATTACHMENT_NOTE.match(content):
        content = ""
    marks: list[str] = []
    for key, mark in (("photos", PHOTO), ("videos", VIDEO), ("audio_files", VOICE), ("files", DOCUMENT)):
        if m.get(key):
            marks.append(mark)  # one marker per kind: an album of six is still "sent the photos"
    share = m.get("share") if isinstance(m.get("share"), dict) else {}
    link = (share.get("link") or "").strip()
    if link and link not in content:
        marks.append(f"{LINK} {link}")
    elif share and not link and share.get("share_text"):
        marks.append(LINK)
    text = " ".join(marks + ([content] if content else [])).strip()
    return text or None  # stickers and GIFs alone say nothing


def _guid(t: Thread, m: dict, text: str, seen: Counter) -> str:
    key = f"ig|{t.key}|{m.get('timestamp_ms')}|{m.get('sender_name', '')}|{text}"
    seen[key] += 1  # two identical lines in the same millisecond stay distinct
    return hashlib.sha256(f"{key}|{seen[key]}".encode()).hexdigest()[:40]  # a dedupe key, not security


def load(paths: list[Path], me: str | None = None) -> Result:
    threads, profile, usernames, notes = read(paths)
    if not threads:
        raise ValueError("no messages/inbox/<thread>/message_N.json found: is this an Instagram JSON export "
                         "with Messages selected?")
    res = Result(infer_me(threads, profile, me), notes=notes)
    skipped: Counter = Counter()
    for t in sorted(threads.values(), key=lambda t: t.folder):
        others = t.names - {res.me}
        if res.me not in t.names:
            skipped["threads you're not in (pass --me if this is wrong)"] += 1
            continue
        senders = {m.get("sender_name") for m in t.messages}
        if t.box == "message_requests" and res.me not in senders:
            skipped["message requests you never answered"] += 1
            continue
        # The zip and its unzipped folder, or a request also filed in the inbox: the same message twice.
        unique = {json.dumps(m, sort_keys=True, ensure_ascii=False): m for m in t.messages}
        msgs = sorted(unique.values(), key=lambda m: m.get("timestamp_ms") or 0)
        seen: Counter = Counter()
        if len(others) >= 2:  # a group, even one everyone else has since left
            title = t.title or ", ".join(sorted(others))
            out = res.groups.setdefault(title, [])
            for m in msgs:
                text, ts = body(m), m.get("timestamp_ms")
                if text is None or text == CALL or not ts or not m.get("sender_name"):
                    continue  # a call in a group says nothing about who talked to whom
                sender = m["sender_name"]
                out.append(GroupLine(_guid(t, m, text, seen), ts / 1000, "me" if sender == res.me else sender, text))
            continue
        if not others:
            skipped["threads with only you in them"] += 1
            continue
        other = others.pop()
        handle = f"thread:{t.key}"
        res.names[handle] = other
        slug = t.folder.rpartition("_")[0] if t.key != t.folder else ""
        if slug and slug in usernames:  # the folder is named after their username, and you're connected
            res.usernames[handle] = slug
        for m in msgs:
            text, ts, sender = body(m), m.get("timestamp_ms"), m.get("sender_name")
            if text is None or not ts or sender not in (res.me, other):
                continue
            res.messages.append(Message(_guid(t, m, text, seen), handle, ts / 1000, sender == res.me, text))
    for why, n in skipped.items():
        res.notes.append(f"skipped {n} {why}")
    res.notes.append(f"you are {res.me!r}; {len(res.messages)} messages in {len(res.names)} 1:1 threads; "
                     f"{sum(map(len, res.groups.values()))} lines in {len(res.groups)} groups kept as evidence "
                     "(closes items, never creates them)")
    return res


# --- writing --------------------------------------------------------------------------------
def save(store, res: Result) -> str:
    """Writes res into the store. Returns a one-line summary. Safe to run again: adds only what's new."""
    conn = store.conn
    conn.execute(ATTRIBUTE_DDL)  # for stores whose core.sql predates the attribute table
    added = store.add_messages(NETWORK, res.messages, res.names)
    attrs = 0
    with conn:
        for handle, name in res.names.items():
            pid = store.person_for(NETWORK, handle)
            if handle in res.usernames:
                attrs += add_attribute(conn, pid, "instagram", res.usernames[handle], SOURCE, time.time())
    lines = sum(store.add_evidence(f"instagram-group:{title}", rows) for title, rows in res.groups.items())
    return (f"{added} new messages from {len(res.names)} threads, {lines} new group lines, "
            f"{attrs} new attributes")
