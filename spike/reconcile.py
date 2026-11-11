"""Merge a re-read of a thread with what the last read found, so the list doesn't flicker.

Read the same chat twice and a model gives two slightly different lists: an item there on Monday is
missing on Tuesday though nothing in the chat changed. On the live store that made marks feel
pointless and the list untrustworthy. The rule here: an item only leaves the list for a stated reason.

- The re-read sees the earlier items ([P1], [P2]..) and returns each one it still holds, by id.
- One it returns in `dropped` (never a real item, with a reason) goes, unless you have marked it:
  your marks always stand.
- One it neither returns nor drops is carried over unchanged. Forgetting is not a reason.
- One returned under a different source message keeps your marks (they're re-keyed to follow it).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Merge:
    items: list[dict]                          # the commitment rows to store
    kept: int = 0                              # earlier items the re-read returned
    carried: int = 0                           # earlier items it forgot: kept as they were
    dropped: list[tuple[dict, str]] = field(default_factory=list)  # (item, reason)
    new: int = 0
    rekeys: list[tuple[tuple[int, str], tuple[int, str]]] = field(default_factory=list)


ROW = ("kind", "owner", "action", "due", "status", "source_message_id", "done_message_id")


def merge(prior: list[dict], result, yours: set[tuple[int, str]] = frozenset()) -> Merge:
    """prior: the stored items, in the order they were shown to the model as [P1].. ; result: its Extraction;
    yours: (source_message_id, owner) of items you've marked.

    One message can hold two items ("refill the spray and the facewash"), so (message, owner) is not an
    item's identity: the [P#] id is. Without one, an item matches an unclaimed earlier item from the same
    message and owner."""
    labels = {f"P{n}": c for n, c in enumerate(prior, start=1)}
    out, matched, seen = Merge(items=[]), set(), set()
    for c in result.commitments:
        row = {k: getattr(c, k) for k in ROW}
        key = (row["source_message_id"], row["owner"])
        if (key, row["action"]) in seen:
            continue  # the same item twice
        seen.add((key, row["action"]))
        label = c.previous if c.previous in labels and c.previous not in matched else next(
            (lb for lb, o in labels.items() if lb not in matched and (o["source_message_id"], o["owner"]) == key), None)
        if label:
            matched.add(label)
            old = labels[label]
            old_key = (old["source_message_id"], old["owner"])
            if old_key != key:
                out.rekeys.append((old_key, key))
            out.kept += 1
        else:
            out.new += 1
        out.items.append(row)
    reasons = {d.previous: d.reason for d in getattr(result, "dropped", [])}
    for label, old in labels.items():
        if label in matched:
            continue
        if label in reasons and (old["source_message_id"], old["owner"]) not in yours:
            out.dropped.append((old, reasons[label]))
            continue
        out.carried += 1
        out.items.append({k: old[k] for k in ROW})
    # A mark stays put while another item still comes from that message: it may be that one's.
    stays = {(i["source_message_id"], i["owner"]) for i in out.items}
    out.rekeys = [(a, b) for a, b in out.rekeys if a not in stays]
    return out
