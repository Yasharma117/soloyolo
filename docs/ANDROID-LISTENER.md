# Android listener: messages from notifications

**Recommendation.** Build a small sideloaded Android app on the official `NotificationListenerService`, with a
package allowlist. It reads the `MessagingStyle` content of incoming message notifications, drops one-time
codes on the phone, keeps a durable queue there, and uploads batches over **Tailscale** to the Mac with a
pairing token. There's no reverse engineering, no logins and no ban risk. What it can see is what the
notification shows, and the chaser signal ("any update?") is exactly that: an incoming message from
someone else. It is a feed of incoming messages with display names only. It is not a sync.

Built: `android/` (it compiles and the APK builds; 5 JVM tests), `spike/notify_ingest.py`,
`python -m spike import-notifications batch.json`, and `spike/test_notify.py`.
Researched 2026-11-08. Confidence: **H** = official docs or source code, **M** = consistent secondary
reports, **L** = expected behaviour, to be checked on the device.

## What a listener can read (H)
- `StatusBarNotification`: `packageName`, `key` (stable per notification; reposts reuse it), `postTime`,
  `notification.flags` (`FLAG_GROUP_SUMMARY`), `category` (`msg`) and `extras`. [1]
- `extras`: `EXTRA_TITLE` and `EXTRA_TEXT`. For MessagingStyle apps there is also `EXTRA_MESSAGES`, "an array
  of MessagingStyle.Message bundles", up to 25 kept. Each message has text, a timestamp in ms, and a sender
  `Person`, which is **null for the user's own messages**. There are also `EXTRA_CONVERSATION_TITLE`,
  `EXTRA_IS_GROUP_CONVERSATION` (API 28+), `EXTRA_MESSAGING_PERSON` (you), `EXTRA_HISTORIC_MESSAGES` and
  `EXTRA_REMOTE_INPUT_HISTORY` (your recent inline replies). [1][2]
- `NotificationCompat.MessagingStyle.extractMessagingStyleFromNotification(n)` (androidx) parses all of this
  for us. Apps are told not to set a conversation title on 1:1 chats, so for a 1:1 the chat is the other
  sender. [2]
- A notification gives **no phone number and no user id**, only the display name as that app shows it.
  Identity is therefore low-confidence by design (see "Store mapping").

## Per-app reality
| App (package) | Shape | 1:1 | Groups | Quirks | Conf. |
|---|---|---|---|---|---|
| WhatsApp (`com.whatsapp`, `.w4b`) | MessagingStyle, one notification per chat, plus a group summary | sender = contact name as saved on the phone | conversation title = group name, sender per message | ongoing "Checking for new messages"; preview off gives a "New message" placeholder; muted chats post nothing | M [3][4] |
| Telegram (`org.telegram.messenger`) | MessagingStyle per dialog, `Person` per sender, timestamps are server `date`×1000 (stable) | name | `setGroupConversation(true)` for chats; channels are not groups | per-chat or global "preview off" gives "New message" or "You have a new message"; summary notification | **H** (source) [5] |
| Google Messages (`com.google.android.apps.messaging`) | MessagingStyle, conversation shortcuts (Google's reference conversation app) | contact name or number | RCS/MMS groups flagged | bank/OTP senders: Android 15 redacts OTPs; we drop codes and business sender ids such as `VM-HDFCBK` | M [6] |
| Slack (`com.Slack`) | MessagingStyle | DM: sender | channel as conversation title | workspace in the title or subtext, so the handle becomes `notif:name@workspace` | L |
| Instagram (`com.instagram.android`) | DMs show as conversation notifications | username or name | group DMs | the same package posts likes and follows, so we keep only MessagingStyle or `category=msg` | L |
| LinkedIn (`com.linkedin.android`) | messages vs. network alerts | sender name | rare | job and profile-view alerts share the package; the same `msg` filter applies | L |
| X (`com.twitter.android`) | DMs | display name | group DMs | DM text may be hidden ("sent you a Direct Message"), which our placeholder filter drops | L |

**Before trusting the L rows**, run the listener for a week with each app, then check the queue for wrong
senders and missed DMs.

## Limits
- **Incoming only, mostly.** Replies you type inside the app clear the notification and are never seen. Inline
  replies from the shade usually come back as a repost with your message (null sender). We store those as
  `from_me` (M) [2][7]. So "assumed done" can't rely on seeing your own reply here. The chaser signal can,
  because chasers are incoming.
- **Chat open in the foreground:** WhatsApp and Telegram don't notify for the chat you're looking at (M).
  Messages that arrive while you're in the chat are missed.
- **Muted chats:** no notification, so nothing to read (M). Notifications the app posts silently are still
  read, because the manifest disables only the `ongoing` filter type.
- **Previews off / lock-screen privacy in the app:** we get placeholders, and they're dropped.
- **Doze:** the system still delivers posts to a bound listener. Uploads run through WorkManager with a
  network constraint, so in deep Doze they wait for a maintenance window. That's fine for a morning nudge. (M)
- **OEM battery killers.** Xiaomi/HyperOS: turn Autostart on and set battery to "No restrictions". Samsung:
  remove the app from Sleeping and Deep sleeping apps. Oppo/Realme: allow auto-launch and set "Don't
  optimise". The app asks for the battery-optimisation exemption and calls `requestRebind` when opened. (M) [8]
- **Android 13+ restricted settings:** for a sideloaded APK, notification access is greyed out until you
  open App info, then ⋮, then "Allow restricted settings". Android 15 extends the list. (M) [9][10]
- **Android 15 OTP redaction:** untrusted listeners get redacted content when the system detects an OTP. [11]
  The permission involved (`RECEIVE_SENSITIVE_NOTIFICATIONS`) is role- or signature-only, but it suits us:
  we want codes dropped anyway. The placeholder text ("Sensitive notification content hidden") is filtered. (H/M) [12]
- **Android 15:** apps that are force-stopped lose their pending intents, and network calls outside a valid
  lifecycle fail. Both are handled by using WorkManager. [11]

## Play Store vs. sideload
Play treats notification access as sensitive user data. It needs a prominent disclosure and a policy-compliant
core purpose, and the battery-exemption permission is restricted on Play (M; Play's policy pages could not be
fetched from this environment, so check them before any listing) [13]. For one user, **sideload a debug or
self-signed APK** (`cd android && ./gradlew assembleDebug`, then `adb install`). There's no review, and the
restricted-settings step above is a one-time tap.

## Transport to the Mac
| Option | Different networks | Mac asleep | Setup | Verdict |
|---|---|---|---|---|
| LAN HTTP + mDNS + token | no | lost unless queued | low | home only |
| **Tailscale + phone queue + token** | **yes** (WireGuard, NAT traversal) | queue waits, retries with backoff | Tailscale on both, `tailscale serve` on the Mac | **pick** |
| Phone queue, batch upload to a cloud relay | yes | yes | needs a server | breaks local-first |
| Encrypted file in a synced folder (Drive or Syncthing) | yes | yes | key management; Android file-sync is flaky in the background | fallback |

**Pick: a durable phone-side queue, batch `POST {url}/v1/notifications` with `Authorization: Bearer <token>`,
sent over Tailscale.** The transport is WireGuard end to end with no relay that can read the data. The phone keeps rows until it gets a
2xx, so a sleeping or unreachable Mac loses nothing. Cost: Android allows one VPN at a time, so Tailscale
takes the VPN slot [14]. On the Mac, `tailscale serve --https=443 localhost:<port>` gives a real
`*.ts.net` certificate [15]. The Mac receiver should be a small connectord endpoint, **not built here**:
it checks the token, writes the body to an inbox, and runs `import-notifications` (same JSON). Pairing:
the Mac makes a random 32-byte token and shows it as a QR or text code; you paste it into the app. Rotate it by re-pairing.

## Privacy, on the phone
1. **Allowlist by package** (`Allowlist.kt`, mirrored in `notify_ingest.NETWORKS`). Other apps return before
   their extras are read. Banks, email and authenticators are never touched.
2. **Drop OTP-like text** (`Privacy.isOtp`). This covers code words with a 4–8 digit or `ABC-123` code,
   "code is 1234", and "123456 is your X code". Times like "1830" pass.
3. Drop group summaries, ongoing notifications, placeholders and redacted content. For plain (non-MessagingStyle)
   notifications, keep only `category=msg`, which removes likes and job alerts.
4. The queue is app-private SQLite with `allowBackup=false`. Sent rows are pruned after 7 days.
5. Python repeats checks 1–2, and drops SMS from business sender ids (bank alerts reach the store only via
   `import-sms`).

## Store mapping (`spike/notify_ingest.py`)
- **Network** comes from the package: whatsapp, linkedin, instagram, x, slack, telegram, sms.
- **Handle** is `notif:<sender>`, or `notif:<sender>@<conversation title>` when the title is something else.
  `is_low_confidence()` marks it. Two "Priya"s on one app merge, and Priya on two apps stays two people
  until something better links them. In a 1:1, your replies join the last sender's thread.
- **Dedupe:** `remote_id = sha256(package, conversation, sender, text, message ts)`, so a repost that
  carries old messages adds nothing. Plain notifications have only a post time, which moves on repost.
  The phone pins the first-seen time per (key, text), and Python collapses same-text rows within 15 minutes.
  A message already synced by connectord or an export (same network, text and direction, within 2 minutes)
  is skipped. The same text days later is kept: asking again is the chaser signal.
- **Group conversations** become evidence (`<network>-group:<title>`, sender `me` for you), never people.

## Open questions
- Should WhatsApp notifications be ingested at all when connectord syncs WhatsApp? The cross-source check
  covers exact duplicates, but it creates a second, name-only person for the same contact.
- Linking `notif:` people to real handles (a phone number from contacts, a WhatsApp JID): whose step is that?
- Instagram, LinkedIn and X shapes are unverified (the L rows). They need a week of real capture.

## Sources (accessed 2026-11-08)
1. NotificationListenerService / Notification reference, developer.android.com/reference/android/app/Notification
2. NotificationCompat.MessagingStyle (androidx.core 1.1+), developer.android.com/reference/androidx/core/app/NotificationCompat.MessagingStyle
3. Stack Overflow: "WhatsApp uses MessagingStyle… read EXTRA_MESSAGES" (2018), stackoverflow.com/a/49181208
4. Open-source logger adapters (WhatsApp/Telegram via EXTRA_MESSAGES), github.com/Athish06/dt-notify (2025)
5. Telegram for Android `NotificationsController.java` (master), github.com/DrKLO/Telegram
6. People and conversations, developer.android.com/develop/ui/views/notifications/conversations
7. Android N notifications (direct reply, remote input history), android-developers.googleblog.com (2016-06)
8. Per-OEM keep-alive guides (secondary; see dontkillmyapp.com), help.biolovision.net, 2024–25
9. Android Authority, "Android 15 restricted settings" (2024-09), androidauthority.com/android-15-restricted-settings-sideloading-3481098
10. 9to5Google, "Android 15 sideloaded apps restrictions" (2024-09-12)
11. Android 15 behavior changes: all apps (OTP redaction, stopped state, network), developer.android.com/about/versions/15/behavior-changes-all
12. Android Authority, Android 15 2FA codes and trusted listeners (2024), androidauthority.com/android-15-two-factor-authentication-codes-3492585; KDE Connect MR 492
13. Play Console, "Permissions and APIs that Access Sensitive Information" (2025), support.google.com/googleplay/android-developer/answer/16558241 (not fetched)
14. Tailscale FAQ, "Can I use Tailscale alongside other VPNs?", tailscale.com/docs/reference/faq/other-vpns
15. Tailscale Serve, tailscale.com/docs/features/tailscale-serve
