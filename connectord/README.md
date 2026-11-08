# connectord

A local daemon that logs into each messaging network **as you** and writes everything into one SQLite file on
your machine. It is Phase 1 of `BUILD-WITHOUT-BEEPER.md`: the same job Mesh's `mesh-integrations` binary does,
without Beeper's SDK or a Matrix homeserver.

```
your app ──JSON-RPC 2.0 over stdio──► connectord ──► store: ~/.soloyolo/soloyolo.db (shared schema: internal/store/core.sql)
                                          │
                     Registry ─► imessage (chat.db, read-only; send via AppleScript)
                              └► whatsapp (whatsmeow, linked device; keys in accounts/<id>/)
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
| `networks.list` | none | `["imessage","slack","whatsapp"]` |
| `accounts.add` | `network` | `{id, network}` |
| `accounts.list` | none | accounts, with `remote_user` once linked |
| `accounts.login` | `account`, optional `value` | a `LoginStep`: `qr` (render the payload as a QR code), `code`, `permission`, or `done`. Call again until `done` |
| `accounts.connect` | `account` | starts syncing (also automatic after login and on restart) |
| `messages.send` | `account`, `chat_id`, `text` | `{remote_id}` |
| `contacts.list` | `account` | contacts the network knows |

Notifications: `event` (a new live message) and `account.status` (`connected`, `syncing`, `logged_out`, `error`).

WhatsApp alternative to scanning: pass `"value": "+14155550101"` to `accounts.login` to get an 8-character
pairing code to type into WhatsApp → Linked devices → Link with phone number.

## What works, what doesn't

Verified here: the build, all unit tests (`-race`), the stdio protocol, and a WhatsApp login that returns a real
linking QR from WhatsApp's servers. **Not verified here:** an actual link and message sync, which needs a phone,
and anything iMessage on a real Mac. This environment is Linux.

| | iMessage | WhatsApp |
|---|---|---|
| Login | Checks Full Disk Access | QR or phone pairing code |
| Live messages | Polls `chat.db` every 2s (FSEvents would be better) | Socket, with whatsmeow's own reconnect |
| History | Everything in `chat.db` on first connect | Only what WhatsApp pushes to a new linked device (recent, not years) |
| Send | Plain text to an existing 1:1 chat, via AppleScript. No attachments or replies | Text |
| Contacts | Not built (needs the Contacts framework) | From WhatsApp's contact store |
| Groups | Skipped | Skipped |

## The hard parts still owed (from BUILD-WITHOUT-BEEPER.md)

- **Key storage.** WhatsApp device keys sit in `~/.soloyolo/accounts/<id>/*.keys.db` (mode 0700 dir). They
  belong in the macOS Keychain.
- **Remote logout handling.** `logged_out` is reported; relinking is the UI's job and isn't built.
- **Edits, reactions, read receipts.** Mapped to event kinds; not stored yet.
- **Media.** Captions only; no download or decrypt.
