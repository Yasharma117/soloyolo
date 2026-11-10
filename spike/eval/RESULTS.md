# Extraction eval: results

## Run 7 (2026-11-10): an open model, so nobody needs a Claude plan

The same 30 cases and 20 items as run 2's table below, read by an open model through OpenRouter's free tier
(`--extractor open-model`, new: any OpenAI-compatible server). The prompt is the one written for Claude, unchanged.

| Extractor | Precision | Recall | F1 | Open/done right | Kind right | Errors |
|---|---|---|---|---|---|---|
| `heuristic` | 0.94 | 0.75 | 0.83 | 12/15 | 15/15 | 0 |
| `nvidia/nemotron-3-ultra-550b-a55b:free` | 0.69 | 1.00 | 0.82 | 19/20 | 17/20 | 0 |
| `claude-code` (earlier runs) | 0.95 to 1.00 | 0.95 to 1.00 | 0.95 to 1.00 | all | 18/19 to 20/20 | 0 |

- **It found every item and invented nine.** Five are the cases built to tempt: a joke ("grab a table", "order a
  drink"), a cancelled plan, a hope ("decide whether to attend"), and "reading it tonight". Four are a second item
  beside a promise it had already listed. Claude lists one of the nine ("reading it tonight") in its worse runs.
- **Every reply parsed.** The schema goes in the prompt and the reply is validated here; no case needed the retry.
- **One model, one run.** The free tier allows 50 requests a day, and the Gemma 4 free endpoints were rate-limited
  both times they were tried, so the model the research favoured for Hinglish is not scored yet. 7 minutes for 30 cases, two at
  a time, mostly waiting on the free queue.
- **Not for real chats.** OpenRouter's free endpoints may keep and train on what they're sent. This set is made up.
  Real chats need a paid endpoint with no retention.

## Run 6 (2026-11-08): the ranked list, scored by the user. Right items, wrong moment

The top 15 of "Do first" on the live store, scored by the user against today's reality. The question this
time was not "was it a real item?" but "is it still something to do?"

| What the user said | Items | Age when shown |
|---|---|---|
| Real and still to do (due today; done that day) | 1 | 1 day |
| Real, done since, off-chat (UPI, in person, never mentioned in chat) | 9 | 2–39 days |
| Real, no longer needed (recovered, plan dropped, place not needed) | 3 | 14–39 days |
| Real, ignored on purpose, or settled in another chat | 2 | 7–12 days |
| Not relevant | 1 | 36 days |
| **Misread: not a real item** | **0** | |

(The user split the one item counted twice above, "was needed, now moot", across both rows. 15 in all.)

**What it means.** Extraction is fine: no item was a misreading. Assuming an item stays open until a chat
says it's done is wrong. Most real promises finish where the chat can't see: a UPI app, a visit, a call. Nobody
writes "done" back, and the user said so plainly: "it was not necessary to update the chat". Even the
2-to-9-day-old items were mostly done. The one useful item was 1 day old. So the useful window is days, not
weeks, and a backlog of open items (57, 42 after these marks, 36 of them over two weeks old) is mostly a
record of things already finished.

## Run 5 (2026-11-08): does the list hold still?

On the live store (the user's own WhatsApp, linked), with the six chats that had the most items. Each was read
twice from the same input the old way (fresh each time), and twice the new way (the second read sees the first
read's items as `[P1]`... and must give a reason to drop one). Items are matched by source message and owner,
then by wording.

| | All items the same | Open items the same (what you see) | Open-vs-done flips |
|---|---|---|---|
| Old: two fresh reads | 84 / 99 (85%) | 25 / 33 (**76%**) | 2 |
| New: re-read with earlier items | 109 / 109 (100%) | 33 / 34 (**97%**) | 1 |

In the new reads, the model kept every earlier item it was shown, dropped one with a stated reason (a "Yes" that
only acknowledged feedback), and forgot none: the carry-over safety net was never needed. Against the store's
earlier read, made before the newest messages arrived, the new way kept 94% of the open list and a fresh read 68%.

What it doesn't fix: a wrong item that got in stays in until you tap **Not real**. Stability makes the list
trustworthy as a list. It doesn't make each item right. The 6 ❌ from run 3 still need your taps.

## Run 4 (2026-11-04): closing what chats don't show

Built from run 3's six ❌, then checked against the same 19 items the user scored. The scores are kept
privately, outside the repo.

| Fix | For the ❌ caused by | Result on the real scored items |
|---|---|---|
| One tap: Done / Snooze / Not real | calls (2) | Any item, one tap. Survives re-extraction |
| Bank SMS matcher (local, closes) | UPI payments (3) | With alerts shaped like the 3 payments, it closes exactly those 3, including "2.7k + 700" as 3,400. Decoys stay: wrong amount, wrong direction, a payment before the item. **None of the 13 real items close.** |
| Closure pass over group chats (Claude, suggests) | family group chat (1) | With a synthetic family group, it suggests only that item. Decoys mention Myntra, Ena bhua and Diwali; none of the 13 real items is suggested |
| Same pass over *other 1:1 chats* | (cross-chat) | **0 of 3 right.** It "settled" items 2, 13 and 17 in both runs; the user had scored all three as still open |

**The last row changed the design.** In other 1:1 chats, evidence like "Yesss" to Dad about a birthday wish
looks conclusive to a model, and to me: my own guesses at cross-chat closures were also mostly wrong. So the
pass only suggests, each item is asked once, your answer is final, and other 1:1 chats are opt-in.

**Still unproven on real data:** bank SMS and group chats were synthetic here, shaped on the real items. The
next real test needs an SMS backup and the family group export.


## Run 3 (2026-11-03): the kill-or-continue test on real WhatsApp chats

The protocol in `spike/README.md`: the user's own threads, every open item scored by the user. Counts and
categories only; no chat text is in this repo.

**Input:** 5 Android 1:1 chats (family and friends, Hinglish), 973 messages, Aug to Nov 3. Two more chats
had no text and were skipped. Extracted with `claude-code`, then 19 open items were scored.

| Score | Items | Share |
|---|---|---|
| ✅ real, and forgotten, drifting or avoided | 13 ("almost all", in the user's words) | 68% |
| ❌ wrong: already done | 6 | 32% |

**Verdict: continue.** The bar was at least 5 ✅ with ❌ under a third. ✅ passes easily; ❌ passes narrowly.

**Every ❌ was done somewhere the extractor can't see. None was a misreading:**

| Where it was done | ❌ |
|---|---|
| Paid in a UPI app | 3 |
| Settled on a phone call | 2 |
| Settled in a family group chat (groups are skipped) | 1 |

**What the run changed before scoring:** the importer dropped call-log lines and media placeholders, so
"I'll call you back" and "send me the pic" stayed open after the call or photo. Keeping both as markers
closed 8 items that would otherwise have been ❌.

**What it means**

- **Precision is now limited by what the data covers, not by the model.** A better prompt won't fix the six ❌.
  Payment signals (bank SMS on Android), group chats read only to close items, and a one-tap "done"
  for calls would.
- **The value is in what people avoid, not only what they forget.** The user said several ✅ were things
  they'd been avoiding, mostly asks from family. Showing those needs care: a list that nags gets ignored.
- **My guesses at "probably closed in another thread" were mostly wrong:** 1 of 4. The user is the only
  judge of what's open.

**Why not to over-read it:** one user, 19 items, family-heavy chats, and the builder ran the test. It's
a go signal for the next build, not proof of demand.


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
