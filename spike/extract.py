"""Find commitments in a 1:1 thread: who promised what, by when, and whether it got done.

Three extractors behind one call shape, `extract(thread) -> Extraction`:

- HeuristicExtractor: regexes, no network. Exists so the pipeline runs offline and as a
  floor to beat. It misses most real-world phrasing (see spike/eval/RESULTS.md).
- ClaudeCodeExtractor: runs Claude through the Claude Code CLI (`claude -p`), so it uses your
  Claude login. No API key needed.
- ClaudeExtractor: the Anthropic API directly. Needs ANTHROPIC_API_KEY or `ant auth login`.

Both Claude extractors send the thread *text* off the machine, which breaks the local-first
promise, so the CLI only uses them when asked for by name.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from datetime import date, datetime, timedelta
from typing import Literal, Optional, Sequence

from pydantic import BaseModel, Field


class Commitment(BaseModel):
    kind: Literal["promise", "ask"] = Field(
        description="'promise' if one side said they would do it, 'ask' if one side asked the other and got no yes or no")
    owner: Literal["me", "them"] = Field(
        description="Who has to act: for a promise, who made it; for an ask, who was asked. 'me' is the thread owner")
    action: str = Field(description="What has to be done, as a short imperative, e.g. 'Intro Sam to Priya'")
    due: Optional[str] = Field(description="ISO date (YYYY-MM-DD) if a deadline was stated or clearly implied, else null")
    status: Literal["open", "done"]
    source_message_id: int = Field(description="id of the message where it was promised or asked")
    done_message_id: Optional[int] = Field(description="id of the message showing it was done, else null")
    previous: Optional[str] = Field(default=None,
                                    description="the [P#] id when this is an item from earlier_items, else null")


class Dropped(BaseModel):
    previous: str = Field(description="the [P#] id of an earlier item that was never a real item")
    reason: str = Field(description="why it isn't one, under 15 words")


class Extraction(BaseModel):
    commitments: list[Commitment]
    topics: list[str] = Field(description="Up to 4 recurring subjects of this relationship, 1-3 words each")
    dropped: list[Dropped] = Field(default_factory=list,
                                   description="earlier items that were never real items; empty when none")


CALL = "[call]"  # a logged call (spike.whatsapp_export): it happened, direction unknown


def render(thread: Sequence) -> str:
    def line(m) -> str:
        stamp = f"[{m['id']}] {datetime.fromtimestamp(m['ts']).strftime('%Y-%m-%d %a %H:%M')}"
        if m["text"] == CALL:
            return f"{stamp} (a call between us)"
        return f"{stamp} {'me' if m['from_me'] else 'them'}: {m['text']}"
    return "\n".join(line(m) for m in thread)


# --- heuristic -------------------------------------------------------------------------
_PROMISE = re.compile(
    r"\b(i'll|i will|i'm going to|im going to|let me|i can|will do|i'll make sure to)\s+"
    r"(?P<what>(?:send|intro|introduce|share|call|email|text|check|book|get back|follow up|forward|review|"
    r"look into|put together|connect|find|ping|drop|grab|bring|loop|pay)\b[^.!?\n]{0,80})",
    re.I,
)
_DONE = re.compile(r"\b(sent|done|here you go|here it is|just (?:intro'?d|introduced|sent|booked|emailed)|"
                   r"introduced you|booked|attached|forwarded)\b", re.I)
_ASK = re.compile(
    r"\b(?:could you|can you|would you|could u|can u|kindly|please|pls|plz)\s+(?:please\s+)?"
    r"(?P<what>(?:send|share|review|check|upload|book|give|forward|confirm|sign|fill|submit|update|add|"
    r"intro|introduce|call|email|look at|let me know)\b[^.!?\n]{0,80})",
    re.I,
)
_STATUS_ASK = re.compile(r"\b(any update|following up|follow(?:ing)? up on|gentle reminder|just checking in)\b", re.I)
_ACCEPT = re.compile(r"^\W*(on it|will do|sure|ok(?:ay)?|yes|lemme|let me|i'?ll|will share|will send)\b", re.I)
_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _due(text: str, ts: float) -> str | None:
    t, d = text.lower(), date.fromtimestamp(ts)
    if "tonight" in t or "today" in t:
        return d.isoformat()
    if "tomorrow" in t:
        return (d + timedelta(days=1)).isoformat()
    if "next week" in t:
        return (d + timedelta(days=7 - d.weekday())).isoformat()
    for i, name in enumerate(_WEEKDAYS):
        if re.search(rf"\b(by |on |this )?{name}\b", t):
            return (d + timedelta(days=(i - d.weekday()) % 7 or 7)).isoformat()
    return None


def _sentence(s: str) -> str:
    s = s.strip()
    return s[:1].upper() + s[1:]


class HeuristicExtractor:
    name = "heuristic"
    remote = False  # never sends text anywhere

    def extract(self, thread: Sequence) -> Extraction:  # deterministic: same thread, same answer; no prior
        out, accepted = self._asks(thread)
        for i, m in enumerate(thread):
            hit = _PROMISE.search(m["text"])
            if not hit or m["id"] in accepted:
                continue
            owner = "me" if m["from_me"] else "them"
            done = next((n for n in thread[i + 1:]
                         if bool(n["from_me"]) == bool(m["from_me"]) and _DONE.search(n["text"])), None)
            out.append(Commitment(
                kind="promise",
                owner=owner,
                action=_sentence(re.split(r",|;| - ", hit.group("what"))[0]),
                due=_due(m["text"], m["ts"]),
                status="done" if done else "open",
                source_message_id=m["id"],
                done_message_id=done["id"] if done else None,
            ))
        return Extraction(commitments=out, topics=[])

    @staticmethod
    def _asks(thread: Sequence) -> tuple[list[Commitment], set[int]]:
        """Requests from one side. The other side's next message decides what it became: a yes makes it
        their promise, a delivery closes it, silence leaves it open on them."""
        out: list[Commitment] = []
        accepted: set[int] = set()
        for i, m in enumerate(thread):
            hit = _ASK.search(m["text"])
            if not hit and not _STATUS_ASK.search(m["text"]):
                continue
            asker = bool(m["from_me"])
            if not hit and any((bool(n["from_me"]) == asker and _ASK.search(n["text"]))
                               or (bool(n["from_me"]) != asker and _PROMISE.search(n["text"]))
                               for n in thread[:i]):
                continue  # chasing something already on the list, not a new item
            replies = [n for n in thread[i + 1:] if bool(n["from_me"]) != asker]
            reply = replies[0] if replies else None
            action = _sentence(re.split(r",|;| - ", hit.group("what"))[0]) if hit else "Reply with an update"
            if reply and _ACCEPT.search(reply["text"]):
                accepted.add(reply["id"])
                done = next((n for n in replies[1:] if _DONE.search(n["text"])), None)
                kind, src = "promise", reply
            else:
                done = reply if reply and (_DONE.search(reply["text"]) or not hit) else None
                kind, src = "ask", m
            out.append(Commitment(
                kind=kind, owner="them" if asker else "me", action=action, due=_due(m["text"], m["ts"]),
                status="done" if done else "open", source_message_id=src["id"],
                done_message_id=done["id"] if done else None,
            ))
        return out, accepted


# --- Claude ----------------------------------------------------------------------------
SYSTEM = """You read one person's private 1:1 text thread with someone and list what each side owes the other.

There are two kinds of item.
- promise: one side said they would do something concrete: send, introduce, call, review, book, pay back,
  find out. Offers that were accepted count. A request the other side agreed to ("On it", "Will do", "Sure,
  sending tonight") is a promise by whoever agreed: list it once, as a promise.
- ask: one side asked the other for something concrete (a document, a decision, access, a review, an update
  on where things stand) and the other side has neither agreed nor said no. A follow-up asking where things
  stand ("any update on next steps?") is an ask while nobody has answered it.

owner is who has to act next: for a promise, whoever made it; for an ask, whoever was asked. 'me' is the
thread owner, 'them' the other person.

Skip: pleasantries and open-ended offers ("we should catch up sometime", "let me know if you need anything"),
questions that are just conversation, rhetorical questions, asks that were turned down, plans both sides simply
attend, reports of things already done, and anything promised by or asked of someone outside the thread. A
message chasing something already on the list ("any luck with that intro?") is not a new item.

For each item: a short imperative action that names the people or things involved, a due date only if stated or
clearly implied (resolve relative dates against the message timestamp), and whether a later message shows it was
done. A promise is done when a later message shows it was delivered; "(a call between us)" lines are calls
that happened, so a promised call is done by the next one. An ask is done when it was fulfilled or, if
it asked for information or an update, answered. Cite message ids from the [id] prefixes. Also give up to 4
recurring topics. Return an empty list when there is nothing.

You may also get <earlier_items>: what an earlier read of this thread found, each with a [P#] id, its status then,
and the message it came from (which may be older than the thread you now see). Return each earlier item that is
still a real item, with its [P#] id in previous, keeping its source message unless it was clearly wrong; update its
status if a message now shows it done, and change nothing else without a reason in the thread. Put an earlier item in
dropped only if, by the rules above, it was never a real item. Age is not a reason: an old promise nobody kept is
still owed. Items not in earlier_items are new: previous is null."""


def render_prior(prior: Sequence[dict]) -> str:
    """Earlier items as the model sees them: [P1].. in order, with the message each came from."""
    out = ["<earlier_items>"]
    for n, c in enumerate(prior, start=1):
        when = datetime.fromtimestamp(c["source_ts"]).strftime("%Y-%m-%d") if c.get("source_ts") else "?"
        status = f"done (by [{c['done_message_id']}])" if c["status"] == "done" and c.get("done_message_id") else c["status"]
        due = f" due={c['due']}" if c.get("due") else ""
        out.append(f"[P{n}] owner={c['owner']} {c.get('kind', 'promise')}: {c['action']}{due} | status: {status}"
                   f" | from message [{c['source_message_id']}] on {when}: {(c.get('source_text') or '')[:200]}")
    out.append("</earlier_items>")
    return "\n".join(out)


def _stdin(thread: Sequence, prior: Sequence[dict] | None) -> str:
    return (render_prior(prior) + "\n" if prior else "") + f"<thread>\n{render(thread)}\n</thread>"


def _today() -> str:
    return datetime.fromtimestamp(time.time()).strftime("%Y-%m-%d")


def _checked(result: Extraction, thread: Sequence, prior: Sequence[dict] | None = None) -> Extraction:
    """Never trust a citation the thread doesn't contain. An earlier item may keep a source that has
    aged out of the thread: it was checked when it was found."""
    valid = {m["id"] for m in thread}
    labels = {f"P{n}": c for n, c in enumerate(prior or [], start=1)}
    for c in result.commitments:
        if c.previous not in labels:
            c.previous = None
    result.commitments = [c for c in result.commitments if c.source_message_id in valid
                          or (c.previous and c.source_message_id == labels[c.previous]["source_message_id"])]
    result.dropped = [d for d in result.dropped if d.previous in labels]
    for c in result.commitments:
        kept = c.previous and c.done_message_id == labels[c.previous].get("done_message_id")
        if c.done_message_id not in valid and not kept:
            c.done_message_id = None
        if c.done_message_id is None and c.status == "done":
            c.status = "open"  # "done" must point at the message that shows it
    result.topics = result.topics[:4]
    return result


class ClaudeCodeExtractor:
    """One `claude -p` call per thread, with the output validated against Extraction's schema.

    The thread goes in on stdin, never argv, so its text doesn't show up in `ps`. The call runs
    with no tools, no MCP servers and no saved session, from an empty directory so no project
    instructions leak in.
    """

    remote = True  # sends thread text to Anthropic

    def __init__(self, model: str = "claude-opus-5-5", effort: str = "medium", binary: str = "claude",
                 timeout: float = 300):
        path = shutil.which(binary)
        if not path:
            raise RuntimeError("Claude Code CLI not found. Install it and log in (`claude`), or use --extractor heuristic.")
        self.cmd = [path]
        self.name = f"{model} (claude code)"
        self.model, self.effort, self.timeout = model, effort, timeout

    def extract(self, thread: Sequence, prior: Sequence[dict] | None = None) -> Extraction:
        result = self.ask(SYSTEM, f"Today is {_today()}. List the promises and asks in the thread on stdin.",
                          _stdin(thread, prior), Extraction)
        return _checked(result, thread, prior)

    def ask(self, system: str, prompt: str, stdin: str, schema: type[BaseModel]) -> BaseModel:
        """One structured call. The private text goes on stdin; the prompt in argv carries none."""
        args = self.cmd + [
            "-p", prompt,
            "--system-prompt", system,
            "--tools", "",
            "--strict-mcp-config",
            "--no-session-persistence",
            "--json-schema", json.dumps(schema.model_json_schema()),
            "--output-format", "json",
            "--model", self.model,
            "--effort", self.effort,
        ]
        with tempfile.TemporaryDirectory() as empty:
            proc = subprocess.run(args, input=stdin, capture_output=True,
                                  text=True, timeout=self.timeout, cwd=empty, env={**os.environ, "NO_COLOR": "1"})
        try:
            out = json.loads(proc.stdout)
        except json.JSONDecodeError:
            raise RuntimeError(f"claude -p failed (exit {proc.returncode}): {proc.stderr.strip()[:300]}") from None
        if out.get("is_error") or out.get("structured_output") is None:
            raise RuntimeError(f"no result: {out.get('subtype')} {out.get('stop_reason')} {str(out.get('result'))[:200]}")
        return schema.model_validate(out["structured_output"])


class ClaudeExtractor:
    """One structured-output call per thread. Needs credentials (ANTHROPIC_API_KEY or `ant auth login`)."""

    remote = True  # sends thread text to Anthropic

    def __init__(self, model: str = "claude-opus-5-5", effort: str = "medium"):
        import anthropic  # imported lazily so the offline path has no dependency on it

        self.client = anthropic.Anthropic()
        self.name = model
        self.effort = effort

    def extract(self, thread: Sequence, prior: Sequence[dict] | None = None) -> Extraction:
        result = self.ask(SYSTEM, f"Today is {_today()}.", _stdin(thread, prior), Extraction)
        return _checked(result, thread, prior)

    def ask(self, system: str, prompt: str, stdin: str, schema: type[BaseModel]) -> BaseModel:
        response = self.client.beta.messages.parse(
            model=self.name,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": f"{prompt}\n\n{stdin}"}],
            output_format=schema,
            output_config={"effort": self.effort},
            # On a safety decline, re-run on a fallback model chosen by refusal category.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if response.stop_reason == "refusal" or response.parsed_output is None:
            raise RuntimeError(f"no result (stop_reason={response.stop_reason}, request={response._request_id})")
        return response.parsed_output
