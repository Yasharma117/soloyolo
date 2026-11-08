"""Replay Today over past mornings, using only what was known each morning.

    python -m spike.replay --db soloyolo.db --days 42 --tz Asia/Kolkata --out replay.md

For each day D it copies the store into memory as of D at 09:00 and runs nudge.today on the copy:
messages after D are gone, items whose source message is after D are gone, an item whose done message
is after D is open again, and marks, signals and evidence made after D are gone.

What it can't undo (the leakage): items were extracted once, on the full thread, after D. So which
items exist, their wording and their due dates were decided with hindsight. An item the model left out
because a later message showed it was a joke, or already done off-chat, is missing on D; an item whose
source is a later re-ask appears only from that re-ask. The report counts what it can measure.

The output lists Today for every morning, numbered across days so each line can be scored, then how the
items you marked yourself behave. It contains your message text: write it somewhere private.
"""
from __future__ import annotations

import argparse
import os
import time
from datetime import date, datetime, timedelta

from . import nudge
from .store import Store

HOUR = 9


def as_of(store: Store, t: float) -> Store:
    """An in-memory copy of the store holding only what was known at time t. The store is not changed."""
    snap = Store(":memory:")
    store.conn.backup(snap.conn)
    with snap.conn:
        snap.conn.executescript(f"""
            DELETE FROM message WHERE ts > {t!r};
            DELETE FROM commitment WHERE source_message_id NOT IN (SELECT id FROM message);
            UPDATE commitment SET status = 'open', done_message_id = NULL
              WHERE done_message_id IS NOT NULL AND done_message_id NOT IN (SELECT id FROM message);
            DELETE FROM resolution WHERE at > {t!r};
            DELETE FROM evidence WHERE ts > {t!r};
        """)
    return snap


def mornings(end: date, days: int) -> list[float]:
    return [datetime(d.year, d.month, d.day, HOUR).timestamp() for d in (end - timedelta(days=n) for n in range(days - 1, -1, -1))]


def key(c: dict) -> tuple[int, int, str]:
    return (c["person_id"], c["source_message_id"], c["owner"])


def run(store: Store, times: list[float]) -> list[dict]:
    """One row per morning: today's items, how many open items were live and quiet, and the done ones reopened."""
    rows = []
    for t in times:
        snap = as_of(store, t)
        try:
            s = nudge.summary(snap, t)
            reopened = snap.conn.execute(
                "SELECT COUNT(*) FROM commitment WHERE status = 'open'").fetchone()[0] - store.conn.execute(
                "SELECT COUNT(*) FROM commitment c JOIN message m ON m.id = c.source_message_id"
                " WHERE c.status = 'open' AND m.ts <= ?", (t,)).fetchone()[0]
        finally:
            snap.close()
        rows.append(dict(s, t=t, reopened=reopened))
    return rows


def _line(c: dict, done_at: dict) -> str:
    who = "You owe" if c["owner"] == "me" else "Waiting on"
    ask = " (asked)" if c.get("kind") == "ask" else ""
    src = datetime.fromtimestamp(c["source_ts"]).strftime("%b %d")
    later = done_at.get(key(c))
    tail = f"  [chat shows done {datetime.fromtimestamp(later).strftime('%b %d')}]" if later else ""
    return f"{who}{ask} · {c['name']}: {c['action']} — {', '.join(c['reasons']) or 'new'} (from {src}){tail}"


def report(store: Store, rows: list[dict], now: float) -> str:
    done_at = {(r[0], r[1], r[2]): r[3] for r in store.conn.execute(
        "SELECT c.person_id, c.source_message_id, c.owner, m.ts FROM commitment c"
        " JOIN message m ON m.id = c.done_message_id WHERE c.status = 'done'")}
    out = [f"# Today, replayed at {HOUR:02d}:00 each morning", "",
           "Mark each numbered line: ✅ worth seeing that morning · ➖ true, already on my mind · ❌ shouldn't be there.",
           "Each morning sees only messages up to then. Items were extracted once on full threads (see the end).", "",
           summarize(rows), ""]
    n = 0
    shown: dict[tuple, list[float]] = {}
    for r in rows:
        day = datetime.fromtimestamp(r["t"]).strftime("%a %b %d")
        out.append(f"## {day} · {r['live']} live, {r['quiet']} quiet of {r['open']} open")
        for c in r["today"]:
            n += 1
            shown.setdefault(key(c), []).append(r["t"])
            out.append(f"{n}. {_line(c, done_at)}")
        if not r["today"]:
            out.append("(nothing)")
        out.append("")
    now_items = nudge.summary(store, now)
    out.append(f"## Now ({datetime.fromtimestamp(now):%a %b %d %H:%M}, your marks applied) · {now_items['live']} live,"
               f" {now_items['quiet']} quiet of {now_items['open']} open")
    for c in now_items["today"]:
        n += 1
        out.append(f"{n}. {_line(c, done_at)}")
    out += ["(nothing)"] if not now_items["today"] else []
    out.append("")
    # The items you marked: would they have been shown, and are they quiet now?
    yours = [dict(x) for x in store.conn.execute(
        "SELECT r.person_id, r.source_message_id, r.owner, r.state, c.action, c.due, m.ts AS source_ts"
        " FROM resolution r JOIN commitment c ON c.person_id = r.person_id AND c.source_message_id = r.source_message_id"
        " AND c.owner = r.owner JOIN message m ON m.id = c.source_message_id WHERE r.decided_by = 'you' ORDER BY m.ts")]
    marked_now = {key(c) for c in nudge.today(store, now)}
    unmarked = as_of(store, now)
    unmarked.conn.execute("DELETE FROM resolution WHERE decided_by = 'you'")
    live_unmarked = {key(c): c for c in nudge.assess(unmarked, now) if c["live"]}
    today_unmarked = {key(c) for c in nudge.today(unmarked, now)}
    unmarked.close()
    out += [f"## The {len(yours)} items you marked", "",
            "| # | Item | Your mark | From | Due | Mornings shown | First | Last | Live now without your mark | In Today now |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    fmt = lambda t: datetime.fromtimestamp(t).strftime("%b %d")
    for k, y in enumerate(yours, start=1):
        days = shown.get(key(y), [])
        out.append(f"| {k} | {y['action']} | {y['state']} | {fmt(y['source_ts'])} | {y['due'] or ''} | {len(days)} |"
                   f" {fmt(days[0]) if days else ''} | {fmt(days[-1]) if days else ''} |"
                   f" {'yes' if key(y) in live_unmarked else 'no'}{' (in Today)' if key(y) in today_unmarked else ''} |"
                   f" {'yes' if key(y) in marked_now else 'no'} |")
    out += ["", "## Leakage", ""] + leakage(store, rows)
    return "\n".join(out) + "\n"


def summarize(rows: list[dict]) -> str:
    shown = [len(r["today"]) for r in rows]
    live = [r["live"] for r in rows]
    opened = [r["open"] for r in rows]
    by = {k: shown.count(k) for k in sorted(set(shown))}
    return (f"{len(rows)} mornings: {sum(shown)} items shown ({sum(shown) / len(rows):.1f} a morning; mornings by count "
            f"{', '.join(f'{k}: {v}' for k, v in by.items())}), from {sum(live) / len(rows):.1f} live of "
            f"{sum(opened) / len(rows):.1f} open on average.")


def leakage(store: Store, rows: list[dict]) -> list[str]:
    start = rows[0]["t"]
    total = store.conn.execute("SELECT COUNT(*) FROM commitment c JOIN message m ON m.id = c.source_message_id"
                               " WHERE m.ts >= ?", (start - nudge.WINDOW,)).fetchone()[0]
    ran = store.conn.execute("SELECT MIN(ran_at), MAX(ran_at) FROM extraction_run").fetchone()
    reopened = sum(r["reopened"] for r in rows)
    lines = [
        f"- Every one of the {total} items from the replayed weeks was extracted after the fact "
        f"(reads ran {datetime.fromtimestamp(ran[0]):%b %d}–{datetime.fromtimestamp(ran[1]):%b %d}), on threads that "
        "already held the later messages. Which items exist, their wording and due dates used hindsight.",
        f"- Done-later: summed over mornings, {reopened} item-mornings were open only because the chat's done "
        "message came later (handled: those are reopened for that morning).",
        "- Not measurable here: items the model never listed because a later message showed them done, joked or "
        "withdrawn (missing from every morning), and items cited at a later re-ask (they appear only from then).",
        "- Marks: every mark of yours was made after the last replayed morning, so none is used in the replay.",
    ]
    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m spike.replay")
    ap.add_argument("--db", default="soloyolo.db")
    ap.add_argument("--days", type=int, default=42)
    ap.add_argument("--end", type=date.fromisoformat, help="last morning (default: the latest one already past)")
    ap.add_argument("--tz", help="the phone's time zone, e.g. Asia/Kolkata (default: this machine's)")
    ap.add_argument("--out", required=True, help="where to write the report (it holds message text)")
    a = ap.parse_args(argv)
    if a.tz:
        os.environ["TZ"] = a.tz
        time.tzset()
    now = time.time()
    end = a.end or (datetime.fromtimestamp(now) - timedelta(hours=HOUR)).date()
    store = Store(a.db)
    try:
        rows = run(store, mornings(end, a.days))
        with open(a.out, "w") as f:
            f.write(report(store, rows, now))
    finally:
        store.close()
    print(f"{summarize(rows)} Wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
