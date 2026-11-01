# soloyolo: building the messaging layer without Beeper (and where Beeper + Mesh fail)

Date: 2026-10-30. Companion to `REPORT.md` (§2.5 has the Mesh desktop teardown this builds on).

---

## 0. Context: the options we weighed

**Is Matrix a risk?** The worry was that Discord might stop funding Matrix. I found no evidence that Discord funds it. In 2026, users moved *from* Discord *to*
Matrix after Discord announced age verification for everyone. The real financial risk is the Matrix.org Foundation itself: it still lost the equivalent of 34% of its costs last year,
and in 2025 it threatened to shut down its hosted bridges unless it raised $100k. That risk barely touches us, because bridgev2 is split in two:

| Layer | Size | Depends on the Matrix.org Foundation? |
|---|---|---|
| `NetworkConnector` / `NetworkAPI` (`refs/mautrix-go/bridgev2/networkinterface.go`): the reverse-engineered network code | 1,600-line interface + big per-network libraries | No. Maintained by Beeper/Automattic |
| `MatrixConnector` (`matrixinterface.go:42-71`): where events go | ~20 methods, 259 lines | Only through the Matrix protocol, and it's swappable |

Mesh proves the swap works: `mesh-integrations` runs the bridgev2 connectors in-process with no homeserver.

**Three ways to get messages without depending on Matrix:**

- **A. Beeper Desktop API.** `POST /v1/chats/{chatID}/messages` with `{text, replyToMessageID, attachment:{uploadID}}` returns
  `{chatID, pendingMessageID}` (`refs/desktop-api-js/api.md:190`, `src/resources/messages.ts:166`). Confirm delivery via
  `GET /v1/chats/{chatID}/messages/{id}` or `message.upserted` on `/v1/ws`. Limits:
  - Localhost only (`127.0.0.1:23373`), so it needs Beeper Desktop running.
  - It sends as *your* accounts only.
  - The networks' own rules still apply.
  - iMessage sends only on a Mac.
  
  Fine for a personal tool; not a hosted multi-user backend.
- **B. Run the bridgev2 connectors yourself behind a local `MatrixConnector`** backed by SQLite. You get every maintained connector.
  Catch: the bridges are **AGPL-3.0** (`mautrix-go` itself is MPL-2.0).
- **C. Use the protocol libraries directly behind your own small interface.** The most independent, and the most work. Section 1 below.

**Rule that removes the risk:** keep your own protocol-neutral data model (`account, chat, message, person, handle, event`).
Then Matrix and Beeper are replaceable transports, never your core.

---

## 1. Building your own "Beeper for Mesh"

What Mesh's `mesh-integrations` binary already is, minus Beeper's SDK: **a local daemon that logs into each network as you and
turns everything into one event stream.**

```
┌ your app (UI, ranking, CRM graph) ┐
│        JSON-RPC over stdio        │   ← same pattern as Mesh (main.js ↔ mesh-integrations)
├───────── connectord (Go) ─────────┤
│ Registry → Adapter per network    │
│ store: SQLite (accounts, keys,    │
│        chats, msgs, cursors)      │
└───┬────────┬────────┬────────┬────┘
 WhatsApp  Signal  Telegram  iMessage ...  (each speaks that network's own client protocol)
```

### The contract (what Matrix is for Beeper, you own)

```go
type Adapter interface {
    Login(ctx, step LoginInput) (LoginStep, error) // QR | cookies | code | done
    Connect(ctx) error                              // long-lived socket/poll
    Events() <-chan Event                           // msg, edit, reaction, read, typing, contact
    Send(ctx, chatID string, m Outgoing) (RemoteID, error)
    Backfill(ctx, chatID string, before Cursor) ([]Event, Cursor, error)
    Contacts(ctx) ([]Contact, error)
}
```

About 6 methods, not bridgev2's ~40 optional ones. Add capabilities only when the product actually needs them.

### Per network

| Network | Library | License | Login | Difficulty and ban risk |
|---|---|---|---|---|
| WhatsApp | `whatsmeow` | MPL-2.0 ✅ | QR as a linked device | Low effort. Ban risk is low for normal use, high for bulk sends |
| Telegram | `gotd/td` or TDLib | MIT / BSL ✅ | phone + code | Low. Telegram tolerates third-party clients |
| Signal | `libsignal` + your own client, or `signal-cli` daemon | AGPL ⚠️ | QR as a linked device | Medium. The whole Signal stack is AGPL |
| Discord / Slack | `discordgo` / `slack-go` | BSD ✅ | token / cookies | Low. Discord bans user tokens used by bots ("self-bots") |
| iMessage | chat.db reader + Messages.app automation | yours | Mac permissions | Medium. Mac only; `mini_mesh.py` is the reader start |
| Instagram / Messenger | no standalone library; `mautrix-meta`'s internal package is AGPL | ⚠️ | cookies | **Hard**, and the **highest ban risk** |
| LinkedIn / X | none maintained; reverse-engineer their internal web APIs | yours | cookies | **Hard**. Endpoints change often; LinkedIn is aggressive about detecting automation |

### Phasing

- **Phase 1:** WhatsApp, Telegram, iMessage. Roughly 70% of a typical person's messaging, all permissively licensed. About 2–4 weeks for one person.
- **Phase 2:** Signal (accept the AGPL, or run `signal-cli` as a separate process to keep it at arm's length), plus Discord and Slack.
- **Phase 3:** Meta, LinkedIn, X. Only if the product really needs them. This is the treadmill that eats Beeper's engineering team.

### What's hard but invisible (bridgev2 handles this for Beeper; you'd build it yourself)

- **Encryption keys and session storage.** Losing them means relinking the device; leaking them means account takeover. Use the macOS Keychain.
- **Reconnects, backoff, and detecting "logged out remotely".**
- **Deduplication and ordering.** The same message can arrive over both the live connection and history backfill.
- **Looking like the real client.** Client version strings, TLS fingerprints (`utls`), rate limits. Mesh's binary includes all of these.
- **Media.** Downloading, decrypting and caching attachments per network.

---

## 2. Where Beeper and Mesh fail badly

### Beeper

1. **iMessage is a graveyard.** Apple killed Beeper Mini and Beeper Cloud's iMessage access in Dec 2023 – Jan 2024 and flagged linked accounts
   as "spam". What's left is screen-scraping Messages.app on a Mac that has to stay on.
2. **Your account carries the ban risk.** Users report Instagram suspensions for "automated activity" after linking through Beeper. Beeper's help page
   admits it "may appear as a new device, browser, or location". The platforms hold the kill switch.
3. **Sync drift.** Beeper's own troubleshooting docs say to reconnect, clear the cache or force-quit when messages go missing. One complete copy of every chat network kept in sync is
   fragile by design.
4. **It's just an inbox.** It knows every message and nothing about the people behind them, or which ones matter. That's why Mesh exists.
5. **Trust model.** Cloud bridges decrypt your end-to-end-encrypted chats on Beeper's servers. Self-hosting is possible but it's a power-user chore.

### Mesh

1. **The core promise is broken where it matters most.** Reviews report failed iMessage imports that can't be retried, missing iPhone contacts,
   and **no automatic duplicate merging** ("merge thousands of entries by hand"), for a product whose whole value is one card per person.
2. **The best data needs a desktop computer that's on.** iMessage, calls, WhatsApp, Signal and the social networks only sync through the Mac or Windows app.
   Phone-only and web users get a much weaker product, and **there's no Android app**.
3. **It sees counts, not context.** iMessage is stored as daily counts per contact (`message_day_details`, REPORT.md §2.3). Mesh knows you texted Sam 40 times;
   it can't know you promised Sam an intro. Its AI, Nexus, is described as "inconsistent".
4. **WhatsApp only gets recent history.** It links as a new device, so it never sees years of past messages.
5. **It's read-only.** Mesh "will never text anyone". It tells you who to contact, then hands you off to Beeper, so the loop never closes
   inside the product.
6. **Organization and trust issues.** Lists and tags are thin; you can archive contacts but not delete them. There are refund complaints,
   App Store reviews that readers suspect are fake, and open questions about direction now that Automattic owns it.

Caveat: Dex is a competitor and the App Store reviews are anecdotal. The structural points (desktop dependency, aggregate-only data,
read-only, platform kill switches) come from our own teardown and hold regardless.

---

## 3. Where that leaves soloyolo

Both products fail at the same seam: **Beeper has the messages but no understanding of the people; Mesh understands the people but can't see what you said or send anything.**
A local-first daemon that keeps message content *on your machine*, uses it to understand relationships (promises, topics,
follow-ups), and can send replies itself would close that loop. Keeping the data local also avoids the privacy problem that probably stops Mesh from doing this on its servers.

**Next step:** a Phase-1 spike: the Go `connectord` with a WhatsApp adapter (`whatsmeow`) and the existing iMessage reader behind the
`Adapter` interface above.

---

Sources:
- [Matrix.org 2026 annual report](https://matrix.org/blog/2026/03/annual-report)
- [Matrix.org: "Crossroads" (Feb 2025)](https://matrix.org/blog/2025/02/crossroads/)
- [Matrix.org bridges shutdown unless $100k raised](https://discuss.privacyguides.net/t/matrix-org-bridges-to-shut-down-unless-100k-is-raised-in-one-month/25202)
- [Matrix vs Discord: age-verification migration](https://ecosistemastartup.com/?p=60423)
- [Dex: Mesh review 2026 (competitor)](https://getdex.com/blog/mesh-review/)
- [Mesh on the App Store](https://apps.apple.com/us/app/mesh-contacts-crm/id1463073824)
- [Apify: Clay personal CRM review 2026](https://use-apify.com/blog/clay-personal-crm-review-2026)
- [Android Central: Beeper drops iMessage after Apple bans](https://androidcentral.com/apps-software/beeper-drops-imessage-integration-after-apple-bans-linked-macs)
- [Notebookcheck: Apple bans iMessage accounts linked to Beeper](https://www.notebookcheck.net/Apple-bans-iMessage-accounts-linked-to-Beeper-app.798639.0.html)
- [Tom's Guide: RIP Beeper Mini](https://www.tomsguide.com/phones/rip-beeper-mini-imessage-on-android-is-now-truly-done)
- [TechCrunch: Apple again targets Beeper](https://techcrunch.com/2023/12/14/apple-again-targets-imessage-on-android-app-beeper-but-company-claims-it-has-a-fix)
- [Beeper help: Instagram](https://help.beeper.com/chat-networks/instagram)
- [Beeper help: common issues](https://help.beeper.com/en_US/troubleshooting/common-issues-and-how-to-report-bugs)
- [r/beeper (mirror)](https://reddit.sudovanilla.org/r/beeper)
- [Gardiner Bryant: Beeper is almost everything I want](https://gardinerbryant.com/beeper-is-almost-everything-i-want-in-a-chat-client.md)
