"""Today: the one to three things that matter now. Silence means done.

Run 6 (eval/RESULTS.md) scored the top 15 of the ranked open list. None was a misreading, and only one
was still to do: it was due that day and a day old. Nine were done where a chat can't see (UPI, in
person), three were no longer needed and two were ignored on purpose. Nobody writes "done" back. So
"open until the chat says done" is the wrong default, and a backlog is mostly a record of finished
things. This module makes the opposite assumption and lets an item back in only on a real signal.

The rules, and why each is what it is:

  live window      3 days from the item's source message. The one useful item in run 6 was 1 day old,
                   and even the 2-9 day old items were mostly done, so the window is days, not weeks.
                   Three days covers a promise made on Friday that is still undone on Monday.
  with a due date  live from the source to the end of the day after the due date, or 3 days, whichever
                   ends first; and again from 2 days before the due date to the end of the day after it.
                   A due date is the one thing that says when an item matters, so a far-off one is shown
                   then, even if it was made weeks earlier. One day of grace, because the due-today item
                   in run 6 was done that day: a day late it is still worth a look, two days late it isn't.
  after the window assumed done. Hidden, never deleted: `top` and the full list still show it.
  a chaser         revives an item for 3 days from the chaser. A chaser comes from the side that is
                   waiting (them, for what you owe; you, for what they owe), at least 6 hours after the
                   item (sooner is the same ask, not a chase), in at most 160 characters, and is about
                   this item. "About" means sharing the item's content words (its action, and its source
                   message if that is short), with prefixes matching ("photo", "photos"):
                     - 2+ shared words and a question or an ask ("did you", "bhej", "kab", "pls"), or
                     - 1+ shared word and a follow-up ("any update", "kya hua", "reminder", "status?"), or
                     - 1 shared word and an ask in 30 characters or less, when that word is most of the
                       message ("photos bhej do" yes, "photos of Meera's car bhejo" no), or
                     - a bare follow-up with no content word at all ("kya hua??", "any update?"), which
                       goes to the newest item that side waits on from the 14 days before it.
                   Why this strict: the first, looser version (any "?" plus one shared word) found 128
                   chasers on the live store and nearly all were wrong (a shared "link", "share" or "time",
                   long bot messages, a bare "????"); live items per morning ran to 15. This version
                   finds 8, and reading them, 7 are real chases. A missed chaser costs little: the other
                   person usually asks again, and a re-read lists the new ask as a fresh item.
                   Deterministic: phrase lists and word overlap, no model. Hinglish spelling variants
                   ("bhejo", "bejo") are not matched beyond the prefix rule.
  your marks win   Done and Not real hide it for good; snoozed hides it until the snooze ends, then it
                   is live for a window (a snooze is "remind me then"). "Still open" makes it live for a
                   window from when you said so; after that silence counts again. No signal overrides
                   any of these.
  picking 1-3      the live items are scored by priority.py's points, plus 2 for a chase (the strongest
                   sign it still matters, stronger than "due within a week"), spread across people the
                   same way, and the top 3 are shown. No live items means an empty Today, on purpose.
"""
from __future__ import annotations

import re
import time
from datetime import date, datetime, timedelta

from . import priority

DAY = 86400.0
WINDOW = 3 * DAY           # live after the source message, a chaser, a snooze ending or a "still open"
DUE_BEFORE = 2             # days before the due date it comes back
DUE_GRACE = 1              # days after the due date it stays
CHASE_GAP = 6 * 3600       # a chaser this soon after the item is the same ask, not a chase
GENERIC_REACH = 14 * DAY   # a bare "any update?" goes to the newest waiting item from this far back
CHASE_POINTS = 2.0
LIMIT = 3

# Follow-ups that mean "where is it?" on their own. English and Hinglish, as people type them.
_BARE = re.compile(
    r"\bany\s*update|\bupdates?\s*\?|\bstatus\s*\?|\bwhat(?:'?s| is) the status|\bwhat happened\s*\?|\bkya\s+hu+w?a\b"
    r"|\bhu+w?a\s+kya\b|\bho\s*gaya\s+kya\b|\bkuch\s+hu+w?a\b|\bstill\s+waiting|\breminder\b|\bjust\s+checking"
    r"|\bfollow(?:ing)?\s*up\b|\bkab\s+tak\b|\babhi\s+tak\s+n(?:a|ah)?h?i\b", re.I)
# Asking for it again, in so many words. With a question mark these are what make a message about the
# item a chase.
_ASK = re.compile(
    r"\bdid\s+(?:you|u)\b|\bhave\s+(?:you|u)\b|\bwhen\b|\bkab\b|\bbhej|\bsend\b|\bpl[sz]e?\b|\bplease\b|\byaad\b"
    r"|\bremember|\bbata|\bkar\s*(?:di|diya|do|de|dena)\b|\bkarde|\bkardo|\bmila\b|\bagain\b|\bphir\s+se\b|\bjaldi\b"
    r"|\basap\b|\bwaiting\b", re.I)
CHASE_MAX_CHARS = 160      # chasers are short; a long message sharing words with an item is about something else
TERSE_CHARS = 30           # "photos bhej do": this short, an ask and one shared word are enough, if it's most of it

_STOP = set("""
a an the and or but if so to of in on at for from by with about as is are was were be been am it its this that
these those there here i me my mine you your yours u ur we us our he she him her they them their what which who
when where why how can could will would shall should may might must do does did done have has had not no yes
ok okay okk hmm haan han ha ji re yaar yr bhai bro brother sir mam please pls plz plss thanks thank thx tq ty
just also too very much more some any all then than now today tomorrow tmrw tmr yesterday soon later again still
yet get got give send sent tell let know make message msg update status waiting wait reminder remember check
need want like sure fine good great nice right well one two back first before after time work full part find
found keep look looks see said say going gone come came take took put use used new old day days week weeks night
morning evening didn isn don doesn wasn won https http www com
hai hain ho hoga hogi hua huwa hui ka ki ke ko se na ne bhi toh to ya aur kya kyu kyun kaise kab kaha kahan
main mein mai mujhe mera meri mere tu tum tumhara aap ap apna apne apni hum humko ye yeh wo woh vo isko usko unko
kar karo karna karke kr kro krna krdo karde kardo de do di diya dena dedo le lo liya lena nahi nhi nai mat abhi
kal aaj phir fir bas bss accha acha achha theek thik thk sahi haa bhej bhejo bhejdo bhejna bhejde bata batao
batana yaad jaldi kiya kiye kari hogya hogaya gaya gaye gayi tha thi the raha rahi rahe rha rhi baar bol dekh
dekhna dekho wala wali wale kuch sab bahut bohot liye pe par tak ab jab tab agar lekin ek
""".split())
_MARKER = re.compile(r"^\s*\[[^\]]*\]\s*$")  # [call], [photo]: what fulfils an item, never a chase
_URL = re.compile(r"\S+://\S+|www\.\S+")


def words(text: str) -> set[str]:
    """Content words: lowercase, no links or stopwords, 3+ letters (or a number of 3+ digits: an amount)."""
    text = _URL.sub(" ", (text or "").lower())
    return {w for w in re.findall(r"[^\W\d_]+|\d{3,}", text) if len(w) >= 3 and w not in _STOP}


def _same(a: str, b: str) -> bool:
    return a == b or (min(len(a), len(b)) >= 4 and (a.startswith(b) or b.startswith(a)))


def shared(msg: set[str], item: set[str]) -> int:
    """How many of the item's words the message also has (prefixes count: photo / photos)."""
    return sum(any(_same(w, v) for w in msg) for v in item)


def _local_midnight(d: date) -> float:
    return datetime(d.year, d.month, d.day).timestamp()


def _due_window(due: str | None) -> tuple[float, float] | None:
    try:
        d = date.fromisoformat(due) if due else None
    except ValueError:
        return None
    if not d:
        return None
    return (_local_midnight(d - timedelta(days=DUE_BEFORE)), _local_midnight(d + timedelta(days=DUE_GRACE + 1)))


def _chase_kind(text: str, item_words: set[str]) -> str | None:
    """'chased' or 'asked again' when this message chases this item by its words; None otherwise."""
    if _MARKER.match(text or "") or len(text or "") > CHASE_MAX_CHARS:
        return None
    w = words(text)
    n = shared(w, item_words)
    bare, ask = bool(_BARE.search(text)), bool(_ASK.search(text))
    terse = n >= 1 and ask and len(text) <= TERSE_CHARS and n * 2 > len(w)
    if (n >= 2 and (ask or bare or "?" in text)) or (n >= 1 and bare) or terse:
        return "asked again" if not bare and n * 2 >= min(len(item_words), 4) else "chased"
    return None


def item_terms(c: dict) -> set[str]:
    """What an item is about: its action's words, and its source message's when that's short (a long
    source shares a word with nearly anything)."""
    src = c.get("source_text") or ""
    return words(c["action"]) | (words(src) if len(src) <= CHASE_MAX_CHARS else set())


def _is_bare(text: str) -> bool:
    """"Any update?", "kya hua?": a chase that names nothing, so it's about the newest thing waited on."""
    text = text or ""
    return len(text) <= CHASE_MAX_CHARS and bool(_BARE.search(text)) and not words(text)


def assess(store, now: float | None = None) -> list[dict]:
    """Every open item (after your marks), scored like priority.rank, each with whether it's live now.

    Adds to each item: live (bool), live_until (epoch or None), chased_at (epoch or None), and nudge
    reasons in front of priority's. Hidden items are kept, with live False, for the full list."""
    now = now or time.time()
    ranked = priority.rank(store, now)
    marks = {(r["person_id"], r["source_message_id"], r["owner"]): dict(r) for r in store.conn.execute(
        "SELECT * FROM resolution WHERE decided_by = 'you'")}
    by_person: dict[int, list[dict]] = {}
    for c in ranked:
        by_person.setdefault(c["person_id"], []).append(c)
    out = []
    for pid, items in by_person.items():
        earliest = min(c["source_ts"] for c in items)
        msgs = [dict(r) for r in store.conn.execute(
            "SELECT id, ts, from_me, text FROM message WHERE person_id = ? AND ts > ? AND ts <= ? ORDER BY ts",
            (pid, earliest, now))]
        every = store.items(pid)  # every item, done ones too: a bare chase goes to the newest
        sources = {i["source_message_id"] for i in every}
        for c in items:
            out.append(_assess_one(c, msgs, every, sources, marks.get((pid, c["source_message_id"], c["owner"])), now))
    return out


def _assess_one(c: dict, msgs: list[dict], every: list[dict], sources: set[int], mark: dict | None,
                now: float) -> dict:
    waiting_side = 0 if c["owner"] == "me" else 1  # from_me of whoever is waiting on this item
    item_words = item_terms(c)
    chased_at, how = None, None
    for m in msgs:
        if m["from_me"] != waiting_side or m["ts"] < c["source_ts"] + CHASE_GAP:
            continue
        if m["id"] in (c["source_message_id"], c.get("done_message_id")):
            continue
        kind = _chase_kind(m["text"], item_words)
        if not kind and m["id"] not in sources and _is_bare(m["text"]) and _newest_waiting(every, m, waiting_side) == (
                c["source_message_id"], c["owner"]):
            kind = "chased"
        if kind:
            chased_at, how = m["ts"], kind  # keep the latest
    windows = [(c["source_ts"], c["source_ts"] + WINDOW)]
    due = _due_window(c["due"])
    if due:
        windows = [(c["source_ts"], max(c["source_ts"] + DAY / 2, min(c["source_ts"] + WINDOW, due[1]))), due]
    if chased_at:
        windows.append((chased_at, chased_at + WINDOW))
    if mark and mark["state"] == "open":
        windows.append((mark["at"], mark["at"] + WINDOW))
    if mark and mark["state"] == "snoozed" and mark["until"]:
        windows.append((mark["until"], mark["until"] + WINDOW))
    live = [w for w in windows if w[0] <= now < w[1]]
    reasons = []
    if chased_at and chased_at <= now < chased_at + WINDOW:
        who = "they" if waiting_side == 0 else "you"
        reasons.append(f"{who} {how} {_ago(now - chased_at)}")
    item = dict(c, live=bool(live), live_until=max(w[1] for w in live) if live else None,
                chased_at=chased_at, reasons=reasons + [r for r in c["reasons"] if r not in reasons])
    if reasons:
        item["score"] = round(c["score"] + CHASE_POINTS, 2)
    return item


def _newest_waiting(every: list[dict], msg: dict, waiting_side: int) -> tuple[int, str] | None:
    """The item a bare "any update?" is about: the newest one this side waits on, from the 14 days before it."""
    side_owner = "me" if waiting_side == 0 else "them"
    best = None
    for i in every:
        if i["owner"] != side_owner or not (msg["ts"] - GENERIC_REACH <= i["source_ts"] <= msg["ts"] - CHASE_GAP):
            continue
        if best is None or i["source_ts"] > best["source_ts"]:
            best = i
    return (best["source_message_id"], best["owner"]) if best else None


def _ago(seconds: float) -> str:
    d = int(seconds // DAY)
    return "today" if d == 0 else "1d ago" if d == 1 else f"{d}d ago"


def today(store, now: float | None = None, limit: int = LIMIT) -> list[dict]:
    """Today's 1-3 items (or none): live items only, best first, spread across people."""
    return priority._spread([c for c in assess(store, now) if c["live"]])[:limit]


def summary(store, now: float | None = None, limit: int = LIMIT) -> dict:
    """What the viewer's first screen needs: today's items, and how many open items are quiet."""
    items = assess(store, now)
    live = [c for c in items if c["live"]]
    return {"today": priority._spread(live)[:limit], "live": len(live), "quiet": len(items) - len(live),
            "open": len(items)}
