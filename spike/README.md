# Content spike

**The question:** does reading what you said beat counting how often you said it? Mesh knows you texted Sam
40 times. This spike tries to find that you *promised Sam an intro nine days ago and haven't sent it*.

If that works on real threads, it's soloyolo's wedge. If it doesn't, the Go daemon is plumbing for a product
nobody needs. So this comes first.

```
chat.db (read-only) ──► store (SQLite: person, handle, message, commitment, topic) ──► viewer (127.0.0.1)
                                         ▲
                       extractor: heuristic (offline) │ Claude (opt-in, no API key needed)
```

## Run it

```bash
pip install -r spike/requirements.txt
```

Demo on synthetic data (works anywhere):

```bash
python -m spike demo
```

From WhatsApp exports (any phone; you pick the chats). On the phone, open a 1:1 chat → the contact's
name (iPhone) or ⋮ → More (Android) → **Export chat** → **Without media**. Do this for 5–10 people you talk
to often, then:

```bash
python -m spike import-whatsapp ~/Downloads/WhatsApp*.zip --tz Asia/Kolkata
```

It reads iPhone and Android layouts, any date order and 12/24-hour clocks, drops media placeholders and
system notices, and skips group chats. With 2+ chats it works out which sender is you; with one, add
`--me "Your Name"`. Re-importing a newer export of the same chat only adds new messages.

Or from your own Messages history (macOS; give your terminal Full Disk Access first):

```bash
python -m spike ingest --days 90
```

```bash
python -m spike extract --extractor claude-code --top 25   # your 25 most active people first
```

No API key needed: `claude-code` runs `claude -p`, so it uses the Claude account you're logged into Claude Code
with. If you do have a key, `--extractor api` uses it directly. The default, `heuristic`, is offline regexes that
miss over half of real phrasing (`eval/RESULTS.md`).

```bash
python -m spike serve              # http://127.0.0.1:8765
```

Tests (offline, never call Claude):

```bash
python -m unittest spike.test_spike
```

Accuracy on 25 labeled threads (`eval/`):

```bash
python -m spike.eval --extractor claude-code
```

Last run: Claude found 16/16 commitments at 0.89–0.94 precision; the regexes found 7/16. Details and caveats
in `eval/RESULTS.md`.

## Privacy, stated plainly

- `ingest` reads `chat.db` read-only and copies 1:1 thread text into `soloyolo.db` in the current folder.
  That file is your message history: it's git-ignored, and you should treat it like `chat.db`.
- `extract --extractor claude-code` (or `api`) **sends each thread's text to Anthropic.** That breaks the local-first promise,
  which is why it needs a flag and the viewer's footer says so. It's fine for testing whether the idea works on
  your own data. A shipping product needs on-device extraction, or explicit per-person consent.
- The viewer binds to `127.0.0.1` only and never logs message text.

## How to judge the result (the actual experiment)

Run `ingest --days 90`, then `extract --extractor claude-code`, then go through the "You owe" lists and score each item:

| Score | Meaning |
|---|---|
| ✅ useful | A real promise you'd forgotten or were about to drop |
| ➖ true but known | A real promise you already had in mind |
| ❌ wrong | Not a promise, wrong person, or already done |

**Kill or continue:** continue if the last 90 days surface **at least 5 ✅** and **❌ stays under a third** of
items. Below that, the thesis is weak: ranking by message counts (what Mesh does) would be nearly as good.

## Known limits (deliberate, for a spike)

- **1:1 threads only.** Group chats need per-speaker attribution and a different prompt.
- **iMessage/SMS only.** WhatsApp arrives through `connectord` (the Go daemon), which writes to the same model.
- **No contact names** from Apple Contacts yet; people show as phone numbers or emails outside the demo.
- **Reads the last 300 messages per person.** Older promises are out of scope.
- **Re-extraction replaces the person's commitments**, so manual edits wouldn't survive it. There are no manual edits yet.
