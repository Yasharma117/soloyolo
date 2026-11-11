# soloyolo sync (Chrome extension)

Keeps soloyolo in sync with your LinkedIn, Instagram and X messages, so you don't have to request a data export every
time. Modelled on Kondo (trykondo.com): it uses the sessions already open in Chrome to read your inboxes through
each site's own web API, at a person's pace. Unlike Kondo, nothing goes to a cloud: messages go to
`python -m spike serve` on your Mac. It never sends, reacts, types or marks anything read on any network.

LinkedIn is on by default. Instagram and X are off until you turn them on in the options page.

On the phone, these networks still come in through their exports (`docs/LINKEDIN.md`, `docs/INSTAGRAM-X.md`), and
the app shows whatever the Mac has synced.

## Set it up

1. On the Mac, start soloyolo and get the pairing token. One token covers all three networks:

   ```bash
   cd ~/soloyolo && .venv/bin/python -m spike --db ~/.soloyolo/soloyolo.db linkedin-token
   .venv/bin/python -m spike --db ~/.soloyolo/soloyolo.db serve
   ```

2. In Chrome, open `chrome://extensions`, turn on **Developer mode**, click **Load unpacked** and pick this
   `extension/` folder. Its options page opens.
3. Paste the token and **Save**.
4. Turn on the networks you want. Be signed in to linkedin.com, instagram.com and x.com, as needed, in the same
   Chrome profile. Then **Sync now**.

After that it syncs every 20 minutes while Chrome is open, one network after another. The toolbar icon shows `!`
when a network's sync stopped; the options page says which one and why.

## Permissions

- `cookies`: reads the session cookies the sites already set, to address requests to you: LinkedIn's `JSESSIONID`
  (its csrf token), Instagram's `csrftoken` and `ds_user_id`, X's `ct0` and `twid`. It never changes a cookie.
- `storage`: the server address, the token, which networks are on, and each network's sync state.
- `alarms`: the sync every 20 minutes.
- `declarativeNetRequestWithHostAccess`: sets the Origin and Referer of this extension's own requests to each
  site's messages page, as the site's own page would send them. Scoped to requests this extension starts.
- Host access: `www.linkedin.com`, `www.instagram.com` and `x.com` to read messages; `127.0.0.1` to post them to
  soloyolo. Nothing else. A server address other than 127.0.0.1 won't work.

## What it does

- **First sync:** conversations active in the last 90 days, at most 5 pages of the inbox and 5 pages of messages
  per conversation (100 of each on LinkedIn and Instagram).
- **Later syncs:** only conversations that changed since the last one. LinkedIn and X give a sync token or cursor
  for that; Instagram's inbox is newest first, so it reads until it reaches the newest thread it saw last time.
- **Pacing:** waits 1.5 to 4 seconds before every request to a network, and runs one network at a time.
- **No data lost:** a conversation is marked as synced only after soloyolo stored it. If the server is down, the
  next run picks up where this one stopped.
- **Fail soft:** an answer in a shape it doesn't expect, an expired session, a checkpoint or a rate limit stops
  that network's sync with the reason in the options page. It tries again by itself after an hour, then two,
  doubling up to a day. **Sync now** tries straight away. The other networks carry on.
- **Group threads** become evidence, as in the exports: they can close items but never create them.
- **Server side:** everything goes to `POST /api/live/sync` and is parsed in `spike/live.py`, then stored by the
  same `save()` the export importers use, so a person has one handle whichever way a message arrived.
  `POST /api/live/status` tells the server when a network is switched on or off or stopped, for the app.

## Files

- `sync.js`: what every network shares: the error type, pacing, back-off and the sync loop.
- `linkedin.js`, `instagram.js`, `x.js`: one module per network, each with `session`, `changed` and `fetch`.
- `background.js`: the alarm, the on and off switches, posting to soloyolo, status.
- `options.html`, `options.js`: the options page.
- `fixtures/`: Instagram and X answers built by hand from the sources in `docs/INSTAGRAM-X.md`.

## Risk

All three sites' terms forbid reading them with tools like this. Kondo, Beeper and others do it for LinkedIn and,
in Beeper's case, Instagram and X. Reading at this pace is unlikely to be flagged on LinkedIn. Instagram and X are
quicker to lock or challenge accounts that use unofficial clients, which is why they are off by default. The
export importers carry no risk and stay the fallback.

## What is verified and what isn't

Verified on fixtures (`node --test`): the request paths, headers and paging each module sends, that every request
is a GET, how answers are turned into soloyolo's shape, that an unexpected shape stops with a clear error, and that
a conversation is remembered only after the server stored it. The Python tests check that what the modules
produce is stored once, alongside the exports.

Never run against a signed-in account, on any of the three networks. In particular:

- **LinkedIn:** query ids and shapes are from mautrix-linkedin on 2026-11-10. When LinkedIn changes them, a sync
  stops with "no conversations in the answer". Whether messaging returns the readable profile URL
  (`/in/priya-natarajan`) or a member id (`/in/ACoAA...`) is unknown; if it's the id, the same person gets two
  handles until `spike/identity.py` merges them.
- **Instagram:** the endpoints are the private API instagrapi reads with the mobile app's id. Whether
  `www.instagram.com/api/v1/direct_v2/` still answers a web session is not known: Instagram's own web client may
  read the inbox over another protocol now (mautrix-meta uses Lightspeed). If it doesn't answer, the sync stops
  with an error and nothing else happens. Whether a thread's `thread_v2_id` is the number in the export's folder
  name is also unknown; if not, a person synced both ways shows up twice until merged.
- **X:** only the older, unencrypted DMs. Encrypted XChat conversations use a different protocol and aren't read.
  Whether X still requires an `x-client-transaction-id` header on these endpoints is unknown; if it does, they
  answer 404 or 403 and the sync stops.

When a site changes, update the one module that reads it; the shapes it expects are in its fixture.

## Test

```bash
cd extension && node --test
```
