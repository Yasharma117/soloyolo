"""Closure pass: was an open item settled in a different chat?

Family logistics close across chats: Dad asks you to sort the flight with Mum, and the answer is in
the family group. Each open item is checked against later group-chat messages (and, opt-in, your other
1:1 chats). Claude names items a later message seems to settle, citing it.

It only ever *suggests*. On the first real test (5 chats, the user's own scores) it "settled" 3 items
from other 1:1 chats, consistently across runs, and all 3 were still open: "Yesss" to Dad about a
birthday wish looks conclusive and wasn't. So a suggestion leaves the item open with the evidence
beside it, and one tap decides. That's also why other 1:1 chats are off by default.

This sends text off the machine (the open items, and the candidate messages), so it needs the same
explicit flag as extraction, and every send is written to the disclosure log first.
"""
from __future__ import annotations

import re
import sys
import time
from datetime import datetime

from pydantic import BaseModel, Field

from .extract import CALL
from .sms import short_date

WINDOW_DAYS = 45      # how long after an item a closing message can come
MAX_EVIDENCE = 250    # lines sent per person; the most relevant win when there are more
CONTEXT = 3           # lines either side of a relevant one, so "9:30" arrives with its question

CLOSE_SYSTEM = """You check whether things a person owes, or is waiting on, were settled in a different chat.

You get open items from one of their 1:1 chats. Each has an id, who has to act ('me' is the user), what it is,
the message it came from and its date. You also get later messages from the user's other chats and group chats,
each with an id, date, chat name and speaker.

An item is settled when a later message clearly shows it was done, answered, or is no longer needed, and the
message is about the same specific thing: the same trip, payment, document, person or decision. The same topic
is not enough ("flight" in another chat doesn't settle a different flight). A plan to do it is not doing it.
Messages dated before the item don't count.

If you are not sure, leave the item out. A wrongly closed item hides something the user still owes; a wrongly
open one costs them one tap. Return only the items you are sure about, each with the evidence message id and a
short reason."""


class Closure(BaseModel):
    item: int = Field(description="id of the open item")
    evidence: int = Field(description="id of the later message that settles it")
    reason: str = Field(description="why that message settles it, under 15 words")


class Closures(BaseModel):
    closures: list[Closure]


_WORD = re.compile(r"[a-zऀ-ॿ]{4,}")
_STOP = set("""that this with from have will your about there their them they then than what when were been
also just only into some more very like okay haan nahi kya hai hain bhai aaj kal karo kardo karna kiya tha
thi the and for you are not but can""".split())


def _words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOP}


def candidates(store, person_id: int, items: list[dict], now: float | None = None,
               other_chats: bool = False) -> list[dict]:
    """Later lines from every group (and with other_chats, every other 1:1 chat) in the window, most
    relevant first if there are too many. Each: {id, ts, chat, speaker, text, ref}."""
    now = now or time.time()
    since = min(i["source_ts"] for i in items)
    until = min(now, max(i["source_ts"] for i in items) + WINDOW_DAYS * 86400)
    lines = []
    names = {p: n for p, n in store.conn.execute("SELECT id, display_name FROM person")}
    for r in store.conn.execute(
            "SELECT id, person_id, ts, from_me, text FROM message WHERE person_id != ? AND ts > ? AND ts <= ?"
            " ORDER BY ts", (person_id, since, until)) if other_chats else []:
        if r["text"] == CALL:
            continue
        lines.append(dict(ts=r["ts"], chat=names.get(r["person_id"], "?"),
                          speaker="me" if r["from_me"] else names.get(r["person_id"], "them"),
                          text=r["text"], ref=("message", r["id"], r["person_id"])))
    # Live sync stores a group sender as a WhatsApp id when history carried no name: show the person.
    by_address = {a: n for a, n in store.conn.execute(
        "SELECT h.address, p.display_name FROM handle h JOIN person p ON p.id = h.person_id")}
    for r in store.conn.execute(
            "SELECT id, source, ts, sender, text FROM evidence WHERE source LIKE '%-group:%'"  # every network's groups
            " AND ts > ? AND ts <= ? ORDER BY ts", (since, until)):
        lines.append(dict(ts=r["ts"], chat=r["source"].split(":", 1)[1] + " (group)",
                          speaker=by_address.get(r["sender"], r["sender"]),
                          text=r["text"], ref=("evidence", r["id"], None)))
    if len(lines) > MAX_EVIDENCE:
        lines = _relevant(lines, items)
    for n, line in enumerate(lines, start=1):
        line["id"] = n
    return lines


def _relevant(lines: list[dict], items: list[dict]) -> list[dict]:
    """Too many lines: keep the likeliest, with the lines around each. Likely means sharing words
    with an item, or coming soon after one. A bare "9:30" an hour after "which flight?" shares
    no words, and without its neighbours means nothing."""
    want = set().union(*(_words(i["action"] + " " + (i.get("source_text") or "")) for i in items))
    starts = [i["source_ts"] for i in items]

    def score(line: dict) -> int:
        soon = any(0 < line["ts"] - s <= 2 * 86400 for s in starts)
        return 2 * len(want & _words(line["text"])) + (1 if soon else 0)

    order = sorted(range(len(lines)), key=lambda n: -score(lines[n]))
    keep: set[int] = set()
    for n in order:
        if len(keep) >= MAX_EVIDENCE or score(lines[n]) == 0:
            break
        for k in range(n - CONTEXT, n + CONTEXT + 1):  # its neighbours in the same chat
            if 0 <= k < len(lines) and lines[k]["chat"] == lines[n]["chat"]:
                keep.add(k)
    return [lines[n] for n in sorted(keep)][:MAX_EVIDENCE * 2]


def _day(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %a %H:%M")


def render(person: str, items: list[dict], lines: list[dict]) -> str:
    out = [f"<open_items chat=\"{person}\">"]
    for n, i in enumerate(items, start=1):
        out.append(f"[{n}] {_day(i['source_ts'])} owner={i['owner']} {i['kind']}: {i['action']}"
                   f" | from the message: {(i.get('source_text') or '')[:200]}")
    out.append("</open_items>\n<later_messages>")
    out += [f"[{l['id']}] {_day(l['ts'])} {l['chat']} | {l['speaker']}: {l['text'][:300]}" for l in lines]
    out.append("</later_messages>")
    return "\n".join(out)


def run(store, ex, only: int | None = None, now: float | None = None,
        other_chats: bool = False) -> list[tuple[dict, dict, str]]:
    """Returns (item, evidence line, reason) for each suggestion written."""
    now = now or time.time()
    by_person: dict[int, list[dict]] = {}
    for item in store.open_items(now):
        by_person.setdefault(item["person_id"], []).append(item)
    closed = []
    for pid, items in by_person.items():
        if only is not None and pid != only:
            continue
        # Asked once, and your own answers stand: neither is sent again.
        items = [i for i in items if not i["suggestion"] and i["resolved_by"] != "you"]
        if not items:
            continue
        lines = candidates(store, pid, items, now, other_chats)
        if not lines:
            continue
        # Logged before sending: whose text leaves. Group lines are logged against this person.
        for p in {pid} | {l["ref"][2] for l in lines if l["ref"][2] is not None}:
            store.record_disclosure(p, ex.name)
        try:
            result = ex.ask(CLOSE_SYSTEM, f"Today is {_day(now)[:10]}. Which open items do the later messages settle?",
                            render(items[0]["name"], items, lines), Closures)
        except Exception as err:  # one refusal or timeout must not stop the others
            print(f"person {pid}: closure check failed: {str(err)[:200]}", file=sys.stderr)
            continue
        by_id = {l["id"]: l for l in lines}
        for c in result.closures:
            if not 1 <= c.item <= len(items) or c.evidence not in by_id:
                continue  # never trust a citation the input didn't contain
            item, line = items[c.item - 1], by_id[c.evidence]
            if line["ts"] <= item["source_ts"]:
                continue
            note = f"{line['chat']}, {short_date(line['ts'])}: “{line['text'][:90]}”"
            eid = line["ref"][1] if line["ref"][0] == "evidence" else None
            if store.resolve(pid, item["source_message_id"], item["owner"], "suggested", "closure",
                             evidence=f"{note} ({c.reason})", evidence_id=eid):
                closed.append((item, line, c.reason))
    return closed
