"""Stand-in for spike/nudge.py until it lands: the same interface, the plain ranking underneath.

nudge.today(store, now) returns the 1-3 things that matter today, each a dict with action, name,
owner, reasons, person_id and source_message_id. This returns the top 3 of priority.rank, cut to
those keys, so nothing downstream comes to depend on fields nudge.py won't have.
"""
from __future__ import annotations

from . import priority

KEYS = ("action", "name", "owner", "reasons", "person_id", "source_message_id")


def today(store, now: float | None = None) -> list[dict]:
    return [{k: c[k] for k in KEYS} for c in priority.rank(store, now)[:3]]
