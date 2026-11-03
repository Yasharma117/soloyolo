"""Import WhatsApp "Export chat" files (.txt, or the .zip WhatsApp shares) into the store.

On the phone: open a chat → contact name (iPhone) or ⋮ → More (Android) → Export chat →
Without media. Each export is one conversation, so you choose exactly what soloyolo reads.

Handles both layouts WhatsApp writes, in any locale:

    iPhone:   [02/11/2026, 10:14:05] Sam Okafor: I'll send it tonight
    Android:  02/11/2026, 10:14 - Sam Okafor: I'll send it tonight
              11/2/26, 10:14 PM - Sam Okafor: ...

plus multi-line messages, system lines ("Messages and calls are end-to-end encrypted"),
media placeholders, deleted messages, "<This message was edited>" and the invisible
direction marks WhatsApp sprinkles in.

Exports don't say which sender is you. With two or more chats, you're the one name in all
of them; with one chat, pass --me "Your Name" (as it appears in the export).
"""
from __future__ import annotations

import hashlib
import io
import re
import zipfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

INVISIBLE = dict.fromkeys(map(ord, "‎‏‪‫‬⁦⁧⁨⁩﻿"), None)

# One message header, iPhone or Android. Groups: date, time, sender, text.
HEADER = re.compile(
    r"^\[?(?P<date>\d{1,4}[./-]\d{1,2}[./-]\d{1,4}),?\s+"
    r"(?P<time>\d{1,2}[:.]\d{2}(?:[:.]\d{2})?(?:[\s  ]*[AaPp]\.?\s?[Mm]\.?)?)\]?"
    r"(?:\s+-\s+|\s+)"
    r"(?P<rest>.*)$"
)

SKIP_TEXT = re.compile(
    r"^(<media omitted>|<[^>]+ omitted>|<album message>|(image|video|audio|sticker|gif|document|contact card) omitted"
    r"|this message was deleted|you deleted this message|null|missed (voice|video) call.*"
    r"|waiting for this message.*|.*\.(jpg|jpeg|png|webp|opus|mp4|pdf|vcf) \(file attached\)"
    # system notices iPhone exports attribute to the contact
    r"|messages (and calls )?(to this chat and calls )?are (now )?(end-to-end encrypted|secured).*"
    r"|your security code with .* changed.*|.* is a contact\.?|.*turned (on|off) disappearing messages.*"
    r"|disappearing messages were turned (on|off).*|.*changed (their|the) phone number.*)$",
    re.I,
)
# A call the export logged on its own line ("[10/13/26, 5:36:43 PM] - [Call]"). The direction isn't
# recorded, but that a call happened is what closes "I'll call you back".
CALL_LINE = re.compile(r"^\[(?:voice |video )?call\]$", re.I)
CALL = "[call]"  # stored text for a call; spike.extract.render shows it without a speaker
EDITED = re.compile(r"\s*<this message was edited>\s*$", re.I)
# "[Forwarded] <image omitted> caption": the label goes. A photo, video, document or voice note
# becomes a marker, because "send me the pic" is done by the photo; stickers and GIFs go.
FORWARDED = re.compile(r"^\[forwarded\]\s*", re.I)
MEDIA = re.compile(r"^<(?P<kind>image|video|document|audio|voice message|[a-z ]+?) omitted>\s*", re.I)
MEDIA_MARK = {"image": "[photo]", "video": "[video]", "document": "[document]", "audio": "[voice note]",
              "voice message": "[voice note]",
              "media": "[media]"}  # native Android exports write every attachment as "<Media omitted>"


def _media(body: str) -> str:
    m = MEDIA.match(body)
    if not m:
        return body
    mark = MEDIA_MARK.get(m["kind"].lower())
    rest = body[m.end():].strip()
    return f"{mark} {rest}".strip() if mark else rest


@dataclass(frozen=True)
class Message:
    guid: str
    handle: str  # the other person's name, prefixed so it can't collide with a phone handle
    ts: float
    from_me: bool
    text: str


@dataclass(frozen=True)
class GroupLine:
    """A group-chat line. Kept as evidence that something got done; never a source of new items."""
    remote_id: str
    ts: float
    sender: str  # 'me' for you
    text: str


@dataclass
class Chat:
    source: str
    lines: list[tuple[str, str, str, str]]  # (date, time, sender, text)

    @property
    def senders(self) -> Counter:
        return Counter(s for _, _, s, _ in self.lines if s)  # "" is a logged call, not a person


def _read_texts(path: Path) -> list[tuple[str, str]]:
    """(source name, text) for a .txt, or for every .txt inside a .zip."""
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as z:
            return [(f"{path.name}:{n}", z.read(n).decode("utf-8-sig", "replace"))
                    for n in z.namelist() if n.lower().endswith(".txt")]
    # "Family from WhatsApp/chat.txt" (some exporters): the folder is the chat's name.
    name = f"{path.parent.name}/{path.name}" if path.stem.lower().lstrip("_") == "chat" else path.name
    return [(name, path.read_text("utf-8-sig", errors="replace"))]


def chat_name(source: str) -> str:
    """'WhatsApp Chat with Family.txt' / 'Family from WhatsApp/chat.txt' / 'x.zip:_chat.txt' -> 'Family'."""
    parts = [p for p in re.split(r"[/:]", source) if p]
    stem = next((p for p in reversed(parts) if Path(p).stem.lower().lstrip("_") != "chat"), parts[-1])
    stem = Path(stem).stem if stem.lower().endswith((".txt", ".zip")) else stem
    stem = re.sub(r"^WhatsApp Chat (?:with|-)\s*", "", stem, flags=re.I)
    return re.sub(r"\s+from WhatsApp$", "", stem, flags=re.I).strip() or source


def parse(source: str, text: str) -> Chat:
    lines: list[tuple[str, str, str, str]] = []
    for raw in io.StringIO(text):
        line = raw.rstrip("\r\n").translate(INVISIBLE)
        m = HEADER.match(line)
        if m:
            sender, sep, body = m["rest"].partition(": ")
            if CALL_LINE.match(m["rest"].strip()):
                lines.append([m["date"], m["time"], "", CALL])  # type: ignore[arg-type]
            elif sep:
                lines.append([m["date"], m["time"], sender.strip(), body])  # type: ignore[arg-type]
            # no "Sender: " means a system line (the encryption notice, "X changed the subject"): drop it
            continue
        if lines and line:
            lines[-1][3] += "\n" + line  # continuation of a multi-line message
    return Chat(source, [tuple(l) for l in lines])  # type: ignore[misc]


def date_order(chats: list[Chat]) -> str | None:
    """'dmy', 'mdy' or 'ymd', decided by any field over 12; None if every date is ambiguous."""
    for chat in chats:
        for d, *_ in chat.lines:
            a, b, *_ = re.split(r"[./-]", d)
            if len(a) == 4:
                return "ymd"
            if int(a) > 12:
                return "dmy"
            if int(b) > 12:
                return "mdy"
    return None


def _timestamp(d: str, t: str, order: str, tz: ZoneInfo | None) -> float:
    parts = [int(x) for x in re.split(r"[./-]", d)]
    if order == "ymd":
        y, mo, day = parts
    elif order == "mdy":
        mo, day, y = parts
    else:
        day, mo, y = parts
    if y < 100:
        y += 2000
    t = t.replace(" ", " ").replace(" ", " ").replace(".", ":").strip()
    marker = re.sub(r"[^a-z]", "", t.lower())  # "PM", "pm", "p. m." (es), "A.M." -> "pm" / "am"
    pm, am = marker == "pm", marker == "am"
    hms = [int(x) for x in re.findall(r"\d+", t)[:3]]
    h, mi, s = (hms + [0, 0])[:3]
    if pm and h < 12:
        h += 12
    if am and h == 12:
        h = 0
    return datetime(y, mo, day, h, mi, s, tzinfo=tz).timestamp()


def infer_me(chats: list[Chat]) -> str | None:
    """You are the sender present in every 1:1 chat. Needs two or more chats to be sure."""
    one_to_one = [c for c in chats if len(c.senders) == 2]
    if len(one_to_one) < 2:
        return None
    common = set.intersection(*(set(c.senders) for c in one_to_one))
    return common.pop() if len(common) == 1 else None


def read_chats(paths: list[Path]) -> list[Chat]:
    """Read and parse every export once; load() and load_groups() both take the result."""
    return [parse(src, text) for p in paths for src, text in _read_texts(Path(p))]


def load(paths: list[Path], me: str | None = None, tz: str | None = None,
         order: str | None = None, chats: list[Chat] | None = None) -> tuple[list[Message], dict[str, str], list[str]]:
    """1:1 chats: (messages, {handle: display name}, notes for the user). Groups are load_groups()'s."""
    chats = chats if chats is not None else read_chats(paths)
    notes: list[str] = []
    me = me or infer_me(chats)
    if not me:
        raise ValueError("can't tell which sender is you: pass --me \"Your Name\" exactly as it appears in the export")
    # No --tz: naive local time, so each date gets its own DST offset (not today's fixed one).
    zone = ZoneInfo(tz) if tz else None
    # Per file: exports from different phones can use different orders. An ambiguous file
    # (every date <= 12/12) follows the other files, else day-first as most locales do.
    fallback = date_order(chats) or "dmy"
    out: list[Message] = []
    names: dict[str, str] = {}
    for chat in chats:
        others = [s for s in chat.senders if s != me]
        if me not in chat.senders:
            notes.append(f"{chat.source}: skipped, '{me}' never speaks in it")
            continue
        if len(others) != 1:
            continue  # a group: load_groups() keeps it as evidence
        other = others[0]
        handle = f"export:{other}"
        names[handle] = other
        chat_order = order or date_order([chat]) or fallback
        seen: Counter = Counter()
        kept = 0
        for d, t, sender, body in chat.lines:
            body = _media(FORWARDED.sub("", EDITED.sub("", body).strip())).strip()
            if not body or (sender and SKIP_TEXT.match(body)):
                continue
            ts = _timestamp(d, t, chat_order, zone)
            # The raw export stamp, not ts: the guid must not change with --tz or a DST switch,
            # or a re-import would duplicate every message.
            key = f"{other}|{d}|{t}|{sender}|{body}"
            seen[key] += 1  # identical lines in the same second stay distinct
            guid = hashlib.sha256(f"{key}|{seen[key]}".encode()).hexdigest()[:40]  # a dedupe key, not security
            out.append(Message(guid, handle, ts, sender == me, body))
            kept += 1
        notes.append(f"{chat.source}: {other}, {kept} messages")
    return out, names, notes


def load_groups(paths: list[Path], me: str | None = None, tz: str | None = None, order: str | None = None,
                chats: list[Chat] | None = None) -> tuple[dict[str, list[GroupLine]], list[str]]:
    """Group chats as evidence: {group name: lines}, notes. 1:1 chats are left to load()."""
    chats = chats if chats is not None else read_chats(paths)
    me = me or infer_me(chats)
    if not me:
        raise ValueError("can't tell which sender is you: pass --me \"Your Name\" exactly as it appears in the export")
    zone = ZoneInfo(tz) if tz else None
    fallback = date_order(chats) or "dmy"
    groups: dict[str, list[GroupLine]] = {}
    notes: list[str] = []
    for chat in chats:
        if len([s for s in chat.senders if s != me]) < 2:
            continue
        name = chat_name(chat.source)
        chat_order = order or date_order([chat]) or fallback
        seen: Counter = Counter()
        out = groups.setdefault(name, [])
        for d, t, sender, body in chat.lines:
            body = _media(FORWARDED.sub("", EDITED.sub("", body).strip())).strip()
            if not body or not sender or SKIP_TEXT.match(body):
                continue  # calls in a group say nothing about who talked to whom
            key = f"group:{name}|{d}|{t}|{sender}|{body}"
            seen[key] += 1
            out.append(GroupLine(hashlib.sha256(f"{key}|{seen[key]}".encode()).hexdigest()[:40],
                                 _timestamp(d, t, chat_order, zone), "me" if sender == me else sender, body))
        notes.append(f"{chat.source}: group '{name}', {len(out)} lines kept as evidence (closes items, never creates them)")
    return groups, notes

