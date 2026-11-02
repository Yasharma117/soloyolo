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
