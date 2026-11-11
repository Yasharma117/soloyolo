"""python -m spike {demo,ingest,import-*,extract,close,watch,show,today,top,digest,telegram,mute,serve}. See spike/README.md."""
from __future__ import annotations

import argparse
import inspect
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from . import (chatdb, closure, fixture, instagram_export, json_import, linkedin_export, linkedin_live, nudge, priority,
               reconcile, sms, whatsapp_export, x_export)
from .council import Council
from .extract import ClaudeCodeExtractor, ClaudeExtractor, HeuristicExtractor, OpenModelExtractor
from .store import Store

DEFAULT_DB = "soloyolo.db"


def ingest(store: Store, source: Path, days: int, names: dict[str, str] | None = None) -> None:
    since = time.time() - days * 86400 if days else None
    rows = chatdb.read(source, since_unix=since)
    added = store.add_messages("imessage", rows, names)
    print(f"read {len(rows)} messages from {source}, {added} new")


EXTRACTORS = {"heuristic": HeuristicExtractor, "claude-code": ClaudeCodeExtractor, "api": ClaudeExtractor,
              "open-model": OpenModelExtractor,  # any OpenAI-compatible server (see its docstring)
              "council": Council}  # several open models, one job each (spike/council.py); eval only for now


WINDOW_DAYS = 60


def extract(store: Store, kind: str, window: int, only: int | None = None, top: int | None = None,
            changed: bool = False, min_messages: int = 1, ex=None, days: float = WINDOW_DAYS) -> int:
    """Returns how many people failed. One failure (a refusal, a timeout) never stops the rest.

    `top` limits the run to the N most active people (the viewer's ranking), so a first pass with
    a Claude extractor costs a few dozen calls, not one per person you've ever texted.
    `changed` skips anyone with no new messages since they were last read: a live store only
    pays for chats that moved. `min_messages` skips one-line threads (a stray "hi", a business).
    Each thread is read by time (the last `days`), capped at `window` messages: on a live store a
    count alone covered three weeks of a busy chat once calls and photos came through.
    """
    ex = ex or EXTRACTORS[kind]()
    failed = 0
    people = {p["id"]: p for p in store.people()}
    if only:
        ids = [only]
    else:
        ids = store.changed_ids() if changed else store.person_ids()
        muted = store.muted()  # never sent for extraction; `mute --undo` to read it again
        ids = [i for i in ids if i in people and people[i]["count"] >= min_messages and i not in muted]
        if top:
            ids = sorted(ids, key=lambda i: -people[i]["score"])[:top]
    for pid in ids:
        thread = [dict(r) for r in store.thread(pid, limit=window, since=time.time() - days * 86400)]
        if not thread:
            store.mark_read(pid)  # all older than the window: nothing to read, and not "changed" again
            continue
        if getattr(ex, "remote", True):  # unknown extractors are assumed to send text
            store.record_disclosure(pid, ex.name)  # before sending, so a failed call is still on record
        # A model re-reading a chat sees what it found last time, so the list doesn't flicker
        # (spike/reconcile.py). The heuristic gives the same answer every time and just replaces.
        prior = store.items(pid) if _takes_prior(ex) else []
        try:
            result = ex.extract(thread, prior=prior) if prior else ex.extract(thread)
        except Exception as err:  # keep going; rerun with --person to retry one
            failed += 1
            print(f"person {pid}: failed, kept previous results ({str(err)[:160]})", file=sys.stderr)
            continue
        m = reconcile.merge(prior, result, store.decided_by_you(pid))
        for old, new in m.rekeys:
            store.rekey(pid, old, new)
        store.replace_extraction(pid, m.items, result.topics, ex.name, last_message_id=max(r["id"] for r in thread))
        churn = f"; kept {m.kept}, carried {m.carried}, dropped {len(m.dropped)}, new {m.new}" if prior else ""
        print(f"person {pid}: {len(m.items)} commitments ({ex.name}{churn})")
        for old, why in m.dropped:
            print(f"  dropped: {old['action']} ({why})")
    if failed:
        print(f"{failed} failed; rerun `extract --person <id>` for each", file=sys.stderr)
    return failed


def _takes_prior(ex) -> bool:
    return "prior" in inspect.signature(ex.extract).parameters


def watch(store: Store, a) -> int:
    """Passes until Ctrl-C. Each reads only the chats that changed, so a quiet hour costs nothing."""
    ex = EXTRACTORS[a.extractor]()
    seen = {(c["person_id"], c["source_message_id"], c["owner"]) for c in store.open_items()}
    while True:
        stamp = datetime.now().strftime("%H:%M")
        changed = store.changed_ids()
        if changed:
            print(f"[{stamp}] {len(changed)} chats changed; reading up to {a.top}")
            extract(store, a.extractor, a.window, top=a.top, changed=True, min_messages=a.min_messages, ex=ex,
                    days=a.days)
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


def top(store: Store, n: int) -> None:
    items = priority.rank(store)
    print(f"{len(items)} open; the first {min(n, len(items))}:")
    for k, c in enumerate(items[:n], start=1):
        who = "you owe" if c["owner"] == "me" else "waiting on"
        print(f"{k:>3}. {c['name']}: {who}: {c['action']}  ({', '.join(c['reasons'])})")


def today(store: Store) -> None:
    s = nudge.summary(store)
    print(f"Today: {len(s['today']) or 'nothing'}. {s['quiet']} of {s['open']} open are quiet (assumed done); `top` lists all")
    for k, c in enumerate(s["today"], start=1):
        who = "you owe" if c["owner"] == "me" else "waiting on"
        print(f"{k:>3}. {c['name']}: {who}: {c['action']}  ({', '.join(c['reasons']) or 'new'})")


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

    li = sub.add_parser("import-linkedin", help="import a LinkedIn data export (.zip or unzipped folder)")
    li.add_argument("paths", nargs="+", type=Path, help="the export; pass both parts of a two-part export")
    li.add_argument("--me", help="your profile URL, when it can't be inferred")
    for cmd, what in (("import-instagram", "an Instagram 'Download your information' export (JSON)"),
                      ("import-x", "an X archive ('Download an archive of your data')")):
        so = sub.add_parser(cmd, help=f"import {what}: .zip(s) or unzipped folder")
        so.add_argument("paths", nargs="+", type=Path)
        so.add_argument("--me", help="who you are, when it can't be inferred: your Instagram name as threads "
                                     "show it, or your X user id")

    sub.add_parser("linkedin-token", help="print the token that pairs the Chrome extension (extension/) for live "
                                          "LinkedIn sync; made on first run")

    j = sub.add_parser("import-json", help="import conversations from a JSON file (format in spike/json_import.py)")
    j.add_argument("file", type=Path)

    n = sub.add_parser("import-notifications", help="import a batch of message notifications from the Android "
                                                    "listener (format in spike/notify_ingest.py)")
    n.add_argument("file", type=Path)

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
    e.add_argument("--window", type=int, default=1000, help="at most this many recent messages per person")
    e.add_argument("--days", type=float, default=WINDOW_DAYS, help="read this many days back (default %(default)s)")
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
    wt.add_argument("--window", type=int, default=1000)
    wt.add_argument("--days", type=float, default=WINDOW_DAYS)
    wt.add_argument("--once", action="store_true", help="one pass, then exit")

    sub.add_parser("show", help="print people and what each side owes")
    sub.add_parser("today", help="the 1-3 things that matter now; quiet items are assumed done (spike/nudge.py)")
    tg = sub.add_parser("telegram", help="the morning message on Telegram: pair once, then send / apply taps "
                                         "(spike/telegram.py)")
    tg.add_argument("action", choices=["pair", "send", "poll", "listen"],
                    help="pair: link your bot and chat. send: today's message. poll: apply waiting taps once. "
                         "listen: apply taps as they come (what the launchd agent runs)")
    mu = sub.add_parser("mute", help="keep a chat that isn't a person (an AI assistant, a bot, a shop) out of "
                                     "Today and the ranked list, and stop sending it for extraction")
    mu.add_argument("person", help="person id, phone number, or part of the name")
    mu.add_argument("--why", default="not a person")
    mu.add_argument("--undo", action="store_true", help="bring it back")
    t = sub.add_parser("top", help="every open item in one list, what to do first at the top, with why")
    t.add_argument("-n", type=int, default=15)
    g = sub.add_parser("digest", help="the morning message: the 1-3 things for today, and a line if sync or "
                                      "extraction stopped. Prints it; sends nothing")
    g.add_argument("--format", choices=["text", "telegram"], default="text",
                   help="telegram: the Bot API sendMessage body (JSON, no chat_id), with Done / Not needed buttons")
    g.add_argument("--out", type=Path, help="also write it to this file (mode 600)")
    g.add_argument("--stale-hours", type=float, default=12, help="warn when the newest live message is older")
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
        elif a.cmd == "import-linkedin":
            try:
                res = linkedin_export.load(a.paths, a.me)
            except ValueError as err:
                ap.error(str(err))
            print("\n".join(res.notes))
            print(linkedin_export.save(store, res))
        elif a.cmd == "linkedin-token":
            print(linkedin_live.token(a.db, create=True))
            print("Paste it into the soloyolo extension's options. Keep `python -m spike serve` running while Chrome is open.")
        elif a.cmd in ("import-instagram", "import-x"):
            mod = instagram_export if a.cmd == "import-instagram" else x_export
            try:
                res = mod.load(a.paths, a.me)
            except ValueError as err:
                ap.error(str(err))
            print("\n".join(res.notes))
            print(mod.save(store, res))
        elif a.cmd == "import-json":
            source, rows, names = json_import.load(a.file)
            print(f"{store.add_messages(source, rows, names)} new messages from {len(names)} people ({source})")
        elif a.cmd == "import-notifications":
            from . import notify_ingest
            batch = notify_ingest.load(a.file)
            out = notify_ingest.ingest(store, batch)
            skipped = ", ".join(f"{n} {why}" for why, n in batch.skipped.items())
            print(f"{out['messages']} new messages, {out['group_lines']} new group lines, "
                  f"{out['already_synced']} already synced" + (f"; skipped {skipped}" if skipped else ""))
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
            return 1 if extract(store, a.extractor, a.window, a.person, a.top, a.changed, a.min_messages,
                                days=a.days) else 0
        elif a.cmd == "watch":
            return watch(store, a)
        elif a.cmd == "show":
            show(store)
        elif a.cmd == "today":
            today(store)
        elif a.cmd == "telegram":
            from . import telegram
            path = telegram.config_path(a.db)
            try:
                if a.action == "pair":
                    import getpass
                    token = os.environ.get("SOLOYOLO_TELEGRAM_TOKEN") or getpass.getpass(
                        "Bot token from @BotFather (not shown as you type): ").strip()
                    telegram.pair(path, telegram.Bot(token), token)
                elif a.action == "send":
                    mid = telegram.send(store, path)
                    print("sent" if mid else "nothing for today: no message sent")
                elif a.action == "poll":
                    print(f"applied {telegram.poll(store, path)} tap(s)")
                else:
                    store.close()
                    telegram.listen(lambda: Store(a.db), path)
            except telegram.TelegramError as err:
                print(f"telegram: {err}", file=sys.stderr)
                return 1
        elif a.cmd == "mute":
            found = store.find_person(a.person)
            if len(found) != 1:
                ap.error(f"{len(found)} people match {a.person!r}" + (": " + ", ".join(f"{i} {n}" for i, n in found[:8])
                                                                    if found else "") + ". Use the id")
            pid, name = found[0]
            store.unmute(pid) if a.undo else store.mute(pid, a.why)
            print(f"{'unmuted' if a.undo else 'muted'}: {name} (person {pid})")
        elif a.cmd == "top":
            top(store, a.n)
        elif a.cmd == "digest":
            from . import daily
            text = daily.digest(store, a.format, stale_hours=a.stale_hours)
            print(text)
            if a.out:
                daily.write_private(a.out, text)
        elif a.cmd == "serve":
            from .server import serve
            serve(a.db, a.port)
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
