// Package imessage reads ~/Library/Messages/chat.db (read-only) and sends through Messages.app.
//
// Reading needs Full Disk Access for the process. It works with SIP on and makes no network
// calls, the same approach as Beeper's platform-imessage (REPORT.md section 1.2). Sending uses
// the AppleScript fast path only: plain text into an existing 1:1 conversation. Anything richer
// (attachments, replies, new threads) needs the Accessibility-API route, which is not built.
package imessage

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"time"

	"github.com/yasharma117/soloyolo/connectord/internal/adapter"
)

const Network = "imessage"

// appleEpoch is 2001-01-01 UTC; chat.db stores `date` as nanoseconds since then.
var appleEpoch = time.Date(2001, 1, 1, 0, 0, 0, 0, time.UTC)

// Same filters as spike/chatdb.py: 1:1 chats, no tapbacks, rows after a ROWID cursor.
const query = `
WITH one_to_one AS (
  SELECT chat_id, MIN(handle_id) AS handle_id
  FROM chat_handle_join GROUP BY chat_id HAVING COUNT(*) = 1
)
SELECT m.ROWID, m.guid, h.id, m.date, m.is_from_me, m.text, m.attributedBody
FROM message m
JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
JOIN one_to_one o ON o.chat_id = cmj.chat_id
JOIN handle h ON h.ROWID = o.handle_id
WHERE m.associated_message_type = 0 AND m.ROWID > ?
ORDER BY m.ROWID
LIMIT ?`

type Adapter struct {
	Path     string        // chat.db location
	Interval time.Duration // poll interval; FSEvents would be better, polling is portable

	mu     sync.Mutex
	db     *sql.DB
	cursor int64 // last ROWID emitted
	events chan adapter.Event
	cancel context.CancelFunc
	done   chan struct{}
}

func New(_, _ string) (adapter.Adapter, error) {
	home, _ := os.UserHomeDir()
	return &Adapter{
		Path:     filepath.Join(home, "Library", "Messages", "chat.db"),
		Interval: 2 * time.Second,
		events:   make(chan adapter.Event, 256),
	}, nil
}

func (a *Adapter) Network() string { return Network }

// Login checks the one permission this adapter needs.
func (a *Adapter) Login(ctx context.Context, _ adapter.LoginInput) (adapter.LoginStep, error) {
	f, err := os.Open(a.Path)
	if err != nil {
		if errors.Is(err, os.ErrPermission) {
			return adapter.LoginStep{Kind: "permission",
				Payload: "Grant Full Disk Access to this app in System Settings → Privacy & Security, then retry."}, nil
		}
		return adapter.LoginStep{}, err // already names the path
	}
	f.Close()
	return adapter.LoginStep{Kind: "done", Payload: "local"}, nil
}

func (a *Adapter) open() error {
	a.mu.Lock()
	defer a.mu.Unlock()
	if a.db != nil {
		return nil
	}
	db, err := sql.Open("sqlite", "file:"+a.Path+"?mode=ro&_pragma=busy_timeout(2000)")
	if err != nil {
		return err
	}
	a.db = db
	return nil
}

// Connect starts polling. The first pass emits history; later passes emit new rows.
func (a *Adapter) Connect(ctx context.Context) error {
	if err := a.open(); err != nil {
		return err
	}
	ctx, a.cancel = context.WithCancel(ctx)
	a.done = make(chan struct{})
	go func() {
		defer close(a.done)
		history := true
		for {
			if _, err := a.Poll(ctx, history); err != nil && ctx.Err() == nil {
				// chat.db is mid-checkpoint or briefly locked: try again next tick.
				log.Printf("imessage: poll: %v", err)
			}
			history = false
			select {
			case <-ctx.Done():
				return
			case <-time.After(a.Interval):
			}
		}
	}()
	return nil
}

// Poll reads rows past the cursor and pushes them to Events. Exposed for tests.
func (a *Adapter) Poll(ctx context.Context, history bool) (int, error) {
	if err := a.open(); err != nil {
		return 0, err
	}
	total := 0
	for {
		rows, err := a.db.QueryContext(ctx, query, a.cursor, 500)
		if err != nil {
			return total, err
		}
		n := 0
		for rows.Next() {
			var (
				rowid, date int64
				fromMe      bool
				guid, h     string
				text        sql.NullString
				body        []byte
			)
			if err := rows.Scan(&rowid, &guid, &h, &date, &fromMe, &text, &body); err != nil {
				rows.Close()
				return total, err
			}
			a.cursor, n = rowid, n+1
			msg := text.String
			if msg == "" {
				msg = DecodeAttributedBody(body)
			}
			msg = strings.TrimSpace(strings.ReplaceAll(msg, "￼", ""))
			if msg == "" || isShortcode(h) {
				continue
			}
			ev := adapter.Event{Kind: adapter.EventMessage, Network: Network, RemoteID: guid, ChatID: h,
				FromMe: fromMe, Time: appleEpoch.Add(time.Duration(date)), Text: msg, History: history}
			if !fromMe {
				ev.Sender = h
			}
			select {
			case a.events <- ev:
				total++
			case <-ctx.Done():
				rows.Close()
				return total, ctx.Err()
			}
		}
		rows.Close()
		if n < 500 {
			return total, rows.Err()
		}
	}
}

func isShortcode(h string) bool {
	if len(h) > 6 {
		return false
	}
	for _, r := range h {
		if r < '0' || r > '9' {
			return false
		}
	}
	return h != ""
}

func (a *Adapter) Events() <-chan adapter.Event { return a.events }

// Send uses Messages.app's AppleScript `send`. macOS only; it returns no remote id because
// Messages.app doesn't report one. The sent row shows up in chat.db and arrives via Events.
func (a *Adapter) Send(ctx context.Context, chatID string, m adapter.Outgoing) (string, error) {
	if runtime.GOOS != "darwin" {
		return "", fmt.Errorf("imessage send: %w on %s", adapter.ErrUnsupported, runtime.GOOS)
	}
	if strings.ContainsAny(m.Text, "\r") || m.Text == "" {
		return "", errors.New("imessage send: empty text or carriage return")
	}
	// Pass values as argv, never by splicing them into the script: no AppleScript injection.
	script := `on run argv
  tell application "Messages"
    set svc to 1st account whose service type = iMessage
    send (item 2 of argv) to participant (item 1 of argv) of svc
  end tell
end run`
	out, err := exec.CommandContext(ctx, "osascript", "-e", script, chatID, m.Text).CombinedOutput()
	if err != nil {
		return "", fmt.Errorf("osascript: %v: %s", err, strings.TrimSpace(string(out)))
	}
	return "", nil
}

func (a *Adapter) Backfill(context.Context, string, adapter.Cursor) ([]adapter.Event, adapter.Cursor, error) {
	return nil, "", adapter.ErrUnsupported // Connect's first poll already emits all local history
}

func (a *Adapter) Contacts(context.Context) ([]adapter.Contact, error) {
	return nil, adapter.ErrUnsupported // needs the Contacts framework (cgo); see REPORT.md 2.5
}

func (a *Adapter) Close() error {
	if a.cancel != nil {
		a.cancel()
		<-a.done
	}
	a.mu.Lock()
	defer a.mu.Unlock()
	if a.db != nil {
		return a.db.Close()
	}
	return nil
}
