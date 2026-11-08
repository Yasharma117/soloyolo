"""The protocol-neutral store: person, handle, message, commitment.

This is the "own your data model" rule from BUILD-WITHOUT-BEEPER.md. chat.db, WhatsApp or
Beeper are just sources that write into it. One SQLite file, on the user's machine.
The schema lives in connectord/internal/store/core.sql so the Go daemon and this spike share it.
"""
from __future__ import annotations

import math
import re
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
        self._migrate()

    def _migrate(self) -> None:
        """Bring stores made by older versions up to the schema. CREATE IF NOT EXISTS won't add columns."""
        # resolution's state CHECK gained 'suggested': SQLite can't alter a CHECK, so rebuild the table.
        sql = self.conn.execute("SELECT sql FROM sqlite_master WHERE name = 'resolution'").fetchone()
        if sql and "'suggested'" not in sql[0]:
            ddl = re.search(r"CREATE TABLE IF NOT EXISTS resolution \(.*?\n\);", SCHEMA, re.S).group(0)
            cols = ", ".join(r[1] for r in self.conn.execute("PRAGMA table_info(resolution)"))
            # One script, one transaction: a crash midway leaves the old table, not an empty new one.
            self.conn.executescript(
                f"BEGIN; ALTER TABLE resolution RENAME TO resolution_old; {ddl}"
                f" INSERT INTO resolution({cols}) SELECT {cols} FROM resolution_old; DROP TABLE resolution_old; COMMIT;")
        if "last_message_id" not in {r[1] for r in self.conn.execute("PRAGMA table_info(extraction_run)")}:
            with self.conn:
                self.conn.execute("ALTER TABLE extraction_run ADD COLUMN last_message_id INTEGER")
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(commitment)")}
        if "kind" not in cols:
            with self.conn:
                self.conn.execute("ALTER TABLE commitment ADD COLUMN kind TEXT NOT NULL DEFAULT 'promise'"
                                  " CHECK (kind IN ('promise', 'ask'))")

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
                           extractor: str, last_message_id: int | None = None) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM commitment WHERE person_id = ?", (person_id,))
            self.conn.execute("DELETE FROM topic WHERE person_id = ?", (person_id,))
            for c in commitments:
                self.conn.execute(
                    "INSERT INTO commitment(person_id, kind, owner, action, due, status, source_message_id,"
                    " done_message_id, extractor) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (person_id, c.get("kind", "promise"), c["owner"], c["action"], c.get("due"), c["status"],
                     c["source_message_id"], c.get("done_message_id"), extractor),
                )
            self.conn.executemany(
                "INSERT OR IGNORE INTO topic(person_id, label) VALUES (?, ?)",
                [(person_id, t) for t in topics],
            )
            self.conn.execute(
                "INSERT OR REPLACE INTO extraction_run(person_id, extractor, ran_at, last_message_id) VALUES (?, ?, ?, ?)",
                (person_id, extractor, time.time(), last_message_id),
            )

    # --- resolutions: what happened to an item after extraction -----------------------------
    STATES = ("done", "dismissed", "snoozed", "open", "suggested")
    RANK = {"closure": 0, "sms": 1, "you": 2}  # who may overwrite whom: you > a bank SMS > a guess

    def resolve(self, person_id: int, source_message_id: int, owner: str, state: str, decided_by: str,
                evidence: str | None = None, until: float | None = None, evidence_id: int | None = None) -> bool:
        """Record what happened to an item. A signal never overrides your own call, and a guess (closure)
        never overrides a bank SMS. Returns whether the row was written."""
        if state not in self.STATES:
            raise ValueError(f"unknown state {state!r}")
        with self.conn:
            if decided_by != "you":
                row = self.conn.execute(
                    "SELECT decided_by FROM resolution WHERE person_id = ? AND source_message_id = ? AND owner = ?",
                    (person_id, source_message_id, owner)).fetchone()
                if row and self.RANK.get(row[0], 2) > self.RANK.get(decided_by, 0):
                    return False
            self.conn.execute(
                "INSERT OR REPLACE INTO resolution(person_id, source_message_id, owner, state, until, decided_by,"
                " evidence, evidence_id, at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (person_id, source_message_id, owner, state, until, decided_by, evidence, evidence_id, time.time()))
        return True

    def unresolve(self, person_id: int, source_message_id: int, owner: str) -> None:
        """Undo: back to whatever the extractor said."""
        with self.conn:
            self.conn.execute("DELETE FROM resolution WHERE person_id = ? AND source_message_id = ? AND owner = ?",
                              (person_id, source_message_id, owner))

    def has_item(self, person_id: int, source_message_id: int, owner: str) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM commitment WHERE person_id = ? AND source_message_id = ? AND owner = ?",
            (person_id, source_message_id, owner)).fetchone() is not None

    def open_items(self, now: float | None = None) -> list[dict]:
        """Every item that's open after resolutions are applied, with its source message's time and text."""
        now = now or time.time()
        return [dict(person_id=p["id"], name=p["name"], **c)
                for p in self.people(now) for c in p["commitments"] if self.is_open(c)]

    @staticmethod
    def is_open(c: dict) -> bool:
        """Open, and not snoozed or marked "not real"."""
        return c["status"] == "open" and not c["snoozed"] and not c["dismissed"]

    def add_evidence(self, source: str, rows) -> int:
        """rows: objects with remote_id, ts, sender, text, and optionally amount, direction, counterparty.
        Returns rows newly inserted (re-importing the same backup adds nothing)."""
        added = 0
        with self.conn:
            for r in rows:
                added += self.conn.execute(
                    "INSERT OR IGNORE INTO evidence(source, remote_id, ts, sender, text, amount, direction, counterparty)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (source, r.remote_id, r.ts, r.sender, r.text, getattr(r, "amount", None),
                     getattr(r, "direction", None), getattr(r, "counterparty", None))).rowcount
        return added

    def record_disclosure(self, person_id: int, recipient: str) -> None:
        """Log that a thread's text is about to leave this machine. Call before sending."""
        with self.conn:
            self.conn.execute("INSERT INTO disclosure(person_id, recipient, at) VALUES (?, ?, ?)",
                              (person_id, recipient, time.time()))

    def disclosures(self) -> list[str]:
        """Every service that has ever received thread text from this store."""
        return [r[0] for r in self.conn.execute("SELECT DISTINCT recipient FROM disclosure ORDER BY recipient")]

    # --- reads -------------------------------------------------------------------------
    def thread(self, person_id: int, limit: int | None = None) -> list[sqlite3.Row]:
        rows = self.conn.execute(
            "SELECT id, ts, from_me, text FROM message WHERE person_id = ? ORDER BY ts DESC LIMIT ?",
            (person_id, limit or -1),
        ).fetchall()
        return rows[::-1]

    def changed_ids(self) -> list[int]:
        """People with messages newer than their last extraction read (or never extracted).
        By row id, not timestamp: history sync delivers old messages after the fact."""
        return [r[0] for r in self.conn.execute(
            "SELECT m.person_id FROM message m LEFT JOIN extraction_run r ON r.person_id = m.person_id"
            " GROUP BY m.person_id HAVING r.last_message_id IS NULL OR MAX(m.id) > r.last_message_id")]

    def person_ids(self) -> list[int]:
        return [r[0] for r in self.conn.execute("SELECT id FROM person ORDER BY id")]

    def people(self, now: float | None = None) -> list[dict]:
        """Everyone, ranked: most open items on you (promises and asks) first, then the mini_mesh decay score.

        Three queries in total, not one per person: the viewer calls this on every load.
        """
        now = now or time.time()
        k = math.log(2) / 86400 / HALF_LIFE_DAYS
        stats: dict[int, dict] = {}
        for pid, ts, from_me in self.conn.execute("SELECT person_id, ts, from_me FROM message"):
            s = stats.setdefault(pid, {"score": 0.0, "sent": 0, "count": 0, "last": 0.0})
            s["score"] += math.exp(-k * (now - ts))
            s["sent"] += from_me
            s["count"] += 1
            s["last"] = max(s["last"], ts)
        resolutions = {(r["person_id"], r["source_message_id"], r["owner"]): dict(r)
                       for r in self.conn.execute("SELECT * FROM resolution")}
        commitments: dict[int, list[dict]] = {}
        hidden: dict[int, int] = {}
        for c in self.conn.execute(
                "SELECT c.person_id, c.id, c.kind, c.owner, c.action, c.due, c.status, c.source_message_id,"
                " c.done_message_id, c.extractor, m.ts AS source_ts, m.text AS source_text"
                " FROM commitment c JOIN message m ON m.id = c.source_message_id"
                " ORDER BY m.ts DESC"):
            d = dict(c)
            pid = d.pop("person_id")
            r = resolutions.get((pid, d["source_message_id"], d["owner"]))
            d.update(resolved_by=None, evidence=None, snoozed=False, snoozed_until=None, dismissed=False,
                     suggestion=None)
            if r:
                if r["state"] == "dismissed":
                    hidden[pid] = hidden.get(pid, 0) + 1
                    d["dismissed"] = True
                elif r["state"] == "snoozed" and (r["until"] or 0) > now:
                    d.update(snoozed=True, snoozed_until=r["until"])
                elif r["state"] in ("done", "open"):
                    d["status"] = r["state"]
                if r["state"] == "suggested":
                    d["suggestion"] = r["evidence"]  # still open: only you can close it
                else:
                    d.update(resolved_by=r["decided_by"], evidence=r["evidence"])
            commitments.setdefault(pid, []).append(d)
        for items in commitments.values():  # open first, snoozed after open, newest first within each
            items.sort(key=lambda d: (d["dismissed"], d["status"] != "open", d["snoozed"]))
        topics: dict[int, list[str]] = {}
        for pid, label in self.conn.execute("SELECT person_id, label FROM topic ORDER BY label"):
            topics.setdefault(pid, []).append(label)
        out = []
        for p in self.conn.execute(
                "SELECT p.id, p.display_name, r.extractor FROM person p"
                " LEFT JOIN extraction_run r ON r.person_id = p.id"):
            s = stats.get(p["id"])
            if not s:
                continue
            score = s["score"] if s["sent"] and s["count"] - s["sent"] else s["score"] * 0.2  # one-way traffic
            out.append({
                "id": p["id"],
                "name": p["display_name"],
                "score": round(score, 2),
                "last": s["last"],
                "count": s["count"],
                "extractor": p["extractor"],  # None until extracted
                "commitments": commitments.get(p["id"], []),
                "hidden": hidden.get(p["id"], 0),  # items you marked "not real"
                "topics": topics.get(p["id"], []),
            })
        owed = lambda p: sum(c["owner"] == "me" and self.is_open(c) for c in p["commitments"])
        return sorted(out, key=lambda p: (-owed(p), -p["score"]))
