// Package store writes adapter events into the shared protocol-neutral SQLite model.
package store

import (
	"context"
	"database/sql"
	_ "embed"
	"errors"
	"fmt"

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

// AddEvent persists a message event. It reports whether the row was new: the same message
// can arrive from the live socket and from history sync, and (network, remote_id) dedupes it.
func (s *Store) AddEvent(ctx context.Context, e adapter.Event) (bool, error) {
	if e.Kind != adapter.EventMessage || e.Text == "" || e.ChatID == "" {
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

// MessageCount is for tests and status output.
func (s *Store) MessageCount(ctx context.Context) (n int, err error) {
	err = s.db.QueryRowContext(ctx, `SELECT COUNT(*) FROM message`).Scan(&n)
	return
}
