package store

import (
	"context"
	"path/filepath"
	"testing"
	"time"

	"github.com/yasharma117/soloyolo/connectord/internal/adapter"
)

func TestAddEventDedupesAndNamesPeople(t *testing.T) {
	ctx := context.Background()
	s, err := Open(filepath.Join(t.TempDir(), "s.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer s.Close()
	ev := adapter.Event{Kind: adapter.EventMessage, Network: "whatsapp", RemoteID: "A1",
		ChatID: "14155550101@s.whatsapp.net", FromMe: true, Time: time.Now(), Text: "I'll send it"}
	for i, want := range []bool{true, false} { // live + history overlap
		got, err := s.AddEvent(ctx, ev)
		if err != nil || got != want {
			t.Fatalf("insert %d: new=%v err=%v", i, got, err)
		}
	}
	// Our own message carries no name; their reply names the person once.
	reply := ev
	reply.RemoteID, reply.FromMe, reply.Name = "A2", false, "Sam Okafor"
	if _, err := s.AddEvent(ctx, reply); err != nil {
		t.Fatal(err)
	}
	var name string
	if err := s.db.QueryRow(`SELECT display_name FROM person`).Scan(&name); err != nil || name != "Sam Okafor" {
		t.Fatalf("name %q err %v", name, err)
	}
	// A later push name must not overwrite it.
	reply.RemoteID, reply.Name = "A3", "sam 🏄"
	s.AddEvent(ctx, reply)
	s.db.QueryRow(`SELECT display_name FROM person`).Scan(&name)
	if name != "Sam Okafor" {
		t.Fatalf("name clobbered to %q", name)
	}
	if n, _ := s.MessageCount(ctx); n != 3 {
		t.Fatalf("messages %d", n)
	}
	// Non-message events and empty text are ignored.
	for _, e := range []adapter.Event{{Kind: adapter.EventReaction, Network: "x", RemoteID: "r", ChatID: "c"},
		{Kind: adapter.EventMessage, Network: "x", RemoteID: "e", ChatID: "c"}} {
		if added, _ := s.AddEvent(ctx, e); added {
			t.Fatalf("stored %+v", e)
		}
	}
}
