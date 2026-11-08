-- soloyolo core schema: the one protocol-neutral data model.
-- Shared by connectord (Go, embedded) and spike/ (Python reads this file). Change it here only.
CREATE TABLE IF NOT EXISTS person (
  id INTEGER PRIMARY KEY,
  display_name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS handle (
  network TEXT NOT NULL,           -- imessage | whatsapp | telegram ...
  address TEXT NOT NULL,           -- phone, email, or network user id
  person_id INTEGER NOT NULL REFERENCES person(id),
  PRIMARY KEY (network, address)
);
CREATE TABLE IF NOT EXISTS message (
  id INTEGER PRIMARY KEY,
  network TEXT NOT NULL,
  remote_id TEXT NOT NULL,         -- the network's own id; dedupes live vs backfill
  person_id INTEGER NOT NULL REFERENCES person(id),
  ts REAL NOT NULL,
  from_me INTEGER NOT NULL,
  text TEXT NOT NULL,
  UNIQUE (network, remote_id)
);
CREATE INDEX IF NOT EXISTS message_person_ts ON message(person_id, ts);
CREATE TABLE IF NOT EXISTS commitment (
  id INTEGER PRIMARY KEY,
  person_id INTEGER NOT NULL REFERENCES person(id),
  owner TEXT NOT NULL CHECK (owner IN ('me', 'them')),  -- who has to act next
  action TEXT NOT NULL,
  due TEXT,                        -- ISO date, when one was stated or implied
  status TEXT NOT NULL CHECK (status IN ('open', 'done')),
  source_message_id INTEGER NOT NULL REFERENCES message(id),
  done_message_id INTEGER REFERENCES message(id),
  extractor TEXT NOT NULL,         -- 'heuristic' | model id
  kind TEXT NOT NULL DEFAULT 'promise' CHECK (kind IN ('promise', 'ask'))  -- ask: requested, no yes or no yet
);
CREATE TABLE IF NOT EXISTS topic (
  person_id INTEGER NOT NULL REFERENCES person(id),
  label TEXT NOT NULL,
  PRIMARY KEY (person_id, label)
);
-- What happened to an item after extraction: your own call, or a closing signal found elsewhere
-- (a bank SMS, a later message in another chat). Keyed by what the item is, not by its row id, so it
-- survives re-extraction. Your own rows (decided_by = 'you') are never overwritten by a signal.
CREATE TABLE IF NOT EXISTS resolution (
  person_id INTEGER NOT NULL REFERENCES person(id),
  source_message_id INTEGER NOT NULL REFERENCES message(id),
  owner TEXT NOT NULL CHECK (owner IN ('me', 'them')),
  -- suggested: a signal thinks it's settled; it stays open until you say so
  state TEXT NOT NULL CHECK (state IN ('done', 'dismissed', 'snoozed', 'open', 'suggested')),
  until REAL,                      -- snoozed until (epoch seconds)
  decided_by TEXT NOT NULL,        -- 'you' | 'sms' | 'closure'
  evidence TEXT,                   -- shown to you: what closed it
  evidence_id INTEGER,             -- the evidence row that closed it, if one did
  at REAL NOT NULL,
  PRIMARY KEY (person_id, source_message_id, owner)
);
-- Things that can close an item but never create one: bank SMS, group-chat lines.
CREATE TABLE IF NOT EXISTS evidence (
  id INTEGER PRIMARY KEY,
  source TEXT NOT NULL,            -- 'sms' | 'whatsapp-group:<name>'
  remote_id TEXT NOT NULL,
  ts REAL NOT NULL,
  sender TEXT,                     -- group: who said it ('me' for you); sms: the sender id
  text TEXT NOT NULL,
  amount REAL,                     -- payments only
  direction TEXT CHECK (direction IN ('in', 'out')),   -- money to you / from you
  counterparty TEXT,
  UNIQUE (source, remote_id)
);
CREATE INDEX IF NOT EXISTS evidence_ts ON evidence(ts);
CREATE TABLE IF NOT EXISTS extraction_run (
  person_id INTEGER PRIMARY KEY REFERENCES person(id),
  extractor TEXT NOT NULL,         -- who read this thread last: 'heuristic' | model id
  ran_at REAL NOT NULL,            -- recorded even when nothing was found, so "did text leave?" is answerable
  last_message_id INTEGER          -- the newest message it read: anything above it is new since
);
CREATE TABLE IF NOT EXISTS disclosure (
  id INTEGER PRIMARY KEY,
  person_id INTEGER NOT NULL REFERENCES person(id),
  recipient TEXT NOT NULL,         -- who received thread text, e.g. 'claude-opus-5-5 (claude code)'
  at REAL NOT NULL                 -- written *before* sending; never deleted, so a later local run can't hide it
);
-- Identity: one card per person across sources. spike/identity.py writes these; docs/IDENTITY.md has the rules.
-- A fact about a person from one source. The same fact from two sources is two rows, so you can see who said it.
CREATE TABLE IF NOT EXISTS attribute (
  person_id INTEGER NOT NULL REFERENCES person(id),
  key TEXT NOT NULL,      -- email | phone | company | position | city | birthday | linkedin | instagram | x | ...
  value TEXT NOT NULL,
  source TEXT NOT NULL,   -- whatsapp | linkedin-export | vcard | message:<id> | ...
  ts REAL NOT NULL,
  PRIMARY KEY (person_id, key, value, source)
);
CREATE INDEX IF NOT EXISTS attribute_key_value ON attribute(key, value);
-- Two cards that may be one person, waiting for your yes or no. One row per unordered pair (a < b).
-- A "no" is kept forever so the matcher never asks again; it follows the people through later merges.
CREATE TABLE IF NOT EXISTS merge_suggestion (
  a INTEGER NOT NULL REFERENCES person(id),
  b INTEGER NOT NULL REFERENCES person(id),
  score REAL NOT NULL,             -- 0..1; ranks the review queue, never merges by itself
  reasons TEXT NOT NULL,           -- JSON list of short strings shown to you: why we think so
  state TEXT NOT NULL DEFAULT 'open' CHECK (state IN ('open', 'merged', 'rejected')),
  at REAL NOT NULL,                -- last scored
  decided_at REAL,
  PRIMARY KEY (a, b),
  CHECK (a < b)
);
-- Every merge, automatic or yours, with what moved, so it can be undone. The absorbed person row is
-- kept (empty) so ids stay stable and undo can refill it.
CREATE TABLE IF NOT EXISTS merge_log (
  id INTEGER PRIMARY KEY,
  kept INTEGER NOT NULL REFERENCES person(id),
  gone INTEGER NOT NULL REFERENCES person(id),
  reason TEXT NOT NULL,            -- 'phone' | 'email' | 'linkedin' ... (the hard key's kind, not its value) | 'you'
  decided_by TEXT NOT NULL CHECK (decided_by IN ('auto', 'you')),
  moved TEXT NOT NULL,             -- JSON: natural keys of the rows moved, and both display names
  at REAL NOT NULL,
  undone_at REAL
);
-- Who knows whom, from what was said: "Asha will forward your profile to Kiran" is Asha -> Kiran, kind 'intro'.
CREATE TABLE IF NOT EXISTS edge (
  id INTEGER PRIMARY KEY,
  src INTEGER NOT NULL REFERENCES person(id),
  dst INTEGER NOT NULL REFERENCES person(id),
  kind TEXT NOT NULL,              -- intro | knows | colleague | family | referred | reports_to | ...
  evidence_message_id INTEGER REFERENCES message(id),  -- the line that says so; NULL only when you added it
  note TEXT,                       -- short, shown on the card: "forwarding your profile", "brother"
  extractor TEXT NOT NULL,         -- 'you' | 'heuristic' | model id
  ts REAL NOT NULL,
  CHECK (src <> dst)
);
CREATE UNIQUE INDEX IF NOT EXISTS edge_key ON edge(src, dst, kind, IFNULL(evidence_message_id, 0));
CREATE INDEX IF NOT EXISTS edge_dst ON edge(dst);
