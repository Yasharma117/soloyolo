# Content spike

**The question:** does reading what you said beat counting how often you said it? Mesh knows you texted Sam
40 times. This spike tries to find that you *promised Sam an intro nine days ago and haven't sent it*.

It lists two kinds of item per person. **Promises**: something one side said they'd do. **Asks**: a concrete
request the other side hasn't said yes or no to. Each is owned by whoever has to act next, which gives two lists:
**You owe** (your promises, requests to you) and **Waiting on them** (their promises, your unanswered requests).

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

It reads iPhone and Android layouts, any date order and 12/24-hour clocks, and skips group chats. System
notices and stickers are dropped. Photos, videos, documents, voice notes and logged calls are kept as markers,
because "send me the pic" is done by the photo and "I'll call you back" by the call. With 2+ chats it works out which sender is you; with one, add
`--me "Your Name"`. Re-importing a newer export of the same chat only adds new messages.

From LinkedIn (no API, no login: its own data export). On the desktop site, **Me → Settings & Privacy → Data
privacy → Get a copy of your data → Download larger data archive**; the emailed zip arrives within a day:

```bash
python -m spike import-linkedin ~/Downloads/Complete_LinkedInDataExport_*.zip
```

1:1 threads become messages, group threads evidence, and connections people with company, position and email.
Format notes and what's unverified: `docs/LINKEDIN.md`.

To stay in sync without re-exporting, use the Chrome extension in `extension/` (setup in `extension/README.md`). It
reads new LinkedIn messages through your logged-in browser while Chrome is open and posts them to `serve`. The
export and the extension store a message both have seen once.

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

Every open item has **Done**, **Snooze 3d** and **Not real**. Your marks are kept across re-extraction, and no
signal overrides them. That matters because some things only you know, like a call where it got sorted.

From Instagram and X, read each network's own data export rather than logging in. Instagram's cookie clients
are the likeliest to get an account banned, and X's DM API needs a paid tier. Request the export: Instagram's
**Accounts Center → Download your information** (Messages, JSON), or X's **Settings → Your account → Download
an archive of your data**. Then run `python -m spike import-instagram ~/Downloads/instagram-*.zip` or
`python -m spike import-x ~/Downloads/twitter-*.zip`. 1:1 threads become messages and groups become evidence.
Steps, format notes and what's unverified: `docs/INSTAGRAM-X.md`.

### Live WhatsApp (no exports)

`connectord` links to WhatsApp as a companion device, like WhatsApp Web, and writes into a store the spike
reads directly:

```bash
(cd connectord && go build -o connectord ./cmd/connectord)
```

```bash
./connectord/connectord link --phone 919800000000   # prints an 8-character code
```

On the phone: **WhatsApp → Linked devices → Link a device → Link with phone number instead**, then type the
code. The phone sends about 90 days of history, and new messages follow as they arrive. Group chats are kept
as evidence only, and calls and photos as markers, the same as the export importer. Leave it running, or run
`./connectord/connectord sync` later.

```bash
python -m spike --db ~/.soloyolo/soloyolo.db watch --extractor claude-code
```

Every 10 minutes this reads only the chats that changed, at most 30 per pass and none shorter than 4 messages.
It prints new items, and `serve` shows them. To stop, remove the device on the phone (**Linked devices** → the
device → **Log out**) and delete `~/.soloyolo`.

**Risk:** this uses an unofficial client (whatsmeow). Reading as a linked device is ordinary personal use, but
WhatsApp's terms don't cover third-party clients, so an account ban is possible. It's unlikely at this volume,
since soloyolo never sends anything. The device keys in `~/.soloyolo/accounts` can read your WhatsApp, so treat
that folder like your phone.

To keep it running on your Mac (sync always on, a pass every 30 minutes, a morning digest), see
`docs/RUNNING-DAILY.md` and `scripts/install-mac.sh`. `python -m spike digest` prints the morning message.

### Today: one to three things, then silence

```bash
python -m spike today        # or open `serve`: "Today" is the first screen
```

Run 6 showed that an item left open in a chat is usually done, not forgotten: of 15 scored, one was still to
do. So Today assumes silence means done. An item is shown for 3 days after it's said, or around its due date
(2 days before to 1 day after), and comes back only when the other side chases ("any update?", "kya hua",
"photos bhej do", the same ask again). Your marks still win. The rules and why are at the top of `nudge.py`.

`python -m spike.replay --db soloyolo.db --tz Asia/Kolkata --out <private path>` shows what Today would have
said each morning for the last 6 weeks, using only what was known then. It writes message text, so keep it
out of the repo. On the live store: 2.5 items a morning out of ~43 open, and 14 of the 15 scored items were
shown for 1 to 3 days after they appeared, then went quiet without any mark. The one still to do is the only
one Today shows now with the marks taken away.

### Everything open, ranked

```bash
python -m spike top          # in the viewer: "All open, ranked", one tap from Today
```

Every open item across every chat goes into one list, best first, and each item shows why it ranks where it
does: *overdue 3d · money · they wrote last*. Ranking is local and adds up visible points: your move over
theirs, due soon or just overdue, 3 to 21 days old (the ones that slip), money, an unanswered last message, and
how close you are. Six weeks overdue counts for little, a "maybe settled" item sinks, and each item ranks a
little lower for every item above it from the same chat. The weights and their reasons are at the top of
`priority.py`. On the live store, 57 open items fit on one screen with the urgent ones on top.

### A list that holds still

A model reading the same chat twice gives two slightly different lists. When a chat changes and is read again,
the earlier items go with it as `[P1]`, `[P2]`.... The model returns each one it still holds, and names any
that were never real, with a reason. An item it forgets is carried over unchanged, because forgetting is not a
reason. Your marks always stand and follow the item if it's re-cited from a different message.
On six live chats read twice from the same input, the open list went from 76% the same to 97% the same
(`eval/RESULTS.md`, run 5).

### Closing what the chats don't show

In the first real test, 6 of 19 items were already done somewhere a chat can't show: a UPI app, a call, a group
chat. Two kinds of evidence close or flag those.

**Bank SMS (Android, local, closes):** install *SMS Backup & Restore*, back up messages to an XML file, then:

```bash
python -m spike import-sms ~/Downloads/sms-*.xml
```

Only bank payment alerts are kept. OTPs, offers, reminders and personal texts are dropped while reading and
never stored. An open money item closes when a payment arrives after it, in the right direction, for its
amount ("send ₹950", or "2.7k meds + 700 cab" = 3,400). The viewer says which alert closed it, with a **Not done**
button.

**Group chats (Claude, suggests):** export them with the 1:1s; `import-whatsapp` keeps groups as evidence only.

```bash
python -m spike close --extractor claude-code
```

This marks items a later group message seems to settle as **Maybe settled?** with the message beside it, and
you decide. It never closes anything itself. Tested on the real scored items, reading other 1:1 chats "settled"
3 items, and all 3 were still open. So 1:1 chats are opt-in (`--other-chats`) and nothing closes on a guess.

Tests (offline, never call Claude):

```bash
python -m unittest spike.test_spike
```

Accuracy on 25 labeled threads (`eval/`):

```bash
python -m spike.eval --extractor claude-code
```

Last run (30 cases, promises and asks): Claude scored F1 0.95–1.00 over three runs; the regexes scored 0.83.
Details, the Gmail before/after and the caveats are in `eval/RESULTS.md`.

## Privacy, stated plainly

- `ingest` reads `chat.db` read-only and copies 1:1 thread text into `soloyolo.db` in the current folder.
  That file is your message history: it's git-ignored, and you should treat it like `chat.db`.
- `extract --extractor claude-code` (or `api`) **sends each thread's text to Anthropic.** That breaks the local-first promise,
  which is why it needs a flag. Each send is logged *before* it happens (the `disclosure` table, never cleared), and the
  viewer's footer reads that log. It's fine for testing whether the idea works on
  your own data. A shipping product needs on-device extraction, or explicit per-person consent.
- The viewer binds to `127.0.0.1` only and never logs message text.

## How to judge the result (the actual experiment)

Run `ingest --days 90`, then `extract --extractor claude-code`, then go through the "You owe" and "Waiting on them"
lists and score each open item:

| Score | Meaning |
|---|---|
| ✅ useful | Something you'd forgotten or were about to drop: a promise, a request to you, or someone to chase |
| ➖ true but known | Real, but already on your mind |
| ❌ wrong | Not owed by anyone, wrong person, or already done |

**Kill or continue** (first real run passed: 13 ✅ / 6 ❌, see `eval/RESULTS.md`): continue if the last 90 days surface **at least 5 ✅** and **❌ stays under a third** of
items. Below that, the thesis is weak: ranking by message counts (what Mesh does) would be nearly as good.

## Known limits (deliberate, for a spike)

- **1:1 threads only.** Group chats need per-speaker attribution and a different prompt.
- **iMessage, and WhatsApp exports only.** The spike reads `chat.db` and WhatsApp "Export chat" files; live
  WhatsApp sync goes through `connectord` (the Go daemon), which writes to the same model.
- **No contact names** from Apple Contacts yet; people show as phone numbers or emails outside the demo.
- **Reads the last 60 days per person, at most 1000 messages.** Older promises are out of scope, except items
  already found, which are carried until they're done or dropped with a reason.
- **Each thread is read alone for new items.** Family logistics often close in a group chat; `close` can
  suggest those, but only you can close them.
- **Marks follow the message an item came from, and one message can hold two items.** A re-read that cites a
  new message for the same item takes your mark with it, but two items from one message share one mark.
- **Asks are judged on text alone.** A reply in another app, or on a call, won't close one.
- **Ranking weights are a first guess**, set by eye on one person's data. They're written down to be argued
  with, not tuned.
