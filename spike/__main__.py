"""python -m spike {demo,ingest,import-*,extract,close,show,serve}. See spike/README.md."""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

from . import chatdb, closure, fixture, json_import, sms, whatsapp_export
from .extract import ClaudeCodeExtractor, ClaudeExtractor, HeuristicExtractor
from .store import Store

DEFAULT_DB = "soloyolo.db"


def ingest(store: Store, source: Path, days: int, names: dict[str, str] | None = None) -> None:
    since = time.time() - days * 86400 if days else None
    rows = chatdb.read(source, since_unix=since)
    added = store.add_messages("imessage", rows, names)
    print(f"read {len(rows)} messages from {source}, {added} new")


EXTRACTORS = {"heuristic": HeuristicExtractor, "claude-code": ClaudeCodeExtractor, "api": ClaudeExtractor}


def extract(store: Store, kind: str, window: int, only: int | None = None, top: int | None = None,
            changed: bool = False, min_messages: int = 1, ex=None) -> int:
    """Returns how many people failed. One failure (a refusal, a timeout) never stops the rest.

    `top` limits the run to the N most active people (the viewer's ranking), so a first pass with
    a Claude extractor costs a few dozen calls, not one per person you've ever texted.
    `changed` skips anyone with no new messages since they were last read: a live store only
    pays for chats that moved. `min_messages` skips one-line threads (a stray "hi", a business).
    """
    ex = ex or EXTRACTORS[kind]()
    failed = 0
    people = {p["id"]: p for p in store.people()}
    if only:
        ids = [only]
    else:
        ids = store.changed_ids() if changed else store.person_ids()
        ids = [i for i in ids if i in people and people[i]["count"] >= min_messages]
        if top:
            ids = sorted(ids, key=lambda i: -people[i]["score"])[:top]
    for pid in ids:
        thread = [dict(r) for r in store.thread(pid, limit=window)]
        if not thread:
            continue
        if getattr(ex, "remote", True):  # unknown extractors are assumed to send text
            store.record_disclosure(pid, ex.name)  # before sending, so a failed call is still on record
        try:
            result = ex.extract(thread)
        except Exception as err:  # keep going; rerun with --person to retry one
            failed += 1
            print(f"person {pid}: failed, kept previous results ({str(err)[:160]})", file=sys.stderr)
            continue
        store.replace_extraction(pid, [c.model_dump() for c in result.commitments], result.topics, ex.name,
                                 last_message_id=max(m["id"] for m in thread))
        print(f"person {pid}: {len(result.commitments)} commitments ({ex.name})")
    if failed:
        print(f"{failed} failed; rerun `extract --person <id>` for each", file=sys.stderr)
    return failed


def watch(store: Store, a) -> int:
    """Passes until Ctrl-C. Each reads only the chats that changed, so a quiet hour costs nothing."""
    ex = EXTRACTORS[a.extractor]()
    seen = {(c["person_id"], c["source_message_id"], c["owner"]) for c in store.open_items()}
    while True:
        stamp = datetime.now().strftime("%H:%M")
        changed = store.changed_ids()
        if changed:
            print(f"[{stamp}] {len(changed)} chats changed; reading up to {a.top}")
            extract(store, a.extractor, a.window, top=a.top, changed=True, min_messages=a.min_messages, ex=ex)
            close_with_sms(store)
            for c in store.open_items():
                key = (c["person_id"], c["source_message_id"], c["owner"])
                if key not in seen:
                    seen.add(key)
                    who = "you owe" if c["owner"] == "me" else "waiting on"
                    print(f"  new: {c['name']}: {who}: {c['action']}")
        else:
            print(f"[{stamp}] nothing new")
        if a.once:
            return 0
        try:
            time.sleep(a.every * 60)
        except KeyboardInterrupt:
            return 0


def close_with_sms(store: Store) -> None:
    for item, pay in sms.match(store):
        print(f"closed: {item['name']}: {item['action']}  <- {sms.describe(pay)}")


def show(store: Store) -> None:
    for p in store.people():
        last = datetime.fromtimestamp(p["last"]).strftime("%b %d")
        print(f"\n{p['name']}  ·  score {p['score']}  ·  last {last}")
        for c in p["commitments"]:
            if c["dismissed"]:
                continue
            who = "you owe" if c["owner"] == "me" else "waiting on"
            asked = " (asked)" if c.get("kind") == "ask" else ""
            mark = "✓" if c["status"] == "done" else "z" if c["snoozed"] else "○"
            due = f"  due {c['due']}" if c["due"] and c["status"] == "open" else ""
            why = f"  [closed by {c['resolved_by']}: {c['evidence']}]" if c["resolved_by"] not in (None, "you") \
                and c["status"] == "done" else ""
            maybe = f"  [maybe settled? {c['suggestion']}]" if c["suggestion"] and c["status"] == "open" else ""
            print(f"  {mark} {who}{asked}: {c['action']}{due}{why}{maybe}")
        if p["hidden"]:
            print(f"  ({p['hidden']} marked not real)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m spike")
    ap.add_argument("--db", default=DEFAULT_DB, help="soloyolo store (default: %(default)s)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("demo", help="build a synthetic chat.db, ingest, extract, then serve")
    d.add_argument("--demo-db", default="soloyolo-demo.db",
                   help="demo store, recreated each run (default: %(default)s). Never your --db")
    d.add_argument("--extractor", choices=EXTRACTORS, default="heuristic",
                   help="claude-code or api send the (synthetic) demo text to Claude")
    d.add_argument("--no-serve", action="store_true")
    d.add_argument("--port", type=int, default=8765)

    i = sub.add_parser("ingest", help="read 1:1 threads from chat.db (needs Full Disk Access)")
    i.add_argument("--chatdb", type=Path, default=chatdb.DEFAULT_PATH)
    i.add_argument("--days", type=int, default=180, help="how far back to read (0 = everything)")

    w = sub.add_parser("import-whatsapp", help="import WhatsApp 'Export chat' files (.txt or .zip)")
    w.add_argument("files", nargs="+", type=Path)
    w.add_argument("--me", help="your name exactly as the export shows it (inferred when 2+ chats are given)")
    w.add_argument("--tz", help="the phone's time zone, e.g. Asia/Kolkata (default: this machine's)")
    w.add_argument("--date-order", choices=["dmy", "mdy", "ymd"], help="override date order detection")

    j = sub.add_parser("import-json", help="import conversations from a JSON file (format in spike/json_import.py)")
    j.add_argument("file", type=Path)

    m = sub.add_parser("import-sms", help="read bank alerts from an Android 'SMS Backup & Restore' XML; "
                                          "they close money items. Other texts are never stored")
    m.add_argument("file", type=Path)

    c = sub.add_parser("close", help="close open items using evidence: bank SMS (local), and with --extractor, "
                                      "later messages in your other chats and groups (sent to Claude)")
    c.add_argument("--extractor", choices=["claude-code", "api"],
                   help="also run the cross-chat closure pass; sends open items and candidate messages off this machine")
    c.add_argument("--person", type=int, help="only this person's items")
    c.add_argument("--other-chats", action="store_true",
                   help="also look in your other 1:1 chats (off by default: on real data its guesses were wrong)")

    e = sub.add_parser("extract", help="find promises and asks in each thread")
    e.add_argument("--extractor", choices=EXTRACTORS, default="heuristic",
                   help="heuristic: offline regexes. claude-code: Claude via your Claude Code login (no API key). "
                        "api: Anthropic API key. Both Claude options send each thread's text off this machine")
    e.add_argument("--window", type=int, default=300, help="most recent N messages per person")
    e.add_argument("--person", type=int, help="only this person id")
    e.add_argument("--top", type=int, help="only the N most active people (start here: --top 25)")
    e.add_argument("--changed", action="store_true", help="only people with new messages since they were last read")
    e.add_argument("--min-messages", type=int, default=1, help="skip threads shorter than this")

    wt = sub.add_parser("watch", help="keep a live store's lists current: every few minutes, read the chats "
                                      "that changed, then close what bank SMS settles")
    wt.add_argument("--extractor", choices=EXTRACTORS, default="heuristic")
    wt.add_argument("--every", type=float, default=10, help="minutes between passes (default %(default)s)")
    wt.add_argument("--top", type=int, default=30, help="at most this many changed people per pass")
    wt.add_argument("--min-messages", type=int, default=4, help="skip threads shorter than this")
    wt.add_argument("--window", type=int, default=300)
    wt.add_argument("--once", action="store_true", help="one pass, then exit")

    sub.add_parser("show", help="print people and what each side owes")
    s = sub.add_parser("serve", help="open the local viewer")
    s.add_argument("--port", type=int, default=8765)

    a = ap.parse_args(argv)
    if a.cmd == "demo":
        # Its own file: recreating the demo must never touch the store `ingest` filled with real messages.
        if Path(a.demo_db).resolve() == Path(a.db).resolve():
            ap.error("--demo-db must differ from --db, which holds your real messages")
        Path(a.demo_db).unlink(missing_ok=True)
        store = Store(a.demo_db)
        src = fixture.build(Path(a.demo_db).with_name("demo-chat.db"))
        ingest(store, src, days=0, names=fixture.NAMES)
        extract(store, a.extractor, window=300)
        show(store)
        store.close()
        if not a.no_serve:
            from .server import serve
            serve(a.demo_db, a.port)
        return 0

    store = Store(a.db)
    try:
        if a.cmd == "ingest":
            ingest(store, a.chatdb, a.days)
        elif a.cmd == "import-whatsapp":
            try:
                chats = whatsapp_export.read_chats(a.files)
                rows, names, notes = whatsapp_export.load(a.files, a.me, a.tz, a.date_order, chats=chats)
                groups, group_notes = whatsapp_export.load_groups(a.files, a.me, a.tz, a.date_order, chats=chats)
            except ValueError as err:
                ap.error(str(err))
            print("\n".join(notes + group_notes))
            print(f"{store.add_messages('whatsapp', rows, names)} new messages from {len(names)} chats")
            for name, lines in groups.items():
                store.add_evidence(f"whatsapp-group:{name}", lines)
        elif a.cmd == "import-json":
            source, rows, names = json_import.load(a.file)
            print(f"{store.add_messages(source, rows, names)} new messages from {len(names)} people ({source})")
        elif a.cmd == "import-sms":
            pays, read = sms.load_backup(a.file)
            added = store.add_evidence("sms", pays)
            print(f"read {read} texts: kept {len(pays)} bank payment alerts ({added} new), discarded the rest")
            close_with_sms(store)
        elif a.cmd == "close":
            close_with_sms(store)
            if a.extractor:
                for item, line, reason in closure.run(store, EXTRACTORS[a.extractor](), a.person,
                                                      other_chats=a.other_chats):
                    print(f"maybe settled: {item['name']}: {item['action']}  <- {line['chat']}: {line['text'][:70]!r}"
                          f" ({reason})")
        elif a.cmd == "extract":
            return 1 if extract(store, a.extractor, a.window, a.person, a.top, a.changed, a.min_messages) else 0
        elif a.cmd == "watch":
            return watch(store, a)
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
