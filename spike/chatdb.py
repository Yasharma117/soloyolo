"""Read 1:1 iMessage/SMS threads, with text, from macOS ~/Library/Messages/chat.db (read-only).

Since macOS 13, many rows have `text` NULL and keep the body only in `attributedBody`, an
NSArchiver "typedstream" blob. `decode_attributed_body` pulls the NSString out of it.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

APPLE_EPOCH = 978307200  # 2001-01-01 UTC; chat.db `date` is nanoseconds since then
DEFAULT_PATH = Path("~/Library/Messages/chat.db").expanduser()


@dataclass(frozen=True)
class RawMessage:
    guid: str
    handle: str  # phone number or email, as chat.db stores it
    ts: float  # unix seconds
    from_me: bool
    text: str


def decode_attributed_body(blob: bytes | None) -> str | None:
    """Extract the plain string from a typedstream-encoded NSAttributedString."""
    if not blob:
        return None
    i = blob.find(b"NSString")
    if i < 0:
        return None
    i = blob.find(b"\x01+", i)  # class-info end, then '+' marks the C string
    if i < 0:
        return None
    i += 2
    if i >= len(blob):
        return None  # truncated: skip the row rather than abort the whole read
    n = blob[i]
    i += 1
    if n == 0x81:  # typedstream int16 length follows
        n = int.from_bytes(blob[i:i + 2], "little")
        i += 2
    elif n == 0x82:  # int32 length follows
        n = int.from_bytes(blob[i:i + 4], "little")
        i += 4
    return blob[i:i + n].decode("utf-8", "replace") or None


# Only chats with exactly one other participant: group chats need per-speaker attribution
# and a different extraction prompt. Tapbacks (associated_message_type != 0) are skipped.
QUERY = """
WITH one_to_one AS (
  SELECT chat_id, MIN(handle_id) AS handle_id
  FROM chat_handle_join GROUP BY chat_id HAVING COUNT(*) = 1
)
SELECT m.guid, h.id, m.date, m.is_from_me, m.text, m.attributedBody
FROM message m
JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
JOIN one_to_one o ON o.chat_id = cmj.chat_id
JOIN handle h ON h.ROWID = o.handle_id
WHERE m.associated_message_type = 0
  AND (? IS NULL OR m.date >= ?)
ORDER BY m.date
"""


def is_shortcode(handle: str) -> bool:
    return handle.isdigit() and len(handle) <= 6


def read(path: Path | str = DEFAULT_PATH, since_unix: float | None = None) -> list[RawMessage]:
    conn = sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True)
    try:
        since = None if since_unix is None else int((since_unix - APPLE_EPOCH) * 1e9)
        out = []
        for guid, handle, date, from_me, text, body in conn.execute(QUERY, (since, since)):
            text = text or decode_attributed_body(body)
            if not text or is_shortcode(handle):
                continue
            text = text.replace("￼", "").strip()  # U+FFFC = attachment placeholder
            if text:
                out.append(RawMessage(guid, handle, APPLE_EPOCH + date / 1e9, bool(from_me), text))
        return out
    finally:
        conn.close()
