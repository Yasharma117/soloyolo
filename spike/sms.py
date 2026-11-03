"""Bank SMS as closing evidence: "send me ₹950" is done when the ₹950 credit alert arrives.

Reads an Android "SMS Backup & Restore" XML export (the usual way to get texts off an Android phone).
Only bank transaction alerts are kept: OTPs, offers, reminders, personal texts and anything else
are dropped while reading and never stored.

Matching is local and deterministic, no model involved: an open money item is closed by a payment
in the expected direction (money to you if they owe it, from you if you do), after the item was
made, for the same amount. No amount in the item, no match: a near miss stays open for you to tap.
"""
from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# --- parsing bank alerts ---------------------------------------------------------------------
_AMOUNT = r"(?:rs\.?|inr|₹)\s*([\d,]+(?:\.\d{1,2})?)"
_AMT = re.compile(_AMOUNT, re.I)
# SBI writes "debited by 950.0" / "credited by Rs1000" with or without the currency.
_AMT_BY = re.compile(r"\b(?:debited|credited)\s+(?:by|for|with)\s+(?:rs\.?|inr|₹)?\s*([\d,]+(?:\.\d{1,2})?)", re.I)
_ACCOUNT = re.compile(r"\b(a/?c|acct|account|upi|vpa|imps|neft|card)\b", re.I)
_OUT = re.compile(r"\b(debited|sent|paid|spent|withdrawn|transferred)\b", re.I)
_IN = re.compile(r"\b(credited|received|deposited)\b", re.I)
# Alerts about money that hasn't moved, or isn't a transfer at all.
_NOT_A_PAYMENT = re.compile(
    r"\b(otp|one time password|will be (?:debited|credited)|is due|amount due|requested|request(?:ed)? money"
    r"|collect request|pre-?approved|offer|loan|limit|declined|failed|reversed|bill)\b", re.I)
_TO = re.compile(r"\b(?:to|trf to|towards)\s+(?:vpa\s+)?([A-Za-z][\w.@ &-]{1,40}?)(?=\s+(?:on|ref\w*|upi|via|at)\b|\.(?:\s|$)|[;,\n(]|$)", re.I)
_FROM = re.compile(r"\b(?:from|by)\s+(?:vpa\s+)?([A-Za-z][\w.@ &-]{1,40}?)(?=\s+(?:on|ref\w*|upi|via|at)\b|\.(?:\s|$)|[;,\n(]|$)", re.I)
_P2A = re.compile(r"UPI/P2[AM]/\d+/([^/\n]+)", re.I)
_NOT_A_NAME = re.compile(r"^(?:a/?c|acct|account|hdfc|sbi|icici|axis|kotak|bank|your|ur|you|rs|inr|upi)(?:\b|\d)", re.I)


@dataclass(frozen=True)
class Payment:
    remote_id: str
    ts: float
    sender: str          # the SMS sender id, e.g. VM-HDFCBK
    text: str
    amount: float
    direction: str       # 'in' (to you) | 'out' (from you)
    counterparty: str | None


def _money(s: str) -> float:
    return float(s.replace(",", ""))


def parse_alert(body: str) -> tuple[float, str, str | None] | None:
    """(amount, direction, counterparty) for a bank transaction alert, else None."""
    if _NOT_A_PAYMENT.search(body) or not _ACCOUNT.search(body):
        return None
    m = _AMT_BY.search(body) or _AMT.search(body)
    if not m:
        return None
    amount = _money(m.group(1))
    if amount <= 0:
        return None
    # "debited ...; SHENA credited" (ICICI) is money out: the first verb wins.
    out, inn = _OUT.search(body), _IN.search(body)
    if out and (not inn or out.start() < inn.start()):
        direction = "out"
    elif inn:
        direction = "in"
    else:
        return None
    p2a = _P2A.search(body)
    names = [p2a.group(1)] if p2a else [m.group(1) for m in (_TO if direction == "out" else _FROM).finditer(body)]
    name = next((n.strip() for n in names if not _NOT_A_NAME.match(n.strip())), None)
    return amount, direction, name


def load_backup(path: Path | str) -> tuple[list[Payment], int]:
    """(bank payments, number of SMS read). Everything that isn't a payment alert is discarded here."""
    payments: list[Payment] = []
    read = 0
    for _, el in ET.iterparse(str(path), events=("end",)):
        if el.tag != "sms":
            if el.tag not in ("smses", "mms"):
                el.clear()
            continue
        read += 1
        body, address, date, kind = (el.get("body") or "", el.get("address") or "", el.get("date") or "0",
                                     el.get("type") or "1")
        el.clear()
        if kind != "1":  # 1 = received; banks don't get texts from you
            continue
        parsed = parse_alert(body)
        if not parsed:
            continue
        amount, direction, who = parsed
        rid = hashlib.sha256(f"{address}|{date}|{body}".encode()).hexdigest()[:40]
        payments.append(Payment(rid, int(date) / 1000, address, body, amount, direction, who))
    return payments, read


# --- matching money items -------------------------------------------------------------------
_K = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s?k\b", re.I)
_BARE = re.compile(r"(?<![\w.:/-])(\d{2,7})(?![\w.:/-])")
_MONEY_WORDS = re.compile(r"\b(pay|paid|money|monies|paise|paisa|rupees?|upi|transfer|bhej\w*|deposit|refund|"
                          r"reimburse|pay ?back|owe)\b|₹|\brs\b", re.I)
WINDOW_DAYS = 45


def amounts(text: str, bare: bool = False) -> set[float]:
    """Amounts written as ₹950, Rs 1,000, 2.7k; with bare=True also plain numbers (model-written actions)."""
    found = {_money(m.group(1)) for m in _AMT.finditer(text)}
    found |= {round(float(m.group(1)) * 1000, 2) for m in _K.finditer(text)}
    if bare:
        found |= {float(m.group(1)) for m in _BARE.finditer(text)}
    return {a for a in found if a >= 10}


def candidate_amounts(item: dict, nearby: list[str]) -> set[float]:
    """What the item could be for. Its own amount if it states one; otherwise the amounts in the nearest
    message that names money (nearby: nearest first, the asker's messages before the payer's), plus their
    sum when a few are listed ("2.7k for meds and 700 for the cab"). Never a union of everything around
    it: a neighbouring request for a different sum would match the wrong payment."""
    own = (amounts(item["action"], bare=True) if _MONEY_WORDS.search(item["action"]) else set())
    own |= amounts(item.get("source_text") or "", bare=bool(_MONEY_WORDS.search(item.get("source_text") or "")))
    if own:
        return own
    for text in nearby:
        near = sorted(amounts(text, bare=bool(_MONEY_WORDS.search(text))))
        if near:
            return set(near) | ({round(sum(near), 2)} if 2 <= len(near) <= 3 else set())
    return set()


def is_money_item(item: dict) -> bool:
    return bool(_MONEY_WORDS.search(item["action"]) or _MONEY_WORDS.search(item.get("source_text") or ""))


def describe(p: dict) -> str:
    when = datetime.fromtimestamp(p["ts"]).strftime("%-d %b")
    who = f" {'from' if p['direction'] == 'in' else 'to'} {p['counterparty']}" if p["counterparty"] else ""
    verb = "credited" if p["direction"] == "in" else "debited"
    return f"₹{p['amount']:,.0f} {verb}{who}, {when} ({p['sender']})"


def match(store, now: float | None = None) -> list[tuple[dict, dict]]:
    """Close open money items with a matching payment. Returns (item, payment) for each closure.
    Each payment closes at most one item; oldest items are matched first."""
    items = sorted((i for i in store.open_items(now)), key=lambda i: i["source_ts"])
    pays = [dict(r) for r in store.conn.execute(
        "SELECT * FROM evidence WHERE source = 'sms' AND amount IS NOT NULL ORDER BY ts")]
    used = {r[0] for r in store.conn.execute(
        "SELECT evidence_id FROM resolution WHERE decided_by = 'sms' AND evidence_id IS NOT NULL")}
    closed = []
    threads: dict[int, list] = {}
    for item in items:
        pid = item["person_id"]
        if pid not in threads:
            threads[pid] = list(store.thread(pid))
        thread = threads[pid]
        idx = next((i for i, m in enumerate(thread) if m["id"] == item["source_message_id"]), None)
        # Nearest first, earlier before later at the same distance, and the asker's own messages before
        # the payer's: whoever wants the money is the one who says how much.
        around = [] if idx is None else [
            thread[j] for d in range(1, 7) for j in (idx - d, idx + d) if 0 <= j < len(thread)]
        asker_is_me = item["owner"] == "them"
        nearby = [m["text"] for m in around if bool(m["from_me"]) == asker_is_me] + \
                 [m["text"] for m in around if bool(m["from_me"]) != asker_is_me]
        if not is_money_item(item):
            continue
        want = candidate_amounts(item, nearby)
        if not want:
            continue
        direction = "in" if item["owner"] == "them" else "out"
        for p in pays:
            if p["direction"] != direction or not item["source_ts"] < p["ts"] <= item["source_ts"] + WINDOW_DAYS * 86400:
                continue
            if p["id"] in used or not any(abs(p["amount"] - a) <= max(1.0, a * 0.005) for a in want):
                continue
            if store.resolve(pid, item["source_message_id"], item["owner"], "done", "sms", evidence=describe(p),
                             evidence_id=p["id"]):
                used.add(p["id"])
                closed.append((item, p))
            break
    return closed
