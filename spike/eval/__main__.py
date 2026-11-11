"""Score an extractor on the labeled cases.

    python -m spike.eval                          # offline heuristic
    python -m spike.eval --extractor claude-code  # Claude via your Claude Code login (~$0.02 a case)
    python -m spike.eval --extractor open-model --model google/gemma-4-31b-it:free   # an open model (OpenRouter)

A prediction matches an expected commitment when the owner agrees and it cites one of the
expected source messages. Each expected item matches at most once; extra predictions count
against precision. Status is right when an open item is open, or a done item cites one of the
expected done messages. Kind (promise or ask) is right when it equals the label, promise by
default; it doesn't affect matching.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..__main__ import EXTRACTORS
from .cases import CASES


def thread_of(case: dict, now: float) -> list[dict]:
    out = []
    for i, (days, hour, me, text) in enumerate(case["messages"], start=1):
        day = time.localtime(now - days * 86400)
        ts = time.mktime((day.tm_year, day.tm_mon, day.tm_mday, hour, 0, 0, 0, 0, -1)) + i
        out.append({"id": i, "ts": ts, "from_me": me, "text": text})
    return out


def score(case: dict, predicted: list) -> dict:
    expected = list(case["expected"])
    tp = status_ok = kind_ok = 0
    extra, used = [], set()
    for c in predicted:
        hit = next((j for j, e in enumerate(expected)
                    if j not in used and e["owner"] == c.owner and c.source_message_id in e["sources"]), None)
        if hit is None:
            extra.append(f"{c.owner} {c.kind}: {c.action} [{c.source_message_id}]")
            continue
        used.add(hit)
        tp += 1
        e = expected[hit]
        kind_ok += c.kind == e.get("kind", "promise")
        if (not e["done"] and c.status == "open") or (e["done"] and c.status == "done" and c.done_message_id in e["done"]):
            status_ok += 1
    missed = [f"{e['owner']} {e.get('kind', 'promise')} @ {e['sources']}" for j, e in enumerate(expected) if j not in used]
    return {"id": case["id"], "tp": tp, "fp": len(extra), "fn": len(missed), "status_ok": status_ok, "kind_ok": kind_ok,
            "extra": extra, "missed": missed}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m spike.eval")
    ap.add_argument("--extractor", choices=EXTRACTORS, default="heuristic")
    ap.add_argument("--model", help="the model id, for extractors that take one")
    ap.add_argument("--jobs", type=int, default=4, help="cases run in parallel")
    ap.add_argument("--out", type=Path, help="write per-case results as JSON")
    a = ap.parse_args(argv)

    ex = EXTRACTORS[a.extractor](model=a.model) if a.model else EXTRACTORS[a.extractor]()
    now = started = time.time()

    def run(case):
        try:
            return score(case, ex.extract(thread_of(case, now)).commitments)
        except Exception as err:  # one failed case is reported, not fatal
            return {"id": case["id"], "error": str(err)[:200], "tp": 0, "fp": 0, "fn": len(case["expected"]),
                    "status_ok": 0, "kind_ok": 0, "extra": [], "missed": ["(error)"]}

    with ThreadPoolExecutor(max_workers=max(1, a.jobs)) as pool:
        rows = list(pool.map(run, CASES))

    tp, fp, fn, ok, kind_ok = (sum(r[k] for r in rows) for k in ("tp", "fp", "fn", "status_ok", "kind_ok"))
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    errors = [r for r in rows if "error" in r]
    print(f"extractor: {ex.name}   cases: {len(rows)}   expected items: {tp + fn}")
    print(f"precision {precision:.2f}   recall {recall:.2f}   F1 {f1:.2f}   "
          f"status right {ok}/{tp}   kind right {kind_ok}/{tp}   errors {len(errors)}")
    print(f"time {time.time() - started:.0f}s" + (f"   {json.dumps(ex.stats)}" if hasattr(ex, "stats") else ""))
    for r in rows:
        if r["fp"] or r["fn"] or "error" in r:
            bits = [f"missed {', '.join(r['missed'])}"] if r["missed"] else []
            bits += [f"extra {e}" for e in r["extra"]]
            print(f"  {r['id']}: " + "; ".join(bits) + (f" ({r['error']})" if "error" in r else ""))
    if a.out:
        a.out.write_text(json.dumps({"extractor": ex.name, "precision": precision, "recall": recall, "f1": f1,
                                     "status_ok": ok, "kind_ok": kind_ok, "matched": tp, "rows": rows}, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
