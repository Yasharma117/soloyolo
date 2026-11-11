# Telegram for soloyolo: what was built, limits, and the policy question

Date: 2026-11-11. Code: `connectord/internal/telegram/`.

**Why Telegram matters here.** For many people Telegram is where the personal promises live: "I'll send it
tonight", "call you Sunday". So, like WhatsApp, 1:1 chats are a **source** of items, and small groups are
**evidence** that something got done.

**How sure I am.** This adapter has **never run against a real Telegram account**. Everything below is checked
by unit tests against a fake Telegram, not against Telegram's servers. Policy facts come from search-result
summaries of Telegram's own pages and from library maintainers' notes. Each claim is tagged **[high]**,
**[med]** or **[low]**. Read the current API Terms yourself before relying on them.

---

## 1. What was built

- **Signs in as you.** An MTProto user session through the Go library gotd/td, not a bot. A bot can't read your
  private chats; a user session sees what you see.
- **Login.** Phone number, then the code Telegram sends (usually inside your Telegram app, in the chat called
  "Telegram"), then your two-step password if you have one. A wrong code or password asks again; nothing is re-sent.
  A flood wait during login is reported as an error, never slept through.
- **Your own api_id and api_hash.** Read from `TELEGRAM_API_ID` and `TELEGRAM_API_HASH`, or from
  `~/.soloyolo/telegram-api.json` (`{"api_id": 12345, "api_hash": "..."}`). Nothing is hard-coded.
- **Session keys.** `~/.soloyolo/accounts/<id>/<id>.session.json`, file mode 0600 in a 0700 directory. Anyone who
  copies that file is signed in as you. Like the WhatsApp keys, it belongs in the macOS Keychain later.
- **What it reads.** 1:1 chats with people, and basic groups as evidence. It skips channels, supergroups, bots,
  Saved Messages, and the Telegram service chat (which carries login codes).
- **First sync is bounded.** The last 90 days, at most 1,000 messages per chat, at most 20 pages of 100 dialogs per
  folder (main list and archive), one request per second. People are read before groups. Progress is saved per chat
  in `sync.json`, so a restart picks up where it stopped.
- **Then live.** New and edited messages arrive over the update stream. A message from someone not seen yet triggers
  a catch-up sync at most once a minute.
- **Flood waits.** When Telegram says "wait N seconds", the adapter sleeps exactly N seconds and retries. A wait
  longer than an hour, or a fifth wait in a row, ends that sync; the next one resumes from the saved cursors.
- **Read-only.** It never sends (`messages.send` returns "unsupported"), never calls `messages.readHistory`, so
  nothing is marked read, and never calls `account.updateStatus`, so it doesn't set you online. The only writes to
  Telegram are the login calls.

## 2. Limits

- Never tested on a real account. The likeliest first failures: the update stream's gap recovery, and accounts
  with thousands of chats.
- Media is a placeholder line ("[photo]" and so on); nothing is downloaded.
- Supergroups and forum topics are skipped, so evidence posted there is missed.
- Secret chats are device-only and can't be read by any other session. **[high]**
- Older than 90 days, or past 1,000 messages in one chat, is not fetched on first sync.
- The session appears in Telegram → Settings → Devices as "soloyolo". You can end it there at any time; the
  daemon then reports `logged_out`.

## 3. The risk and policy question

**Short answer.** Signing in with your own api_id to read your own chats slowly is what Telegram's API exists for.
The real risk is Telegram's anti-abuse system flagging a new unofficial client, which can freeze or ban the
account, and the appeal path is an email.

- **Third-party clients are allowed.** **[high]** Telegram publishes the API for anyone to build clients, and asks
  each developer to get their own api_id and follow the API Terms of Service.
- **Use your own api_id.** **[high]** Using another app's api_id or hash, or pulling them out of official clients, is
  against the terms and a known cause of bans.
- **Abuse means bans.** **[high]** Telegram's own page says using the API for flooding, spamming, or faking channel
  counters gets accounts banned forever. This adapter does none of that: one request a second, read-only.
- **New unofficial sessions are watched.** **[low]** Library maintainers (Telethon, gotd) say logins from unofficial
  clients are put under observation, and that accounts sometimes get banned with no clear cause. gotd's docs suggest
  emailing recover@telegram.org before the first login to say you'll use the account with your own client. This is
  their advice, not a Telegram rule.
- **Unbanning.** **[med]** Telegram points banned API users to recover@telegram.org with an explanation of what they
  intend to do with the API.
- **Whether reading your own chats into a local file is fine.** **[med]** Nothing found forbids it. The data stays
  on your machine. If soloyolo ever sends message text to a cloud model, that is your data leaving your device by
  your choice, but tell the user.

**What I'd do.** Try it on your own account first, not a fresh number: fresh numbers on unofficial clients are the
pattern most bans describe. Don't run it on an account you can't afford to lose for a day or two.

Sources:
- [Telegram API Terms of Service](https://core.telegram.org/api/terms)
- [Creating your Telegram application (api_id)](https://core.telegram.org/api/obtaining_api_id)
- [gotd/td support notes on userbots and bans](https://github.com/gotd/td/blob/main/.github/SUPPORT.md)
- [Telethon: next steps (accounts and bans)](https://docs.telethon.dev/en/v2/basic/next-steps.html)
- [WTelegramClient FAQ](https://wiz0u.github.io/WTelegramClient/FAQ)

## 4. How to try it

1. Go to https://my.telegram.org and sign in with your phone number (the code arrives in your Telegram app).
2. Open **API development tools** and fill in the form: any app title and short name, platform "Desktop". You get an
   **api_id** (a number) and an **api_hash**. Keep them private; they're tied to your account.
3. Build the daemon: `cd connectord && go build -o bin/connectord ./cmd/connectord`
4. Run the link command with your number, country code first:

   ```bash
   TELEGRAM_API_ID=12345 TELEGRAM_API_HASH=0123abcd... \
     ./bin/connectord link --network telegram --phone 919800000000
   ```

   Or put `{"api_id": 12345, "api_hash": "..."}` in `~/.soloyolo/telegram-api.json` (chmod 600) and leave out the variables.
5. You'll see `Telegram code needed: the login code Telegram sent you (in your Telegram app, from the chat called
   Telegram)`. Type the code and press Enter.
6. If you have two-step verification you'll see `Telegram password needed: ...`. Type the password; it isn't echoed.
7. You'll see `Linked as <your user id>. Syncing history; Ctrl-C to stop.` Every 15 seconds a line reports what the
   store holds. Telegram also posts a "new login" notice in your app; that is expected.
8. To stop, press Ctrl-C. `./bin/connectord sync` resumes it later. To sign it out, end the "soloyolo" session in
   Telegram → Settings → Devices.
