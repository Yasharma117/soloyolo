// Package telegram signs in to Telegram as you (a user session over MTProto, not a bot) with
// gotd/td (MIT) and reads your chats. It is read-only by construction: the only requests it
// makes are the login calls, users.getUsers for yourself, messages.getDialogs,
// messages.getHistory and the updates.* calls that keep the live stream gap-free. It never
// sends, never marks anything read, and never sets your online status. See docs/TELEGRAM.md
// for the routes, the limits and the account-risk question; read that before linking.
//
// What it reads: 1:1 chats with people become messages; basic groups become evidence lines that
// can close an item but never create one. Bots, channels, supergroups, Saved Messages, the
// Telegram service chat (login codes) and auto-deleting messages are skipped. Secret chats live
// only on the device that started them and are not reachable at all.
//
// The session key lives in dataDir/<account>.session.json (mode 0600, dir 0700). Leaking it
// means someone else can read your Telegram. api_id and api_hash are yours, from
// my.telegram.org: TELEGRAM_API_ID / TELEGRAM_API_HASH, or telegram-api.json beside the store (telegram.json there is the morning-message bot's).
package telegram

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/gotd/td/telegram/auth"
	"github.com/gotd/td/tg"
	"github.com/gotd/td/tgerr"

	"github.com/yasharma117/soloyolo/connectord/internal/adapter"
)

const Network = "telegram"

// HistoryDays is how far back the first sync reads. Matches WhatsApp and Slack.
const HistoryDays = 90

// remote is the handful of Telegram calls the adapter makes. The real one wraps a gotd client
// (client.go); tests use a fake. There is deliberately no send or read-receipt method on it.
type remote interface {
	// Self returns the signed-in user, or errNotLinked.
	Self(ctx context.Context) (*tg.User, error)
	// SendCode asks Telegram to send a login code. via says where it went ("app", "sms"...).
	SendCode(ctx context.Context, phone string) (hash, via string, err error)
	SignIn(ctx context.Context, phone, code, hash string) error
	Password(ctx context.Context, password string) error
	Dialogs(ctx context.Context, req *tg.MessagesGetDialogsRequest) (tg.MessagesDialogsClass, error)
	History(ctx context.Context, req *tg.MessagesGetHistoryRequest) (tg.MessagesMessagesClass, error)
	// Live delivers new and edited messages to the adapter's live method until ctx ends.
	Live(ctx context.Context, self int64) error
	Close()
}

var errNotLinked = errors.New("telegram: not linked yet, run login first")

type Adapter struct {
	accountID string
	dataDir   string

	// Knobs, set by New; tests change them before Connect.
	Since        time.Time     // first-sync horizon; zero means HistoryDays ago
	PageSize     int           // messages per history page and dialogs per page (Telegram's cap is 100)
	MaxPerChat   int           // newest messages read per chat in one sync
	MaxPages     int           // dialog pages per folder: bounds the walk on accounts with thousands of chats
	Pace         time.Duration // pause between requests during a sync
	ResyncEvery  time.Duration // least time between two catch-up syncs
	MaxFloodWait time.Duration // a longer flood wait than this ends the sync instead of sleeping

	dial  func(ctx context.Context) (remote, error)
	sleep func(context.Context, time.Duration) error
	now   func() time.Time

	mu       sync.Mutex
	cli      remote
	self     int64
	phone    string // login in progress
	codeHash string
	stage    string // "" | "code" | "password"
	people   map[int64]person
	groups   map[int64]string // basic group id → title
	named    map[int64]bool   // people already announced as contacts this run
	state    syncState
	cancel   context.CancelFunc
	done     chan struct{}
	resync   chan struct{}
	events   chan adapter.Event

	// gotd calls the update handler on its receive path, so it must never block: live events
	// are appended here and a forwarder feeds Events at whatever pace the consumer reads.
	qmu     sync.Mutex
	pending []adapter.Event
	wake    chan struct{}
}

// syncState is what survives a restart: where each chat's history got to.
type syncState struct {
	Cursors  map[string]int `json:"cursors"`   // "u123" / "g456" → newest message id stored
	SyncedAt int64          `json:"synced_at"` // unix seconds of the last sync that finished
}

func New(accountID, dataDir string) (adapter.Adapter, error) {
	return newAdapter(accountID, dataDir), nil
}

func newAdapter(accountID, dataDir string) *Adapter {
	a := &Adapter{
		accountID:    accountID,
		dataDir:      dataDir,
		PageSize:     100,
		MaxPerChat:   1000,
		MaxPages:     20,
		Pace:         time.Second,
		ResyncEvery:  time.Minute,
		MaxFloodWait: time.Hour,
		sleep:        sleepCtx,
		now:          time.Now,
		people:       map[int64]person{},
		groups:       map[int64]string{},
		named:        map[int64]bool{},
		state:        syncState{Cursors: map[string]int{}},
		resync:       make(chan struct{}, 1),
		events:       make(chan adapter.Event, 256),
		wake:         make(chan struct{}, 1),
	}
	a.dial = a.dialMTProto
	go a.forward()
	return a
}

func (a *Adapter) Network() string { return Network }

func (a *Adapter) Events() <-chan adapter.Event { return a.events }

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
				a.events <- ev // blocks only this goroutine, never gotd
			}
		}
	}
}

// client connects once and reuses the connection for login, sync and live updates.
func (a *Adapter) client(ctx context.Context) (remote, error) {
	a.mu.Lock()
	defer a.mu.Unlock()
	if a.cli != nil {
		return a.cli, nil
	}
	cli, err := a.dial(ctx)
	if err != nil {
		return nil, err
	}
	a.cli = cli
	return cli, nil
}

// Login drives sign-in. Pass your phone number (digits, with country code) to have Telegram
// send a code ("code" step); call again with the code; if the account has a two-step password
// you get a "password" step and call once more with it. A wrong code or password returns the
// same step again, so nothing is re-sent. With no input and nothing in progress it returns a
// "phone" step. Unlike WhatsApp's, these steps never block waiting: each needs a value.
func (a *Adapter) Login(ctx context.Context, in adapter.LoginInput) (adapter.LoginStep, error) {
	cli, err := a.client(ctx)
	if err != nil {
		return adapter.LoginStep{}, err
	}
	if me, err := cli.Self(ctx); err == nil {
		a.signedIn(me)
		return adapter.LoginStep{Kind: "done", Payload: strconv.FormatInt(me.ID, 10)}, nil
	} else if !errors.Is(err, errNotLinked) {
		return adapter.LoginStep{}, loginErr(err)
	}
	v := strings.TrimSpace(in.Value)
	a.mu.Lock()
	stage, phone, hash := a.stage, a.phone, a.codeHash
	a.mu.Unlock()

	switch stage {
	case "code":
		if v == "" {
			return adapter.LoginStep{Kind: "code", Payload: "the login code Telegram sent you"}, nil
		}
		err := cli.SignIn(ctx, phone, digits(v), hash)
		var signUp *auth.SignUpRequired
		switch {
		case err == nil:
			return a.finish(ctx, cli)
		case errors.Is(err, auth.ErrPasswordAuthNeeded):
			a.setStage("password")
			return adapter.LoginStep{Kind: "password", Payload: "your Telegram two-step verification password"}, nil
		case tgerr.Is(err, "PHONE_CODE_INVALID", "PHONE_CODE_EMPTY"):
			return adapter.LoginStep{Kind: "code", Payload: "that code was wrong; enter the code Telegram sent you"}, nil
		case tgerr.Is(err, "PHONE_CODE_EXPIRED"):
			a.setStage("")
			return adapter.LoginStep{}, errors.New("telegram: that code has expired; start again with your phone number")
		case errors.As(err, &signUp):
			a.setStage("")
			return adapter.LoginStep{}, errors.New("telegram: there is no Telegram account for that number")
		}
		return adapter.LoginStep{}, loginErr(err)
	case "password":
		if v == "" {
			return adapter.LoginStep{Kind: "password", Payload: "your Telegram two-step verification password"}, nil
		}
		err := cli.Password(ctx, in.Value) // untrimmed: a password may start or end with a space
		switch {
		case err == nil:
			return a.finish(ctx, cli)
		case errors.Is(err, auth.ErrPasswordInvalid), tgerr.Is(err, "PASSWORD_HASH_INVALID"):
			return adapter.LoginStep{Kind: "password", Payload: "that password was wrong; enter your two-step verification password"}, nil
		}
		return adapter.LoginStep{}, loginErr(err)
	}

	p := digits(v)
	if p == "" {
		return adapter.LoginStep{Kind: "phone", Payload: "your Telegram phone number with country code, e.g. 919800000000"}, nil
	}
	hash, via, err := cli.SendCode(ctx, p)
	if err != nil {
		if tgerr.Is(err, "PHONE_NUMBER_INVALID") {
			return adapter.LoginStep{}, errors.New("telegram: that phone number is not valid; include the country code")
		}
		return adapter.LoginStep{}, loginErr(err)
	}
	if hash == "" { // Telegram signed this session in without a code
		return a.finish(ctx, cli)
	}
	a.mu.Lock()
	a.stage, a.phone, a.codeHash = "code", p, hash
	a.mu.Unlock()
	return adapter.LoginStep{Kind: "code", Payload: "the login code Telegram sent you (" + via + ")"}, nil
}

func (a *Adapter) setStage(s string) {
	a.mu.Lock()
	a.stage = s
	if s == "" {
		a.phone, a.codeHash = "", ""
	}
	a.mu.Unlock()
}

func (a *Adapter) finish(ctx context.Context, cli remote) (adapter.LoginStep, error) {
	a.setStage("")
	me, err := cli.Self(ctx)
	if err != nil {
		return adapter.LoginStep{}, loginErr(err)
	}
	a.signedIn(me)
	return adapter.LoginStep{Kind: "done", Payload: strconv.FormatInt(me.ID, 10)}, nil
}

func (a *Adapter) signedIn(me *tg.User) {
	a.mu.Lock()
	a.self = me.ID
	a.mu.Unlock()
}

// loginErr never sleeps on a flood wait: a login that hangs for an hour looks broken, and
// asking again sooner only lengthens the wait. It says how long instead.
func loginErr(err error) error {
	if d, ok := tgerr.AsFloodWait(err); ok {
		return fmt.Errorf("telegram: too many login attempts; Telegram says wait %s before trying again", d)
	}
	return err
}

func digits(s string) string {
	return strings.Map(func(r rune) rune {
		if r >= '0' && r <= '9' {
			return r
		}
		return -1
	}, s)
}

// Connect checks the session, then syncs in the background: recent history for every kept
// chat (1:1 first), then live updates, with a catch-up sync whenever a new chat appears.
func (a *Adapter) Connect(ctx context.Context) error {
	a.mu.Lock()
	running := a.cancel != nil
	a.mu.Unlock()
	if running {
		return nil
	}
	cli, err := a.client(ctx)
	if err != nil {
		return err
	}
	me, err := cli.Self(ctx)
	if err != nil {
		if isLoggedOut(err) {
			a.emit(adapter.Event{Kind: adapter.EventLogout, Network: Network})
		}
		return err
	}
	a.signedIn(me)
	a.loadState()
	runCtx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{})
	a.mu.Lock()
	a.cancel, a.done = cancel, done
	a.mu.Unlock()
	go func() {
		// Start listening before the backfill so nothing sent during it is missed; the store
		// dedupes what both paths deliver.
		if err := cli.Live(runCtx, me.ID); err != nil && runCtx.Err() == nil {
			a.fail(runCtx, fmt.Errorf("live updates: %w", err))
		}
	}()
	go func() {
		defer close(done)
		a.run(runCtx, cli)
	}()
	return nil
}

// fail reports whether the run should stop: the context ended, or the session was revoked.
func (a *Adapter) fail(ctx context.Context, err error) bool {
	if err == nil || ctx.Err() != nil {
		return ctx.Err() != nil
	}
	if isLoggedOut(err) {
		a.emit(adapter.Event{Kind: adapter.EventLogout, Network: Network})
		return true
	}
	log.Printf("telegram %s: %v", a.accountID, err) // stderr; the next sync retries
	return false
}

func isLoggedOut(err error) bool {
	return errors.Is(err, errNotLinked) || auth.IsUnauthorized(err)
}

func (a *Adapter) run(ctx context.Context, cli remote) {
	if a.fail(ctx, a.syncAll(ctx, cli)) {
		return
	}
	for {
		select {
		case <-ctx.Done():
			return
		case <-a.resync:
			// A message arrived from someone not seen yet. Wait, so a burst costs one sync.
			if a.sleep(ctx, a.ResyncEvery) != nil {
				return
			}
			select {
			case <-a.resync:
			default:
			}
			if a.fail(ctx, a.syncAll(ctx, cli)) {
				return
			}
		}
	}
}

// call runs one request. On a flood wait it sleeps exactly as long as Telegram says and tries
// again; a wait longer than MaxFloodWait, or a fifth in a row, ends the sync instead.
func (a *Adapter) call(ctx context.Context, do func() error) error {
	for try := 1; ; try++ {
		err := do()
		d, flood := tgerr.AsFloodWait(err)
		if !flood {
			return err
		}
		if try >= 5 || d > a.MaxFloodWait {
			return fmt.Errorf("telegram: flood wait of %s, giving up for now: %w", d, err)
		}
		log.Printf("telegram %s: flood wait, sleeping %s as told", a.accountID, d)
		if err := a.sleep(ctx, d); err != nil {
			return err
		}
	}
}

// target is one chat whose history needs reading.
type target struct {
	key   string // cursor key
	peer  tg.InputPeerClass
	top   int // newest message id in the chat
	group bool
}

// syncAll walks the dialog list, newest first, as far back as the horizon, and reads the
// history of every kept chat that has something newer than its cursor.
func (a *Adapter) syncAll(ctx context.Context, cli remote) error {
	started := a.now()
	horizon := a.Since
	if horizon.IsZero() {
		horizon = started.AddDate(0, 0, -HistoryDays)
	}
	// Later syncs only need dialogs that moved since the last one finished.
	stop := horizon
	a.mu.Lock()
	if last := time.Unix(a.state.SyncedAt, 0).Add(-time.Hour); a.state.SyncedAt != 0 && last.After(stop) {
		stop = last
	}
	a.mu.Unlock()

	var targets []target
	for _, folder := range []int{0, 1} { // the main list, then the archive
		ts, err := a.dialogs(ctx, cli, folder, horizon, stop)
		if err != nil {
			return err
		}
		targets = append(targets, ts...)
	}
	// People before groups: messages matter more than evidence if the sync is cut short.
	sort.SliceStable(targets, func(i, j int) bool { return !targets[i].group && targets[j].group })
	for _, t := range targets {
		if err := a.history(ctx, cli, t, horizon); err != nil {
			return err
		}
		a.mu.Lock()
		a.state.Cursors[t.key] = t.top
		a.mu.Unlock()
		a.saveState()
	}
	a.mu.Lock()
	a.state.SyncedAt = started.Unix()
	a.mu.Unlock()
	a.saveState()
	return nil
}

// dialogs pages through one folder's chat list and returns the chats that need reading.
func (a *Adapter) dialogs(ctx context.Context, cli remote, folder int, horizon, stop time.Time) ([]target, error) {
	var out []target
	req := &tg.MessagesGetDialogsRequest{OffsetPeer: &tg.InputPeerEmpty{}, Limit: a.PageSize}
	if folder != 0 {
		req.SetFolderID(folder)
	}
	for page := 0; page < a.MaxPages; page++ {
		if page > 0 {
			if err := a.sleep(ctx, a.Pace); err != nil {
				return nil, err
			}
		}
		var res tg.MessagesDialogsClass
		if err := a.call(ctx, func() (err error) { res, err = cli.Dialogs(ctx, req); return }); err != nil {
			return nil, fmt.Errorf("dialogs: %w", err)
		}
		d, ok := res.AsModified()
		if !ok {
			break
		}
		a.remember(d.GetUsers(), d.GetChats())
		dates := map[string]int{} // peer key + message id → date
		for _, m := range d.GetMessages() {
			if ne, ok := m.AsNotEmpty(); ok {
				dates[peerKey(ne.GetPeerID())+"/"+strconv.Itoa(m.GetID())] = ne.GetDate()
			}
		}
		oldest, last := 0, (*tg.Dialog)(nil)
		for _, dc := range d.GetDialogs() {
			dlg, ok := dc.(*tg.Dialog) // the other kind is the archive folder itself
			if !ok {
				continue
			}
			date := dates[peerKey(dlg.Peer)+"/"+strconv.Itoa(dlg.TopMessage)]
			last = dlg
			if !dlg.Pinned && (oldest == 0 || date < oldest) {
				oldest = date // pinned chats sit on top whatever their age
			}
			if int64(date) < horizon.Unix() {
				continue // older than the window; announcing the person would add an empty contact
			}
			if t, ok := a.target(dlg); ok {
				out = append(out, t)
			}
		}
		_, whole := res.(*tg.MessagesDialogs) // the full list, not a slice of it
		if whole || last == nil || (oldest != 0 && int64(oldest) < stop.Unix()) {
			break
		}
		req.OffsetDate = dates[peerKey(last.Peer)+"/"+strconv.Itoa(last.TopMessage)]
		req.OffsetID = last.TopMessage
		req.OffsetPeer = inputPeer(last.Peer, d.GetUsers(), d.GetChats())
	}
	return out, nil
}

// target decides whether a dialog is kept and has anything newer than its cursor.
func (a *Adapter) target(dlg *tg.Dialog) (target, bool) {
	a.mu.Lock()
	defer a.mu.Unlock()
	key := peerKey(dlg.Peer)
	if dlg.TopMessage <= a.state.Cursors[key] {
		return target{}, false
	}
	switch p := dlg.Peer.(type) {
	case *tg.PeerUser:
		who, ok := a.people[p.UserID]
		if !ok || !who.keep || p.UserID == a.self {
			return target{}, false
		}
		a.announce(p.UserID, who, true)
		return target{key: key, top: dlg.TopMessage, peer: &tg.InputPeerUser{UserID: p.UserID, AccessHash: who.hash}}, true
	case *tg.PeerChat:
		title, ok := a.groups[p.ChatID]
		if !ok {
			return target{}, false // left, or migrated to a supergroup
		}
		if title != "" {
			a.emit(adapter.Event{Kind: adapter.EventContact, Network: Network, History: true,
				Group: key, GroupName: title})
		}
		return target{key: key, top: dlg.TopMessage, group: true, peer: &tg.InputPeerChat{ChatID: p.ChatID}}, true
	}
	return target{}, false // channels and supergroups
}

// announce emits a person's name once per run. Callers hold a.mu.
func (a *Adapter) announce(id int64, who person, history bool) {
	if a.named[id] || who.name == "" {
		return
	}
	a.named[id] = true
	a.emit(adapter.Event{Kind: adapter.EventContact, Network: Network, History: history,
		ChatID: strconv.FormatInt(id, 10), Name: who.name, Saved: who.saved})
}

// history reads one chat backwards from its newest message until the cursor, the horizon or
// MaxPerChat, whichever comes first.
func (a *Adapter) history(ctx context.Context, cli remote, t target, horizon time.Time) error {
	a.mu.Lock()
	cursor := a.state.Cursors[t.key]
	a.mu.Unlock()
	req := &tg.MessagesGetHistoryRequest{Peer: t.peer, Limit: a.PageSize, MinID: cursor}
	for n := 0; n < a.MaxPerChat; {
		if err := a.sleep(ctx, a.Pace); err != nil {
			return err
		}
		var res tg.MessagesMessagesClass
		if err := a.call(ctx, func() (err error) { res, err = cli.History(ctx, req); return }); err != nil {
			return fmt.Errorf("history %s: %w", t.key, err)
		}
		h, ok := res.AsModified()
		if !ok || len(h.GetMessages()) == 0 {
			return nil
		}
		a.remember(h.GetUsers(), h.GetChats())
		for _, m := range h.GetMessages() {
			ne, ok := m.AsNotEmpty()
			if m.GetID() <= cursor || (ok && int64(ne.GetDate()) < horizon.Unix()) || n >= a.MaxPerChat {
				return nil
			}
			n++
			if ev, ok := a.convert(m, true); ok {
				a.emit(ev)
			}
			req.OffsetID = m.GetID()
		}
		if _, whole := res.(*tg.MessagesMessages); whole || len(h.GetMessages()) < req.Limit {
			return nil // the full list, or a short last page: nothing older to ask for
		}
	}
	return nil
}

// live takes one new or edited message from the update stream. It must not block.
func (a *Adapter) live(e tg.Entities, m tg.MessageClass, edit bool) {
	for _, u := range e.Users {
		a.rememberUser(u)
	}
	for _, c := range e.Chats {
		a.rememberChat(c)
	}
	ev, ok := a.convert(m, false)
	if !ok {
		if a.stranger(m) {
			select {
			case a.resync <- struct{}{}:
			default: // one is already queued
			}
		}
		return
	}
	if edit {
		ev.Kind = adapter.EventEdit
	}
	if ev.Group == "" && !ev.FromMe {
		if id, err := strconv.ParseInt(ev.ChatID, 10, 64); err == nil {
			a.mu.Lock()
			a.announce(id, a.people[id], false)
			a.mu.Unlock()
		}
	}
	a.emit(ev)
}

func (a *Adapter) Send(context.Context, string, adapter.Outgoing) (string, error) {
	// Read-only on purpose: an account that only reads is the low-risk case (docs/TELEGRAM.md).
	return "", adapter.ErrUnsupported
}

func (a *Adapter) Backfill(context.Context, string, adapter.Cursor) ([]adapter.Event, adapter.Cursor, error) {
	// Not built: the sync on connect covers the spike.
	return nil, "", adapter.ErrUnsupported
}

// Contacts lists the people seen in your chat list so far. It makes no request of its own.
func (a *Adapter) Contacts(context.Context) ([]adapter.Contact, error) {
	a.mu.Lock()
	defer a.mu.Unlock()
	out := make([]adapter.Contact, 0, len(a.people))
	for id, p := range a.people {
		if p.keep && id != a.self {
			out = append(out, adapter.Contact{Address: strconv.FormatInt(id, 10), Name: p.name, Saved: p.saved})
		}
	}
	return out, nil
}

func (a *Adapter) Close() error {
	a.mu.Lock()
	cancel, done, cli := a.cancel, a.done, a.cli
	a.cancel, a.done, a.cli = nil, nil, nil
	a.mu.Unlock()
	if cancel != nil {
		cancel()
		<-done
	}
	if cli != nil {
		cli.Close()
	}
	return nil
}

func (a *Adapter) statePath() string { return filepath.Join(a.dataDir, "sync.json") }

func (a *Adapter) loadState() {
	b, err := os.ReadFile(a.statePath())
	if err != nil {
		return
	}
	var s syncState
	if json.Unmarshal(b, &s) == nil && s.Cursors != nil {
		a.mu.Lock()
		a.state = s
		a.mu.Unlock()
	}
}

func (a *Adapter) saveState() {
	a.mu.Lock()
	b, err := json.Marshal(a.state)
	a.mu.Unlock()
	if err != nil || os.MkdirAll(a.dataDir, 0o700) != nil {
		return
	}
	tmp := a.statePath() + ".tmp"
	if os.WriteFile(tmp, b, 0o600) == nil {
		os.Rename(tmp, a.statePath())
	}
}

func sleepCtx(ctx context.Context, d time.Duration) error {
	if d <= 0 {
		return ctx.Err()
	}
	t := time.NewTimer(d)
	defer t.Stop()
	select {
	case <-t.C:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}
