# Running soloyolo daily on your Mac

Goal: WhatsApp keeps syncing, chats get read as they change, and every morning you get the 1–3 things
you said you'd do that matter today, with one tap to answer each. Today everything runs in a throwaway
container and stops when it does. This page covers moving it to your Mac (you're in India, on Android).

## Decision in one paragraph

Three **launchd user agents** (no root, no app bundle): `connectord sync` always on, an extraction pass
every 30 minutes, and the digest at 07:30. Data stays in `~/.soloyolo`. Extraction uses your **Claude Code
login**. A usage limit delays reads and never loses data. **Deliver the morning message through a
Telegram bot.** It's the only option that pushes to an Android phone, has real buttons, carries no
ban risk and needs no open port. The cost: the 1–3 item lines (never chat text) pass through Telegram's
servers. Built: `spike/telegram.py` (`python -m spike telegram pair|send|poll|listen`).

## Setting up from the app (built: `spike/setup.py`)

`scripts/setup-mac.sh` once, then `scripts/build-app.sh`, then `python -m spike --db ~/.soloyolo/soloyolo.db serve`
and open **http://127.0.0.1:8765/welcome** in a browser on the Mac. From there:

- **Link WhatsApp:** type your number, and the screen shows the 8-character code to enter on your phone (WhatsApp →
  Linked devices → Link a device → Link with phone number instead). The server runs `connectord link` for this and
  keeps it running afterwards, since the same process syncs. It stops when `serve` stops; once WhatsApp is linked,
  `scripts/install-mac.sh` hands syncing to launchd. Only one connectord may run: if launchd's is up, the app says so.
- **Read an export:** a LinkedIn, Instagram, X or WhatsApp export saved to `~/Downloads` under the name the network
  gave it shows up on the screen; pick it to read it. The app can only name a file the server found there.
- **Find your promises:** when chats have messages no pass has read, the screen (and Today) says how many, and
  offers **Read with Claude** or **Read on Mac**. Either runs one `watch --once --top 15` pass and shows which chat
  it's on. Claude sends those chats' text to Claude through your Claude Code login, and the screen says so before
  you pick; on Mac is the offline heuristic. It takes the same lock as the launchd jobs, so two passes never
  overlap. Only counts come back to the app: the pass's own output names people and promises, and is dropped.
- Nothing asks for a password. connectord's output is read for the code and the link result only; the message lines
  it logs are dropped.

## Process model (built: `scripts/`)

| Agent | Runs | When | If it dies |
|---|---|---|---|
| `com.soloyolo.connectord` | `connectord --data ~/.soloyolo sync` | at login, forever (`KeepAlive`) | launchd restarts it, at most once a minute (`ThrottleInterval 60`) |
| `com.soloyolo.watch` | `python -m spike watch --once --top 15` | every 30 min (`StartInterval`) | the next interval runs it again |
| `com.soloyolo.digest` | one pass, then `python -m spike digest --out …` | 07:30 local (`StartCalendarInterval`) | runs the next morning |

- All three call `scripts/soloyolo-job.sh {sync,watch,digest}`, which rotates logs and holds one lock so
  watch and digest never extract at the same time. launchd itself never runs two copies of one job.
- **Backoff:** launchd has no exponential backoff, only the 60 s floor. That's enough: a crash loop costs
  one restart a minute. whatsmeow reconnects with its own backoff after a connection drops.
- **Gap found:** if connectord's *first* connect fails (no Wi-Fi at login), it stays up doing nothing.
  whatsmeow only retries connections it once had, and the process never exits, so `KeepAlive` can't help.
  The watch job checks: if the last status in `connectord.log` is `error`, it runs `launchctl kickstart -k`.
  A proper fix (exit non-zero on a failed connect in `sync`) belongs in connectord, outside this step.
- Only one connectord per device. Stop `link` (Ctrl-C) before installing, or the two sessions fight.
- The viewer stays manual: `python -m spike --db ~/.soloyolo/soloyolo.db serve` (127.0.0.1 only).

## Data and permissions

- `~/.soloyolo/` mode 700: `soloyolo.db` (+`-wal`/`-shm`), `accounts/` (WhatsApp device keys: whoever has
  them can read your WhatsApp), `logs/`, `digest/`. The plists set `Umask 077`, so new files are 600.
- Turn on FileVault. Keep the keys out of backups: `tmutil addexclusion ~/.soloyolo/accounts` (relinking
  is cheap; a stolen backup disk with keys is not).
- No Full Disk Access is needed for WhatsApp. That's only for iMessage `ingest`, which this doesn't schedule.
- macOS shows "Background item added: bash" once. The scripts aren't signed. Login Items lists them.

## Claude, unattended

- Run `claude` once in Terminal and log in. The CLI keeps its credentials in your login Keychain, and
  launchd user agents run inside your login session, so they can reach it. Nothing runs before you log in.
- launchd's PATH is `/usr/bin:/bin:…`. The installer puts `claude`'s and Python's folders on it, and fails
  if it can't find `claude`.
- **Usage limit or expired login:** each `claude -p` fails fast. The person keeps their previous items and
  stays "changed", so the next pass retries; nothing is lost and nothing is half-written. Watch that it
  shares your subscription with your own Claude use. Start with `SOLOYOLO_TOP=10` and 30-minute passes.
- The digest says so: `! 7 changed chats waiting, nothing read for 9h: a Claude usage limit or login?`
  It also warns when the newest WhatsApp message is over 12 h old (sync stopped, or you were logged out).
  A silent failure is the one to avoid: "nothing today" must never mean "the pipe broke on Tuesday".

## Logs and uninstall

- `~/.soloyolo/logs/{connectord,watch,digest,launchd}.log`, rotated at 5 MB (one `.1` kept).
- connectord writes every live message, text included, to stderr as an `event` line. The job script
  drops those lines before the log. `watch.log` still prints new item lines ("new: <name>: …"), so treat
  logs like the store.
- State: `launchctl print gui/$(id -u)/com.soloyolo.connectord`. Run now: `launchctl kickstart gui/$(id -u)/com.soloyolo.digest`.
- `scripts/uninstall-mac.sh` stops and removes the agents and keeps the data. `PURGE=1` also deletes
  `~/.soloyolo`. Then on the phone: **WhatsApp → Linked devices → the device → Log out**. Deleting local keys
  doesn't unlink you.

## Delivering the morning message

| | Reaches you on Android at 07:30 | One-tap answer | Risk / cost | Verdict |
|---|---|---|---|---|
| macOS notification | only if you're at the Mac | no: `osascript` notifications have no buttons; actions need a signed app | none; local | **built as fallback** |
| WhatsApp "Message yourself" via whatsmeow | **probably silent**: a message from your own linked device counts as sent by you, so expect no notification (verify once) | no buttons on personal accounts; typing "1 done" could be parsed from the self-chat | **ban risk goes up**: soloyolo stops being read-only, and the account at stake is the one India runs on (family, UPI). The self-chat would also need filtering out of extraction | no |
| Email to self (Gmail) | depends on your Gmail notification settings; morning mail gets skimmed | links only, so a tap needs a URL that reaches the Mac, or IMAP reply parsing | SMTP app password or OAuth on the Mac | no |
| **Telegram bot** | **yes**: ordinary push | **yes**: inline buttons; taps come back by polling | official Bot API, no ban risk. Bot chats aren't end-to-end encrypted: the 1–3 lines pass through Telegram | **recommended** |
| Local web page / PWA on the LAN | no push: Web Push on Android needs HTTPS with a trusted cert, which LAN IPs don't get | yes, if you open it | opens your message history to the Wi-Fi (the viewer binds to 127.0.0.1 on purpose) | no; good as the page *behind* the nudge |

(ntfy.sh is a fair second choice: push, action buttons, self-hostable. But its buttons call a URL, so taps
need a way back to a sleeping Mac behind NAT. Telegram's queue does that for free.)

**How Telegram works here** (`spike/daily.py` formats, `spike/telegram.py` sends and applies taps):
1. Setup, once: in Telegram, message **@BotFather** → `/newbot` → get a token. Run `telegram pair`, paste
   the token (not echoed), send your bot `/start`. The token and your chat id go in `~/.soloyolo/telegram.json`
   (mode 600, in a mode-700 folder; `SOLOYOLO_TELEGRAM_TOKEN` overrides it). Only that chat is ever answered.
2. 07:30: `python -m spike digest --format telegram` produces the `sendMessage` body: plain text, no
   `parse_mode`, one row of buttons per item: **Done · Not needed · Still on**. The sender adds `chat_id`, and
   before sending it records a `telegram` disclosure for each person named, like extraction does for Claude.
3. A tap sends a `callback_query` carrying `sy1:<d|x|o>:<person>:<message>:<m|t>` (≤64 bytes, no state on
   the Mac). The `com.soloyolo.telegram` agent long-polls `getUpdates` (outbound HTTPS only, works behind Jio/Airtel CGNAT),
   drops any update not from your own chat, and calls `daily.apply_callback` (it records your mark).
   `daily.tapped` collapses the row to "2: not needed". Telegram keeps taps for 24 h, so a tap made while
   the Mac sleeps is applied when it wakes.
4. **Silence = done.** Run 6 showed most items get finished off-chat and nobody reports back. So the message
   says "No tap = done", and the button that changes the outcome is **Still on** (an explicit keep).
   Done vs Not needed only feeds evaluation (finished vs moot). `nudge.py` has to honour that rule.

## What breaks when the Mac sleeps

| | Asleep | Shut down |
|---|---|---|
| WhatsApp sync | disconnected; reconnects on wake and the server delivers what arrived meanwhile | same, once you log in |
| Extraction | one coalesced pass on wake, not one per missed interval | first pass 30 min after login |
| Digest | **runs on wake**, so the "morning" message arrives when you open the lid | **skipped that day** |
| Telegram taps | queued 24 h | queued 24 h; older ones are lost |
| Weeks away | WhatsApp unlinks companion devices when the *phone* is unused for ~14 days | same |

To get it at 07:30 sharp, keep the Mac plugged in with **Battery → Options → Prevent automatic sleeping when
the display is off** on, or schedule a wake: `sudo pmset repeat wakeorpoweron MTWRFSU 07:20:00`. On a
closed MacBook this isn't reliable. A Mac mini or an always-on box is the real answer, later.
The digest uses the Mac's time zone: keep it on Asia/Kolkata.

## Your steps on the Mac

```bash
git clone <repo> ~/soloyolo && cd ~/soloyolo
scripts/setup-mac.sh       # checks python3, go, claude; makes .venv; builds connectord; prints the rest
```

It then prints the three remaining steps: link WhatsApp with a pairing code, `telegram pair`, and
`scripts/install-mac.sh` (or `SOLOYOLO_DIGEST_AT=07:15 SOLOYOLO_TOP=10 scripts/install-mac.sh`).

Settings are environment variables, listed at the top of `scripts/install-mac.sh`. Re-run it after you
change one or move the checkout. It's idempotent.
