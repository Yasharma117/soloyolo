# connectord

A local daemon that logs into each messaging network **as you** and writes everything into one SQLite file on
your machine. It is Phase 1 of `BUILD-WITHOUT-BEEPER.md`: the same job Mesh's `mesh-integrations` binary does,
without Beeper's SDK or a Matrix homeserver.

```
your app ──JSON-RPC 2.0 over stdio──► connectord ──► store: ~/.soloyolo/soloyolo.db (shared schema: internal/store/core.sql)
                                          │
                     Registry ─► imessage (chat.db, read-only; send via AppleScript)
                              ├► whatsapp (whatsmeow, linked device; keys in accounts/<id>/)
                              └► telegram (gotd/td, user session, read-only; session in accounts/<id>/)
```

## Build and test

```bash
cd connectord && go test -race ./...
```

```bash
go build -o bin/connectord ./cmd/connectord
```

Pure Go (SQLite via `modernc.org/sqlite`), so no cgo and it cross-compiles. The Go toolchain fetches 1.26
automatically if yours is older.

## Talk to it

One JSON object per line on stdin; responses and notifications on stdout; logs on stderr.

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"accounts.add","params":{"network":"whatsapp"}}' \
  '{"jsonrpc":"2.0","id":2,"method":"accounts.login","params":{"account":"whatsapp-1"}}' \
  | ./bin/connectord
```

| Method | Params | Result |
|---|---|---|
| `networks.list` | none | `["imessage","slack","telegram","whatsapp"]` |
| `accounts.add` | `network` | `{id, network}` |
| `accounts.list` | none | accounts, with `remote_user` once linked |
| `accounts.login` | `account`, optional `value` | a `LoginStep`: `qr` (render the payload as a QR code), `code`, `phone`, `password`, `permission`, or `done`. Call again until `done` |
| `accounts.connect` | `account` | starts syncing (also automatic after login and on restart) |
| `messages.send` | `account`, `chat_id`, `text` | `{remote_id}` |
| `contacts.list` | `account` | contacts the network knows |

Notifications: `event` (a new live message) and `account.status` (`connected`, `syncing`, `logged_out`, `error`).

WhatsApp alternative to scanning: pass `"value": "+14155550101"` to `accounts.login` to get an 8-character
pairing code to type into WhatsApp → Linked devices → Link with phone number.

Telegram: call `accounts.login` with `"value": "919800000000"` (your number), then again with the code Telegram
sent, then, if asked (`password` step), with your two-step password. Each step needs a value; none blocks. It needs
your own api_id and api_hash from my.telegram.org in `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` or
`~/.soloyolo/telegram.json`. From a terminal: `connectord link --network telegram --phone 919800000000`, which asks
for the code (and password) on stdin. Details, limits and the ban risk: `docs/TELEGRAM.md`.

## What works, what doesn't

Verified here: the build, all unit tests (`-race`), the stdio protocol, and a WhatsApp login that returns a real
linking QR from WhatsApp's servers. **Not verified here:** an actual link and message sync, which needs a phone,
and anything iMessage on a real Mac. This environment is Linux. Telegram has only run against a fake server in
unit tests, never a real account.

| | iMessage | WhatsApp | Telegram |
|---|---|---|---|
| Login | Checks Full Disk Access | QR or phone pairing code | Phone, login code, optional two-step password |
| Live messages | Polls `chat.db` every 2s (FSEvents would be better) | Socket, with whatsmeow's own reconnect | MTProto update stream, with gap recovery |
| History | Everything in `chat.db` on first connect | Only what WhatsApp pushes to a new linked device (recent, not years) | Last 90 days, up to 1,000 messages per chat, one request a second; flood waits slept as told |
| Send | Plain text to an existing 1:1 chat, via AppleScript. No attachments or replies | Text | Never (read-only; never marks read or sets you online) |
| Contacts | Not built (needs the Contacts framework) | From WhatsApp's contact store | People seen in your chats (bots skipped) |
| Groups | Skipped | Skipped | Basic groups as evidence; channels, supergroups and bots skipped |

## The hard parts still owed (from BUILD-WITHOUT-BEEPER.md)

- **Key storage.** WhatsApp device keys sit in `~/.soloyolo/accounts/<id>/*.keys.db` (mode 0700 dir). They
  belong in the macOS Keychain. So does the Telegram session, `accounts/<id>/<id>.session.json` (mode 0600).
- **Remote logout handling.** `logged_out` is reported; relinking is the UI's job and isn't built.
- **Edits, reactions, read receipts.** Mapped to event kinds; not stored yet.
- **Media.** Captions only; no download or decrypt.
