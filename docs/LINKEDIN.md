# LinkedIn data export: format notes

What `spike/linkedin_export.py` (`python -m spike import-linkedin`) relies on. LinkedIn has no personal messaging
API, and cookie-based clients risk a ban, so soloyolo reads only the official "Get a copy of your data" export.
Researched 2026-11-08. linkedin.com could not be reached from the research sandbox, so **LinkedIn's own help
pages were not read.** Everything below comes from parsers and docs written against real exports (sources at the end).

## Getting it

1. On the desktop site (the mobile app doesn't offer this): **Me → Settings & Privacy → Data privacy → Get a copy
   of your data**. The direct link is `linkedin.com/mypreferences/d/download-my-data`.
2. Choose **Download larger data archive**, then **Request archive**.
3. LinkedIn emails you a link. It's often two emails: "The first installment of your LinkedIn data archive is
   ready!" (minutes to hours), then "Your full LinkedIn data archive is ready!" (within 24 hours, sometimes up to
   48). Each link works for about 72 hours.
4. `python -m spike import-linkedin ~/Downloads/Complete_LinkedInDataExport_*.zip`. Pass both zips if you got two.
   Passing both, or importing again later, adds only what's new.

The other option, "Want something in particular?", picks single categories and arrives in about 10 minutes.
Sources disagree about whether it offers Connections and Messages (Hestia and one prompt library say yes, the
opportun docs say no). Syftdata and several others say only the larger archive reliably has `messages.csv`.
**Confidence: medium.**

## Container

- It's a **zip**, named `Complete_LinkedInDataExport_MM-DD-YYYY.zip` or `Basic_LinkedInDataExport_MM-DD-YYYY.zip`.
  The date is month first (`08-30-2025` has been seen). The importer uses that date as the attributes' `ts`.
  **High.**
- Most CSVs sit at the root, with some subfolders (`Jobs/`, `Articles/Articles/`). The importer finds files by
  name anywhere in the zip or folder. **High.**
- The files are UTF-8, sometimes with a BOM. Some exports show accents double-encoded (`Ã©` for `é`); the
  importer repairs that only when the repair decodes cleanly. **Medium** (one source).

## Files used

| File | Columns | Notes |
|---|---|---|
| `messages.csv` | `CONVERSATION ID, CONVERSATION TITLE, FROM, SENDER PROFILE URL, TO, RECIPIENT PROFILE URLS, DATE, SUBJECT, CONTENT, FOLDER, ATTACHMENTS, IS MESSAGE DRAFT, IS CONVERSATION DRAFT` | Every header name is quoted. Older exports (2023) lack `RECIPIENT PROFILE URLS`, `ATTACHMENTS` and the draft columns. **High** |
| `Connections.csv` | `First Name, Last Name, URL, Email Address, Company, Position, Connected On` | Preceded by a `Notes:` line, a quoted paragraph about missing emails, and a blank line. **High** |
| `Invitations.csv` | `From, To, Sent At, Message, Direction, inviterProfileUrl, inviteeProfileUrl` | `Direction` is `INCOMING` or `OUTGOING`. **High** |
| `Profile.csv` | `First Name, Last Name, Maiden Name, Address, Birth Date, Headline, Summary, Industry, Zip Code, Geo Location, Twitter Handles, Websites, Instant Messengers` | No profile URL. **High** |

A full export has about 39 other files (Positions, Skills, Shares_<id>, Reactions_<id>, Ads, Learning, ...). They're
ignored. `guide_messages.csv`, `learning_coach_messages.csv` and `learning_role_play_messages.csv` share the message
schema but are LinkedIn's AI coach chats, not people, so they're ignored too.

## messages.csv quirks

- **Dates:** `DATE` is `YYYY-MM-DD HH:MM:SS UTC`. `Connected On` is `DD Mon YYYY` (e.g. `14 Mar 2024`), a date
  with no time. `Sent At` in Invitations is `M/D/YY, H:MM AM` with no zone; the importer assumes UTC for it. **High**
  for the first two, **low** for the Invitations zone.
- **Rows** are one per message, newest first, and grouped by `CONVERSATION ID` (a base64-ish `2-…==` string).
  There's no per-message id, so the importer hashes conversation, date, sender, subject and content. **High**
- **Multiline content** is quoted, with `""` for quotes. Some files (Comments) use `\"`; the importer falls back
  to that only if rows break. **High** for `""`, **medium** for whether messages ever use `\"`.
- **HTML bodies:** sponsored messages and InMail often come as editor HTML (`<p class="spinmail-quill-editor…">`).
  They're stripped to text. **High**
- **`SUBJECT`:** usually empty. InMail and recruiter messages have one, and the importer puts it before the body.
  **Medium**
- **`FOLDER`:** `INBOX` for most rows, `ARCHIVE` (your archived threads, which include some spam), and `SPAM`.
  `SPAM` is skipped; `ARCHIVE` is kept. **Medium:** there's no list of every value.
- **Sponsored:** `CONVERSATION TITLE` = `Sponsored Conversation`, `FROM` = `LinkedIn Member`, an empty sender URL,
  and `%FIRSTNAME%` placeholders. Skipped. **High** (seen in several real exports)
- **`LinkedIn Member` with no URL** also marks a deleted or hidden account. Threads with no other profile URL are
  skipped. **Medium**
- **Group threads:** `TO` lists every other name, and `RECIPIENT PROFILE URLS` lists URLs separated by commas or
  semicolons (sources differ). URLs can be missing for members you can't see, so the URL and name lists don't
  line up. The importer calls a thread a group if it has more than one other URL or more than one other name; a
  name like `Dana Kim, MBA` counts as one name. `CONVERSATION TITLE` is the group's name, usually empty for 1:1s.
  **Medium**
- **Attachments:** `ATTACHMENTS` holds expiring signed `linkedin.com/dms/…` links, and the files themselves aren't
  in the zip. An attachment with no text is stored as `[attachment]`. **Medium**
- **Drafts:** the `IS MESSAGE DRAFT` and `IS CONVERSATION DRAFT` columns. Skipped when `Yes`/`true`. **Low** (the
  values were seen in one parser only)

## Who is me

The export never labels the owner. In order, the importer uses:
1. `--me <profile URL>`, or `--me "Your Name"` if that name matches exactly one sender URL.
2. Invitations: the inviter on `OUTGOING` rows and the invitee on `INCOMING` rows.
3. The one profile in every conversation, with the name in Profile.csv breaking a tie (when every thread is with
   the same person).

**High** that the owner's URL appears as sender or recipient in every row. Profile URLs are normalized to
`https://www.linkedin.com/in/<slug>`, lower case and percent-decoded, without country subdomains, query strings
or trailing slashes. Connections and messages for the same person therefore share one handle.

## Not verified

- LinkedIn's help-center wording and timings, and the category list of the "particular" export.
- Whether message rows stay byte-identical between exports. Dedupe depends on it: an edited body imports again.
- The zone of Invitations `Sent At`, every `FOLDER` value, how Sales Navigator and Recruiter InMail appear
  (Recruiter has its own export), and whether `Connected On` is ever localized.

## Sources (read 2026-11-08 on GitHub; commit dates weren't readable, and the data in them is 2023 to 2026)

- NolwennD/linkedin-archive-explorer `docs/archive-structure.md`: every file and header of a real 2026 Complete
  export, plus the Connections preamble and the quoted messages header.
- activout/Activout.MemberData `skills/member/SKILL.md`: columns and date formats (LinkedIn's DMA API, same keys).
- thephm/linkedin_md `docs/linkedin_export.md`: `FOLDER` values, `Ã©` encoding. chronicle-app/chronicle
  `LinkedInArchiveMessagesExtractor.ts`: group name/URL misalignment, HTML bodies, attachment links.
- lildaddyo/lnkd-engine, syftdata/linkedin-claude-plugin, gbrlpzz/ppl-kit, moritzWa/orbit, Yosolita1978/LinkedIn-Agent:
  inferring "me", formats, the sponsored filter. Public sample rows (Shreeyashj, predator-911, steveraaen; shape only).
- hestiaAI/data-catalog `workshop/linkedin.md`, bgoleno/opportun `docs/guide/network.md`: two-email delivery,
  72-hour link, "larger archive" advice.

## Live sync (the Chrome extension)

The export is a snapshot. To stay current, `extension/` reads LinkedIn's own web API through the session in Chrome
(as Kondo does) and posts to `/api/live/sync` (`spike/live.py`; `/api/linkedin/sync`, where its first version
posted, still works). The same extension can read Instagram and X, each behind its own switch
(`docs/INSTAGRAM-X.md`). Setup, pacing, permissions, risk and what's unverified: `extension/README.md`. Both
paths go through `linkedin_export.save()`. Its `_unseen` check matches a message across
the two by person, direction, text and a 2-second window, because the export rounds times to the second and gives
messages no stable id. Group lines aren't matched across the two yet, so a group line can be stored twice as
evidence. That's harmless: evidence only closes items.
