"""Several small models, each with one job, instead of one large model doing everything.

    triage    does this thread hold anything owed at all? A yes/no from the cheapest model. Most chats that
              change hold nothing, so this is what keeps the steady state cheap.
    reader    lists every candidate item. Tuned to miss nothing; it may list too much.
    checker   takes each candidate back to the thread and says whether it's a real item. A different model
              from the reader, so the two don't share blind spots. It can only remove, never add.

Each role is a model id on an OpenAI-compatible server (spike.extract.OpenModelExtractor): a local Ollama for
trying things out, a hosted endpoint for real use. Any role but the reader can be left out.

    python -m spike.eval --extractor council --model reader=qwen3.5:4b,checker=gemma4:e4b,triage=llama3.2:3b

It reads fresh each time (no earlier items yet), so it is for the eval, not the live store.
"""
from __future__ import annotations

import os
import time
from typing import Sequence

from pydantic import BaseModel, Field

from .extract import SYSTEM, Extraction, OpenModelExtractor, _checked, _stdin, _today, render

TRIAGE = """You read one person's private 1:1 text thread with someone and decide one thing: is there anything in
it that one side owes the other?

Something is owed when one side said they would do something concrete (send, introduce, call, review, book, pay,
find out), or accepted a request, or asked the other for something concrete that hasn't been answered or turned down.
Nothing is owed by pleasantries, vague offers ("we should catch up sometime"), jokes, plans both sides simply attend,
reports of things already done, or requests that were declined.

When unsure, say yes: a wrong yes costs one more read, a wrong no loses a promise."""

CHECK = """You check a list of items another reader found in one person's private 1:1 text thread. Each candidate
says who owes what, and cites the message it came from. For each one, decide whether it is a real item.

A real item is one of:
- promise: someone said they would do something concrete, or agreed to a request.
- ask: someone asked the other for something concrete, and the other has neither agreed nor said no.

Not real: a joke or banter, a hope or a maybe ("might come", "will see"), a pleasantry or open-ended offer, a
plan that was later cancelled or withdrawn, a request that was turned down, something the person does for
themselves that nobody is waiting on (reading an article, deciding whether to go), a report of something already
done with nothing left to do, and a second candidate for the same thing as another candidate (keep the one citing
the message where it was promised or accepted; mark the other not real).

Judge only from the thread. Give a verdict for every candidate, by its number."""


class Any(BaseModel):
    owed: bool = Field(description="true if anything in the thread is owed by either side")


class Verdict(BaseModel):
    n: int = Field(description="the candidate's number")
    real: bool
    reason: str = Field(description="why, under 12 words")


class Verdicts(BaseModel):
    verdicts: list[Verdict]


class Council:
    remote = True

    def __init__(self, model: str | None = None):
        spec = model or os.environ.get("SOLOYOLO_COUNCIL") or ""
        roles = dict(part.split("=", 1) for part in spec.split(",") if "=" in part)
        if "reader" not in roles or set(roles) - {"reader", "checker", "triage"}:
            raise RuntimeError("Name the council: reader=<model>[,checker=<model>][,triage=<model>]")
        self.models = {role: OpenModelExtractor(m) for role, m in roles.items()}
        self.name = "council: " + ", ".join(f"{r} {roles[r]}" for r in ("triage", "reader", "checker") if r in roles)
        self.stats = {r: {"calls": 0, "seconds": 0.0} for r in roles}
        self.stats.update(skipped=0, removed=0)

    def _ask(self, role: str, system: str, prompt: str, stdin: str, schema: type[BaseModel]) -> BaseModel:
        t = time.time()
        try:
            return self.models[role].ask(system, prompt, stdin, schema)
        finally:
            self.stats[role]["calls"] += 1
            self.stats[role]["seconds"] += time.time() - t

    def extract(self, thread: Sequence) -> Extraction:
        text = _stdin(thread, None)
        if "triage" in self.models and not self._ask("triage", TRIAGE, "Is anything owed in this thread?", text, Any).owed:
            self.stats["skipped"] += 1
            return Extraction(commitments=[], topics=[])
        found = _checked(self._ask("reader", SYSTEM, f"Today is {_today()}. List the promises and asks in the thread.",
                                   text, Extraction), thread)
        if "checker" in self.models and found.commitments:
            lines = [f"{n}. {'I owe' if c.owner == 'me' else 'they owe'} ({c.kind}): {c.action}, from message [{c.source_message_id}]"
                     for n, c in enumerate(found.commitments, start=1)]
            out = self._ask("checker", CHECK, "Check each candidate against the thread.",
                            f"<thread>\n{render(thread)}\n</thread>\n<candidates>\n" + "\n".join(lines) + "\n</candidates>", Verdicts)
            fake = {v.n for v in out.verdicts if not v.real}  # a candidate with no verdict stays: the checker only removes
            self.stats["removed"] += len(fake)
            found.commitments = [c for n, c in enumerate(found.commitments, start=1) if n not in fake]
        return found
