# Extraction eval: results

## Run 2 (2026-11-02): promises and asks

Every item now has a kind. A **promise** is something one side said they'd do. An **ask** is a concrete request
the other side hasn't said yes or no to, owned by whoever was asked. Together they fill two lists: **You owe**
(your promises, plus requests to you) and **Waiting on them** (their promises, plus your unanswered requests).

What changed in the set: 5 new cases (an upload-documents request, an unanswered status chase, an ask fulfilled
on the spot, a declined ask, a rhetorical question). `unanswered-request` now expects an ask instead of nothing.
On 7 accepted-request cases the request message now counts as a fair citation, alongside the reply that
accepted it. That's 30 cases with 20 items.

| Extractor | Precision | Recall | F1 | Open/done right | Kind right |
|---|---|---|---|---|---|
| `heuristic` | 0.94 | 0.75 | 0.83 | 12/15 | 15/15 |
| `claude-code`, run 1 | 1.00 | 1.00 | 1.00 | 20/20 | 20/20 |
| `claude-code`, run 2 | 0.95 | 0.95 | 0.95 | 19/19 | 19/19 |
| `claude-code`, run 3 | 0.95 | 0.95 | 0.95 | 19/19 | 18/19 |

- **Claude's misses are the same two in every run that missed.** It dropped "I'll ask Meera" after a cancelled
  promise, and it listed "reading it tonight" as owed. Run 3 called an ask fulfilled on the spot ("Done, added
  you") a promise.
- **The heuristic's jump from 0.44 to 0.75 recall is mostly not new intelligence.** The ask rule catches
  "please book… / Will do" pairs it used to miss, and the widened citations help it. It still misses
  "ill drop it tmrw", "I'll UPI you" and every promise with no request in front of it.
- **These numbers are more optimistic than run 1's.** The ask cases were written after the Gmail run showed the
  gap, and the prompt was written alongside them. Nothing here was held out.

### Gmail, 90 days, 8 people, 36 messages (not in the repo)

| | Before asks | With asks |
|---|---|---|
| Items found | 7 | 14 |
| Wrong (my reading of each thread) | 0 | 0 (one weak "done" citation) |
| Open: you owe | 0 | 1: upload verification documents (Rentomojo) |
| Open: waiting on them | 2: Cashfree, Volopay | 3: Cashfree, Volopay, Birdeye (cold outreach, no reply) |

Asks closed both gaps the first run showed: the document request that was misread as a promise *to* you, and
the unanswered outreach that was dropped entirely. The 7 extra items are done ones (a recruiter's request you
answered, an offer letter you signed). They're correct but they're history, so the viewer strikes them through.

**What it still doesn't prove:** none of the 4 open items is something you'd forgotten. A job-search inbox is
all waiting; the forgotten promises, if they exist, are in WhatsApp. The kill-or-continue test in
`spike/README.md` still needs your real chats.

## Run 1 (2026-11-02): promises only

25 hand-labeled 1:1 threads (`cases.py`) with 16 commitments, including hard cases: Hinglish ("lemme check and
revert"), typos ("ill drop it tmrw"), one-word acceptances ("On it 👍", "Will do"), done shown only by the other
side's thanks, a withdrawn promise, jokes, hopes, plans both sides attend, past-tense reports, and promises by
someone outside the thread.

| Extractor | Precision | Recall | F1 | Open/done right | Cost | Time |
|---|---|---|---|---|---|---|
| `heuristic` (regexes, offline) | 0.88 | 0.44 | 0.58 | 6/7 | free | instant |
| `claude-code` (Opus 5.5 via `claude -p`), run 1 | 0.94 | 1.00 | 0.97 | 16/16 | ~$0.02/thread | ~32s for 25, 5 at a time |
| `claude-code`, run 2 | 0.94 | 1.00 | 0.97 | 16/16 | | |
| `claude-code`, run 3 | 0.89 | 1.00 | 0.94 | 16/16 | | |

Reproduce (either run; the cases file is run 2's):

```bash
python -m spike.eval
```

```bash
python -m spike.eval --extractor claude-code
```

## What it means

- **The regexes are not a viable product.** They miss over half of real phrasing: "On it", "Will do",
  "ill drop it", "lemme… revert", "I'll UPI you". They're a floor and an offline fallback, nothing more.
- **Claude found every commitment in every run** and got open-vs-done right each time, including "done" shown
  only by the other person's "Got it, thanks!".
- **Its errors are over-inclusion, and they're consistent.** Every run listed "reading it tonight" (a courtesy,
  labeled not a commitment here) as something you owe; one run turned a joke ("ordering you a drink as penance")
  into a commitment. In a "You owe" list, these are noise, not harm.
- **The prompt was not tuned on these cases.** Fixing the courtesy-read error would be easy, but it would make
  these numbers optimistic. Tune against a separate set.

## Why not to trust this yet

- **Same-family labels.** The cases and labels were written by the same model family that does the extraction.
  The threads are cleaner than real life: short, 1:1, with no forwarded links, voice notes or month-long gaps.
- **Small.** 16 positives means each miss moves recall by 6 points.
- **The real test is still your data.** `spike/README.md` has the protocol: 90 days of your own threads, scored
  ✅ / ➖ / ❌ by you. Only that answers whether this finds promises you'd actually forgotten.

## Privacy note

`claude-code` sends each thread's text to Anthropic through your Claude Code login, the same as the API path.
It's fine for testing on your own data; a shipped product needs on-device extraction or per-person consent.
