package imessage

import (
	"context"
	"database/sql"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/yasharma117/soloyolo/connectord/internal/adapter"
	_ "modernc.org/sqlite"
)

// body builds an attributedBody blob shaped like real rows (same as spike/fixture.py).
func body(text string) []byte {
	n := []byte{byte(len(text))}
	if len(text) >= 0x80 {
		n = []byte{0x81, byte(len(text)), byte(len(text) >> 8)}
	}
	b := []byte("\x04\x0bstreamtyped\x81\xe8\x03\x84\x01@\x84\x84\x84\x12NSAttributedString\x00" +
		"\x84\x84\x08NSObject\x00\x85\x92\x84\x84\x84\x08NSString\x01\x94\x84\x01+")
	b = append(append(b, n...), text...)
	return append(b, "\x86\x84\x02iI\x01"...)
}

func TestDecodeAttributedBody(t *testing.T) {
	for _, s := range []string{"hi", strings.Repeat("x", 300), "emoji 🎉 ok"} {
		if got := DecodeAttributedBody(body(s)); got != s {
			t.Fatalf("got %q want %q", got, s)
		}
	}
	for _, bad := range [][]byte{nil, []byte("NSString"), []byte("NSString\x01+"), []byte("NSString\x01+\x81\x05")} {
		if got := DecodeAttributedBody(bad); got != "" {
			t.Fatalf("garbage decoded to %q", got)
		}
	}
}

func fixture(t *testing.T) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "chat.db")
	db, err := sql.Open("sqlite", "file:"+path)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	ns := func(d time.Duration) int64 { return int64(time.Since(appleEpoch) - d) }
	stmts := []string{
		`CREATE TABLE handle(ROWID INTEGER PRIMARY KEY, id TEXT)`,
		`CREATE TABLE chat_handle_join(chat_id INT, handle_id INT)`,
		`CREATE TABLE chat_message_join(chat_id INT, message_id INT)`,
		`CREATE TABLE message(ROWID INTEGER PRIMARY KEY, guid TEXT, handle_id INT, date INT, is_from_me INT,
			text TEXT, attributedBody BLOB, associated_message_type INT DEFAULT 0)`,
		`INSERT INTO handle VALUES (1, '+14155550101'), (2, '+14155550102'), (3, '88600')`,
		`INSERT INTO chat_handle_join VALUES (1, 1), (2, 2), (3, 3), (9, 1), (9, 2)`, // chat 9 is a group
	}
	for _, s := range stmts {
		if _, err := db.Exec(s); err != nil {
			t.Fatal(err)
		}
	}
	rows := []struct {
		chat, handle, fromMe, tapback int
		text                          any
		blob                          []byte
	}{
		{1, 1, 1, 0, "I'll intro you to Priya by Friday", body("I'll intro you to Priya by Friday")},
		{1, 1, 0, 0, nil, body("Any luck reaching Priya?")}, // text only in attributedBody
		{1, 1, 0, 2001, "Loved a message", nil},             // tapback
		{3, 3, 0, 0, "Your code is 123456", nil},            // shortcode
		{9, 2, 0, 0, "Count me in", nil},                    // group
		{2, 2, 0, 0, "￼", nil},                              // attachment only
	}
	for i, r := range rows {
		if _, err := db.Exec(`INSERT INTO message VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
			i+1, "guid-"+string(rune('a'+i)), r.handle, ns(time.Duration(10-i)*time.Hour), r.fromMe, r.text, r.blob, r.tapback); err != nil {
			t.Fatal(err)
		}
		if _, err := db.Exec(`INSERT INTO chat_message_join VALUES (?, ?)`, r.chat, i+1); err != nil {
			t.Fatal(err)
		}
	}
	return path
}

func TestPollFiltersAndDecodes(t *testing.T) {
	a := &Adapter{Path: fixture(t), events: make(chan adapter.Event, 16)}
	defer a.Close()
	n, err := a.Poll(context.Background(), true)
	if err != nil {
		t.Fatal(err)
	}
	if n != 2 {
		t.Fatalf("emitted %d events, want 2", n)
	}
	first, second := <-a.events, <-a.events
	if !first.FromMe || first.Sender != "" || first.ChatID != "+14155550101" || !first.History {
		t.Fatalf("bad first event: %+v", first)
	}
	if second.Text != "Any luck reaching Priya?" || second.Sender != "+14155550101" {
		t.Fatalf("bad second event: %+v", second)
	}
	if time.Since(first.Time) > 11*time.Hour || time.Since(first.Time) < 9*time.Hour {
		t.Fatalf("timestamp off: %v", first.Time)
	}
	// The cursor advanced: nothing new on the next poll.
	if n, _ := a.Poll(context.Background(), false); n != 0 {
		t.Fatalf("re-poll emitted %d", n)
	}
}

func TestShortcode(t *testing.T) {
	for h, want := range map[string]bool{"88600": true, "123456": true, "+14155550101": false, "a@b.co": false, "": false} {
		if isShortcode(h) != want {
			t.Fatalf("isShortcode(%q) != %v", h, want)
		}
	}
}

func TestConnectTwiceIsOnePoller(t *testing.T) {
	a := &Adapter{Path: fixture(t), Interval: 10 * time.Millisecond, events: make(chan adapter.Event, 16)}
	ctx := context.Background()
	if err := a.Connect(ctx); err != nil {
		t.Fatal(err)
	}
	if err := a.Connect(ctx); err != nil {
		t.Fatal(err)
	}
	deadline := time.Now().Add(5 * time.Second) // slow CI with -race: wait for the first pass, bounded
	for len(a.events) < 2 && time.Now().Before(deadline) {
		time.Sleep(5 * time.Millisecond)
	}
	time.Sleep(5 * a.Interval) // a second poller, if any, would add duplicates in this window
	if err := a.Close(); err != nil {
		t.Fatal(err)
	}
	if n := len(a.events); n != 2 { // one poller: each fixture message exactly once
		t.Fatalf("got %d events, want 2", n)
	}
}
