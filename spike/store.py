"""The protocol-neutral store: person, handle, message, commitment.

This is the "own your data model" rule from BUILD-WITHOUT-BEEPER.md. chat.db, WhatsApp or
Beeper are just sources that write into it. One SQLite file, on the user's machine.
The schema lives in connectord/internal/store/core.sql so the Go daemon and this spike share it.
"""
from __future__ import annotations

import math
import sqlite3
import time
from pathlib import Path
from typing import Iterable

SCHEMA = (Path(__file__).resolve().parents[1] / "connectord/internal/store/core.sql").read_text()

HALF_LIFE_DAYS = 30  # same decay as mini_mesh.py


class Store:
    def __init__(self, path: Path | str):
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    # --- ingest -----------------------------------------------------------------------
    def person_for(self, network: str, address: str, name: str | None = None) -> int:
        row = self.conn.execute(
            "SELECT person_id FROM handle WHERE network = ? AND address = ?", (network, address)
        ).fetchone()
        if row:
            if name:
                self.conn.execute("UPDATE person SET display_name = ? WHERE id = ?", (name, row[0]))
            return row[0]
        pid = self.conn.execute(
            "INSERT INTO person(display_name) VALUES (?)", (name or address,)
        ).lastrowid
        self.conn.execute(
            "INSERT INTO handle(network, address, person_id) VALUES (?, ?, ?)", (network, address, pid)
        )
        return pid

    def add_messages(self, network: str, rows: Iterable, names: dict[str, str] | None = None) -> int:
        """rows: objects with guid, handle, ts, from_me, text. Returns rows newly inserted."""
        names = names or {}
        added = 0
        for r in rows:
            pid = self.person_for(network, r.handle, names.get(r.handle))
            added += self.conn.execute(
                "INSERT OR IGNORE INTO message(network, remote_id, person_id, ts, from_me, text)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (network, r.guid, pid, r.ts, int(r.from_me), r.text),
            ).rowcount
        self.conn.commit()
        return added

    # --- extraction results -------------------------------------------------------------
    def replace_extraction(self, person_id: int, commitments: list[dict], topics: list[str],
                           extractor: str) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM commitment WHERE person_id = ?", (person_id,))
            self.conn.execute("DELETE FROM topic WHERE person_id = ?", (person_id,))
            for c in commitments:
                self.conn.execute(
                    "INSERT INTO commitment(person_id, owner, action, due, status, source_message_id,"
                    " done_message_id, extractor) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (person_id, c["owner"], c["action"], c.get("due"), c["status"],
                     c["source_message_id"], c.get("done_message_id"), extractor),
                )
            self.conn.executemany(
                "INSERT OR IGNORE INTO topic(person_id, label) VALUES (?, ?)",
                [(person_id, t) for t in topics],
            )

    # --- reads -------------------------------------------------------------------------
    def thread(self, person_id: int, limit: int | None = None) -> list[sqlite3.Row]:
        rows = self.conn.execute(
            "SELECT id, ts, from_me, text FROM message WHERE person_id = ? ORDER BY ts DESC LIMIT ?",
            (person_id, limit or -1),
        ).fetchall()
        return rows[::-1]

    def person_ids(self) -> list[int]:
        return [r[0] for r in self.conn.execute("SELECT id FROM person ORDER BY id")]

    def people(self, now: float | None = None) -> list[dict]:
        """Everyone, ranked: open promises you made first, then the mini_mesh decay score."""
        now = now or time.time()
        out = []
        for p in self.conn.execute("SELECT id, display_name FROM person"):
            msgs = self.conn.execute(
                "SELECT ts, from_me FROM message WHERE person_id = ?", (p["id"],)
            ).fetchall()
            if not msgs:
                continue
            score = sum(math.exp(-math.log(2) * (now - m["ts"]) / 86400 / HALF_LIFE_DAYS) for m in msgs)
            sent = sum(m["from_me"] for m in msgs)
            if not (sent and len(msgs) - sent):
                score *= 0.2  # one-way traffic is rarely a relationship
            cs = [dict(c) for c in self.conn.execute(
                "SELECT c.id, c.owner, c.action, c.due, c.status, c.source_message_id,"
                " c.done_message_id, c.extractor, m.ts AS source_ts"
                " FROM commitment c JOIN message m ON m.id = c.source_message_id"
                " WHERE c.person_id = ? ORDER BY c.status DESC, m.ts DESC", (p["id"],))]
            out.append({
                "id": p["id"],
                "name": p["display_name"],
                "score": round(score, 2),
                "last": max(m["ts"] for m in msgs),
                "count": len(msgs),
                "commitments": cs,
                "topics": [r[0] for r in self.conn.execute(
                    "SELECT label FROM topic WHERE person_id = ? ORDER BY label", (p["id"],))],
            })
        owed = lambda p: sum(c["owner"] == "me" and c["status"] == "open" for c in p["commitments"])
        return sorted(out, key=lambda p: (-owed(p), -p["score"]))
