# Slack for soloyolo: routes, limits, and the policy question

Date: 2026-11-08. Step 5 of the adapter plan (`BUILD-WITHOUT-BEEPER.md` §1, Phase 2). Code: `connectord/internal/slack/`.

**Why Slack matters here.** On real data, most items get closed where the chat can't see. Work Slack is the
exception: people close things in the open. They post the link, answer the thread, react ✅. So Slack is
mostly an **evidence** source. DMs can also create items.

**How sure I am.** `api.slack.com`, `docs.slack.dev` and `slack.com` were blocked from this session. Every Slack fact
below comes from search-result summaries of Slack's own pages, or from secondary coverage. None comes from a page I read in full.
Each claim is tagged **[high]**, **[med]** or **[low]**. Before anyone relies on the terms, they must read the current API Terms text themselves.

---

## 1. Facts

**Creating your own app with a user token (xoxp-).** **[high]**
- Go to api.slack.com/apps, choose Create New App, then add **User Token Scopes**: `im:history mpim:history channels:history
  groups:history`, the matching `*:read` scopes (needed to list conversations), `users:read users:read.email reactions:read`.
  Add `chat:write` only if you want soloyolo to send.
- A user token acts as you. It sees exactly what you see, DMs included. A bot token (xoxb-) can't read your DMs.
- Installing it in your own workspace makes it an **internal, customer-built app**. It isn't distributed and it isn't on the Marketplace.

**Who can install it.** **[med]**
- By default any member can install an app.
- A Workspace Owner can turn on **app approval**. Then members can only install pre-approved apps or request approval,
  and an admin can restrict an app outright.
- On Enterprise Grid, an org-level app policy turns approval on for every workspace. Expect it to be on at any company with
  an IT team.
- **Free** workspaces cap installs at **10 third-party or custom apps**, and a custom app counts.
- Nothing says user-token custom apps are treated differently: assume they need approval wherever it's on. **[low]**

**Rate limits: the May 2025 change.**
- **What changed** **[high]**: Since 2025-05-29, `conversations.history` and `conversations.replies` are limited for
  *commercially distributed apps that are not Marketplace-approved*. The limit applies to new apps and to new installs.
  Existing installs were moved from **2026-03-03**; the original date was 2025-09-02.
- **The numbers** **[med]**: Tier 1 (**1 request/min**). Secondary sources say the cap is also **15 messages per page**; I couldn't
  confirm that on Slack's own page.
- **Internal apps are exempt** **[high]**: Slack's FAQ says internal customer-built apps are excluded and keep **Tier 3 (50+/min)**,
  up to 1,000 messages per page (200 recommended).
- A personal app installed only where you created it is internal, so 50/min applies. The adapter defaults to that, with
  `HistoryPerMinute` / `PageSize` knobs for the 1/min, 15-per-page case.

**Slack API Terms, 2025.**
- **May 2025** **[med]**: The version effective 2025-05-29 (2025-06-30 for older apps) is reported by Hunton (Jul 2025) and
  Computerworld to prohibit (i) bulk export of API data, (ii) "persistent copies, archives, indexes or long-term data
  stores", and (iii) use of the data in LLMs. Slack described this as a clarification aimed at bulk downloads for indexing, and pointed developers to its
  Real-Time Search API.
- **Oct 2025** **[med]**: Terms dated 2025-10-10 (changelog 2025-10-13) shipped with the Data Access API (GA) and the
  Real-Time Search API. They add exceptions for **temporary caching** and for **storage required by law**. Slack called the
  other changes minor.
- **Coverage** **[low]**: I found no carve-out for "my own data, on my own machine, in an internal app". Commentary says the
  restrictions reach internal AI tools too.
- **What this means for soloyolo.** It is literally what the terms describe: a persistent local copy, indexed, with some
  text sent to an LLM for extraction. Being local-first doesn't change that. What's different is scale (one person, not a
  company-wide index) and purpose (closing *your* items).
- **Who answers for it.** On a workspace you don't own, the "Customer" is the workspace owner, usually your employer. They can
  revoke the app and treat the copy as a policy breach whatever Slack's terms say. Treat LLM use of Slack text as
  **not permitted unless the workspace owner says yes**.

**Socket Mode / Events API.** **[med]**
- Enable Socket Mode and create an **app-level token (xapp-)** with `connections:write`. Then subscribe to *events on behalf of
  users*: `message.im message.mpim message.channels message.groups reaction_added`.
- `apps.connections.open` returns a one-time `wss://` URL. Slack pushes envelopes down it, which must be acked within
  ~3s, and sends `disconnect` when it rotates the connection.
- There is no public URL and no polling cost. Without an app token the adapter polls `conversations.history` with an `oldest` cursor. Polling misses new replies on
  old threads, so Socket Mode is the better live path.

**Enterprise Grid and admin visibility.** **[med]**
- Admins see every installed app, who installed it and its scopes, and the Audit Logs API records app installs and scope
  changes. Installing a personal app with history scopes on a work Slack is **visible**.
- Separately, on Grid, approved eDiscovery/DLP vendors read **all content including DMs** through the Discovery API. Your
  work DMs are already visible to your employer's compliance tooling, and DLP may flag bulk reads. (Audit logs carry no content.)

**Workspace exports.** **[med]**
- Owners/Admins on any plan can export **public channels**. Free/Pro get a full export only "in limited circumstances".
- **Business+** Owners can apply for public and private channels; whether **DMs** are included is disputed **[low]**.
  **Enterprise** Org Owners can apply for an export with DMs. A **member can't export anything**,
  so for one person exports are useless unless you own the workspace.

**Free plan history.** **[med]** A free workspace shows only the last **90 days**, and data older than a year is deleted.
The API almost certainly returns no more than the UI shows.

---

## 2. Routes compared

| | User-token app (built) | Android notification listener | Workspace export |
|---|---|---|---|
| Sees | All your DMs, group DMs, channels, threads, reactions | Only what notified you (DMs, mentions), truncated text | Public channels; DMs only via an owner's approved application |
| History | 90 days by default (more on paid plans) | None: from install onward | Full, one-off |
| Live | Socket Mode, or polling | Yes | No |
| Closing signals (links, thread replies, ✅) | Yes, all three | Barely. Reactions and your own replies don't notify | Yes, but stale the day after |
| Needs | App install, possibly admin approval | Android, notification access; doesn't see a **work profile** from the personal side; Slack doesn't notify mobile while you're active on desktop | Owner/admin role |
| Visible to admins | Yes (app list, audit logs) | No API footprint, but your data policy still applies | They ran it |
| Slack API Terms | Apply in full | Not the API (the user terms and employer policy still apply) | Customer's own data; customer's call |
| Verdict | **Best data, most policy exposure** | Fallback for personal use; weak on evidence, which is Slack's main value | Only for a workspace you own |

---

## 3. Recommendation

**Work Slack (employer data).** Don't connect it until the user has answers to §4 in writing.
- **If the employer allows it:** use the user-token app as an internal app, with approval from IT if approval is on.
  Keep its default narrow mode (DMs as messages; in channels only your lines, mentions of you, your threads, ✅ on or by
  you). Retention isn't built yet, so delete the local copy on a schedule.
- **Only send Slack text to an LLM the employer has approved** (for example, a company Claude/Anthropic agreement). Otherwise
  run the heuristic extractor locally, and let Slack close items as evidence without creating new ones.
- **If the employer says no, or won't answer:** don't use any route. The notification listener isn't a way around
  policy. It copies the same data.

**Personal or community Slack.**
- **Use the user-token app with Socket Mode.**
- If you own the workspace, you are the Customer: install it, and the LLM question is yours to judge against the API Terms.
  The risk is low at personal scale, but nonzero.
- In a community you don't own, ask the admin if approval is on. On a free workspace, ask anyway: you'd take one of the 10 app slots.
- Keep the channel filter on there as well: other people's chatter isn't yours to index.

---

## 4. What the user must check with their employer

1. Is app approval on, and will IT approve a personal app with `im:history`/`channels:history` user scopes? (They'll see it either way.)
2. Does the acceptable-use or data-handling policy allow copying work messages to a personal or unmanaged device?
   For how long?
3. May work message text go to an external LLM? Which vendor is approved, under which agreement, and with training off?
4. Does the Slack contract incorporate the 2025 API Terms (Hunton: they bind customers who haven't negotiated their own terms)?
   Does legal read "persistent copy" and "LLM use" as covering an employee's internal app?
5. Are there legal holds, data residency rules or regulated data (health, finance, customer PII) in your channels?
6. Is the Slack Connect content in shared channels with other companies off limits? It's someone else's data too.
7. Must you remove the app and delete the local copy when you leave? Plan to do both.

---

## 5. What the adapter does (`connectord/internal/slack`)

- **Auth:** `SLACK_USER_TOKEN`/`SLACK_APP_TOKEN` env, or the OS keychain (`security` / `secret-tool`). A pasted token is
  checked with `auth.test` and saved there. Bot (xoxb-) and browser (xoxc-/xoxd-) tokens are refused.
- **Backfill:** `users.conversations`, then `conversations.history` back 90 days with cursors (DMs first), `conversations.replies`
  for DM threads and your channel threads. Calls are spaced per tier, 429s honour `Retry-After`, and restarts are incremental.
- **Live:** Socket Mode (acks, reconnects with backoff) when an app token is set, otherwise polling.
- **Mapping:** DMs become `message` rows. Group DMs and filtered channel lines become `evidence` (`slack-group:#launch`).
  ✅ reactions become `[✅ on: …]` lines and files become the spike's markers. Links are kept, and ids are qualified (`T…:U…`).
- **People:** one `users.info` per person seen, emitted as a contact event with **email** (new `Event.Email`). The store adds
  it as an `email` handle on that person, and never takes an email already used by someone else.
- **Not built:** edits (the store ignores them), file downloads, Grid org-wide tokens.

Sources (accessed 2026-11-08):
- Slack changelog, "Rate limit changes for non-Marketplace apps" (2025-05-29; FAQ updated for 2026-03-03): https://docs.slack.dev/changelog/2025/05/29/rate-limit-changes-for-non-marketplace-apps and https://api.slack.com/changelog/2025-05-terms-rate-limit-update-and-faq
- Slack changelog, "Slack API Terms of Service updates" (2025-10-13): https://docs.slack.dev/changelog/2025/10/13/api-terms-update ; API Terms archive (2025-05-29): https://slack.com/policy-archives/terms-of-service-api/2025-05-29
- Hunton, "Salesforce Locks Down Slack Data: Time to Review Your Slack API Terms" (Jul 2025): https://www.hunton.com/insights/legal/salesforce-locks-down-slack-data-time-to-review-your-slack-api-terms
- Computerworld, "Salesforce changes Slack API terms to block bulk data access for LLMs" (2025): https://www.computerworld.com/article/4005509/salesforce-changes-slack-api-terms-to-block-bulk-data-access-for-llms.html
- allanninal.dev, "conversations.history clamped to 15 objects and 1 per minute" (secondary): https://www.allanninal.dev/slack/non-marketplace-history-clamp/
- Slack Help, "Manage app approval for your workspace": https://slack.com/help/articles/222386767 ; "Set organization-level policies for apps": https://slack.com/help/articles/360038559694 ; free-workspace limits: https://slack.com/help/articles/27204752526611
- Slack Trust, "Data Management" (exports): https://slack.com/trust/data-management
- Slack scope `auditlogs:read` (Grid only, no message content): https://api.slack.com/scopes/auditlogs:read ; Strac on the Discovery API (vendor): https://www.strac.io/blog/slack-discovery-api
- Slack scope `connections:write` (Socket Mode): https://api.slack.com/scopes/connections:write
