// Package adapter is the contract every network implements. It is soloyolo's equivalent of
// what Matrix is for Beeper: six methods instead of bridgev2's ~40 optional interfaces.
// Add a capability only when the product needs it (BUILD-WITHOUT-BEEPER.md section 1).
package adapter

import (
	"context"
	"errors"
	"fmt"
	"sort"
	"sync"
	"time"
)

// ErrUnsupported is returned by adapters for capabilities their network or platform lacks.
var ErrUnsupported = errors.New("not supported by this adapter")

// LoginInput carries the user's answer to the previous LoginStep (empty on the first call).
type LoginInput struct {
	Value string `json:"value,omitempty"` // phone number, code, cookie blob...
}

// LoginStep tells the UI what to show next.
type LoginStep struct {
	Kind    string `json:"kind"`              // "qr" | "code" | "phone" | "permission" | "done"
	Payload string `json:"payload,omitempty"` // QR data, instructions, or the logged-in user id when done
}

// EventKind is a closed set; adapters map their network's events onto it.
type EventKind string

const (
	EventMessage  EventKind = "message"
	EventEdit     EventKind = "edit"
	EventReaction EventKind = "reaction"
	EventRead     EventKind = "read"
	EventLogout   EventKind = "logged_out" // the session was revoked remotely: relink needed
	EventCall     EventKind = "call"       // a call happened in a 1:1 chat; Text is "[call]"
	EventContact  EventKind = "contact"    // a name for ChatID (address book or the person's own push name)
)

// CallText is what a call is stored as: the spike reads it as "(a call between us)".
const CallText = "[call]"

// Event is one protocol-neutral thing that happened.
type Event struct {
	Kind     EventKind `json:"kind"`
	Network  string    `json:"network"`
	RemoteID string    `json:"remote_id"` // network's message id; the store dedupes on (network, remote_id)
	ChatID   string    `json:"chat_id"`
	Sender   string    `json:"sender"` // handle address of the other person, or "" when FromMe
	FromMe   bool      `json:"from_me"`
	Time     time.Time `json:"time"`
	Text     string    `json:"text,omitempty"`
	Name     string    `json:"name,omitempty"` // display name if the network offers one
	History  bool      `json:"history,omitempty"`
	// Group chats are kept as evidence that something got done, never as a source of new items.
	Group     string `json:"group,omitempty"`      // the group's id; set only for group messages
	GroupName string `json:"group_name,omitempty"` // its subject, when known
	Saved     bool   `json:"saved,omitempty"`      // contact events: the name is from your address book
	Email     string `json:"email,omitempty"`      // contact events: the person's email, an identity key across networks
}

// Outgoing is what the user wants to send. Text only for now.
type Outgoing struct {
	Text string `json:"text"`
}

// Cursor is an opaque, adapter-defined backfill position.
type Cursor string

// Contact is a person as the network knows them.
type Contact struct {
	Address string `json:"address"`
	Name    string `json:"name"`
	Saved   bool   `json:"saved,omitempty"` // the name is from your address book, not the person's own
}

// Adapter is one logged-in account on one network.
type Adapter interface {
	Network() string
	Login(ctx context.Context, in LoginInput) (LoginStep, error)
	Connect(ctx context.Context) error
	Events() <-chan Event
	Send(ctx context.Context, chatID string, m Outgoing) (remoteID string, err error)
	Backfill(ctx context.Context, chatID string, before Cursor) ([]Event, Cursor, error)
	Contacts(ctx context.Context) ([]Contact, error)
	Close() error
}

// Factory builds an adapter for one account. dataDir holds that account's private state
// (for example WhatsApp device keys), kept apart from the shared message store.
type Factory func(accountID, dataDir string) (Adapter, error)

// Registry maps network names to factories.
type Registry struct {
	mu        sync.RWMutex
	factories map[string]Factory
}

func NewRegistry() *Registry { return &Registry{factories: map[string]Factory{}} }

func (r *Registry) Register(network string, f Factory) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.factories[network] = f
}

func (r *Registry) New(network, accountID, dataDir string) (Adapter, error) {
	r.mu.RLock()
	f, ok := r.factories[network]
	r.mu.RUnlock()
	if !ok {
		return nil, fmt.Errorf("unknown network %q", network)
	}
	return f(accountID, dataDir)
}

func (r *Registry) Networks() []string {
	r.mu.RLock()
	defer r.mu.RUnlock()
	out := make([]string, 0, len(r.factories))
	for n := range r.factories {
		out = append(out, n)
	}
	sort.Strings(out)
	return out
}
