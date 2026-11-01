package daemon

import (
	"bufio"
	"context"
	"encoding/json"
	"io"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/yasharma117/soloyolo/connectord/internal/adapter"
	"github.com/yasharma117/soloyolo/connectord/internal/store"
)

// fake is an in-memory network: login is one QR step then done; Connect emits a backlog
// with a duplicate (as live + history overlap does) and one live message.
type fake struct {
	logins int
	events chan adapter.Event
	sent   []string
}

func (f *fake) Network() string { return "fake" }
func (f *fake) Login(context.Context, adapter.LoginInput) (adapter.LoginStep, error) {
	if f.logins++; f.logins == 1 {
		return adapter.LoginStep{Kind: "qr", Payload: "2@abc"}, nil
	}
	return adapter.LoginStep{Kind: "done", Payload: "me@fake"}, nil
}
func (f *fake) Connect(context.Context) error {
	t := time.Unix(1_790_000_000, 0)
	msg := func(id, text string, me, hist bool) adapter.Event {
		return adapter.Event{Kind: adapter.EventMessage, Network: "fake", RemoteID: id, ChatID: "sam",
			FromMe: me, Time: t, Text: text, Name: "Sam", History: hist}
	}
	f.events <- msg("1", "I'll send the deck", true, true)
	f.events <- msg("1", "I'll send the deck", true, false) // duplicate: must not double-insert
	f.events <- msg("2", "thanks!", false, false)
	return nil
}
func (f *fake) Events() <-chan adapter.Event { return f.events }
func (f *fake) Send(_ context.Context, chat string, m adapter.Outgoing) (string, error) {
	f.sent = append(f.sent, chat+":"+m.Text)
	return "srv-1", nil
}
func (f *fake) Backfill(context.Context, string, adapter.Cursor) ([]adapter.Event, adapter.Cursor, error) {
	return nil, "", adapter.ErrUnsupported
}
func (f *fake) Contacts(context.Context) ([]adapter.Contact, error) {
	return []adapter.Contact{{Address: "sam", Name: "Sam"}}, nil
}
func (f *fake) Close() error { return nil }

type client struct {
	t   *testing.T
	in  *io.PipeWriter
	out *bufio.Scanner
	id  int
}

// call sends a request and returns its response, collecting notifications seen on the way.
func (c *client) call(method string, params any) (map[string]any, []map[string]any) {
	c.t.Helper()
	c.id++
	b, _ := json.Marshal(map[string]any{"jsonrpc": "2.0", "id": c.id, "method": method, "params": params})
	if _, err := c.in.Write(append(b, '\n')); err != nil {
		c.t.Fatal(err)
	}
	var notes []map[string]any
	for c.out.Scan() {
		var m map[string]any
		if err := json.Unmarshal(c.out.Bytes(), &m); err != nil {
			c.t.Fatalf("bad line %q: %v", c.out.Text(), err)
		}
		if id, ok := m["id"].(float64); ok && int(id) == c.id {
			return m, notes
		}
		notes = append(notes, m)
	}
	c.t.Fatalf("stream ended waiting for %s", method)
	return nil, nil
}

func TestDaemonEndToEnd(t *testing.T) {
	dir := t.TempDir()
	st, err := store.Open(filepath.Join(dir, "s.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	f := &fake{events: make(chan adapter.Event, 8)}
	reg := adapter.NewRegistry()
	reg.Register("fake", func(string, string) (adapter.Adapter, error) { return f, nil })

	inR, inW := io.Pipe()
	outR, outW := io.Pipe()
	done := make(chan error, 1)
	go func() { done <- New(reg, st, dir).Serve(context.Background(), inR, outW); outW.Close() }()
	c := &client{t: t, in: inW, out: bufio.NewScanner(outR)}

	if r, _ := c.call("networks.list", nil); r["result"].([]any)[0] != "fake" {
		t.Fatalf("networks: %v", r)
	}
	r, _ := c.call("accounts.add", map[string]string{"network": "fake"})
	acct := r["result"].(map[string]any)["id"].(string)
	if acct != "fake-1" {
		t.Fatalf("account id %q", acct)
	}
	if r, _ := c.call("accounts.add", map[string]string{"network": "nope"}); r["error"] == nil {
		t.Fatal("unknown network accepted")
	}
	if r, _ := c.call("accounts.login", map[string]string{"account": acct}); r["result"].(map[string]any)["kind"] != "qr" {
		t.Fatalf("first login step: %v", r)
	}
	r, _ = c.call("accounts.login", map[string]string{"account": acct})
	if r["result"].(map[string]any)["kind"] != "done" {
		t.Fatalf("second login step: %v", r)
	}
	r, _ = c.call("messages.send", map[string]string{"account": acct, "chat_id": "sam", "text": "on it"})
	if r["result"].(map[string]any)["remote_id"] != "srv-1" || strings.Join(f.sent, ",") != "sam:on it" {
		t.Fatalf("send: %v %v", r, f.sent)
	}
	if r, _ := c.call("bogus", nil); r["error"].(map[string]any)["code"].(float64) != -32601 {
		t.Fatalf("unknown method: %v", r)
	}

	// The pump runs async; wait for both unique messages to land.
	deadline := time.Now().Add(2 * time.Second)
	for {
		n, _ := st.MessageCount(context.Background())
		if n == 2 {
			break
		}
		if time.Now().After(deadline) {
			t.Fatalf("store has %d messages, want 2 (dedupe or pump broken)", n)
		}
		time.Sleep(10 * time.Millisecond)
	}
	r, _ = c.call("accounts.list", nil)
	if got := r["result"].([]any)[0].(map[string]any)["remote_user"]; got != "me@fake" {
		t.Fatalf("remote_user not stored: %v", got)
	}

	inW.Close()
	for c.out.Scan() { // drain trailing notifications so Serve can finish writing
	}
	if err := <-done; err != nil {
		t.Fatal(err)
	}
}
