"""A synthetic chat.db with the real schema's relevant columns, for demos and tests.

Some rows store text only in `attributedBody` (as macOS 13+ does), one chat is a group, and
there is a tapback and a shortcode, so the reader's filters are exercised.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from .chatdb import APPLE_EPOCH

NAMES = {
    "+14155550101": "Sam Okafor",
    "+14155550102": "Priya Nair",
    "maya@example.com": "Maya Lin",
    "+14155550104": "Dev Shah",
    "+14155550105": "Ana Torres",
}

# (handle, days_ago, hour, from_me, text). Days count back from "now".
THREADS = [
    ("+14155550101", 12, 19, 0, "Good seeing you at the founders dinner"),
    ("+14155550101", 12, 19, 1, "Likewise. You mentioned you're hiring a design lead?"),
    ("+14155550101", 12, 20, 0, "Yes, it's the hardest role to fill right now"),
    ("+14155550101", 12, 20, 1, "I'll intro you to Priya, she built the design team at her last startup. Will do it by Friday"),
    ("+14155550101", 12, 20, 0, "That would be huge, thank you"),
    ("+14155550101", 3, 9, 0, "Any luck reaching Priya?"),
    ("+14155550102", 40, 10, 0, "Congrats on the new place!"),
    ("+14155550102", 40, 11, 1, "Thanks! Housewarming on the 20th, you should come"),
    ("+14155550102", 39, 9, 0, "I'm going to send you the article on design hiring loops I mentioned"),
    ("+14155550102", 38, 9, 0, "Here you go: the design hiring loops piece"),
    ("+14155550102", 38, 10, 1, "Perfect, reading it tonight"),
    ("+14155550102", 6, 18, 1, "Are you open to advising a seed-stage team?"),
    ("+14155550102", 6, 18, 0, "Depends on the team. Tell me more next week?"),
    ("maya@example.com", 20, 14, 1, "Loved the deck. One note on pricing, want me to mark it up?"),
    ("maya@example.com", 20, 14, 0, "Yes please"),
    ("maya@example.com", 20, 15, 1, "Let me review it properly and send notes tomorrow"),
    ("maya@example.com", 19, 22, 1, "Sent, check your email"),
    ("maya@example.com", 19, 23, 0, "These are great. I'll send you the revised version on Monday"),
    ("maya@example.com", 2, 8, 0, "Raising in two weeks, wish me luck"),
    ("+14155550104", 90, 12, 1, "Happy birthday Dev!"),
    ("+14155550104", 90, 13, 0, "Thanks man, we should catch up sometime"),
    ("+14155550104", 4, 21, 0, "Back in SF for a week, coffee?"),
    ("+14155550104", 4, 21, 1, "Yes. Let me check my calendar and get back to you tonight"),
    ("+14155550105", 1, 10, 0, "Thanks for covering lunch, I'll pay you back on Friday"),
    ("+14155550105", 1, 11, 1, "No rush"),
    ("88600", 0, 9, 0, "Your verification code is 123456"),
]

GROUP = [("+14155550101", 5, 1, "I'll book the table for Saturday"), ("+14155550102", 5, 0, "Count me in")]

ATTRIBUTED_ONLY = {"Sent, check your email", "Any luck reaching Priya?"}  # stored like macOS 13+


def attributed_body(text: str) -> bytes:
    """Minimal typedstream NSAttributedString wrapper around `text`, shaped like real rows."""
    raw = text.encode()
    n = bytes([len(raw)]) if len(raw) < 0x80 else b"\x81" + len(raw).to_bytes(2, "little")
    return (b"\x04\x0bstreamtyped\x81\xe8\x03\x84\x01@\x84\x84\x84\x12NSAttributedString\x00"
            b"\x84\x84\x08NSObject\x00\x85\x92\x84\x84\x84\x08NSString\x01\x94\x84\x01+" + n + raw +
            b"\x86\x84\x02iI\x01" )


def build(path: Path | str, now: float | None = None) -> Path:
    now = now or time.time()
    path = Path(path)
    path.unlink(missing_ok=True)
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE handle(ROWID INTEGER PRIMARY KEY, id TEXT);
        CREATE TABLE chat(ROWID INTEGER PRIMARY KEY, chat_identifier TEXT);
        CREATE TABLE chat_handle_join(chat_id INT, handle_id INT);
        CREATE TABLE chat_message_join(chat_id INT, message_id INT);
        CREATE TABLE message(ROWID INTEGER PRIMARY KEY, guid TEXT, handle_id INT, date INT,
            is_from_me INT, text TEXT, attributedBody BLOB, associated_message_type INT DEFAULT 0);
    """)
    handles = {h: i + 1 for i, h in enumerate(dict.fromkeys(h for h, *_ in THREADS))}
    db.executemany("INSERT INTO handle VALUES (?, ?)", [(i, h) for h, i in handles.items()])
    for h, i in handles.items():  # one 1:1 chat per handle
        db.execute("INSERT INTO chat VALUES (?, ?)", (i, h))
        db.execute("INSERT INTO chat_handle_join VALUES (?, ?)", (i, i))
    group = len(handles) + 1
    db.execute("INSERT INTO chat VALUES (?, 'chat-group-1')", (group,))
    for h, *_ in GROUP:
        db.execute("INSERT INTO chat_handle_join VALUES (?, ?)", (group, handles[h]))

    def ts(days_ago: int, hour: int) -> int:
        day = time.localtime(now - days_ago * 86400)
        t = time.mktime((day.tm_year, day.tm_mon, day.tm_mday, hour, 0, 0, 0, 0, -1))
        return int((t - APPLE_EPOCH) * 1e9)

    rowid = 0

    def add(chat: int, handle: str, days: int, hour: int, me: int, text: str, tapback: int = 0) -> None:
        nonlocal rowid
        rowid += 1
        only_body = text in ATTRIBUTED_ONLY
        db.execute("INSERT INTO message VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
            rowid, f"guid-{rowid}", handles[handle], ts(days, hour) + rowid, me,
            None if only_body else text, attributed_body(text), tapback))
        db.execute("INSERT INTO chat_message_join VALUES (?, ?)", (chat, rowid))

    for h, days, hour, me, text in THREADS:
        add(handles[h], h, days, hour, me, text)
    add(handles["+14155550101"], "+14155550101", 3, 10, 1, 'Loved "Any luck reaching Priya?"', tapback=2001)
    for h, days, me, text in GROUP:
        add(group, h, days, 12, me, text)
    db.commit()
    db.close()
    return path
