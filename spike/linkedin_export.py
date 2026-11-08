"""Import a LinkedIn data export ("Get a copy of your data") into the store. Format notes: docs/LINKEDIN.md.

LinkedIn has no personal messaging API, and the cookie-based clients risk a ban. The export is LinkedIn's
own copy of your data, so reading it carries no risk. On the desktop site: Me → Settings & Privacy →
Data privacy → Get a copy of your data → "Download larger data archive" → Request archive. LinkedIn
emails a zip (often in two parts: a first one in minutes to hours, the full one within about a day).

    python -m spike import-linkedin ~/Downloads/Complete_LinkedInDataExport_11-02-2026.zip

What it reads (anywhere in the zip or folder; other files are ignored):

    messages.csv     1:1 threads become messages on network 'linkedin', keyed by profile URL. Group
                     threads become evidence ('linkedin-group:<title>'): they can close items, never
                     create them. Sponsored messages, the SPAM folder and drafts are skipped.
    Connections.csv  a person per connection, with company, position, email (when shared) and the
                     date you connected as attributes. The "Notes:" preamble is skipped.
    Invitations.csv  only to tell which profile is you.
    Profile.csv      only your name, to break a tie when telling which profile is you.

Re-importing the same or a newer export adds only what's new. Passing both parts of a two-part
export, or the zip and its unzipped folder, doesn't duplicate anything.
"""
from __future__ import annotations

import csv
import hashlib
import html
import io
import re
import time
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

NETWORK = "linkedin"
SOURCE = "linkedin"  # attribute.source
ATTRIBUTE_DDL = ("CREATE TABLE IF NOT EXISTS attribute (person_id INTEGER NOT NULL REFERENCES person(id),"
                 " key TEXT NOT NULL, value TEXT NOT NULL, source TEXT NOT NULL, ts REAL NOT NULL,"
                 " PRIMARY KEY (person_id, key, value, source));")
FILES = ("messages.csv", "connections.csv", "invitations.csv", "profile.csv")
csv.field_size_limit(1 << 30)  # one message can be long

PROFILE = re.compile(r"linkedin\.com/(in|pub)/([^?#\s,;]+)", re.I)
SPONSORED = re.compile(r"%FIRSTNAME%|spinmail-quill-editor", re.I)
HTML_TAG = re.compile(r"</?(?:p|br|div|span|a|b|i|strong|em|ul|ol|li)\b[^>]*>", re.I)
CREDENTIAL = re.compile(r"^(?:[A-Z][A-Z.]{1,7}|Ph\.?D\.?|Jr\.?|Sr\.?|[IVX]{1,4})$")  # "Dana Kim, MBA"
EXPORT_DATE = re.compile(r"(\d{2})-(\d{2})-(\d{4})")  # Complete_LinkedInDataExport_11-02-2026: month first
ATTACHMENT = "[attachment]"  # LinkedIn keeps only an expiring link, but that one was sent is what counts


@dataclass(frozen=True)
class Message:
    guid: str
    handle: str  # the other person's normalized profile URL
    ts: float
    from_me: bool
    text: str


@dataclass(frozen=True)
class GroupLine:
    remote_id: str
    ts: float
    sender: str  # 'me' for you
    text: str


@dataclass(frozen=True)
class Connection:
    handle: str
    name: str
    email: str
    company: str
    position: str
    connected_on: str  # ISO date, or ''


@dataclass
class Result:
    me: str
    messages: list[Message] = field(default_factory=list)
    names: dict[str, str] = field(default_factory=dict)
    groups: dict[str, list[GroupLine]] = field(default_factory=dict)
    connections: list[Connection] = field(default_factory=list)
    snapshot_ts: float | None = None  # the export's date, from its file name
    notes: list[str] = field(default_factory=list)


# --- reading ------------------------------------------------------------------------------
def _files(path: Path) -> dict[str, list[tuple[str, str]]]:
    """{'messages.csv': [(where, text)], ...} from a zip, a folder, or one CSV. Matched by file name."""
    found: dict[str, list[tuple[str, str]]] = defaultdict(list)
    if path.is_dir():
        for p in sorted(path.rglob("*.csv")):
            if p.name.lower() in FILES:
                found[p.name.lower()].append((str(p), p.read_bytes().decode("utf-8-sig", "replace")))
    elif path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as z:
            for n in sorted(z.namelist()):
                if Path(n).name.lower() in FILES:
                    found[Path(n).name.lower()].append((f"{path.name}:{n}", z.read(n).decode("utf-8-sig", "replace")))
    elif path.name.lower() in FILES:
        found[path.name.lower()].append((str(path), path.read_bytes().decode("utf-8-sig", "replace")))
    else:
        raise ValueError(f"{path}: not a LinkedIn export (expected a .zip, a folder, or one of {', '.join(FILES)})")
    return found


def _rows(text: str, header_starts: str | None = None) -> list[dict[str, str]]:
    """CSV rows with upper-cased keys, since LinkedIn's header case differs between files and years."""
    if header_starts:  # Connections.csv: "Notes:", a quoted paragraph and a blank line come first
        lines = text.splitlines(keepends=True)
        start = next((i for i, l in enumerate(lines) if l.lstrip('"').upper().startswith(header_starts)), 0)
        text = "".join(lines[start:])

    def parse(**kw) -> list[dict]:
        return list(csv.DictReader(io.StringIO(text, newline=""), **kw))
    rows = parse()
    # Some LinkedIn files escape quotes as \" instead of "". Read that way only if it fixes broken rows.
    if any(None in r or None in r.values() for r in rows) and '\\"' in text:
        retry = parse(escapechar="\\")
        if not any(None in r or None in r.values() for r in retry):
            rows = retry
    return [{(k or "").strip().upper(): (v or "").strip() for k, v in r.items() if k is not None} for r in rows]


def normalize_url(url: str | None) -> str | None:
    """Any form of a profile link -> 'https://www.linkedin.com/in/<slug>' (lower case, decoded)."""
    m = PROFILE.search(url or "")
    if not m:
        return None
    kind, slug = m[1].lower(), unquote(m[2]).strip("/").lower()
    if kind == "in":
        slug = slug.split("/")[0]
    return f"https://www.linkedin.com/{kind}/{slug}" if slug else None


def _urls(cell: str) -> list[str]:
    """RECIPIENT PROFILE URLS: separated by commas or semicolons, depending on who you ask."""
    return [u for u in (normalize_url(p) for p in re.split(r"[\s,;]+", cell or "")) if u]


def _names(cell: str) -> list[str]:
    """'Ana Ruiz, Dana Kim, MBA' -> ['Ana Ruiz', 'Dana Kim, MBA']: a credential stays with its name."""
    out: list[str] = []
    for part in (p.strip() for p in (cell or "").split(",")):
        if not part:
            continue
        if out and CREDENTIAL.match(part):
            out[-1] += ", " + part
        else:
            out.append(part)
    return out


def fix_text(s: str) -> str:
    """UTF-8 read as Windows-1252 ('JosÃ©' for 'José') appears in some exports: undo it when it's that."""
    if not re.search(r"[ÃÂâ][\x80-\xbfŒ-™]", s):
        return s
    for enc in ("cp1252", "latin-1"):
        try:
            return s.encode(enc).decode("utf-8")
        except UnicodeError:
            continue
    return s


def clean(content: str) -> str:
    """Message body as the reader saw it: sponsored mail and InMail arrive as editor HTML."""
    s = fix_text(content or "")
    if HTML_TAG.search(s):
        s = re.sub(r"<br\s*/?>|</p>|</div>|</li>", "\n", s, flags=re.I)
        s = re.sub(r"<[^>]+>", "", s)
        s = html.unescape(s).replace("\xa0", " ")
    s = re.sub(r"[ \t]+\n", "\n", s.replace("\r\n", "\n"))
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def _ts(s: str) -> float | None:
    """messages.csv: '2026-10-20 18:40:11 UTC'. Invitations.csv: '10/30/26, 4:18 PM' (assumed UTC too)."""
    s = re.sub(r"\s*(UTC|GMT|Z)$", "", (s or "").strip())
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%m/%d/%y, %I:%M %p", "%m/%d/%Y, %I:%M %p"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
    return None


def _date(s: str) -> str:
    """Connections.csv 'Connected On': '14 Mar 2024' -> '2024-03-14'."""
    for fmt in ("%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y", "%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime((s or "").strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def _truthy(s: str) -> bool:
    return (s or "").strip().lower() in ("yes", "true", "1")


# --- who is me ------------------------------------------------------------------------------
def infer_me(msgs: list[dict], invitations: list[dict], profile: list[dict], me: str | None = None) -> tuple[str, str]:
    """(your profile URL, how it was decided). Raises ValueError when it can't be told."""
    if me:
        url = normalize_url(me)
        if url:
            return url, "--me"
        hits = Counter(normalize_url(r.get("SENDER PROFILE URL")) for r in msgs
                       if fix_text(r.get("FROM", "")).casefold() == me.strip().casefold())
        hits.pop(None, None)
        if len(hits) == 1:
            return next(iter(hits)), f"--me name '{me}'"
        raise ValueError(f"--me '{me}' matches no sender: pass your profile URL (linkedin.com/in/...)")
    # Invitations say it outright: you are the inviter of what you sent and the invitee of what you got.
    inv = Counter()
    for r in invitations:
        d = r.get("DIRECTION", "").upper()
        u = normalize_url(r.get("INVITERPROFILEURL") if d == "OUTGOING" else
                          r.get("INVITEEPROFILEURL") if d == "INCOMING" else None)
        if u:
            inv[u] += 1
    if len(inv) == 1:
        return next(iter(inv)), "Invitations.csv"
    # Otherwise: the one profile that is in every conversation.
    convs: dict[str, set[str]] = defaultdict(set)
    for r in msgs:
        convs[r.get("CONVERSATION ID", "")].update(_urls(r.get("SENDER PROFILE URL", "")),
                                                   _urls(r.get("RECIPIENT PROFILE URLS", "")))
    sets = [s for s in convs.values() if s]
    common = set.intersection(*sets) if sets else set()
    if len(common) > 1 and profile:  # one partner in every thread: your name decides
        mine = f"{profile[0].get('FIRST NAME', '')} {profile[0].get('LAST NAME', '')}".strip().casefold()
        named = {normalize_url(r.get("SENDER PROFILE URL")) for r in msgs if fix_text(r.get("FROM", "")).casefold() == mine}
        common &= named
    if len(common) == 1:
        return common.pop(), "the profile in every conversation"
    raise ValueError("can't tell which profile is you: pass --me https://www.linkedin.com/in/<your-profile>")


# --- loading --------------------------------------------------------------------------------
def load(paths: list[Path | str], me: str | None = None) -> Result:
    found: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for p in paths:
        for name, items in _files(Path(p)).items():
            found[name] += items
    if not found.get("messages.csv") and not found.get("connections.csv"):
        raise ValueError("no messages.csv or Connections.csv found: request the larger data archive "
                         "(the quick one may not have them)")
    notes: list[str] = []
    # Guids are made per file, so the same rows read from two copies of a file come out identical.
    msgs: dict[str, dict] = {}
    for where, text in found.get("messages.csv", []):
        seen: Counter = Counter()
        rows = _rows(text)
        for r in rows:
            key = "|".join(r.get(k, "") for k in ("CONVERSATION ID", "DATE", "SENDER PROFILE URL", "SUBJECT", "CONTENT"))
            seen[key] += 1
            msgs.setdefault(hashlib.sha256(f"{key}|{seen[key]}".encode()).hexdigest()[:40], r)
        notes.append(f"{where}: {len(rows)} rows")
    invitations = [r for _, t in found.get("invitations.csv", []) for r in _rows(t)]
    profile = [r for _, t in found.get("profile.csv", []) for r in _rows(t)]
    me_url, how = infer_me(list(msgs.values()), invitations, profile, me) if msgs or me else ("", "")
    res = Result(me=me_url, snapshot_ts=_snapshot(paths))
    if me_url:
        notes.append(f"you are {me_url} (from {how})")
    _load_messages(res, msgs, notes)
    _load_connections(res, found.get("connections.csv", []), notes)
    res.notes = notes
    return res


def _snapshot(paths: list[Path | str]) -> float | None:
    stamps = []
    for p in paths:
        m = EXPORT_DATE.search(Path(p).name)
        if m:
            try:
                stamps.append(datetime(int(m[3]), int(m[1]), int(m[2]), tzinfo=timezone.utc).timestamp())
            except ValueError:
                pass
    return max(stamps) if stamps else None


def _load_messages(res: Result, msgs: dict[str, dict], notes: list[str]) -> None:
    me = res.me
    skipped: Counter = Counter()
    convs: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for guid, r in msgs.items():
        if r.get("FOLDER", "").upper() == "SPAM":
            skipped["spam folder"] += 1
        elif r.get("CONVERSATION TITLE", "").casefold() == "sponsored conversation" or SPONSORED.search(r.get("CONTENT", "")):
            skipped["sponsored"] += 1
        elif _truthy(r.get("IS MESSAGE DRAFT", "")) or _truthy(r.get("IS CONVERSATION DRAFT", "")):
            skipped["drafts"] += 1
        else:
            convs[r.get("CONVERSATION ID", "") or guid].append((guid, r))
    for cid, rows in convs.items():
        others: set[str] = set()
        other_names: set[str] = set()
        name_for: dict[str, str] = {}
        for _, r in rows:
            sender = normalize_url(r.get("SENDER PROFILE URL"))
            others.update(u for u in [sender, *_urls(r.get("RECIPIENT PROFILE URLS", ""))] if u and u != me)
            if sender and sender != me:
                name_for[sender] = fix_text(r.get("FROM", ""))
                other_names.add(name_for[sender].casefold())
            if sender == me:
                other_names.update(n.casefold() for n in _names(fix_text(r.get("TO", ""))))
        # A group lists every name in TO but only some profile URLs, so the names count too.
        if len(others) > 1 or len(other_names) > 1:
            _group(res, rows, name_for, skipped)
            continue
        if not others:
            skipped["threads with no other profile URL (a deleted member, or an old export without recipient URLs)"] += 1
            continue
        other = others.pop()
        if other not in name_for:  # you wrote and they never answered: their name is in TO
            names = _names(fix_text(rows[0][1].get("TO", "")))
            name_for[other] = names[0] if names else other
        res.names[other] = name_for[other]
        for guid, r in rows:
            sender = normalize_url(r.get("SENDER PROFILE URL"))
            ts = _ts(r.get("DATE", ""))
            if sender not in (me, other) or ts is None:
                skipped["rows with no sender or date"] += 1
                continue
            text = _body(r)
            if text:
                res.messages.append(Message(guid, other, ts, sender == me, text))
    for why, n in skipped.items():
        notes.append(f"skipped {n} {why}")
    notes.append(f"{len(res.messages)} messages in {len(res.names)} 1:1 threads; "
                 f"{sum(map(len, res.groups.values()))} lines in {len(res.groups)} groups kept as evidence "
                 "(closes items, never creates them)")


def _body(r: dict) -> str:
    text = clean(r.get("CONTENT", ""))
    subject = clean(r.get("SUBJECT", ""))
    if subject and subject.casefold() not in text.casefold():  # InMail: the subject is often the ask
        text = f"{subject}\n{text}".strip()
    if not text and r.get("ATTACHMENTS", ""):
        text = ATTACHMENT
    return text


def _group(res: Result, rows: list[tuple[str, dict]], name_for: dict[str, str], skipped: Counter) -> None:
    title = fix_text(next((r.get("CONVERSATION TITLE", "") for _, r in rows if r.get("CONVERSATION TITLE")), ""))
    if not title:  # untitled group: its members, so the same group gets the same name next import
        title = ", ".join(sorted(set(name_for.values()) or {"unnamed"}))
    out = res.groups.setdefault(title, [])
    for guid, r in rows:
        sender = normalize_url(r.get("SENDER PROFILE URL"))
        ts = _ts(r.get("DATE", ""))
        text = _body(r)
        if ts is None or not text:
            skipped["group rows with no date or text"] += 1
            continue
        out.append(GroupLine(guid, ts, "me" if sender == res.me else fix_text(r.get("FROM", "")) or "?", text))


def _load_connections(res: Result, files: list[tuple[str, str]], notes: list[str]) -> None:
    seen: set[str] = set()
    for where, text in files:
        rows = _rows(text, header_starts="FIRST NAME")
        no_url = 0
        for r in rows:
            url = normalize_url(r.get("URL"))
            if not url:  # LinkedIn blanks some members' URLs; there's nothing to key them by
                no_url += 1
                continue
            if url in seen or url == res.me:
                continue
            seen.add(url)
            name = fix_text(f"{r.get('FIRST NAME', '')} {r.get('LAST NAME', '')}".strip()) or url
            res.connections.append(Connection(url, name, r.get("EMAIL ADDRESS", "").lower(),
                                              fix_text(r.get("COMPANY", "")), fix_text(r.get("POSITION", "")),
                                              _date(r.get("CONNECTED ON", ""))))
        notes.append(f"{where}: {len(rows)} connections" + (f", {no_url} without a profile URL skipped" if no_url else ""))


# --- writing --------------------------------------------------------------------------------
def save(store, res: Result) -> str:
    """Writes res into the store. Returns a one-line summary. Safe to run again: adds only what's new."""
    conn = store.conn
    conn.execute(ATTRIBUTE_DDL)  # until core.sql has it
    ts = res.snapshot_ts or time.time()
    attrs = 0
    with conn:
        for c in res.connections:
            pid = store.person_for(NETWORK, c.handle, c.name)
            for key, value in (("linkedin", c.handle), ("email", c.email), ("company", c.company),
                               ("position", c.position), ("connected_on", c.connected_on)):
                if value:
                    attrs += conn.execute("INSERT OR IGNORE INTO attribute(person_id, key, value, source, ts)"
                                          " VALUES (?, ?, ?, ?, ?)", (pid, key, value, SOURCE, ts)).rowcount
    added = store.add_messages(NETWORK, res.messages, res.names)
    with conn:
        for handle in res.names:
            pid = store.person_for(NETWORK, handle)
            attrs += conn.execute("INSERT OR IGNORE INTO attribute(person_id, key, value, source, ts)"
                                  " VALUES (?, ?, ?, ?, ?)", (pid, "linkedin", handle, SOURCE, ts)).rowcount
    lines = sum(store.add_evidence(f"linkedin-group:{title}", rows) for title, rows in res.groups.items())
    return (f"{added} new messages from {len(res.names)} threads, {lines} new group lines, "
            f"{len(res.connections)} connections ({attrs} new attributes)")
