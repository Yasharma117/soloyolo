# Status: overnight run, 11 November 2026

Kept current as work lands, so this is true even if the session stopped part-way. Newest first under each heading.
Nothing here is in a pull request: everything is committed and pushed to `claude/gifted-fermi-3xfkyc`.

## To do

| # | Workstream | Who | State |
|---|---|---|---|
| 1 | Model pair: small Gemma 4 reads, mid-size Gemma 4 (thinking off) checks | main session | scored (F1 0.95); next: run it on the live store |
| 2 | Score the remaining models (mid-size Qwen 3.5) | main session | done: not a fit |
| 3 | Browser extension, Kondo-style: one extension for LinkedIn, Instagram and X messages | subagent | started |
| 4 | Telegram personal chats in connectord | subagent | started |
| 5 | Cloud plan: where the model pair runs, and the multi-user server | subagent | done: `docs/CLOUD.md` |
| 6 | App screens for the new sources (pairing the extension, per-network state) | main session | after 3 |

## Done

- **Cloud plan written: `docs/CLOUD.md`.** The exact pair is not on any hosted API: hosts serve Gemma 4 only at
  26B A4B and 31B. Recommended: DeepInfra for those two (no retention, about $45 to $70 a month at the plan's
  volume, which assumes 60 chats an hour all day), one small VM with a folder per tester, Oracle free or $12 a
  month at DigitalOcean Bangalore. Fallback: the exact pair on Modal's serverless GPU. Its step 0 is scoring the
  two hosted sizes.
- **The pair works.** Small Gemma 4 reading and mid-size Gemma 4 (thinking off) checking finds every item on the
  eval and lists two false ones: F1 0.95, Claude's score in its worse runs. Caveat: tuned on the same set.
  `spike/eval/RESULTS.md`, run 9. Mid-size Qwen 3.5 was scored too and is not a fit for either job.
- At 06:40 the subagents stopped again on the Fable model limit. The session moved to Opus 5.5 and they were
  restarted from what each had left in the working tree.
- The session hit its usage limit at about 01:30 and resumed at 06:20. The three subagents stopped mid-work and
  were resumed from where they were; local model scoring kept running in between.
- The pair as first scored: lists nothing false, finds 70% of real items. The checker was removing kept promises.
  Its instructions are fixed and the pair is being re-scored. Full table: `spike/eval/RESULTS.md`, run 8.
- The council can now re-read a chat with its earlier items, which the live store needs (tests in `spike/test_open_model.py`).

- Council of models (`spike/council.py`) and the thinking setting, with every score so far in `spike/eval/RESULTS.md`.

## Try the pair yourself

With Ollama running (`brew install ollama`, then `ollama pull gemma4:e4b gemma4:12b`):

```bash
export SOLOYOLO_LLM_URL=http://localhost:11434/v1 SOLOYOLO_COUNCIL=reader=gemma4:e4b,checker=gemma4:12b@none
.venv/bin/python -m spike.eval --extractor council --jobs 1                         # the 30 made-up chats, ~10 min
.venv/bin/python -m spike --db ~/.soloyolo/soloyolo.db watch --once --extractor council --top 15   # your store
```

For real chats start Ollama with `OLLAMA_CONTEXT_LENGTH=16384`: by default it reads only the first 4,096 tokens
of a prompt, which cuts off a long chat. The app's "Find your promises" card and the launchd jobs don't offer the
council yet.

## Needs you

- **The `/usage` changes.** Three proposals are waiting for your yes (subagent model, unused skills off, a cheaper
  design skill). Nothing in your settings has been changed.
- **Scoring the hosted Gemma sizes.** OpenRouter's free Gemma 4 26B and 31B endpoints answered "rate-limited
  upstream" every time they were tried (10 November evening, 11 November morning). Either try again later, or put
  a few dollars on DeepInfra and the score takes ten minutes for under a cent.
- **Decisions in `docs/CLOUD.md`** ("Decisions that are the owner's"), above all whether to hold testers'
  WhatsApp keys on a server at all.
