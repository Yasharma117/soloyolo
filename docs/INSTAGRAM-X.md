# Instagram and X: read the official exports

Reading DMs live is risky on both networks. Instagram's private API through browser cookies carries the
highest ban risk of any network we looked at. X's DM API needs a paid tier, and encrypted chats may not be
in it at all. Both networks hand you a copy of your own data, and reading that file carries no risk. So
`import-instagram` and `import-x` read those exports. A fresh export shows what's new, so the import is
something you rerun now and then. It isn't live.

Research done 2026-11-08. help.instagram.com and help.x.com were unreachable from the research machine,
so the format facts come from open-source parsers that read real exports, cited below. The request steps
are from those parsers' docs and from memory of the UI, and menus move.

## Getting the exports

**Instagram** (app or instagram.com, roughly 10 minutes to request; the email comes in hours, up to ~2 days):
1. Profile → ☰ → **Accounts Center** → **Your information and permissions** → **Download your information**.
2. **Download or transfer information** → pick the Instagram account → **Some of your information**.
3. Tick **Messages**. Also tick **Followers and following** and **Personal information**, which are small.
   They let the importer tell which sender is you and confirm usernames.
4. **Download to device** → Date range **All time**, Format **JSON** (not HTML), Media quality **Low**. The
   importer never opens media, so low keeps the zip small → **Create files**.
5. When the email arrives, download from the same page. The link expires after about 4 days. A big
   account comes as several zips; pass all of them.

```bash
python -m spike import-instagram ~/Downloads/instagram-*.zip
```

**X** (x.com or the app; the email comes in a day or more):
1. **More** → **Settings and privacy** → **Your account** → **Download an archive of your data**.
2. Confirm your password and the emailed or texted code → **Request archive**.
3. When X emails you, return to the same page → **Download archive**. The link expires after a few days.

```bash
python -m spike import-x ~/Downloads/twitter-*.zip
```

Both commands take a zip, several zips or the unzipped folder, plus `--me` when you can't be inferred.

## Instagram format (JSON)

| Fact | Confidence |
|---|---|
| Threads are at `your_instagram_activity/messages/inbox/<thread>/message_N.json` (2023+). Older exports used `messages/inbox/...` at the top level. The importer matches either one, at any depth [1][2][5]. | high |
| `message_requests/<thread>/` sits beside `inbox/`. A request you later accepted can stay there [1][2]. | high |
| `<thread>` is `<slug>_<numeric id>`, as in `kabirsharma_1784512345678901`. Deleted accounts appear as `instagramuser_<id>` and as the sender "Instagram User" [1][5]. | high |
| Whether the slug is the username or the squashed display name | **unverified** |
| A long thread splits into `message_1.json` (newest) … `message_N.json`. Within a file, the newest message comes first [3][4]. | medium |
| Top level: `participants[{name}]`, `messages[]`, `title`, `thread_path`, `is_still_participant`, `joinable_mode` (groups) [3][4]. | high |
| A message has `sender_name` (the display name, with no user id), `timestamp_ms`, `content`, `photos[{uri, creation_timestamp}]`, `videos`, `audio_files` (voice notes, `.mp4`), `share{link, share_text, original_content_owner}`, `reactions[{reaction, actor, timestamp}]`, `call_duration` (seconds), `is_unsent`, `is_geoblocked_for_viewer` [3][4]. | high, except `call_duration` and `is_unsent`: medium |
| **Mojibake.** Meta writes each UTF-8 byte as its own `\u00xx` escape, so 👍 arrives as `ð\u009f\u0091\u008d`. The fix is `s.encode("latin-1").decode("utf-8")`. It applies to names, titles and profile values too [3][4][6]. | high |
| A group has more than two participants. A 1:1 has exactly two, and the title is the other person's name [1]. | high |
| "Me": the export never marks you. `personal_information/personal_information/personal_information.json` has `profile_user[0].string_map_data.{Name,Username}.value`, and 2026 exports may carry Username only. The fallback is the one participant present in every thread [3][4]. | high |
| `following.json` (`relationships_following[]`) and `followers_N.json` list usernames. In 2025+ exports the username moved to `title`, and `string_list_data` keeps only `href` [4]. | medium |
| HTML variant: `message_N.html` with `<h2>` senders, timestamps like "Sep 22, 2017 6:33 am", plus `secret_conversations.html` (devices only, no messages) [1]. | high |
| End-to-end encrypted Instagram chats: their content isn't in the export, and Meta reportedly ended Instagram E2EE DMs after 8 May 2026 [11] | low |

**What the importer does.** Each 1:1 thread becomes messages on network `instagram`. The handle is
`thread:<numeric id>`, which survives renames and is never mistaken for a username. A group becomes
`instagram-group:<title>` evidence. A request is kept only if you replied. Photos, videos and voice notes
become `[photo]`, `[video]` and `[voice note]`. A share becomes `[link] <url>`. A call that connected
becomes `[call]`; missed, unanswered and "started" lines are dropped. Reactions, "Liked a message", unsent
messages, stickers and group notices are dropped too. An HTML export is refused with a hint to re-request
it as JSON. The `instagram` username attribute is written only when the thread slug is a username that
also appears in your following or followers lists. Message ids are hashes of thread id, time, sender and
text, so re-importing, passing the zip and the folder together, or splitting the export across zips adds
nothing new.

## X archive format

| Fact | Confidence |
|---|---|
| Each `data/*.js` file is `window.YTD.<feed>.partN = [ ... ]`, a JS assignment wrapping JSON. The 1:1 feed is `direct_messages`, the group feed `direct_messages_group`. Big feeds spill into `-part1.js` [7][8][9]. | high |
| `direct-messages.js`: `[{dmConversation: {conversationId: "<idA>-<idB>", messages: [{messageCreate: {...}}]}}]` [7][8]. | high |
| `messageCreate` has `id`, `senderId`, `recipientId`, `text` (with `&amp;` escapes and t.co links), `createdAt` (ISO 8601, UTC, ms), `urls[{url, expanded, display}]`, `mediaUrls[]`, `reactions[{senderId, reactionKey, eventId, createdAt}]`, `editHistory` [7][8]. | high, except `reactions`/`editHistory`: medium |
| An attachment's t.co link is in `text`, and in `urls` with `expanded` = `x.com/messages/media/<id>` [7]. | medium |
| `direct-messages-group.js`: `conversationId` is one numeric id. `messageCreate` has no `recipientId`, alongside `joinConversation`, `participantsJoin{userIds}`, `participantsLeave` and `conversationNameUpdate{name}`. `direct-message-group-headers.js` holds participant snapshots [7][8]. | high |
| `account.js`: `[{account: {accountId, username, accountDisplayName, email, createdAt}}]`, which gives your own id [8]. | high |
| Names for numeric ids: the archive has no user table. Follower and following files carry ids only. The only names are your tweets' `entities.user_mentions[{id_str, screen_name, name}]` and `in_reply_to_user_id_str`/`_screen_name` [7][8]. | high |
| A 2026-03-16 archive still had `direct-messages.js` and `direct-messages-group.js` [10] | high |
| Encrypted DMs and XChat (launched 2025 [12], apps pulled from the stores Sept 2026 [13]) in the archive | **unverified** |

**What the importer does.** You are `account.js`'s `accountId`, or else the one id in every 1:1
conversation id. Each 1:1 becomes messages on network `x` with handle `id:<user id>`, and the DM's own `id`
dedupes. Every person gets an `x_id` attribute, plus `x` (handle) and a display name when your tweets name
them. Anyone unnamed gets the placeholder "X user <id>" on a new card only; it never replaces a real
name. A group becomes `x-group:<conversationId>` evidence. The importer expands t.co links, unescapes HTML,
and turns `mediaUrls` into `[photo]` / `[video]` / `[voice note]`. A GIF alone is dropped. Joins, renames
and reactions are dropped.

## Could not verify

- Whether Instagram's thread slug is the username. That's why the username attribute is written only on
  a match with your connections.
- The exact wording of Instagram's call lines across locales, and whether `type: "Call"` still exists.
  The importer handles English and `call_duration`. Other locales' system lines may slip through as text.
- Whether a renamed contact's old messages carry the old `sender_name`. If they do, a 1:1 looks like a group.
- Whether X archives include encrypted DMs or XChat messages. Most likely they don't, because the keys
  live on devices.
- How X represents voice notes and calls in DMs. Voice notes are probably `dm_video` media and import
  as `[video]`. Calls aren't recognised at all.
- The pre-2020 Instagram `messages.json`, keyed by username, which isn't supported.

## Sources (fetched 2026-11-08)

1. ethanriverpage/memoria, `docs/Instagram-Messages-Schema.md`: paths by version, HTML, requests, deleted users.
2. chronicle-app/chronicle, `plugins/instagram/README.md`: file paths, owner from personal_information.json.
3. NotYuSheng/Doppelganger, `docs/sources/instagram.md`: request steps, mojibake, how "me" is identified.
4. chronicle-app/chronicle, `plugins/instagram/src/fixture.test-helper.js`: message, profile and following shapes (2025/2026).
5. GitHub code search: `your_instagram_activity/messages/inbox/` in exports dated 2024–2025 (e.g. Danfr4nk/wikibrain export-20250824).
6. joweich/chat-miner, `chatminer/chatparsers.py`: latin-1→UTF-8 repair.
7. timhutton/twitter-archive-parser, `parser.py`: DM fields, group events, id-to-handle lookups.
8. chronicle-app/chronicle, `plugins/twitter/README.md` and its fixture: prefixes, account.js keys, group headers.
9. rrika/cant-believe-its-not-twitter, `db.py`: the `window.YTD.direct_messages_group.part0 = ` prefix.
10. lhl/tweetxvault, `docs/ANALYSIS-archive-import.md`: an archive generated 2026-03-16.
11. vpncentral.com, "Meta will remove encrypted Instagram DMs after May 8, 2026".
12. MacRumors, 2025-11-17, "X Launches 'Chat' Encrypted DM Service"; TechCrunch, 2025-09-04.
13. Privacy Guides, 2026-09-15, "X's Encrypted Messenger, X Chat, Disappears From the App Store…".
