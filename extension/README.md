# soloyolo for LinkedIn (Chrome extension)

Keeps soloyolo in sync with your LinkedIn messages, so you don't have to request a data export every time. Modelled
on Kondo (trykondo.com): it uses the LinkedIn session already open in Chrome to read your inbox through LinkedIn's
own web API, at a person's pace. Unlike Kondo, nothing goes to a cloud: messages go to `python -m spike serve` on
your Mac, and it never sends, reacts or marks anything read on LinkedIn.

On the phone, LinkedIn still comes in through the export (`python -m spike import-linkedin`, see
`docs/LINKEDIN.md`), and the app shows whatever the Mac has synced.

## Set it up

1. On the Mac, start soloyolo and get the pairing token:

   ```bash
   cd ~/soloyolo && .venv/bin/python -m spike --db ~/.soloyolo/soloyolo.db linkedin-token
   .venv/bin/python -m spike --db ~/.soloyolo/soloyolo.db serve
   ```

2. In Chrome, open `chrome://extensions`, turn on **Developer mode**, click **Load unpacked** and pick this
   `extension/` folder. Its options page opens.
3. Paste the token, **Save**, then **Sync now**. Be signed in to linkedin.com in the same Chrome profile.

After that it syncs every 20 minutes while Chrome is open. The toolbar icon shows `!` when a sync stopped; click
it to see why.

## What it does

- **First sync:** reads conversations active in the last 90 days, up to about 100 conversations and 100 messages
  each.
- **Later syncs:** asks LinkedIn only for conversations that changed since the last one, using LinkedIn's sync
  token, then fetches just their new messages.
- **Pacing:** waits 1.5 to 4 seconds between LinkedIn requests.
- **No data lost:** a conversation is marked as synced only after soloyolo has stored it. If the server is down,
  the next run picks up where this one stopped.
- **Requests:** sets the Origin and Referer of its own LinkedIn requests to the messaging page
  (`declarativeNetRequest`, scoped to this extension's requests only).
- **Group threads** become evidence, as in the export: they can close items but never create them. Company pages
  and sponsored messages are skipped.
- **Server side:** `spike/linkedin_live.py` receives the posts. Both paths use `linkedin_export.save`, so a person
  is keyed by their profile URL either way.

## Risk

This reads LinkedIn the way its own web app does, which LinkedIn's terms don't allow for third-party tools.
Kondo, Beeper and others do the same. Reading at this pace is unlikely to be flagged, but a restriction on your
account is possible. The export importer carries no risk and stays the fallback.

## Not verified yet (needs a signed-in run)

- **Query ids and response shapes:** taken from mautrix-linkedin on 2026-11-10 (`linkedin.js` holds them all).
  When LinkedIn changes them, a sync fails with "no conversations in the answer" and the ids need updating.
- **Profile URL form:** whether messaging returns the readable profile URL (`/in/priya-natarajan`) or a member id
  (`/in/ACoAA...`). The export uses the readable form. If messaging returns member ids, the same person gets two
  handles until the identity layer (`spike/identity.py`) merges them.

## Test

```bash
cd extension && node --test
```
