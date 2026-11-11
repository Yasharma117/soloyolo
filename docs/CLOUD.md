# Cloud plan: soloyolo for ten testers with no Mac

Written 11 November 2026. Every external fact was fetched that day; numbers in square brackets point to
the source list at the end. "Unverified" means no primary source was reached. Not legal advice.

## Recommendation in one paragraph

Run the models on a **hosted API at DeepInfra**, called directly, and run everything else on **one small
VM** with one folder per tester. The exact pair the project scored (Gemma 4 E4B reads, Gemma 4 12B checks)
**is not served by any hosted API I could find**: hosts carry only the 26B A4B and 31B sizes. So the first
step is to score those two on the 30-chat set (an afternoon, free on made-up data). If they hold up, use
them: about **$45 to $70 a month** at the stated volume, nothing kept by the provider, no GPU to look after.
If only the exact pair will do, the fallback is **Modal**, a serverless GPU that runs both models from
their open weights: about **$25 to $100 a month** after its free credit, with a cold start on every pass.

## 1. Where the models run

Gemma 4 comes in five sizes: E2B, E4B, 12B (released 3 June 2026), 26B A4B and 31B, all Apache 2.0 [1].
The 26B A4B is a mixture-of-experts model with 3.8B active parameters, which is why it is priced like a
small model [1].

| Host | Gemma 4 sizes served | $ per 1M in / out | Thinking on/off | JSON schema | Data terms |
|---|---|---|---|---|---|
| **DeepInfra** [2][3] | 26B A4B, 31B | 0.07 / 0.34, 0.20 / 0.40 | yes via OpenRouter; direct parameter unverified | yes [4] | not stored on disk, deleted after the reply, not trained on |
| Cloudflare Workers AI [5] | 26B A4B | 0.10 / 0.30; 10,000 neurons a day free | `chat_template_kwargs.enable_thinking` | accepted by the schema; the JSON-mode page omits Gemma 4 | not retained, not trained on; 300 requests/min |
| OpenRouter, paid [4][6] | 26B A4B, 31B through 15 to 19 hosts | 0.025 / 0.076 to 0.15 / 0.60 (26B) | `reasoning: {enabled}` | most hosts | `provider: {zdr: true}`; set the account to "ZDR only"; 5.5% fee on credits |
| Novita [4] | 26B A4B, 31B | 0.13 / 0.40, 0.14 / 0.40 | yes | JSON object | listed as no-retention by OpenRouter; own terms not read |
| Google Gemini API [7] | 26B A4B, 31B | free tier only, no paid tier | `thinkingLevel` | unverified | free-tier terms: used to improve products, humans may read it. **Not for real chats** |
| Google Vertex [7] | 26B A4B | 0.15 / 0.60 | unverified | unverified | no training; abuse logging may apply |
| Groq [8] | none (gpt-oss-20b at 0.075 / 0.30, about 1,000 tokens/s) | | | | not read |
| Together, Fireworks, Cerebras, Hyperbolic, Nebius | none listed among OpenRouter's Gemma 4 hosts [4]; own catalogues not checked | | | | unverified |

Rate limits for a new DeepInfra account were not verified. OpenRouter's free Gemma endpoint is served by
Google's free tier, so the same "not for real chats" applies [6][7].

**Cost, with the arithmetic.** Per chat (the brief's 3,000-token thread; the rest is my estimate): the
reader takes 4,000 tokens in (thread plus instructions) and 1,300 out (300 of answer, about 1,000 of
thinking); the checker takes 4,200 in and 200 out.

| Per 1,000 chats, DeepInfra list price | In | Out | Cost |
|---|---|---|---|
| Reader, 26B A4B | 4.0M × $0.07 | 1.3M × $0.34 | $0.72 |
| Checker, 31B | 4.2M × $0.20 | 0.2M × $0.40 | $0.92 |

- **Steady state:** 60 chats an hour, all day, is 43,200 chats a month. Checking every chat: 43.2 × $1.64 =
  **$71**. The code only calls the checker when the reader found something; if that is 3 chats in 10 (a
  guess), 43.2 × $1.00 = **$43**.
- **Onboarding ten users:** 10 × 300 chats = 3,000 chats × $1.64 = **about $5, once**.
- The cheapest no-retention host on OpenRouter (PrimeIntellect, 0.025 / 0.076) cuts the reader to $0.20 per
  1,000 chats, at the price of a host nobody here has vetted.

**Running the exact pair yourself.** At 4-bit, E4B needs 4.5 GB and 12B 6.7 GB [1], so both fit on one
24 GB card.

| Option | Price | Monthly at this volume | Fit |
|---|---|---|---|
| **Modal**, L4 24 GB [9] | $0.80/h, per second, load time billed; $30 a month free | 48 passes a day × 2.5 to 6 min = 60 to 144 h × ~$0.90 = $55 to $130, less $30 | scale-to-zero suits a pass every 30 minutes; start-up is "tens of seconds to a few minutes" |
| RunPod serverless, 24 GB [10] | $0.75/h, cold start billed | similar, no free credit | same |
| Always-on RunPod A5000, secure [10] | $0.27/h | $197 | no cold start; pays for 23 idle hours a day |
| Replicate, Beam, Baseten [11] | T4 $0.81/h; 4090 $0.69/h; L4 $0.85/h with a 15-minute scale-down | no better | |
| Cloudflare Containers [5] | no GPU | | |

The minutes per pass are a guess: no vendor publishes a load time for a 10 GB model, and nobody has run
this workload on an L4.

**Primary: DeepInfra direct**, 26B A4B and 31B. **Fallback: Modal**, the exact pair. Cloudflare is a spare
hosted route for the 26B, since `SOLOYOLO_LLM_URL` already points anywhere.

## 2. The council by task

| Job | Model | Evidence |
|---|---|---|
| Reading new messages | Gemma 4 26B A4B, thinking on | **Guess.** Measured: E4B with thinking finds 100% and 20% of its list is false |
| Checking | Gemma 4 31B, thinking off | **Guess.** Measured: the E4B + 12B pair lists nothing false but finds only 70%, because the checker removed real items; its instructions are fixed and it is being re-scored. Treat the pair's quality as still being tuned |
| Triage | none | Measured: small-model triage loses real items. It would save under $1 per 1,000 chats |
| First sync | the same two, eight calls at a time, chats active in the last 14 days first | A hosted API has no queue to outrun, so a faster model buys nothing. Run 6 found the useful window is days, so old chats can wait. About 90 minutes for 3,000 chats (guess) |
| Cross-chat closure | off for the pilot | Measured with Claude: 0 of 3 right on other 1:1 chats. Not scored on any open model |

## 3. The server

**Where.** Oracle's free tier is now 2 OCPU and 12 GB (confirmed), 200 GB disk, 10 TB out, with regions in
Mumbai and Hyderabad [12]. It is enough. The catch: Oracle may reclaim an instance whose CPU, network and
memory all stay under 20% for seven days [12], and this server will look exactly like that. That upgrading
to pay-as-you-go prevents it is a forum claim, not Oracle's [12]. **Paid fallback: DigitalOcean Bangalore,
2 GB, $12 a month** [13]: an Indian region, a published price, no reclaiming. Hetzner CX23 (€5.99) and OVH
VPS-1 ($4.54) are the $5 options, in Europe only, and Hetzner showed no stock today [13]. Build so that
moving hosts is a restore from backup.

**Layout.**

- `/srv/soloyolo/users/<id>/` holds one tester's `soloyolo.db`, `accounts/` and logs. This is today's
  `~/.soloyolo`, once per tester. Deleting a tester is deleting a folder.
- One `connectord --data <folder> sync` per tester, as a systemd template unit. connectord opens the first
  device in its folder, so one process per tester is what the code already does.
- One API process (`spike serve`) on 127.0.0.1 behind Caddy, which gets the TLS certificate. A domain is
  needed (about $12 a year, unverified).
- One reader loop: for each tester, `watch --once` every 30 minutes.

**Sign-in.** An invite code per tester, swapped once for a long random token the app keeps. No email, no
passwords. The token picks the folder.

**The app.** The web build already talks to whatever origin served it, so a tester opens
`https://<domain>` on their phone and installs nothing. A native build sets `EXPO_PUBLIC_SOLOYOLO_URL`.

**Encryption and keys.** Put `/srv/soloyolo` on an encrypted volume whose passphrase the owner types after
a reboot. That protects a reclaimed disk or a snapshot. It does not protect testers from the operator: the
owner holds the key and can read everything. Say so in the consent.

**Backups.** Nightly `sqlite3 .backup` of each store, encrypted to a key kept on the owner's laptop, sent
to Cloudflare R2 or Backblaze B2 (10 GB free at either) [14]. Leave `accounts/` out, as on the Mac:
relinking is cheap.

**Monitoring.** The digest's existing warnings (chats waiting, sync stale), per tester, counts only, sent
to the owner's Telegram; plus an outside ping on a health URL.

**What changes in the code.**

| Area | Change | Size |
|---|---|---|
| `spike/server.py` | token check, pick the store per request, allow the public host name | medium |
| `spike/setup.py` | one connectord per tester (drop the `pgrep` single-process check), upload exports instead of reading `~/Downloads`, offer the council as a reader | medium |
| `spike/council.py`, `watch` | the council on the live store (in progress elsewhere) | medium |
| `scripts/` | systemd units and a provision/delete-tester script in place of launchd | small |
| `connectord` | exit non-zero when the first connect fails; surface `logged_out` to the app | small |
| `mobile/src/lib/api.ts` | send the token; an invite-code screen; a consent screen | small |
| `spike/telegram.py` | one bot, a chat id per tester | small |

**At 1,000 users** this design stops: real accounts, a job queue, several machines, a key per user that the
operator cannot use alone, signed contracts with the model host, and above all not holding WhatsApp keys at
all. `docs/ANDROID-LISTENER.md` is the route that keeps reading on the phone.

## 4. Consent and risk

What each tester must agree to, in these words or plainer:

1. **The person running this can read your WhatsApp messages.** Your account is linked to their server like
   WhatsApp Web. You can end it at any time: WhatsApp → Linked devices → Log out.
2. **WhatsApp may restrict or ban your number.** Its terms let it suspend accounts for any reason, and its
   help pages say unofficial apps can lead to a ban [15]. Users of the library report warnings and forced
   logouts, some on accounts that never sent anything [15]. Whether a data-centre address adds risk is
   unverified.
3. **Your chat text is sent to a model company** (DeepInfra, in the US), which says it does not store or
   train on it [3].
4. **Other people's messages are in there too**, and they have not been asked.

India's DPDP Act: the Rules were notified on 13 November 2025, and the main duties (notice, consent,
safeguards, breach reports, erasure) start about 12 or 13 May 2027 [16, secondary sources]. Until then
section 43A of the IT Act and the 2011 rules apply [16]. Build to the new law now: a plain itemised notice
and a clear yes; withdrawal as easy as consent; a named contact; breach notice to those affected without
delay and a report within 72 hours; no transfer ban list exists yet [16]. The Act exempts an individual's
"personal or domestic" use; whether a pilot run for friends counts is open, so do not rely on it.

**Deletion on request:** stop the tester's connectord, delete the folder, let backups roll off within 30
days, and ask them to log the device out on their phone. Write that as one script before the first tester
joins.

## 5. Phases

| Step | What it unblocks | Main risk |
|---|---|---|
| 0. Score 26B A4B and 31B on the 30-chat set | the hosted-or-Modal decision | they score worse than the pair |
| 1. Point the owner's Mac at DeepInfra (`SOLOYOLO_LLM_URL`, key, council) | **no Claude subscription**; real cost and speed figures | recall still being tuned |
| 2. The server with one user, the owner, for a week | proof that sync, reading and the digest run with no Mac | a ban or logout from a server address; Oracle reclaiming |
| 3. Sign-in, per-tester folders, consent and delete; two testers, then ten | "no Mac needed" | holding other people's keys |
| 4. Backups, monitoring, extension and Telegram per tester | leaving it unattended | time |

## Decisions that are the owner's

- Accept the 26B and 31B sizes if they score well, or insist on the exact pair and run a GPU.
- Oracle free with the reclaim risk, or $12 a month from day one.
- Whether to hold testers' WhatsApp keys at all, and who else has access to the server.
- A spending cap at the model host, and how long raw messages are kept.
- The consent wording, and whether to get it reviewed by a lawyer.

## Sources (all fetched 2026-11-11)

1. Gemma 4 sizes, licence, memory, thinking: https://huggingface.co/google/gemma-4-E4B-it, https://ai.google.dev/gemma/docs/releases, https://ai.google.dev/gemma/docs/core, https://ai.google.dev/gemma/docs/capabilities/thinking
2. DeepInfra catalogue and prices: https://deepinfra.com/models?q=gemma
3. DeepInfra data: https://docs.deepinfra.com/account/data-privacy
4. OpenRouter per-host listings (hosts, prices, parameters): https://openrouter.ai/api/v1/models, https://openrouter.ai/api/v1/models/google/gemma-4-26b-a4b-it/endpoints, https://openrouter.ai/api/v1/models/google/gemma-4-31b-it/endpoints
5. Cloudflare: https://developers.cloudflare.com/workers-ai/models/gemma-4-26b-a4b-it/, https://developers.cloudflare.com/workers-ai/platform/pricing/, https://developers.cloudflare.com/workers-ai/platform/limits/, https://developers.cloudflare.com/workers-ai/platform/data-usage/, https://developers.cloudflare.com/containers/pricing/
6. OpenRouter retention, routing, fee: https://openrouter.ai/docs/guides/features/zdr, https://openrouter.ai/docs/guides/routing/provider-selection, https://openrouter.ai/pricing, https://openrouter.ai/api/v1/endpoints/zdr
7. Google: https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api, https://ai.google.dev/gemini-api/docs/pricing, https://ai.google.dev/gemini-api/terms, https://cloud.google.com/vertex-ai/generative-ai/pricing
8. Groq: https://console.groq.com/docs/models
9. Modal: https://modal.com/pricing, https://modal.com/docs/guide/cold-start, https://modal.com/docs/examples/vllm_inference
10. RunPod: https://www.runpod.io/pricing, https://docs.runpod.io/serverless/pricing
11. https://replicate.com/pricing, https://www.beam.cloud/pricing, https://docs.baseten.co/deployment/resources
12. Oracle: https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm; the change, third party: https://www.infoq.com/news/2026/07/oracle-cloud-free-tier-limits/; forum claim: https://community.oracle.com/CustomerConnect/discussion/671904/reclamation-of-idle-compute-instances
13. https://www.digitalocean.com/pricing/droplets, https://www.hetzner.com/cloud/cost-optimized/, https://www.ovhcloud.com/en/vps/
14. https://developers.cloudflare.com/r2/pricing/, https://www.backblaze.com/cloud-storage/pricing
15. WhatsApp: https://www.whatsapp.com/legal/terms-of-service, https://faq.whatsapp.com/1217634902127718, https://github.com/tulir/whatsmeow/issues/810, https://github.com/tulir/whatsmeow/issues/561
16. DPDP, from an unofficial mirror and law-firm notes (government sites refused the fetch): https://dpdpa.com/dpdparules/rule1.html, https://dpdpa.com/dpdparules/rule7.html, https://www.dpdpa.com/dpdpa2023/chapter-1/section3.html, https://acuitylaw.co.in/notification-of-digital-personal-data-protection-law-in-india-certain-key-timelines/, https://www.legal500.com/intelligence/india/privacy/faqs-on-the-digital-personal-data-protection-act-and-rules
