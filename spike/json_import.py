"""Import conversations from a plain JSON file, for sources the spike has no reader for yet
(an email export, a CRM dump, a hand-assembled test set).

    {
      "source": "gmail",
      "threads": [
        {"person": "Sumit Sharma (Cars24)", "handle": "sumit@cars24.com",
         "messages": [{"id": "m1", "ts": "2026-10-05T02:30:00Z", "from_me": true, "text": "..."}]}
      ]
    }

`id` must be unique within the source; it dedupes re-imports. `ts` is ISO 8601 (a trailing Z is
UTC). Several threads with the same handle are merged into one person.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class Message:
    guid: str
    handle: str
    ts: float
    from_me: bool
    text: str


def load(path: Path | str) -> tuple[str, list[Message], dict[str, str]]:
    """Returns (source network, messages, {handle: display name})."""
    data = json.loads(Path(path).read_text("utf-8"))
    source = data.get("source") or "import"
    rows: list[Message] = []
    names: dict[str, str] = {}
    for t in data["threads"]:
        handle = t["handle"].strip().lower()
        names[handle] = t.get("person") or handle
        for m in t["messages"]:
            text = (m.get("text") or "").strip()
            if not text:
                continue
            ts = datetime.fromisoformat(m["ts"].replace("Z", "+00:00")).timestamp()
            rows.append(Message(str(m["id"]), handle, ts, bool(m["from_me"]), text))
    return source, rows, names
