# Extraction eval: results (2026-11-02)

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

Reproduce:

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
