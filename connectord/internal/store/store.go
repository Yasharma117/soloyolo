// Package store writes adapter events into the shared protocol-neutral SQLite model.
package store

import (
	"context"
	"database/sql"
	_ "embed"
	"errors"
	"fmt"
	"strings"

	_ "modernc.org/sqlite" // pure Go, no cgo: registers driver "sqlite"

	"github.com/yasharma117/soloyolo/connectord/internal/adapter"
)

//go:embed core.sql
var coreSchema string

// Daemon-only state. Not part of the shared model: the UI never needs it.
const daemonSchema = `
CREATE TABLE IF NOT EXISTS account (
  id TEXT PRIMARY KEY,           -- local id, e.g. "whatsapp-1"
  network TEXT NOT NULL,
  remote_user TEXT,              -- the network's id for you, once logged in
  created_at INTEGER NOT NULL DEFAULT (unixepoch())
);`

type Store struct{ db *sql.DB }

type Account struct {
	ID         string `json:"id"`
	Network    string `json:"network"`
	RemoteUser string `json:"remote_user,omitempty"`
}

func Open(path string) (*Store, error) {
	db, err := sql.Open("sqlite", "file:"+path+"?_pragma=foreign_keys(1)&_pragma=journal_mode(WAL)&_pragma=busy_timeout(5000)")
	if err != nil {
		return nil, err
	}
	db.SetMaxOpenConns(1) // one writer; SQLite serializes anyway
	if _, err := db.Exec(coreSchema + daemonSchema); err != nil {
		db.Close()
		return nil, fmt.Errorf("schema: %w", err)
	}
	return &Store{db: db}, nil
}

func (s *Store) Close() error { return s.db.Close() }

// PersonFor returns the person behind (network, address), creating both if new.
func (s *Store) PersonFor(ctx context.Context, network, address, name string) (int64, error) {
	var id int64
	err := s.db.QueryRowContext(ctx,
		`SELECT person_id FROM handle WHERE network = ? AND address = ?`, network, address).Scan(&id)
	switch {
	case err == nil:
		if name != "" {
			// Only replace a placeholder (the raw address); never clobber a name the user set.
			_, err = s.db.ExecContext(ctx,
				`UPDATE person SET display_name = ? WHERE id = ? AND display_name = ?`, name, id, address)
		}
		return id, err
	case !errors.Is(err, sql.ErrNoRows):
		return 0, err
	}
	if name == "" {
		name = address
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return 0, err
	}
	defer tx.Rollback()
	res, err := tx.ExecContext(ctx, `INSERT INTO person(display_name) VALUES (?)`, name)
	if err != nil {
		return 0, err
	}
	id, _ = res.LastInsertId()
	if _, err := tx.ExecContext(ctx,
		`INSERT INTO handle(network, address, person_id) VALUES (?, ?, ?)`, network, address, id); err != nil {
		return 0, err
	}
	return id, tx.Commit()
}

// AddEvent persists an event. It reports whether a row was new: the same message can arrive
// from the live socket and from history sync, and (network, remote_id) dedupes it.
//
//   - a 1:1 message or call: a message row for the person on the other side
//   - a group message: an evidence row (closes items, never creates them)
//   - a contact: a better name for a person or a group, never over one you set
func (s *Store) AddEvent(ctx context.Context, e adapter.Event) (bool, error) {
	switch {
	case e.Kind == adapter.EventContact:
		return false, s.rename(ctx, e)
	case e.Group != "" && e.Kind == adapter.EventMessage && e.Text != "":
		return s.addGroupLine(ctx, e)
	case e.Kind == adapter.EventCall:
		e.Text = adapter.CallText
	case e.Kind != adapter.EventMessage || e.Text == "" || e.ChatID == "":
		return false, nil
	}
	if e.ChatID == "" {
		return false, nil
	}
	// 1:1 chats only for now: the person is the chat's other party.
	pid, err := s.PersonFor(ctx, e.Network, e.ChatID, nameIfTheirs(e))
	if err != nil {
		return false, err
	}
	res, err := s.db.ExecContext(ctx,
		`INSERT OR IGNORE INTO message(network, remote_id, person_id, ts, from_me, text) VALUES (?, ?, ?, ?, ?, ?)`,
		e.Network, e.RemoteID, pid, float64(e.Time.UnixMilli())/1000, e.FromMe, e.Text)
	if err != nil {
		return false, err
	}
	n, _ := res.RowsAffected()
	return n == 1, nil
}

// GroupSource is the evidence source for a group: its subject when known, else its id.
// The spike shows the part after the colon as the chat's name.
func GroupSource(e adapter.Event) string {
	if e.GroupName != "" {
		return e.Network + "-group:" + e.GroupName
	}
	return e.Network + "-group:" + e.Group
}

func (s *Store) addGroupLine(ctx context.Context, e adapter.Event) (bool, error) {
	sender := "me"
	if !e.FromMe {
		sender = e.Name
		if sender == "" {
			sender = e.Sender
		}
	}
	res, err := s.db.ExecContext(ctx,
		`INSERT OR IGNORE INTO evidence(source, remote_id, ts, sender, text) VALUES (?, ?, ?, ?, ?)`,
		GroupSource(e), e.RemoteID, float64(e.Time.UnixMilli())/1000, sender, e.Text)
	if err != nil {
		return false, err
	}
	n, _ := res.RowsAffected()
	return n == 1, nil
}

func (s *Store) rename(ctx context.Context, e adapter.Event) error {
	if e.Group != "" && e.GroupName != "" {
		// Lines stored before the subject was known move under its name.
		_, err := s.db.ExecContext(ctx, `UPDATE OR IGNORE evidence SET source = ? WHERE source = ?`,
			GroupSource(e), e.Network+"-group:"+e.Group)
		return err
	}
	if e.ChatID == "" || (e.Name == "" && e.Email == "") {
		return nil
	}
	// Names often arrive before the first message (history sync sends them first), so a name for
	// someone not seen yet creates them. A person with no messages never shows in the lists.
	// A push name only fills in the placeholder (the raw address); PersonFor does exactly that.
	id, err := s.PersonFor(ctx, e.Network, e.ChatID, e.Name)
	if err != nil {
		return err
	}
	if e.Email != "" {
		// The email becomes a second handle on the same person, so another network that knows
		// them by email (mail, calendar) lands on this card. An email already taken by someone
		// else is left alone: merging people is the user's call.
		if _, err := s.db.ExecContext(ctx, `INSERT OR IGNORE INTO handle(network, address, person_id) VALUES ('email', ?, ?)`,
			strings.ToLower(strings.TrimSpace(e.Email)), id); err != nil {
			return err
		}
	}
	if !e.Saved || e.Name == "" {
		return nil
	}
	// A saved address-book name replaces whatever is there: it's what you call them.
	_, err = s.db.ExecContext(ctx, `UPDATE person SET display_name = ? WHERE id = ?`, e.Name, id)
	return err
}

func nameIfTheirs(e adapter.Event) string {
	if e.FromMe {
		return ""
	}
	return e.Name
}

func (s *Store) PutAccount(ctx context.Context, a Account) error {
	_, err := s.db.ExecContext(ctx,
		`INSERT INTO account(id, network, remote_user) VALUES (?, ?, NULLIF(?, ''))
		 ON CONFLICT(id) DO UPDATE SET remote_user = COALESCE(NULLIF(excluded.remote_user, ''), remote_user)`,
		a.ID, a.Network, a.RemoteUser)
	return err
}

func (s *Store) Accounts(ctx context.Context) ([]Account, error) {
	rows, err := s.db.QueryContext(ctx, `SELECT id, network, COALESCE(remote_user, '') FROM account ORDER BY created_at, id`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []Account{} // [] not null in JSON on a fresh install
	for rows.Next() {
		var a Account
		if err := rows.Scan(&a.ID, &a.Network, &a.RemoteUser); err != nil {
			return nil, err
		}
		out = append(out, a)
	}
	return out, rows.Err()
}

// Stats is for status output: what the store holds right now.
type Stats struct {
	People     int `json:"people"`
	Messages   int `json:"messages"`
	GroupLines int `json:"group_lines"`
}

func (s *Store) Stats(ctx context.Context) (st Stats, err error) {
	err = s.db.QueryRowContext(ctx, `SELECT (SELECT COUNT(DISTINCT person_id) FROM message), (SELECT COUNT(*) FROM message),
		(SELECT COUNT(*) FROM evidence WHERE source LIKE '%-group:%')`).Scan(&st.People, &st.Messages, &st.GroupLines)
	return
}

// MessageCount is for tests and status output.
func (s *Store) MessageCount(ctx context.Context) (n int, err error) {
	err = s.db.QueryRowContext(ctx, `SELECT COUNT(*) FROM message`).Scan(&n)
	return
}
