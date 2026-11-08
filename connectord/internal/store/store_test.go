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

func TestGroupsCallsAndNames(t *testing.T) {
	ctx := context.Background()
	s, err := Open(filepath.Join(t.TempDir(), "s.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer s.Close()
	now := time.Now()
	papa := "919800000003@s.whatsapp.net"
	group := "120363000000000001@g.us"

	// A group line before its subject is known, then the subject arrives: the line moves under it.
	line := adapter.Event{Kind: adapter.EventMessage, Network: "whatsapp", RemoteID: "G1", ChatID: group, Group: group,
		Sender: papa, Name: "Papa", Time: now, Text: "Done, 9:30 wali book kar di"}
	if added, err := s.AddEvent(ctx, line); !added || err != nil {
		t.Fatalf("group line: added=%v err=%v", added, err)
	}
	if n, _ := s.MessageCount(ctx); n != 0 {
		t.Fatal("a group line must never become a message (items come from 1:1 chats only)")
	}
	s.AddEvent(ctx, adapter.Event{Kind: adapter.EventContact, Network: "whatsapp", Group: group, GroupName: "Family"})
	var source, sender string
	if err := s.db.QueryRow(`SELECT source, sender FROM evidence`).Scan(&source, &sender); err != nil ||
		source != "whatsapp-group:Family" || sender != "Papa" {
		t.Fatalf("evidence %q %q %v", source, sender, err)
	}

	// A call is a 1:1 message the spike reads as "(a call between us)"; history and live dedupe.
	call := adapter.Event{Kind: adapter.EventCall, Network: "whatsapp", RemoteID: "call:C1", ChatID: papa, Time: now}
	for i, want := range []bool{true, false} {
		if added, _ := s.AddEvent(ctx, call); added != want {
			t.Fatalf("call %d added=%v", i, added)
		}
	}
	var text string
	s.db.QueryRow(`SELECT text FROM message`).Scan(&text)
	if text != adapter.CallText {
		t.Fatalf("call stored as %q", text)
	}

	// A name can arrive before any message: it must not be lost.
	sonu := "919800000004@s.whatsapp.net"
	s.AddEvent(ctx, adapter.Event{Kind: adapter.EventContact, Network: "whatsapp", ChatID: sonu, Name: "Sonu Bhaiya", Saved: true})
	s.AddEvent(ctx, adapter.Event{Kind: adapter.EventMessage, Network: "whatsapp", RemoteID: "S1", ChatID: sonu,
		Time: now, Text: "Will call later", Name: "sonu"})
	var sonuName string
	s.db.QueryRow(`SELECT p.display_name FROM person p JOIN handle h ON h.person_id = p.id WHERE h.address = ?`, sonu).Scan(&sonuName)
	if sonuName != "Sonu Bhaiya" {
		t.Fatalf("name before first message: %q", sonuName)
	}

	// Names: a push name fills the placeholder; a saved address-book name replaces it.
	name := func() (n string) {
		s.db.QueryRow(`SELECT p.display_name FROM person p JOIN handle h ON h.person_id = p.id WHERE h.address = ?`, papa).Scan(&n)
		return
	}
	if name() != papa {
		t.Fatalf("placeholder %q", name())
	}
	s.AddEvent(ctx, adapter.Event{Kind: adapter.EventContact, Network: "whatsapp", ChatID: papa, Name: "Rajesh"})
	s.AddEvent(ctx, adapter.Event{Kind: adapter.EventContact, Network: "whatsapp", ChatID: papa, Name: "rajesh 🌞"})
	if name() != "Rajesh" {
		t.Fatalf("push name: %q", name())
	}
	s.AddEvent(ctx, adapter.Event{Kind: adapter.EventContact, Network: "whatsapp", ChatID: papa, Name: "PAPA", Saved: true})
	if name() != "PAPA" {
		t.Fatalf("saved name: %q", name())
	}
}
