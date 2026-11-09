"""What to do first: every open item across every chat, in one ranked list, each with its reasons.

57 open items across 23 people is a list nobody reads. A per-person list also hides the one urgent
thing behind whoever happens to have the most. So items are scored on their own, additively, from
signals you could check yourself, and each one carries the reasons that put it there. No model, no
network: the ranking runs on the store as it is.

The weights are a first guess, written down so they can be argued with:

  you owe it                      +3    (waiting on them: +1.5. Your move matters more)
  overdue / due within 2 days     +4    overdue by more than 2 weeks: +0.5. A birthday wish six
                                        weeks late is gone; it is still shown, just not first
  due within a week               +2
  age, the "forgotten" curve      +0.5 under a day (you remember it), +1.5 under 3 days,
                                  +2 for 3-21 days (the ones that slip), +1 to 45 days, then 0
  money, said in the item itself  +1.5  (not a stray "pay" in the message it came from)
  they wrote last, you didn't reply +1
  a close person                  up to +2, from how much you two talk lately (log scale: ~100
                                        recent messages is +1.5, a handful is +0.5)
  maybe settled elsewhere         -3    (it waits for your tap, below the rest)
  each item above it from the same person  -0.5  (six app fixes from one chat don't fill the top 15)
"""
from __future__ import annotations

import math
import time
from datetime import date, datetime

from .sms import _MONEY_WORDS, amounts

DAY = 86400


def _due_points(due: str | None, today: date) -> tuple[float, str | None]:
    if not due:
        return 0, None
    try:
        d = (date.fromisoformat(due) - today).days
    except ValueError:
        return 0, None
    if d < -14:
        return 0.5, f"overdue {-d}d"
    if d < 0:
        return 4, f"overdue {-d}d"
    if d <= 2:
        return 4, "due today" if d == 0 else "due tomorrow" if d == 1 else "due in 2d"
    if d <= 7:
        return 2, f"due in {d}d"
    return 0, None


def _age_points(days: float) -> float:
    if days < 1:
        return 0.5
    if days < 3:
        return 1.5
    if days <= 21:
        return 2
    if days <= 45:
        return 1
    return 0


def is_money(action: str) -> bool:
    return bool(_MONEY_WORDS.search(action) or amounts(action))


def rank(store, now: float | None = None, limit: int | None = None) -> list[dict]:
    """Open items, best first. Each is the item from Store.people() plus person_id, name, score, reasons."""
    now = now or time.time()
    today = datetime.fromtimestamp(now).date()
    people = store.people(now)
    last_from_them = {r[0]: not r[1] for r in store.conn.execute(
        "SELECT person_id, from_me FROM message m WHERE ts = (SELECT MAX(ts) FROM message WHERE person_id = m.person_id)"
        " AND text != '[call]'")}
    muted = store.muted()  # a bot or an assistant: nothing in it is owed to a person
    out = []
    for p in people:
        if p["id"] in muted:
            continue
        close = min(2.0, math.log1p(p["score"]) / 3)  # score: recent messages, decayed (store.people)
        for c in p["commitments"]:
            if not store.is_open(c):
                continue
            reasons: list[str] = []
            score = 3.0 if c["owner"] == "me" else 1.5
            pts, why = _due_points(c["due"], today)
            score += pts
            if why:
                reasons.append(why)
            age = (now - c["source_ts"]) / DAY
            score += _age_points(age)
            if age >= 3:
                reasons.append(f"{int(age)} days")
            if is_money(c["action"]):
                score += 1.5
                reasons.append("money")
            if c["owner"] == "me" and last_from_them.get(p["id"]):
                score += 1
                reasons.append("they wrote last")
            score += close
            if close >= 1.5:
                reasons.append("close")
            if c["suggestion"]:
                score -= 3
                reasons.append("maybe settled")
            out.append(dict(c, person_id=p["id"], name=p["name"], score=round(score, 2),
                            reasons=reasons[:3] if "maybe settled" not in reasons else reasons[:2] + ["maybe settled"]))
    return _spread(out)[:limit] if limit else _spread(out)


def _spread(items: list[dict], step: float = 0.5) -> list[dict]:
    """Best first, each pick lowering the rest of that person's items by `step`."""
    left = sorted(items, key=lambda i: (-i["score"], -i["source_ts"]))
    taken: dict[int, int] = {}
    out = []
    while left:
        best = max(range(len(left)), key=lambda n: (left[n]["score"] - step * taken.get(left[n]["person_id"], 0),
                                                   left[n]["source_ts"]))
        item = left.pop(best)
        taken[item["person_id"]] = taken.get(item["person_id"], 0) + 1
        out.append(item)
    return out
