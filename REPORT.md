# soloyolo — how Beeper and Mesh actually work

Date: 2026-10-30. Sources: 9 Beeper repos + `mautrix/go` shallow-cloned in `refs/`, Mesh's public web bundle
(`refs/mesh-web/js/index-*.js`, 6.5 MB) and help center. Nothing was logged into, no private APIs called.

---

## TL;DR

| | **Beeper** | **Mesh (me.sh, ex-Clay)** |
|---|---|---|
| What it is | One inbox for every chat network | Personal CRM: everyone you know, ranked + enriched |
| Core trick | Make every network look like **Matrix** | Make every network look like a **contact card + "moments"** |
| Reads message content? | Yes, it *is* the client | **No**, metadata only (who/when), per their docs |
| Can send? | Yes | No, it never writes back |
| Where the scraping happens | Bridges (cloud, self-hosted, or on-device) | **Desktop app, locally** (LinkedIn/WhatsApp/iMessage are desktop-only) |
| AI | `ai-bridge`: models as chat contacts, MCP server in Desktop | "Nexus": a chat agent over your network, Vercel AI SDK stream |
| Open source | Largely, yes | No. `github.com/meshhq` is an unrelated company (Mesh Studio) |

They're two halves of the same idea. **Beeper = the pipes into every network. Mesh = the graph on top of the pipes.**
Beeper's Desktop API + MCP server could feed a Mesh-style CRM directly (see "Build it" at the bottom).

---

## 1. Beeper

### 1.1 Architecture

```
 WhatsApp  iMessage  Signal  Telegram  Discord  LinkedIn  Slack ...  AI models
    │         │        │        │         │        │        │           │
    ▼         ▼        ▼        ▼         ▼        ▼        ▼           ▼
 ┌────────────────────── bridges (mautrix bridgev2, mostly Go) ──────────────────┐
 │ one NetworkConnector per network: login, ghosts (remote users), portals (rooms)│
 └───────────────────────────────┬───────────────────────────────────────────────┘
                                 │ Matrix appservice protocol
                                 ▼
         Beeper homeserver ("hungryserv"; new: babbleserv on FoundationDB)
                                 │ Matrix C-S API + E2EE
                                 ▼
          Beeper Desktop / mobile  ──►  Desktop API :23373  (REST + WS + MCP)
                                              ▲
                              beeper CLI · desktop-api-js/py/go SDKs · Raycast · Claude
```

- **Everything is Matrix.** Each remote chat is a Matrix room ("portal"), each remote person is a puppet user ("ghost").
  Bridges are Matrix application services. That's why one client can show 15 networks.
- **Bridges are built on `mautrix/go/bridgev2`** (`refs/mautrix-go/bridgev2/networkinterface.go`). A network implements:
  - `NetworkConnector`: `Init`, `Start`, `GetName`, `GetCapabilities`, `GetLoginFlows`, `CreateLogin`, `LoadUserLogin`
  - `NetworkAPI` (per logged-in account): `Connect`, `GetChatInfo`, `GetUserInfo`, `HandleMatrixMessage`, …
  - ~40 optional `XHandlingNetworkAPI` interfaces (reactions, edits, typing, read receipts, backfill, contact listing,
    user search, group creation…). The capability set is discovered by Go type assertion, so a bridge only implements what its network supports.
  - Remote → Matrix events go through `RemoteEvent` types (message, edit, reaction, chat resync, backfill…).
  - `refs/dummybridge` is the smallest working example.
- **Protocol libraries are forks of the reverse-engineered clients**: `whatsmeow` (WhatsApp Web multi-device), `discordgo`, `slackgo`, `td`
  (Telegram MTProto), `groupme-lib`, `libgmessages`, plus `linkedin`/`linkedin-messaging-api` (now archived; used LinkedIn's internal Voyager API).
- **Self-hosting**: `bridge-manager` (`bbctl`) runs official or third-party bridges on your machine against beeper.com, so message
  re-encryption happens on hardware you control (`bridgeconfig/*.tpl.yaml` are the per-bridge configs it generates).

### 1.2 iMessage, the hard one (`refs/platform-imessage`)

Three generations of approach show up in the org:
1. `imessage` (archived) + `barcelona`: a Mac relay hooking private frameworks.
2. `mac-registration-provider` / `phone-registration-provider` / `registration-relay` (archived): generate Apple registration data on a
   real device, then speak the iMessage protocol from Linux ("Beeper Mini"-era). Apple killed this.
3. **Current: `platform-imessage`**, a Swift library in Beeper Desktop for macOS, works with **SIP on** and makes no network calls:
   - **Read**: open `~/Library/Messages/chat.db` (SQLite) read-only. Needs Full Disk Access on macOS 27+.
   - **Realtime**: `FSEventsWatcher` on `~/Library/Messages` + file watchers on `chat.db-wal` (`IMDatabase.swift:150-170`).
     The WAL gets deleted and recreated, so watchers are re-armed dynamically. Each tick diffs chat state (unreads) and
     advances a `MessageUpdatesCursor`. Rows that aren't fully hydrated yet (link previews, attachments) are retried on later ticks.
   - **Send** (`MessagesController.swift:1229`):
     - fast path: **AppleScript/OSA** `send` for plain text (no `@` mentions, no links) to an existing thread;
     - otherwise: open an **`imessage://open?address=…&body=…` deep link** (or `?groupid=`, or `?message-guid=p:0/GUID` for replies),
       then drive Messages.app through the **Accessibility (AX) API**: find the body field, assign text, press send, paste files.
     - Lots of window choreography (`WindowCoordination/`, Spaces/"eclipsing") so Messages.app does this without stealing your screen.
   - Exposed to Electron via N-API (`node-swift`), plus a standalone `imessage-cli`.
   - Chat IDs are hashed before leaving the module (`Hasher.thread.tokenizeRemembering(pii:)`).

### 1.3 Beeper Desktop API (the part you'd actually build on)

Beeper Desktop runs a local server at **`http://127.0.0.1:23373`**, auth'd with a bearer token or OAuth/PKCE. It's generated with Stainless
(`desktop-api-js/api.md`), and there are SDKs in JS, Python and Go.

- `GET /v1/accounts`, `/v1/accounts/{id}/contacts[/list]`: every connected network and its contacts
- `GET /v1/chats`, `/v1/chats/search`, `/v1/chats/{id}`, `POST /v1/chats` / `/v1/chats/start`
- `GET|POST /v1/chats/{id}/messages`, `PUT` (edit), `DELETE`, reactions, `/read`, `/unread`, `/archive`, `/reminders`, `/notify-anyway`
- `GET /v1/messages/search`, `GET /v1/search`: cross-network search
- `/v1/assets/{upload,download,serve}`: media
- `/v1/bridges/...`: login flows/sessions/steps, so you can drive a network login from a script
- `/v1/app/setup/...`: device verification (SAS/QR), recovery key
- **`/v1/ws`**: WebSocket event stream. Send `{"type":"subscriptions.set","chatIDs":["*"]}` (`cli/.../commands/watch.ts:57`)
- **`/v0/mcp`**: Streamable-HTTP MCP server with OAuth. `desktop-api-mcp` is just an `mcp-remote` stdio shim for Claude Desktop.

`beeper` CLI (`refs/cli`, Bun/TS/oclif) wraps all of it: `--json` everywhere, NDJSON events, `watch` → HMAC-SHA256-signed
webhooks (`X-Beeper-Signature: sha256=<hex>`), `rpc` over stdio, `--read-only` mode, and a plugin SDK.

### 1.4 `ai-bridge`: AI as a chat network

A bridgev2 connector where the "network" is LLM providers. A model is a ghost, a DM is a room bound to a branching session tree
(per-conversation SQLite), and replies stream as live-edited Matrix events carrying a `com.beeper.ai` payload built on
**AG-UI** events (anchor → stream → final, with a workaround for the 64 KiB event limit). It has tool calls, approvals (human-in-the-loop),
compaction, and runs that resume after a restart. Layering: `connector` → `msgconv`/`ai-stream` → `agent`/`harness` → `ai` (provider registry).

### 1.5 Other notable repos
`babbleserv` (new Matrix homeserver on FoundationDB), `synapse` (Beeper fork), `beeper-ingestor` (gomuks-based message search REST),
`chat-adapter-matrix` (Vercel Chat SDK adapter), `BetterSwiftAX` (their AX wrapper), `mcp-android`, `themes` (Desktop custom CSS).

---

## 2. Mesh (me.sh)

Closed source, so this comes from the public web bundle + help center. Confidence is marked per row.

### 2.1 Stack (from `app.me.sh` bundle)

| Piece | Finding | Confidence |
|---|---|---|
| Web app | Vite SPA (`index-CA3G9cj8.js`), React, RxJS observables everywhere | high |
| Marketing site | Next.js (Turbopack chunks) at me.sh | high |
| Auth | **Clerk** (`/v1/client/sync`, `organizations/memberships/invitations/domains` routes, `oauth_*` strategies) | high |
| API | `https://backend.me.sh/api` (REST, bearer token from Clerk), `https://api.me.sh/` | high |
| Search | Legacy Clay field `algolia_restricted_search_key` → **Algolia** (at least historically). Default plan name in code is still **"Clay Personal"** | medium |
| Billing | Stripe (web) + **RevenueCat** (iOS/Mac in-app) via `/billing/revenuecat/register` | high |
| Analytics | Segment, Plausible, Sentry | high |
| Short links | `go.me.sh` | high |

### 2.2 Data model / product surface (routes in the bundle)
`/people`, `/people/duplicates`, `/people/map`, `/notes`, `/reminders`, `/search`, `/nexus`, `/nexus/history`,
`/settings/integrations/{card-dav,zapier,make}`, `/settings/microsoft-contacts`, `/integrations/{id}/callback` (OAuth),
`/integrations/notion/connect`, `/users/workspace-settings`, `/organizations/*` (teams).

Integrations referenced: Google (Gmail/Calendar/Contacts), Microsoft/Outlook/Exchange, CardDAV, Apple Contacts, LinkedIn, X/Twitter,
Facebook, Instagram, WhatsApp, iMessage, phone calls, Notion, Zapier, Make, HubSpot, Slack.

### 2.3 How the integrations work

Two classes, split by where they run:

**Cloud (OAuth, any platform):** Google, Microsoft, Notion, CardDAV, Zapier/Make. Standard `/integrations/{id}/callback` OAuth;
the server pulls email/calendar *headers* → "moments" (who you emailed/met, when).

**Local (desktop app only):** the help center says LinkedIn, Facebook, Instagram, Twitter, WhatsApp, iMessage, phone calls and iOS Contacts
"won't be available in the browser version" because they "run locally on your device". Updated 2026-10-30 from the
web bundle's desktop-bridge code (`window.desktopIntegrations`, `window.api.syncEngine`) plus the engine WASM:

| Source | How | Confidence | Evidence |
|---|---|---|---|
| iMessage | Reads the Messages folder, read-only. On the App Store (sandboxed) build you **pick the folder in a macOS picker** (`integration.authorizeDiskAccess`), not a blanket Full Disk Access grant. Mac only. Stored as **per-day counts per contact, no message text** (`message_day_details`: counts from/to me, group vs 1:1, first/last timestamps) | confirmed (see §2.5) | copy: "Mesh needs read-only access to your Messages folder"; `hasDiskAccess(provider)` |
| Phone calls | Same flow, `CallHistoryDB` folder. Mac only. Stored per call: start/end, answered, outgoing, media type, group | confirmed | `apple-phone-log`, `call_details` table, `import_calls.go` |
| WhatsApp | **Linked device via QR code** ("Settings → Linked Devices → Link a Device, scan this code") | confirmed: mautrix-whatsapp/whatsmeow (§2.5) | `jHt` config |
| Signal | **New, not in the help center.** Same linked-device QR flow | confirmed (UI) | `DHt` config |
| LinkedIn/FB/IG/X | Desktop `integration.authorize(provider, {friendType, recoverBrowserSession})`. Runs on your own logged-in browser session. X/IG can filter by follow type (everyone/mutual/followers/following). LinkedIn data goes in through engine RPCs `importLinkedInConnections` / `importLinkedInProfile` | confirmed: cookie capture → mautrix bridges (§2.5) | `recoverBrowserSession`, `GWt` options |
| Platforms | Social/WhatsApp/Signal: Mac, Windows, iOS. iMessage/calls: Mac only | confirmed | `G9e` |

**The desktop app is Electron**, not Catalyst. Evidence: `window.app.isElectron`, a preload bridge, `appInfo.isMAS ? "MAS" : "self-distributed"`
(so a **non-App-Store build exists**), and builds for `darwin-universal` + `win32-x64`.

**The architecture is local-first.** `@mesh/sync-engine-sdk` 0.4.24 ("embedded mesh sync engine, loaded via N-API",
repo `mesh/mesh-backend`, `apps/sync-engine`) is a **Go** engine (go1.26) using SQLite via `ncruces/go-sqlite3`, goose migrations,
and jrpc2. It runs as a native N-API addon in Electron and as WASM (42 MB, `assets.me.sh/clients/sync-engine/<hash>/mesh-sync-browser.wasm`)
inside a SharedWorker in the browser, with storage in OPFS. The UI never queries the server for people. It calls about 90 engine RPCs
(`getContact`, `mergeContacts`, `getTimeline`, `saveReminder`, …). Writes go to `sync_outbox` stamped with **HLC** timestamps
(`internal/hlc`) and a `device_id`, and get flushed over HTTP. Server changes come back through a puller plus a websocket waker
(`coder/websocket`). This is basically the "local-first CRM" soloyolo wants to build.

**Beeper hook:** after login the desktop app calls `isAppInstalled("beeper")`, and if it's installed it sets `outreach_app="beeper"`,
which is how Mesh opens replies in Beeper.

Then the server side **dedupes/merges** ("`/people/duplicates`", the `merge_contacts` tool), **enriches** (job changes, news, birthdays → Feed),
and **ranks by relevance**. From the docs: "the more relevant someone is … the higher they'll be ranked", and shortcodes/non-people
are excluded. `mini_mesh.py` here replicates that ranking for iMessage.

### 2.4 Nexus (the AI)
- `POST /chat` with `{message:{content}, conversation_id, contact_ids:[target], regenerate}`; resume with `GET /chat/{id}/stream`
  (204 = nothing left to stream).
- Transport: SSE via `@microsoft/fetch-event-source` (`openWhenHidden`), bearer auth.
- **Wire format is the Vercel AI SDK UI-message stream**: `start`, `tool-input-start`, `tool-input-available`, `tool-output-available`,
  `finish*`, plus custom `data-conversation-id` / `data-run-id` parts. So the backend almost certainly runs AI SDK `streamText` with tools.
- Only one tool is named client-side: **`merge_contacts`** (`input.contact_ids`), which the UI special-cases to refresh merged cards.
  Search/lookup tools run server-side and aren't visible. The model/provider isn't in the client.

### 2.5 Desktop app, verified (Mesh 3.0.9 DMG, 2026-10-30)
Source: `me.sh/api/download/mac` → `Mesh-3.0.9-universal.dmg` (sha256 `a45f2562…0116`), bundle `com.clay.mac`, team `C68GA48KN3`.
I mounted it read-only and copied out the code; nothing was run. REA (`analyze-javascript-application` on `app.asar`, main.js + preload.js)
→ Evidence `ev_327cd212…79d4` in `rea-out/mesh-desktop.json`. The ten integrity mismatches it recorded are native binaries that were re-signed after packing.

Three processes:
1. **Electron main** (`main.js`, 1.5 MB). REA counted 3 context-bridge APIs (85 members) and 61 literal IPC channels (`integrationRequest`,
   `sync-engine:*`, `oauth:*`, `iap*`, `bundle:*` for UI hot-updates, …). `integrationRequest` sends to each platform's methods: `requestAuthorization`,
   `checkDiskAccess`/`requestDiskAccess`, `requestSync`, `remove`.
2. **`mesh-sync.node`** (41 MB N-API addon): the Go sync engine from §2.3 (local SQLite, HLC outbox).
3. **`mesh-integrations`** (257 MB universal Go executable, `me.sh/sync-engine/cmd/mesh-integrations`). Main spawns it as a child process and talks
   **JSON-RPC 2.0 over stdin/stdout**. Every local data source lives here.

**`mesh-integrations` is built on Beeper's stack.** It statically links `github.com/beeper/beeper-client-sdk` (`pkg/sdk`, `pkg/bridges`,
`pkg/matrix`, `pkg/beepermatrix`, `internal/tdesktop`, `pkg/wamclient`) plus the mautrix bridgev2 connectors:
**whatsapp (whatsmeow), signal, telegram, meta (FB/IG), twitter, linkedin, gmessages, gvoice, slack, discord**, plus `tumblr-dms`.
Mesh's adapter is `internal/beeper.Provider` (`AddAccount`, `runLoginFlow`, `ImportHistory`, `ImportMessageDays`, `PurgeAccountMessages`).
I found no `matrix.beeper.com` hostname in the binary, which suggests the bridges run **locally, in-process**, not through Beeper's servers
(inferred: string search, not traced).
Telegram, Google Messages, Google Voice, Slack and Discord connectors ship but aren't shown in the UI yet, so they're likely coming.

| Source | How (confirmed in desktop code) |
|---|---|
| iMessage | `internal/imessage.Watcher` watches `chat.db` (`ChatDBPath`, `doImport` loop) → `PushMessageDays`: per-day aggregates via `messaging.AggregateMessageDays` |
| Phone calls | `internal/callhistory.Poller` polls `CallHistory.storedata` → `PushCalls` |
| Apple Contacts | `internal/applecontacts`, cgo into the Contacts framework (`MeshCopyContactsJSON`, `MeshRequestContactsAccess`) |
| WhatsApp / Signal | Beeper SDK → mautrix-whatsapp / mautrix-signal bridgev2, linked-device QR login |
| LinkedIn / FB / IG / X | Login opens a sandboxed `BrowserWindow` on its own session partition. Main grabs the fields the bridge's login flow asks for **from cookies and request headers** (the bridgev2 cookie-login step), then hands them to mautrix-linkedin/meta/twitter. `friendsSyncStore` keeps the X/IG follow-type filter |

So Mesh is a CRM on top of Beeper's own bridge SDK. That's strong support for §3: the same pipes are available to you
through Beeper Desktop's API, with no need to embed the bridges.

---

## 3. Build it: soloyolo = local-first Mesh on Beeper's pipes

> Not depending on Beeper or Matrix, plus where Beeper and Mesh fail: see `BUILD-WITHOUT-BEEPER.md`.

The cheap version that beats both on privacy:
1. **Ingest**: Beeper Desktop API `GET /v1/accounts/*/contacts` + `GET /v1/chats` + `/v1/ws` events → every network, already logged in,
   already decrypted, locally. No scrapers to maintain (Beeper maintains them).
2. **Graph**: one SQLite file: `person`, `handle(person_id, network, id)`, `moment(person_id, ts, direction, network)`. Metadata only.
3. **Rank**: the decay score in `mini_mesh.py` (two-way > inbound, 30-day half-life).
4. **Merge**: same phone/email = same person; name matches → ask the user. (That's literally what Mesh's `merge_contacts` tool is.)
5. **Nexus**: point Claude at Beeper's `/v0/mcp` + a 3-tool MCP over your SQLite (`search_people`, `get_person`, `merge_people`).

`mini_mesh.py` is step 2+3 for iMessage alone: `python3 mini_mesh.py --demo` (self-check, passes) or
`python3 mini_mesh.py 20` (real `chat.db`; give your terminal Full Disk Access).

Sources: [me.sh](https://me.sh) · [Mesh: WhatsApp](https://library.me.sh/knowledge-base/whatsapp/) ·
[Mesh: iMessage](https://library.me.sh/knowledge-base/imessage/) · [Mesh for Web](https://library.me.sh/knowledge-base/mesh-for-web/) ·
[Mesh x WhatsApp](https://me.sh/integrations/whatsapp) · [github.com/beeper](https://github.com/beeper) · [github.com/mautrix/go](https://github.com/mautrix/go)
