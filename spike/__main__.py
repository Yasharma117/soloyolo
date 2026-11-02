"""python -m spike {demo,ingest,extract,show,serve}. See spike/README.md."""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

from . import chatdb, fixture
from .extract import ClaudeCodeExtractor, ClaudeExtractor, HeuristicExtractor
from .store import Store

DEFAULT_DB = "soloyolo.db"


def ingest(store: Store, source: Path, days: int, names: dict[str, str] | None = None) -> None:
    since = time.time() - days * 86400 if days else None
    rows = chatdb.read(source, since_unix=since)
    added = store.add_messages("imessage", rows, names)
    print(f"read {len(rows)} messages from {source}, {added} new")


EXTRACTORS = {"heuristic": HeuristicExtractor, "claude-code": ClaudeCodeExtractor, "api": ClaudeExtractor}


def extract(store: Store, kind: str, window: int, only: int | None = None) -> None:
    ex = EXTRACTORS[kind]()
    for pid in [only] if only else store.person_ids():
        thread = [dict(r) for r in store.thread(pid, limit=window)]
        if not thread:
            continue
        result = ex.extract(thread)
        store.replace_extraction(pid, [c.model_dump() for c in result.commitments], result.topics, ex.name)
        print(f"person {pid}: {len(result.commitments)} commitments ({ex.name})")


def show(store: Store) -> None:
    for p in store.people():
        last = datetime.fromtimestamp(p["last"]).strftime("%b %d")
        print(f"\n{p['name']}  ·  score {p['score']}  ·  last {last}")
        for c in p["commitments"]:
            who = "you owe" if c["owner"] == "me" else "owes you"
            mark = "✓" if c["status"] == "done" else "○"
            due = f"  due {c['due']}" if c["due"] else ""
            print(f"  {mark} {who}: {c['action']}{due}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m spike")
    ap.add_argument("--db", default=DEFAULT_DB, help="soloyolo store (default: %(default)s)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("demo", help="build a synthetic chat.db, ingest, extract, then serve")
    d.add_argument("--extractor", choices=EXTRACTORS, default="heuristic",
                   help="claude-code or api send the (synthetic) demo text to Claude")
    d.add_argument("--no-serve", action="store_true")
    d.add_argument("--port", type=int, default=8765)

    i = sub.add_parser("ingest", help="read 1:1 threads from chat.db (needs Full Disk Access)")
    i.add_argument("--chatdb", type=Path, default=chatdb.DEFAULT_PATH)
    i.add_argument("--days", type=int, default=180, help="how far back to read (0 = everything)")

    e = sub.add_parser("extract", help="find commitments in each thread")
    e.add_argument("--extractor", choices=EXTRACTORS, default="heuristic",
                   help="heuristic: offline regexes. claude-code: Claude via your Claude Code login (no API key). "
                        "api: Anthropic API key. Both Claude options send each thread's text off this machine")
    e.add_argument("--window", type=int, default=300, help="most recent N messages per person")
    e.add_argument("--person", type=int, help="only this person id")

    sub.add_parser("show", help="print people and commitments")
    s = sub.add_parser("serve", help="open the local viewer")
    s.add_argument("--port", type=int, default=8765)

    a = ap.parse_args(argv)
    if a.cmd == "demo":
        Path(a.db).unlink(missing_ok=True)
        store = Store(a.db)
        src = fixture.build(Path(a.db).with_name("demo-chat.db"))
        ingest(store, src, days=0, names=fixture.NAMES)
        extract(store, a.extractor, window=300)
        show(store)
        store.close()
        if not a.no_serve:
            from .server import serve
            serve(a.db, a.port)
        return 0

    store = Store(a.db)
    try:
        if a.cmd == "ingest":
            ingest(store, a.chatdb, a.days)
        elif a.cmd == "extract":
            extract(store, a.extractor, a.window, a.person)
        elif a.cmd == "show":
            show(store)
        elif a.cmd == "serve":
            from .server import serve
            serve(a.db, a.port)
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
