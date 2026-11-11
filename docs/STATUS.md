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
| 5 | Cloud plan: where the model pair runs, and the multi-user server | subagent | started |
| 6 | App screens for the new sources (pairing the extension, per-network state) | main session | after 3 |

## Done

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

## Needs you

(Filled in as things come up that only you can do: logins, keys, decisions.)
