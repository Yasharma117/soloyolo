// Package whatsapp links to your WhatsApp account as a companion device (like WhatsApp Web)
// using whatsmeow (MPL-2.0). Device keys live in a per-account SQLite file in dataDir, apart
// from the shared message store. Losing that file means relinking; leaking it means someone
// else can read your WhatsApp. Moving it into the macOS Keychain is on the list.
//
// Ban risk: normal personal use as a linked device is low risk. Bulk or automated sending is not.
package whatsapp

import (
	"context"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"

	"go.mau.fi/whatsmeow"
	"go.mau.fi/whatsmeow/proto/waE2E"
	"go.mau.fi/whatsmeow/store/sqlstore"
	"go.mau.fi/whatsmeow/types"
	"go.mau.fi/whatsmeow/types/events"
	waLog "go.mau.fi/whatsmeow/util/log"
	"google.golang.org/protobuf/proto"

	"github.com/yasharma117/soloyolo/connectord/internal/adapter"
	_ "modernc.org/sqlite"
)

const Network = "whatsapp"

type Adapter struct {
	accountID string
	dataDir   string

	mu     sync.Mutex
	client *whatsmeow.Client
	qr     <-chan whatsmeow.QRChannelItem
	events chan adapter.Event

	// whatsmeow calls the event handler on its receive loop, so the handler must never block:
	// it appends here and a forwarder feeds Events at whatever pace the consumer reads.
	qmu     sync.Mutex
	pending []adapter.Event
	wake    chan struct{}
}

func New(accountID, dataDir string) (adapter.Adapter, error) {
	a := &Adapter{
		accountID: accountID,
		dataDir:   dataDir,
		events:    make(chan adapter.Event, 256),
		wake:      make(chan struct{}, 1),
	}
	go a.forward()
	return a, nil
}

// emit queues an event without blocking the caller.
func (a *Adapter) emit(ev adapter.Event) {
	a.qmu.Lock()
	a.pending = append(a.pending, ev)
	a.qmu.Unlock()
	select {
	case a.wake <- struct{}{}:
	default: // the forwarder is already awake
	}
}

func (a *Adapter) forward() {
	for range a.wake {
		for {
			a.qmu.Lock()
			batch := a.pending
			a.pending = nil
			a.qmu.Unlock()
			if len(batch) == 0 {
				break
			}
			for _, ev := range batch {
				a.events <- ev // blocks only this goroutine, never whatsmeow
			}
		}
	}
}

func (a *Adapter) Network() string { return Network }

func (a *Adapter) ensureClient(ctx context.Context) (*whatsmeow.Client, error) {
	a.mu.Lock()
	defer a.mu.Unlock()
	if a.client != nil {
		return a.client, nil
	}
	if err := os.MkdirAll(a.dataDir, 0o700); err != nil {
		return nil, err
	}
	path := filepath.Join(a.dataDir, a.accountID+".keys.db")
	container, err := sqlstore.New(ctx, "sqlite",
		"file:"+path+"?_pragma=foreign_keys(1)&_pragma=busy_timeout(5000)", waLog.Noop) // never a stdout logger: stdout is the JSON-RPC channel
	if err != nil {
		return nil, fmt.Errorf("whatsapp key store: %w", err)
	}
	device, err := container.GetFirstDevice(ctx)
	if err != nil {
		return nil, err
	}
	a.client = whatsmeow.NewClient(device, waLog.Noop)
	a.client.AddEventHandler(a.handle)
	return a.client, nil
}

// Login drives linking. Call with empty input to get a QR code ("qr" step), then call again
// to get the next code or "done". Or pass a phone number (digits, with country code) to get
// an 8-character pairing code to type into WhatsApp instead ("code" step).
func (a *Adapter) Login(ctx context.Context, in adapter.LoginInput) (adapter.LoginStep, error) {
	cli, err := a.ensureClient(ctx)
	if err != nil {
		return adapter.LoginStep{}, err
	}
	if cli.Store.ID != nil {
		return adapter.LoginStep{Kind: "done", Payload: cli.Store.ID.ToNonAD().String()}, nil
	}
	if phone := strings.TrimPrefix(strings.TrimSpace(in.Value), "+"); phone != "" {
		if !cli.IsConnected() {
			if err := cli.Connect(); err != nil {
				return adapter.LoginStep{}, err
			}
		}
		code, err := cli.PairPhone(ctx, phone, true, whatsmeow.PairClientChrome, "Chrome (soloyolo)")
		if err != nil {
			return adapter.LoginStep{}, err
		}
		return adapter.LoginStep{Kind: "code",
			Payload: code + "  (WhatsApp → Linked devices → Link with phone number)"}, nil
	}
	a.mu.Lock()
	if a.qr == nil {
		// The QR channel must outlive this call: use a background context, not the request's.
		qr, err := cli.GetQRChannel(context.Background())
		if err != nil {
			a.mu.Unlock()
			return adapter.LoginStep{}, err
		}
		a.qr = qr
		if err := cli.Connect(); err != nil {
			a.qr = nil
			a.mu.Unlock()
			return adapter.LoginStep{}, err
		}
	}
	qr := a.qr
	a.mu.Unlock()
	select {
	case item, ok := <-qr:
		if !ok || item.Event == whatsmeow.QRChannelSuccess.Event {
			a.mu.Lock()
			a.qr = nil
			a.mu.Unlock()
			if cli.Store.ID == nil {
				return adapter.LoginStep{}, errors.New("whatsapp: QR channel closed before linking")
			}
			return adapter.LoginStep{Kind: "done", Payload: cli.Store.ID.ToNonAD().String()}, nil
		}
		if item.Event == "code" {
			return adapter.LoginStep{Kind: "qr", Payload: item.Code}, nil
		}
		a.mu.Lock()
		a.qr = nil
		a.mu.Unlock()
		return adapter.LoginStep{}, fmt.Errorf("whatsapp linking: %s %v", item.Event, item.Error)
	case <-ctx.Done():
		return adapter.LoginStep{}, ctx.Err()
	}
}

func (a *Adapter) Connect(ctx context.Context) error {
	cli, err := a.ensureClient(ctx)
	if err != nil {
		return err
	}
	if cli.Store.ID == nil {
		return errors.New("whatsapp: not linked yet, run login first")
	}
	if cli.IsConnected() {
		return nil
	}
	return cli.Connect() // whatsmeow reconnects with backoff on its own after this
}

func (a *Adapter) Events() <-chan adapter.Event { return a.events }

func (a *Adapter) handle(evt any) {
	switch e := evt.(type) {
	case *events.Message:
		if ev, ok := a.convert(e, false); ok {
			a.emit(ev)
		}
	case *events.HistorySync:
		// WhatsApp pushes recent history to a new companion device. It is not years of
		// backlog (a known Mesh limitation too: REPORT.md / BUILD-WITHOUT-BEEPER.md 2).
		for _, conv := range e.Data.GetConversations() {
			chat, err := types.ParseJID(conv.GetID())
			if err != nil {
				continue
			}
			for _, hm := range conv.GetMessages() {
				msg, err := a.client.ParseWebMessage(chat, hm.GetMessage())
				if err != nil {
					continue
				}
				if ev, ok := a.convert(msg, true); ok {
					a.emit(ev)
				}
			}
		}
	case *events.LoggedOut:
		a.emit(adapter.Event{Kind: adapter.EventLogout, Network: Network})
	}
}

// convert keeps 1:1 text messages. Groups, status updates and newsletters are dropped for now.
func (a *Adapter) convert(e *events.Message, history bool) (adapter.Event, bool) {
	if e.Info.IsGroup || e.Info.Chat.Server == types.BroadcastServer || e.Info.Chat.Server == types.NewsletterServer {
		return adapter.Event{}, false
	}
	text := Text(e.Message)
	if text == "" {
		return adapter.Event{}, false
	}
	kind := adapter.EventMessage
	if e.IsEdit {
		kind = adapter.EventEdit
	}
	chat := e.Info.Chat.ToNonAD()
	// Prefer the phone-number address over a privacy LID so one person keeps one handle.
	if chat.Server == types.HiddenUserServer {
		if alt := e.Info.SenderAlt; !e.Info.IsFromMe && !alt.IsEmpty() {
			chat = alt.ToNonAD()
		} else if alt := e.Info.RecipientAlt; e.Info.IsFromMe && !alt.IsEmpty() {
			chat = alt.ToNonAD()
		}
	}
	ev := adapter.Event{Kind: kind, Network: Network, RemoteID: e.Info.ID, ChatID: chat.String(),
		FromMe: e.Info.IsFromMe, Time: e.Info.Timestamp, Text: text, History: history}
	if !e.Info.IsFromMe {
		ev.Sender, ev.Name = chat.String(), e.Info.PushName
	}
	return ev, true
}

// Text pulls the human-readable text out of the message kinds that carry it.
func Text(m *waE2E.Message) string {
	switch {
	case m == nil:
		return ""
	case m.GetConversation() != "":
		return m.GetConversation()
	case m.GetExtendedTextMessage().GetText() != "":
		return m.GetExtendedTextMessage().GetText()
	case m.GetImageMessage().GetCaption() != "":
		return m.GetImageMessage().GetCaption()
	case m.GetVideoMessage().GetCaption() != "":
		return m.GetVideoMessage().GetCaption()
	case m.GetDocumentMessage().GetCaption() != "":
		return m.GetDocumentMessage().GetCaption()
	}
	return ""
}

func (a *Adapter) Send(ctx context.Context, chatID string, m adapter.Outgoing) (string, error) {
	cli, err := a.ensureClient(ctx)
	if err != nil {
		return "", err
	}
	to, err := types.ParseJID(chatID)
	if err != nil {
		return "", fmt.Errorf("chat id %q: %w", chatID, err)
	}
	resp, err := cli.SendMessage(ctx, to, &waE2E.Message{Conversation: proto.String(m.Text)})
	if err != nil {
		return "", err
	}
	return resp.ID, nil
}

func (a *Adapter) Backfill(context.Context, string, adapter.Cursor) ([]adapter.Event, adapter.Cursor, error) {
	// On-demand history needs a request to the phone and async delivery as HistorySync.
	// Not built: initial sync on link covers the spike.
	return nil, "", adapter.ErrUnsupported
}

func (a *Adapter) Contacts(ctx context.Context) ([]adapter.Contact, error) {
	cli, err := a.ensureClient(ctx)
	if err != nil {
		return nil, err
	}
	all, err := cli.Store.Contacts.GetAllContacts(ctx)
	if err != nil {
		return nil, err
	}
	out := make([]adapter.Contact, 0, len(all))
	for jid, c := range all {
		name := c.FullName
		if name == "" {
			name = c.PushName
		}
		out = append(out, adapter.Contact{Address: jid.String(), Name: name})
	}
	return out, nil
}

func (a *Adapter) Close() error {
	a.mu.Lock()
	defer a.mu.Unlock()
	if a.client != nil {
		a.client.Disconnect()
	}
	return nil
}
