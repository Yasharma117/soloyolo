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
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"go.mau.fi/whatsmeow"
	"go.mau.fi/whatsmeow/proto/waE2E"
	"go.mau.fi/whatsmeow/store"
	"go.mau.fi/whatsmeow/store/sqlstore"
	"go.mau.fi/whatsmeow/types"
	"go.mau.fi/whatsmeow/types/events"
	waLog "go.mau.fi/whatsmeow/util/log"
	"google.golang.org/protobuf/proto"

	"github.com/yasharma117/soloyolo/connectord/internal/adapter"
	_ "modernc.org/sqlite"
)

const Network = "whatsapp"

// HistoryDays is how much history a new link asks the phone for. The spike reads the last 300
// messages per person; 90 days covers that for most chats without pulling years of media metadata.
const HistoryDays = 90

func init() {
	// What the phone shows under Linked devices, and how much history it sends on link.
	store.DeviceProps.Os = proto.String("soloyolo")
	store.DeviceProps.RequireFullSync = proto.Bool(true)
	store.DeviceProps.HistorySyncConfig.FullSyncDaysLimit = proto.Uint32(HistoryDays)
}

type Adapter struct {
	accountID string
	dataDir   string

	mu      sync.Mutex
	client  *whatsmeow.Client
	qr      <-chan whatsmeow.QRChannelItem
	pairing bool // a phone-number pairing code is out: wait for success, don't hand back QR codes
	events  chan adapter.Event

	// whatsmeow calls the event handler on its receive loop, so the handler must never block:
	// it appends here and a forwarder feeds Events at whatever pace the consumer reads.
	qmu     sync.Mutex
	pending []adapter.Event
	wake    chan struct{}

	gmu    sync.Mutex
	groups map[types.JID]string // group subject cache

	// pnForLID maps a privacy LID to the phone-number JID, so one person keeps one handle.
	// Tests replace it; in use it reads the device's LID map.
	pnForLID func(types.JID) types.JID
}

func New(accountID, dataDir string) (adapter.Adapter, error) {
	a := &Adapter{
		accountID: accountID,
		dataDir:   dataDir,
		events:    make(chan adapter.Event, 256),
		wake:      make(chan struct{}, 1),
		groups:    map[types.JID]string{},
	}
	a.pnForLID = a.lookupPN
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
		"file:"+path+"?_pragma=foreign_keys(1)&_pragma=busy_timeout(5000)", logger("store")) // never stdout: that's the JSON-RPC channel
	if err != nil {
		return nil, fmt.Errorf("whatsapp key store: %w", err)
	}
	device, err := container.GetFirstDevice(ctx)
	if err != nil {
		return nil, err
	}
	a.client = whatsmeow.NewClient(device, logger("client"))
	// Honour HTTPS_PROXY like every other program on the machine (a no-op where none is set).
	a.client.SetProxy(http.ProxyFromEnvironment)
	a.client.AddEventHandler(a.handle)
	return a.client, nil
}

// Login drives linking. Call with empty input to get a QR code ("qr" step), then call again
// to get the next code or "done". Or pass a phone number (digits, with country code) to get
// an 8-character pairing code to type into WhatsApp instead ("code" step), then call again
// with empty input to wait for "done".
func (a *Adapter) Login(ctx context.Context, in adapter.LoginInput) (adapter.LoginStep, error) {
	cli, err := a.ensureClient(ctx)
	if err != nil {
		return adapter.LoginStep{}, err
	}
	if cli.Store.ID != nil {
		return adapter.LoginStep{Kind: "done", Payload: cli.Store.ID.ToNonAD().String()}, nil
	}
	qr, err := a.qrChannel(cli)
	if err != nil {
		return adapter.LoginStep{}, err
	}
	if phone := strings.Trim(strings.TrimSpace(in.Value), "+"); phone != "" {
		// whatsmeow wants the socket up and the first QR event in before a pairing code can be asked for.
		select {
		case item, ok := <-qr:
			if !ok || item.Event != "code" {
				a.resetQR()
				return adapter.LoginStep{}, fmt.Errorf("whatsapp linking: %s %v", item.Event, item.Error)
			}
		case <-ctx.Done():
			return adapter.LoginStep{}, ctx.Err()
		}
		code, err := cli.PairPhone(ctx, phone, true, whatsmeow.PairClientChrome, "Chrome (soloyolo)")
		if err != nil {
			return adapter.LoginStep{}, err
		}
		a.mu.Lock()
		a.pairing = true
		a.mu.Unlock()
		return adapter.LoginStep{Kind: "code",
			Payload: code + "  (WhatsApp → Linked devices → Link a device → Link with phone number instead)"}, nil
	}
	for {
		select {
		case item, ok := <-qr:
			if !ok || item.Event == whatsmeow.QRChannelSuccess.Event {
				a.resetQR()
				if cli.Store.ID == nil {
					return adapter.LoginStep{}, errors.New("whatsapp: linking ended before it succeeded")
				}
				return adapter.LoginStep{Kind: "done", Payload: cli.Store.ID.ToNonAD().String()}, nil
			}
			if item.Event == "code" {
				a.mu.Lock()
				pairing := a.pairing
				a.mu.Unlock()
				if pairing {
					continue // the user is typing the pairing code; a fresh QR is noise
				}
				return adapter.LoginStep{Kind: "qr", Payload: item.Code}, nil
			}
			a.resetQR()
			return adapter.LoginStep{}, fmt.Errorf("whatsapp linking: %s %v", item.Event, item.Error)
		case <-ctx.Done():
			return adapter.LoginStep{}, ctx.Err()
		}
	}
}

// qrChannel opens the linking channel once and connects; later calls reuse it.
func (a *Adapter) qrChannel(cli *whatsmeow.Client) (<-chan whatsmeow.QRChannelItem, error) {
	a.mu.Lock()
	defer a.mu.Unlock()
	if a.qr != nil {
		return a.qr, nil
	}
	// The QR channel must outlive this call: use a background context, not the request's.
	qr, err := cli.GetQRChannel(context.Background())
	if err != nil {
		return nil, err
	}
	if err := cli.Connect(); err != nil {
		return nil, err
	}
	a.qr = qr
	return qr, nil
}

func (a *Adapter) resetQR() {
	a.mu.Lock()
	a.qr, a.pairing = nil, false
	a.mu.Unlock()
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
		if !e.Info.IsFromMe && e.Info.PushName != "" && !e.Info.IsGroup {
			a.emit(adapter.Event{Kind: adapter.EventContact, Network: Network,
				ChatID: a.person(e.Info.Chat, e.Info.SenderAlt).String(), Name: e.Info.PushName})
		}
	case *events.HistorySync:
		a.history(e)
	case *events.CallOffer:
		// Live calls only arrive as offers to this device; the phone's own outgoing calls come
		// later through history sync's call log.
		if e.GroupJID.IsEmpty() {
			a.emit(adapter.Event{Kind: adapter.EventCall, Network: Network, RemoteID: "call:" + e.CallID,
				ChatID: a.person(e.From, e.CallCreatorAlt).String(), Time: e.Timestamp, Text: adapter.CallText})
		}
	case *events.AppStateSyncComplete:
		// The address book has arrived: the names you saved beat the names people give themselves.
		go func() {
			contacts, err := a.Contacts(context.Background())
			if err != nil {
				return
			}
			for _, c := range contacts {
				if c.Name != "" && c.Saved {
					a.emit(adapter.Event{Kind: adapter.EventContact, Network: Network, ChatID: c.Address,
						Name: c.Name, Saved: true})
				}
			}
		}()
	case *events.LoggedOut:
		a.emit(adapter.Event{Kind: adapter.EventLogout, Network: Network})
	}
}

// history unpacks what the phone sends a newly linked device: recent conversations, the names
// people go by, and the call log.
func (a *Adapter) history(e *events.HistorySync) {
	for _, pn := range e.Data.GetPushnames() {
		if jid, err := types.ParseJID(pn.GetID()); err == nil && pn.GetPushname() != "" && jid.Server != types.GroupServer {
			a.emit(adapter.Event{Kind: adapter.EventContact, Network: Network, History: true,
				ChatID: a.person(jid, types.EmptyJID).String(), Name: pn.GetPushname()})
		}
	}
	for _, conv := range e.Data.GetConversations() {
		chat, err := types.ParseJID(conv.GetID())
		if err != nil {
			continue
		}
		if chat.Server == types.GroupServer && conv.GetName() != "" {
			a.gmu.Lock()
			a.groups[chat] = conv.GetName()
			a.gmu.Unlock()
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
	for _, c := range e.Data.GetCallLogRecords() {
		if c.GetGroupJID() != "" {
			continue
		}
		other := c.GetCallCreatorJID()
		if a.client != nil && a.client.Store.ID != nil && isMe(other, *a.client.Store.ID, a.client.Store.LID) {
			if ps := c.GetParticipants(); len(ps) > 0 {
				other = ps[0].GetUserJID()
			}
		}
		jid, err := types.ParseJID(other)
		if err != nil || jid.IsEmpty() {
			continue
		}
		a.emit(adapter.Event{Kind: adapter.EventCall, Network: Network, History: true, RemoteID: "call:" + c.GetCallID(),
			ChatID: a.person(jid, types.EmptyJID).String(), Time: unixAny(c.GetStartTime()), Text: adapter.CallText,
			FromMe: other != c.GetCallCreatorJID()})
	}
}

func isMe(jid string, me, lid types.JID) bool {
	j, err := types.ParseJID(jid)
	return err == nil && (j.User == me.User || (!lid.IsEmpty() && j.User == lid.User))
}

// unixAny reads a timestamp that may be in seconds or milliseconds.
func unixAny(v int64) time.Time {
	if v > 1e12 {
		return time.UnixMilli(v)
	}
	return time.Unix(v, 0)
}

// person is the handle a 1:1 chat is stored under: the phone-number JID when one is known,
// so a contact seen once by LID and once by number stays one person.
func (a *Adapter) person(chat, alt types.JID) types.JID {
	chat = chat.ToNonAD()
	if chat.Server != types.HiddenUserServer {
		return chat
	}
	if !alt.IsEmpty() && alt.Server == types.DefaultUserServer {
		return alt.ToNonAD()
	}
	if pn := a.pnForLID(chat); !pn.IsEmpty() {
		return pn.ToNonAD()
	}
	return chat
}

func (a *Adapter) lookupPN(lid types.JID) types.JID {
	if a.client == nil {
		return types.EmptyJID
	}
	pn, err := a.client.Store.LIDs.GetPNForLID(context.Background(), lid)
	if err != nil {
		return types.EmptyJID
	}
	return pn
}

// groupName answers from the cache only: it runs inside whatsmeow's event handler, where a
// network request would stall the receive loop that has to deliver its own reply. A miss starts
// one lookup in the background, which renames the group's evidence once the subject is known.
func (a *Adapter) groupName(g types.JID) string {
	a.gmu.Lock()
	name, ok := a.groups[g]
	if !ok {
		a.groups[g] = "" // one lookup per group per run
	}
	a.gmu.Unlock()
	if !ok && a.client != nil {
		go func() {
			ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
			defer cancel()
			info, err := a.client.GetGroupInfo(ctx, g)
			if err != nil || info.Name == "" {
				return
			}
			a.gmu.Lock()
			a.groups[g] = info.Name
			a.gmu.Unlock()
			a.emit(adapter.Event{Kind: adapter.EventContact, Network: Network, Group: g.String(), GroupName: info.Name})
		}()
	}
	return name
}

// convert keeps 1:1 messages, and group messages as evidence. Status updates, broadcast lists
// and channels are dropped.
func (a *Adapter) convert(e *events.Message, history bool) (adapter.Event, bool) {
	if e.Info.Chat.Server == types.BroadcastServer || e.Info.Chat.Server == types.NewsletterServer {
		return adapter.Event{}, false
	}
	text := Content(e.Message)
	if text == "" {
		return adapter.Event{}, false
	}
	kind := adapter.EventMessage
	if e.IsEdit {
		kind = adapter.EventEdit
	}
	ev := adapter.Event{Kind: kind, Network: Network, RemoteID: e.Info.ID, FromMe: e.Info.IsFromMe,
		Time: e.Info.Timestamp, Text: text, History: history}
	if e.Info.IsGroup {
		g := e.Info.Chat.ToNonAD()
		ev.Group, ev.ChatID = g.String(), g.String()
		ev.GroupName = a.groupName(g)
		if !e.Info.IsFromMe {
			ev.Sender, ev.Name = a.person(e.Info.Sender, e.Info.SenderAlt).String(), e.Info.PushName
		}
		return ev, true
	}
	alt := e.Info.SenderAlt
	if e.Info.IsFromMe {
		alt = e.Info.RecipientAlt
	}
	chat := a.person(e.Info.Chat, alt)
	ev.ChatID = chat.String()
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

// Content is what gets stored: the text, with a marker for media and calls. "Send me the pic"
// is done by the photo and "I'll call you back" by the call, so those count as evidence.
// Stickers, reactions and GIFs carry nothing and are dropped. Markers match the spike's import.
func Content(m *waE2E.Message) string {
	if m == nil {
		return ""
	}
	text := Text(m)
	mark := ""
	switch {
	case m.GetImageMessage() != nil:
		mark = "[photo]"
	case m.GetVideoMessage() != nil:
		if m.GetVideoMessage().GetGifPlayback() {
			return text
		}
		mark = "[video]"
	case m.GetDocumentMessage() != nil:
		mark = "[document]"
		if text == "" {
			text = m.GetDocumentMessage().GetFileName()
		}
	case m.GetAudioMessage() != nil:
		mark = "[voice note]"
	case m.GetCallLogMesssage() != nil:
		return adapter.CallText
	}
	return strings.TrimSpace(mark + " " + text)
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
		name, saved := c.FullName, true
		if name == "" {
			name = c.FirstName
		}
		if name == "" {
			name, saved = c.PushName, false
		}
		out = append(out, adapter.Contact{Address: a.person(jid, types.EmptyJID).String(), Name: name, Saved: saved})
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

// logger is silent unless SOLOYOLO_DEBUG is set, and then writes to stderr, never stdout.
func logger(module string) waLog.Logger {
	if os.Getenv("SOLOYOLO_DEBUG") == "" {
		return waLog.Noop
	}
	return stderrLog{module}
}

type stderrLog struct{ module string }

func (l stderrLog) put(level, msg string, args ...any) {
	log.Printf("whatsapp %s %s: %s", l.module, level, fmt.Sprintf(msg, args...))
}
func (l stderrLog) Errorf(msg string, args ...any) { l.put("ERROR", msg, args...) }
func (l stderrLog) Warnf(msg string, args ...any)  { l.put("WARN", msg, args...) }
func (l stderrLog) Infof(msg string, args ...any)  { l.put("INFO", msg, args...) }
func (l stderrLog) Debugf(msg string, args ...any) {
	if os.Getenv("SOLOYOLO_DEBUG") == "2" {
		l.put("DEBUG", msg, args...)
	}
}
func (l stderrLog) Sub(module string) waLog.Logger { return stderrLog{l.module + "/" + module} }
