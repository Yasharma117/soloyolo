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
    owner: Literal["me", "them"] = Field(description="'me' if the user made the promise, 'them' if the other person did")
    action: str = Field(description="What was promised, as a short imperative, e.g. 'Intro Sam to Priya'")
    due: Optional[str] = Field(description="ISO date (YYYY-MM-DD) if a deadline was stated or clearly implied, else null")
    status: Literal["open", "done"]
    source_message_id: int = Field(description="id of the message where the promise was made")
    done_message_id: Optional[int] = Field(description="id of the message showing it was done, else null")


class Extraction(BaseModel):
    commitments: list[Commitment]
    topics: list[str] = Field(description="Up to 4 recurring subjects of this relationship, 1-3 words each")


def render(thread: Sequence) -> str:
    return "\n".join(
        f"[{m['id']}] {datetime.fromtimestamp(m['ts']).strftime('%Y-%m-%d %a %H:%M')} "
        f"{'me' if m['from_me'] else 'them'}: {m['text']}"
        for m in thread
    )


# --- heuristic -------------------------------------------------------------------------
_PROMISE = re.compile(
    r"\b(i'll|i will|i'm going to|im going to|let me|i can|will do|i'll make sure to)\s+"
    r"(?P<what>(?:send|intro|introduce|share|call|email|text|check|book|get back|follow up|forward|review|"
    r"look into|put together|connect|find|ping|drop|grab|bring|loop|pay)\b[^.!?\n]{0,80})",
    re.I,
)
_DONE = re.compile(r"\b(sent|done|here you go|here it is|just (?:intro'?d|introduced|sent|booked|emailed)|"
                   r"introduced you|booked|attached|forwarded)\b", re.I)
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

    def extract(self, thread: Sequence) -> Extraction:
        out: list[Commitment] = []
        for i, m in enumerate(thread):
            hit = _PROMISE.search(m["text"])
            if not hit:
                continue
            owner = "me" if m["from_me"] else "them"
            done = next((n for n in thread[i + 1:]
                         if bool(n["from_me"]) == bool(m["from_me"]) and _DONE.search(n["text"])), None)
            out.append(Commitment(
                owner=owner,
                action=_sentence(re.split(r",|;| - ", hit.group("what"))[0]),
                due=_due(m["text"], m["ts"]),
                status="done" if done else "open",
                source_message_id=m["id"],
                done_message_id=done["id"] if done else None,
            ))
        return Extraction(commitments=out, topics=[])


# --- Claude ----------------------------------------------------------------------------
SYSTEM = """You read one person's private 1:1 text thread with someone and list the commitments in it.

A commitment is a concrete thing one side said they would do: send, introduce, call, review, book, pay back,
find out. Include offers that were accepted. Skip pleasantries with no concrete action ("we should catch up
sometime", "let me know"), questions, and plans both sides simply attended.

For each one: who owes it ('me' is the thread owner, 'them' the other person), a short imperative action that
names the people or things involved, a due date only if stated or clearly implied (resolve relative dates against
the message timestamp), and whether a later message shows it was done. Cite message ids from the [id] prefixes.
Also give up to 4 recurring topics. Return an empty list when there are no commitments."""


def _today() -> str:
    return datetime.fromtimestamp(time.time()).strftime("%Y-%m-%d")


def _checked(result: Extraction, thread: Sequence) -> Extraction:
    """Never trust a citation the thread doesn't contain."""
    valid = {m["id"] for m in thread}
    result.commitments = [c for c in result.commitments if c.source_message_id in valid]
    for c in result.commitments:
        if c.done_message_id not in valid:
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

    def __init__(self, model: str = "claude-opus-5-5", effort: str = "medium", binary: str = "claude",
                 timeout: float = 300):
        path = shutil.which(binary)
        if not path:
            raise RuntimeError("Claude Code CLI not found. Install it and log in (`claude`), or use --extractor heuristic.")
        self.cmd = [path]
        self.name = f"{model} (claude code)"
        self.model, self.effort, self.timeout = model, effort, timeout
        self.schema = json.dumps(Extraction.model_json_schema())

    def extract(self, thread: Sequence) -> Extraction:
        prompt = f"Today is {_today()}. List the commitments in the thread on stdin."
        args = self.cmd + [
            "-p", prompt,
            "--system-prompt", SYSTEM,
            "--tools", "",
            "--strict-mcp-config",
            "--no-session-persistence",
            "--json-schema", self.schema,
            "--output-format", "json",
            "--model", self.model,
            "--effort", self.effort,
        ]
        with tempfile.TemporaryDirectory() as empty:
            proc = subprocess.run(args, input=f"<thread>\n{render(thread)}\n</thread>", capture_output=True,
                                  text=True, timeout=self.timeout, cwd=empty, env={**os.environ, "NO_COLOR": "1"})
        try:
            out = json.loads(proc.stdout)
        except json.JSONDecodeError:
            raise RuntimeError(f"claude -p failed (exit {proc.returncode}): {proc.stderr.strip()[:300]}") from None
        if out.get("is_error") or out.get("structured_output") is None:
            raise RuntimeError(f"no extraction: {out.get('subtype')} {out.get('stop_reason')} {str(out.get('result'))[:200]}")
        return _checked(Extraction.model_validate(out["structured_output"]), thread)


class ClaudeExtractor:
    """One structured-output call per thread. Needs credentials (ANTHROPIC_API_KEY or `ant auth login`)."""

    def __init__(self, model: str = "claude-opus-5-5", effort: str = "medium"):
        import anthropic  # imported lazily so the offline path has no dependency on it

        self.client = anthropic.Anthropic()
        self.name = model
        self.effort = effort

    def extract(self, thread: Sequence) -> Extraction:
        response = self.client.beta.messages.parse(
            model=self.name,
            max_tokens=16000,
            system=SYSTEM,
            messages=[{"role": "user", "content": f"Today is {_today()}.\n\n<thread>\n{render(thread)}\n</thread>"}],
            output_format=Extraction,
            output_config={"effort": self.effort},
            # On a safety decline, re-run on a fallback model chosen by refusal category.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if response.stop_reason == "refusal" or response.parsed_output is None:
            raise RuntimeError(f"no extraction (stop_reason={response.stop_reason}, request={response._request_id})")
        return _checked(response.parsed_output, thread)
