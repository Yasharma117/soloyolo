# soloyolo

A local-first personal CRM that reads what you actually said in your messages, reminds you of the promises
you made, and lets you follow through. Beeper has the messages but doesn't understand the people behind them;
Mesh understands the people but can't see what you said or send anything. soloyolo aims to do both, on your machine.

| Path | What it is | State |
|---|---|---|
| `REPORT.md` | Teardown of how Beeper and Mesh work | Research |
| `BUILD-WITHOUT-BEEPER.md` | The plan: own the data model, use protocol libraries directly | Current plan |
| `spike/` | **Start here.** Tests the thesis: extract promises and asks from your message threads, view them locally | Runs; tested offline |
| `connectord/` | Go daemon: iMessage and WhatsApp adapters → one SQLite store, JSON-RPC over stdio | Builds; unit-tested; not run on a Mac |
| `site/` | Landing hero, an animated demo built with the Stageshow skill | Builds; filmed and gated |
| `mini_mesh.py` | Mesh-style ranking from message counts alone (the baseline to beat) | Runs |
| `refs/` | Reference repos (submodules). Mesh's proprietary files are local-only, see `refs/README.md` | Reference |

`spike/` and `connectord/` share one schema: `connectord/internal/store/core.sql`.

## Quick start

From the repository root:

```bash
pip install -r spike/requirements.txt && python -m spike demo
```

```bash
(cd connectord && go test ./...)
```

```bash
(cd site && npm install && npm run dev)
```

## The next decision

Run the spike on your own last 90 days of messages (`spike/README.md`, "How to judge the result"). If it finds
real promises you'd forgotten, wire `connectord` to the spike's viewer. If it doesn't, the thesis needs rethinking
before more plumbing gets built.
