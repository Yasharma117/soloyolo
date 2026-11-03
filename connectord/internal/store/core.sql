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
  ran_at REAL NOT NULL             -- recorded even when nothing was found, so "did text leave?" is answerable
);
CREATE TABLE IF NOT EXISTS disclosure (
  id INTEGER PRIMARY KEY,
  person_id INTEGER NOT NULL REFERENCES person(id),
  recipient TEXT NOT NULL,         -- who received thread text, e.g. 'claude-opus-5-5 (claude code)'
  at REAL NOT NULL                 -- written *before* sending; never deleted, so a later local run can't hide it
);
