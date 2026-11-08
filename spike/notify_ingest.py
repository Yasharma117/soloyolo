"""Messages read off the Android phone's notifications (android/, docs/ANDROID-LISTENER.md).

The phone app uploads JSON batches; `python -m spike import-notifications batch.json` stores them.

    {
      "schema": 1,
      "device": "pixel",
      "messages": [
        {"package": "com.linkedin.android", "conversation": "Priya Shah", "group": false,
         "sender": "Priya Shah", "from_me": false, "text": "Any update on the intro?",
         "ts": 1760000000000, "ts_source": "message"}
      ]
    }

`ts` is epoch milliseconds. `ts_source` is "message" when it came from the MessagingStyle message itself
(stable across reposts) or "post" when the app gave only the notification's post time (it can move).
`sender` is null or "me" for your own replies. For 1:1 chats the phone puts the other person in
`conversation`, so your replies land in their thread.

What a notification tells us about who someone is: a display name, as that app shows it, and nothing
else (no phone number, no user id). So every handle here is `notif:<name>`, a low-confidence identity:
two people with the same name merge, and the same person on two apps stays two people until something
better links them. `is_low_confidence()` lets later code tell these apart from real handles.

The phone already drops apps outside its allowlist and OTP-like texts; this does both again, because
a batch can come from an older app build or a hand-made file.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

LOW_CONFIDENCE_PREFIX = "notif:"

# package -> store network. Keep in sync with android/.../Allowlist.kt.
NETWORKS = {
    "com.whatsapp": "whatsapp",
    "com.whatsapp.w4b": "whatsapp",
    "com.linkedin.android": "linkedin",
    "com.instagram.android": "instagram",
    "com.twitter.android": "x",
    "com.Slack": "slack",
    "org.telegram.messenger": "telegram",
    "org.telegram.messenger.web": "telegram",
    "org.thunderdog.challegram": "telegram",
    "com.google.android.apps.messaging": "sms",
    "com.samsung.android.messaging": "sms",
}

# One-time codes and login prompts. Matched on the phone too (Privacy.kt); this is the second net.
_OTP_WORDS = re.compile(
    r"\b(otp|one[- ]?time (?:pass(?:word|code)|code)|verification code|security code|login code|sign[- ]?in code"
    r"|auth(?:entication)? code|passcode|2fa|two[- ]factor|do not share|don'?t share|never share)\b", re.I)
_CODE = re.compile(r"(?<![\d.,])\d{4,8}(?![\d.,])|\b[A-Z0-9]{3}-[A-Z0-9]{3}\b")
_CODE_IS = re.compile(r"\b(?:code|pin)\s*(?:is|:)\s*\S*\d", re.I)
_IS_YOUR_CODE = re.compile(r"\bis your\b[^.\n]{0,40}\b(?:code|pin|otp|password)\b", re.I)
# Senders that are businesses, not people: "VM-HDFCBK", "AD-AMAZON", short codes like 57575.
_SMS_BUSINESS = re.compile(r"^(?:[A-Z]{2}-[A-Z0-9]{3,9}(?:-[A-Z])?|\d{3,6})$", re.I)
# Placeholders an app shows when previews are off or Android 15 redacted the content: no real text.
_PLACEHOLDER = re.compile(
    r"^(?:\d+ )?new messages?\b|^sensitive notification content hidden$|^message$|^you have a new message"
    r"|^checking for new messages|^this message was deleted$", re.I)


def is_otp(text: str) -> bool:
    return bool(_CODE_IS.search(text) or ((_OTP_WORDS.search(text) or _IS_YOUR_CODE.search(text)) and _CODE.search(text)))


def is_low_confidence(address: str) -> bool:
    return address.startswith(LOW_CONFIDENCE_PREFIX)


@dataclass(frozen=True)
class Message:  # what Store.add_messages takes
    guid: str
    handle: str
    ts: float
    from_me: bool
    text: str


@dataclass(frozen=True)
class GroupLine:  # what Store.add_evidence takes
    remote_id: str
    ts: float
    sender: str  # 'me' for you
    text: str


@dataclass
class Batch:
    rows: dict[str, list[Message]]          # network -> 1:1 messages
    names: dict[str, dict[str, str]]        # network -> {handle: display name}
    groups: dict[str, list[GroupLine]]      # evidence source -> lines
    skipped: dict[str, int]                 # reason -> count
    post_ts: set[str]                       # guids whose ts is a post time, not the message's own


def _norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _key(s: str) -> str:
    return _norm(s).casefold()


def _is_me(sender) -> bool:
    return sender is None or _key(sender) in ("", "me", "you")


def remote_id(package: str, conversation: str, sender: str, text: str, ts_ms: int) -> str:
    """The dedupe key: the same message reposted in a later notification hashes the same."""
    raw = "\x1f".join([package, _key(conversation), _key(sender), _norm(text), str(ts_ms)])
    return LOW_CONFIDENCE_PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:24]


def handle_for(counterpart: str, conversation: str | None) -> str:
    """`notif:<name>`, or `notif:<name>@<title>` when the app titles the chat with something else
    (a Slack workspace, say), so the same first name in two places stays two people."""
    h = LOW_CONFIDENCE_PREFIX + _key(counterpart)
    if conversation and _key(conversation) != _key(counterpart):
        h += "@" + _key(conversation)
    return h


def parse(data: dict) -> Batch:
    b = Batch({}, {}, {}, {}, set())

    def skip(why: str) -> None:
        b.skipped[why] = b.skipped.get(why, 0) + 1

    # Oldest first, so a 1:1 reply of yours can attach to whoever last wrote in that chat.
    msgs = sorted(data.get("messages") or [], key=lambda m: int(m.get("ts") or 0))
    last_incoming: dict[tuple[str, str], tuple[str, str]] = {}  # (package, conversation) -> (handle, name)
    for m in msgs:
        package = m.get("package") or ""
        network = NETWORKS.get(package)
        text = _norm(m.get("text"))
        if not network:
            skip("app not on the allowlist")
            continue
        if not text or _PLACEHOLDER.search(text):
            skip("no message text (preview off or redacted)")
            continue
        if is_otp(text):
            skip("one-time code")
            continue
        sender = m.get("sender")
        from_me = bool(m.get("from_me")) or _is_me(sender)
        sender = "me" if from_me else _norm(sender)
        conversation = _norm(m.get("conversation")) or (None if from_me else sender)
        if network == "sms" and not from_me and _SMS_BUSINESS.match(sender.replace(" ", "")):
            skip("business SMS sender")
            continue
        ts_ms = int(m.get("ts") or 0)
        if ts_ms <= 0:
            skip("no timestamp")
            continue
        rid = remote_id(package, conversation or "", sender, text, ts_ms)
        if m.get("group"):
            title = conversation or "untitled"
            b.groups.setdefault(f"{network}-group:{title}", []).append(GroupLine(rid, ts_ms / 1000, sender, text))
            continue
        if from_me:
            if not conversation:
                skip("your reply, chat unknown")
                continue
            handle, name = last_incoming.get((package, _key(conversation)), (handle_for(conversation, None), conversation))
        else:
            handle, name = handle_for(sender, conversation), sender
            last_incoming[(package, _key(conversation))] = (handle, name)
        b.rows.setdefault(network, []).append(Message(rid, handle, ts_ms / 1000, from_me, text))
        b.names.setdefault(network, {})[handle] = name
        if m.get("ts_source") == "post":
            b.post_ts.add(rid)
    return b


def load(path: Path | str) -> Batch:
    return parse(json.loads(Path(path).read_text("utf-8")))


# A message we already hold from a real sync (connectord's WhatsApp, a chat export) shows up again
# here as a notification. Same network, same text, same direction, close in time: keep the synced one.
SYNCED_SLACK_S = 120
# Apps that give only a post time repost the same text with a new time: treat those as one.
REPOST_SLACK_S = 900


def _seen(store, network: str, r: Message, post_ts: bool) -> bool:
    rows = store.conn.execute(
        "SELECT remote_id FROM message WHERE network = ? AND text = ? AND from_me = ? AND ABS(ts - ?) <= ?",
        (network, r.text, int(r.from_me), r.ts, REPOST_SLACK_S if post_ts else SYNCED_SLACK_S)).fetchall()
    return any(post_ts or not is_low_confidence(x[0]) for x in rows)


def ingest(store, batch: Batch) -> dict[str, int]:
    """Writes a batch. Returns counts: new messages, new group lines, and duplicates of synced messages."""
    out = {"messages": 0, "group_lines": 0, "already_synced": 0}
    for network, rows in batch.rows.items():
        names = batch.names.get(network)
        for r in rows:  # one at a time, so a repost later in the same batch sees the first copy
            if _seen(store, network, r, r.guid in batch.post_ts):
                out["already_synced"] += 1
            else:
                out["messages"] += store.add_messages(network, [r], names)
    for source, lines in batch.groups.items():
        out["group_lines"] += store.add_evidence(source, lines)
    return out
