package telegram

import (
	"context"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"testing"
	"time"

	"github.com/gotd/td/telegram/auth"
	"github.com/gotd/td/tg"
	"github.com/gotd/td/tgerr"

	"github.com/yasharma117/soloyolo/connectord/internal/adapter"
)

const me = 1000

// fake is Telegram as far as the adapter can tell. It has no way to send or mark read, so a
// test that compiles is a test that only read.
type fake struct {
	mu       sync.Mutex
	in       bool // signed in
	code     string
	password string // "" means no two-step password
	sendErr  error
	sent     int
	users    []tg.UserClass
	chats    []tg.ChatClass
	dialogs  []tg.DialogClass
	msgs     map[string][]tg.MessageClass // peer key → newest first
	floods   int                          // history calls that fail with FLOOD_WAIT_7 first
	calls    []string
}

func (f *fake) Self(context.Context) (*tg.User, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if !f.in {
		return nil, errNotLinked
	}
	return &tg.User{ID: me, Self: true, FirstName: "Me"}, nil
}

func (f *fake) SendCode(_ context.Context, phone string) (string, string, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.sent++
	f.calls = append(f.calls, "sendCode "+phone)
	return "hash1", "by SMS", f.sendErr
}

func (f *fake) SignIn(_ context.Context, phone, code, hash string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	switch {
	case hash != "hash1" || phone != "919800000000":
		return errors.New("wrong phone or hash")
	case code != f.code:
		return tgerr.New(400, "PHONE_CODE_INVALID")
	case f.password != "":
		return auth.ErrPasswordAuthNeeded
	}
	f.in = true
	return nil
}

func (f *fake) Password(_ context.Context, pw string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	if pw != f.password {
		return auth.ErrPasswordInvalid
	}
	f.in = true
	return nil
}

func (f *fake) Dialogs(_ context.Context, req *tg.MessagesGetDialogsRequest) (tg.MessagesDialogsClass, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.calls = append(f.calls, fmt.Sprintf("dialogs folder=%d", req.FolderID))
	if req.FolderID != 0 {
		return &tg.MessagesDialogs{}, nil
	}
	var tops []tg.MessageClass
	for _, d := range f.dialogs {
		if ms := f.msgs[peerKey(d.(*tg.Dialog).Peer)]; len(ms) > 0 {
			tops = append(tops, ms[0])
		}
	}
	return &tg.MessagesDialogs{Dialogs: f.dialogs, Messages: tops, Users: f.users, Chats: f.chats}, nil
}

func (f *fake) History(_ context.Context, req *tg.MessagesGetHistoryRequest) (tg.MessagesMessagesClass, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.floods > 0 {
		f.floods--
		return nil, tgerr.New(420, "FLOOD_WAIT_7")
	}
	key := ""
	switch p := req.Peer.(type) {
	case *tg.InputPeerUser:
		key = peerKey(&tg.PeerUser{UserID: p.UserID})
	case *tg.InputPeerChat:
		key = peerKey(&tg.PeerChat{ChatID: p.ChatID})
	}
	f.calls = append(f.calls, fmt.Sprintf("history %s offset=%d min=%d", key, req.OffsetID, req.MinID))
	var page []tg.MessageClass
	for _, m := range f.msgs[key] {
		if (req.OffsetID == 0 || m.GetID() < req.OffsetID) && m.GetID() > req.MinID && len(page) < req.Limit {
			page = append(page, m)
		}
	}
	return &tg.MessagesMessagesSlice{Messages: page, Users: f.users}, nil
}

func (f *fake) Live(ctx context.Context, _ int64) error { <-ctx.Done(); return nil }
func (f *fake) Close()                                  {}

var t0 = time.Date(2026, 11, 10, 9, 0, 0, 0, time.UTC)

func msg(id int, peer tg.PeerClass, out bool, age time.Duration, text string) *tg.Message {
	return &tg.Message{ID: id, PeerID: peer, Out: out, Date: int(t0.Add(-age).Unix()), Message: text}
}

func user(id int64) *tg.PeerUser { return &tg.PeerUser{UserID: id} }

// newTest wires an adapter to a fake, with no real waiting: sleeps are recorded instead.
func newTest(t *testing.T, f *fake) (*Adapter, *[]time.Duration) {
	t.Helper()
	a := newAdapter("telegram-1", t.TempDir())
	a.dial = func(context.Context) (remote, error) { return f, nil }
	a.now = func() time.Time { return t0 }
	a.Pace = 0
	var slept []time.Duration
	var mu sync.Mutex
	a.sleep = func(ctx context.Context, d time.Duration) error {
		mu.Lock()
		if d > 0 {
			slept = append(slept, d)
		}
		mu.Unlock()
		return ctx.Err()
	}
	t.Cleanup(func() { a.Close() })
	return a, &slept
}

func step(t *testing.T, a *Adapter, value, wantKind string) adapter.LoginStep {
	t.Helper()
	s, err := a.Login(context.Background(), adapter.LoginInput{Value: value})
	if err != nil || s.Kind != wantKind {
		t.Fatalf("Login(%q) = %+v, %v; want kind %q", value, s, err, wantKind)
	}
	return s
}

func TestLoginPhoneCodePassword(t *testing.T) {
	f := &fake{code: "12345", password: "hunter 2 "}
	a, _ := newTest(t, f)
	step(t, a, "", "phone")
	step(t, a, "+91 98000-00000", "code")
	step(t, a, "", "code")      // no answer yet: ask again, send nothing
	step(t, a, "99999", "code") // wrong code: same step, no new code requested
	step(t, a, " 12345 ", "password")
	step(t, a, "nope", "password")
	if s := step(t, a, "hunter 2 ", "done"); s.Payload != "1000" {
		t.Fatalf("done payload %q", s.Payload)
	}
	if f.sent != 1 {
		t.Fatalf("code requested %d times, want once", f.sent)
	}
	step(t, a, "", "done") // already linked: nothing to ask
}

func TestLoginWithoutPassword(t *testing.T) {
	f := &fake{code: "54321"}
	a, _ := newTest(t, f)
	step(t, a, "919800000000", "code")
	step(t, a, "54321", "done")
}

func TestLoginFloodWaitIsReportedNotSleptThrough(t *testing.T) {
	f := &fake{sendErr: tgerr.New(420, "FLOOD_WAIT_3600")}
	a, slept := newTest(t, f)
	_, err := a.Login(context.Background(), adapter.LoginInput{Value: "919800000000"})
	if err == nil || len(*slept) != 0 {
		t.Fatalf("err=%v slept=%v", err, *slept)
	}
	if want := "wait 1h0m0s"; !contains(err.Error(), want) {
		t.Fatalf("error %q should say %q", err, want)
	}
}

func contains(s, sub string) bool {
	for i := 0; i+len(sub) <= len(s); i++ {
		if s[i:i+len(sub)] == sub {
			return true
		}
	}
	return false
}

func TestConnectNeedsLogin(t *testing.T) {
	a, _ := newTest(t, &fake{})
	if err := a.Connect(context.Background()); !errors.Is(err, errNotLinked) {
		t.Fatalf("Connect before login: %v", err)
	}
}

// world is an account with a friend, a bot, the Telegram service chat, Saved Messages, a
// basic group and a channel.
func world() *fake {
	group, channel := &tg.PeerChat{ChatID: 50}, &tg.PeerChannel{ChannelID: 60}
	old := 100 * 24 * time.Hour
	return &fake{in: true,
		users: []tg.UserClass{
			&tg.User{ID: me, Self: true, FirstName: "Me"},
			&tg.User{ID: 1, AccessHash: 11, FirstName: "Asha", LastName: "Rao", Contact: true},
			&tg.User{ID: 2, AccessHash: 22, FirstName: "Reminder", Bot: true},
			&tg.User{ID: serviceUser, FirstName: "Telegram"},
			&tg.User{ID: 3, AccessHash: 33, FirstName: "Old", LastName: "Friend"},
		},
		chats: []tg.ChatClass{
			&tg.Chat{ID: 50, Title: "Goa trip"},
			&tg.Channel{ID: 60, Title: "News", Broadcast: true},
		},
		dialogs: []tg.DialogClass{
			&tg.Dialog{Peer: user(1), TopMessage: 9},
			&tg.Dialog{Peer: user(2), TopMessage: 8},
			&tg.Dialog{Peer: user(serviceUser), TopMessage: 7},
			&tg.Dialog{Peer: user(me), TopMessage: 6},
			&tg.Dialog{Peer: group, TopMessage: 5},
			&tg.Dialog{Peer: channel, TopMessage: 400},
			&tg.Dialog{Peer: user(3), TopMessage: 1},
		},
		msgs: map[string][]tg.MessageClass{
			"u1": {
				msg(9, user(1), false, time.Hour, "did you send the deck?"),
				&tg.MessageService{ID: 4, PeerID: user(1), Out: true, Date: int(t0.Add(-2 * time.Hour).Unix()),
					Action: &tg.MessageActionPhoneCall{}},
				msg(3, user(1), true, 3*time.Hour, "I'll send the deck tonight"),
				msg(2, user(1), false, old, "too old to read"),
			},
			"u2":      {msg(8, user(2), false, time.Hour, "bot says hi")},
			"u777000": {msg(7, user(serviceUser), false, time.Hour, "Login code: 12345")},
			"u1000":   {msg(6, user(me), true, time.Hour, "note to self")},
			"g50": {&tg.Message{ID: 5, PeerID: group, FromID: user(1), Date: int(t0.Add(-time.Hour).Unix()),
				Message: "tickets booked"}},
			"c60": {msg(400, channel, false, time.Hour, "channel post")},
			"u3":  {msg(1, user(3), false, old, "long ago")},
		},
	}
}

// drain collects events until the stream has been quiet for a moment.
func drain(a *Adapter) (out []adapter.Event) {
	for {
		select {
		case ev := <-a.Events():
			out = append(out, ev)
		case <-time.After(150 * time.Millisecond):
			return out
		}
	}
}

func waitSynced(t *testing.T, a *Adapter) {
	t.Helper()
	for i := 0; i < 200; i++ {
		a.mu.Lock()
		done := a.state.SyncedAt != 0
		a.mu.Unlock()
		if done {
			return
		}
		time.Sleep(10 * time.Millisecond)
	}
	t.Fatal("sync never finished")
}

func TestSyncKeepsPeopleAndGroupsOnly(t *testing.T) {
	f := world()
	a, _ := newTest(t, f)
	if err := a.Connect(context.Background()); err != nil {
		t.Fatal(err)
	}
	waitSynced(t, a)
	got := map[string]adapter.Event{}
	for _, ev := range drain(a) {
		if ev.Kind == adapter.EventContact {
			got["contact:"+ev.ChatID+ev.Group] = ev
			continue
		}
		if !ev.History || ev.Network != Network {
			t.Fatalf("backfill event not marked history: %+v", ev)
		}
		got[ev.RemoteID] = ev
	}
	want := map[string]bool{"1000:9": true, "1000:4": true, "1000:3": true, "1000:5": true,
		"contact:1": true, "contact:g50": true}
	if len(got) != len(want) {
		t.Fatalf("stored %v, want %v", keys(got), want)
	}
	for k := range want {
		if _, ok := got[k]; !ok {
			t.Fatalf("missing %s in %v", k, keys(got))
		}
	}
	if ev := got["1000:9"]; ev.ChatID != "1" || ev.Sender != "1" || ev.Name != "Asha Rao" || ev.FromMe ||
		!ev.Time.Equal(t0.Add(-time.Hour)) {
		t.Fatalf("incoming: %+v", ev)
	}
	if ev := got["1000:3"]; !ev.FromMe || ev.Sender != "" || ev.Name != "" || ev.ChatID != "1" {
		t.Fatalf("outgoing: %+v", ev)
	}
	if ev := got["1000:4"]; ev.Kind != adapter.EventCall || ev.Text != adapter.CallText || !ev.FromMe {
		t.Fatalf("call: %+v", ev)
	}
	if ev := got["1000:5"]; ev.Group != "g50" || ev.GroupName != "Goa trip" || ev.Sender != "1" || ev.Name != "Asha Rao" {
		t.Fatalf("group evidence: %+v", ev)
	}
	if ev := got["contact:1"]; ev.Name != "Asha Rao" || !ev.Saved {
		t.Fatalf("contact: %+v", ev)
	}
	// Only the kept chats inside the window were asked for, people before groups.
	var hist []string
	for _, c := range f.calls {
		if len(c) > 7 && c[:7] == "history" {
			hist = append(hist, c)
		}
	}
	if fmt.Sprint(hist) != "[history u1 offset=0 min=0 history g50 offset=0 min=0]" {
		t.Fatalf("history calls: %v", hist)
	}
	if fi, err := os.Stat(filepath.Join(a.dataDir, "sync.json")); err != nil || fi.Mode().Perm() != 0o600 {
		t.Fatalf("sync.json: %v %v", fi, err)
	}
}

func keys(m map[string]adapter.Event) (out []string) {
	for k := range m {
		out = append(out, k)
	}
	return
}

func TestSecondSyncReadsOnlyWhatIsNew(t *testing.T) {
	f := world()
	a, _ := newTest(t, f)
	ctx := context.Background()
	a.self = me
	if err := a.syncAll(ctx, f); err != nil {
		t.Fatal(err)
	}
	drain(a)
	f.calls = nil
	if err := a.syncAll(ctx, f); err != nil {
		t.Fatal(err)
	}
	for _, c := range f.calls {
		if c[:7] == "history" {
			t.Fatalf("nothing changed, but asked for %q", c)
		}
	}
	f.msgs["u1"] = append([]tg.MessageClass{msg(10, user(1), false, 0, "ping")}, f.msgs["u1"]...)
	f.dialogs[0].(*tg.Dialog).TopMessage = 10
	if err := a.syncAll(ctx, f); err != nil {
		t.Fatal(err)
	}
	evs := drain(a)
	if len(evs) != 1 || evs[0].RemoteID != "1000:10" {
		t.Fatalf("second sync: %+v", evs)
	}
}

func TestHistoryPagesAndStopsAtTheCap(t *testing.T) {
	f := world()
	f.msgs["u1"] = nil
	for id := 30; id >= 11; id-- {
		f.msgs["u1"] = append(f.msgs["u1"], msg(id, user(1), false, time.Minute, fmt.Sprint("m", id)))
	}
	f.dialogs = []tg.DialogClass{&tg.Dialog{Peer: user(1), TopMessage: 30}}
	a, _ := newTest(t, f)
	a.self, a.PageSize, a.MaxPerChat = me, 4, 10
	if err := a.syncAll(context.Background(), f); err != nil {
		t.Fatal(err)
	}
	n := 0
	for _, ev := range drain(a) {
		if ev.Kind == adapter.EventMessage {
			n++
		}
	}
	if n != 10 {
		t.Fatalf("read %d messages, want the cap of 10", n)
	}
}

func TestFloodWaitSleepsExactlyAsTold(t *testing.T) {
	f := world()
	f.floods = 2
	a, slept := newTest(t, f)
	a.self = me
	if err := a.syncAll(context.Background(), f); err != nil {
		t.Fatal(err)
	}
	if fmt.Sprint(*slept) != "[7s 7s]" {
		t.Fatalf("slept %v, want two waits of exactly 7s", *slept)
	}
	if len(drain(a)) == 0 {
		t.Fatal("the request should have been retried after the wait")
	}
}

func TestLongFloodWaitEndsTheSync(t *testing.T) {
	a, slept := newTest(t, &fake{})
	err := a.call(context.Background(), func() error { return tgerr.New(420, "FLOOD_WAIT_86400") })
	if d, ok := tgerr.AsFloodWait(err); !ok || d != 24*time.Hour || len(*slept) != 0 {
		t.Fatalf("err=%v slept=%v", err, *slept)
	}
	tries := 0
	err = a.call(context.Background(), func() error { tries++; return tgerr.New(420, "FLOOD_PREMIUM_WAIT_2") })
	if err == nil || tries != 5 || fmt.Sprint(*slept) != "[2s 2s 2s 2s]" {
		t.Fatalf("err=%v tries=%d slept=%v", err, tries, *slept)
	}
}

func TestLiveMessages(t *testing.T) {
	f := world()
	a, _ := newTest(t, f)
	a.self = me
	a.remember(f.users, f.chats)

	a.live(tg.Entities{}, msg(20, user(1), false, 0, "are we on for 5?"), false)
	a.live(tg.Entities{}, msg(20, user(1), false, 0, "are we on for 6?"), true)
	a.live(tg.Entities{}, msg(21, user(2), false, 0, "bot"), false)
	a.live(tg.Entities{}, msg(22, &tg.PeerChannel{ChannelID: 60}, false, 0, "post"), false)
	a.live(tg.Entities{}, msg(23, user(serviceUser), false, 0, "Login code: 99999"), false)
	evs := drain(a)
	if len(evs) != 3 || evs[0].Kind != adapter.EventContact || evs[0].Saved != true ||
		evs[1].Kind != adapter.EventMessage || evs[1].History || evs[1].Text != "are we on for 5?" ||
		evs[2].Kind != adapter.EventEdit || evs[2].RemoteID != "1000:20" {
		t.Fatalf("live: %+v", evs)
	}
	select {
	case <-a.resync:
		t.Fatal("known peers should not ask for a catch-up sync")
	default:
	}

	// Someone not in the chat list yet: not stored blind, a catch-up sync is asked for instead.
	a.live(tg.Entities{}, msg(24, user(77), false, 0, "hi, got your number from Asha"), false)
	if len(drain(a)) != 0 {
		t.Fatal("a stranger's message should wait for the sync")
	}
	select {
	case <-a.resync:
	default:
		t.Fatal("a stranger should ask for a catch-up sync")
	}
	// When the update carries the user, the message is kept straight away.
	e := tg.Entities{Users: map[int64]*tg.User{78: {ID: 78, FirstName: "Dev"}}}
	a.live(e, msg(25, user(78), false, 0, "hello"), false)
	if evs := drain(a); len(evs) != 2 || evs[1].Name != "Dev" || evs[1].ChatID != "78" {
		t.Fatalf("live with entities: %+v", evs)
	}
}

func TestConvertDropsAutoDeleteAndLeftGroups(t *testing.T) {
	a := newAdapter("t", t.TempDir())
	a.self = me
	a.remember([]tg.UserClass{&tg.User{ID: 1, FirstName: "Asha"}},
		[]tg.ChatClass{&tg.Chat{ID: 50, Title: "Goa trip"}, &tg.Chat{ID: 51, Title: "Left", Left: true}})
	m := msg(1, user(1), false, 0, "gone in a day")
	m.TTLPeriod = 86400
	if _, ok := a.convert(m, false); ok {
		t.Fatal("auto-deleting messages must not be kept")
	}
	if _, ok := a.convert(msg(2, &tg.PeerChat{ChatID: 51}, true, 0, "x"), false); ok {
		t.Fatal("a group you left is skipped")
	}
	if _, ok := a.convert(&tg.MessageService{ID: 3, PeerID: user(1), Action: &tg.MessageActionPinMessage{}}, false); ok {
		t.Fatal("service messages other than calls are dropped")
	}
	if ev, ok := a.convert(msg(4, &tg.PeerChat{ChatID: 50}, true, 0, "done, booked"), false); !ok || ev.Group != "g50" || ev.Sender != "" {
		t.Fatalf("my group line: %+v ok=%v", ev, ok)
	}
}

func TestContentMarksMedia(t *testing.T) {
	doc := func(attrs ...tg.DocumentAttributeClass) tg.MessageMediaClass {
		return &tg.MessageMediaDocument{Document: &tg.Document{Attributes: attrs}}
	}
	cases := []struct {
		m    *tg.Message
		want string
	}{
		{&tg.Message{Message: "hey"}, "hey"},
		{&tg.Message{Media: &tg.MessageMediaPhoto{}}, "[photo]"},
		{&tg.Message{Media: &tg.MessageMediaPhoto{}, Message: "Jiofi done ji"}, "[photo] Jiofi done ji"},
		{&tg.Message{Media: doc(&tg.DocumentAttributeVideo{})}, "[video]"},
		{&tg.Message{Media: doc(&tg.DocumentAttributeVideo{}, &tg.DocumentAttributeAnimated{})}, ""},
		{&tg.Message{Media: doc(&tg.DocumentAttributeFilename{FileName: "Itinerary.pdf"})}, "[document] Itinerary.pdf"},
		{&tg.Message{Media: doc(&tg.DocumentAttributeAudio{Voice: true})}, "[voice note]"},
		{&tg.Message{Media: doc(&tg.DocumentAttributeSticker{})}, ""},
		{&tg.Message{Media: &tg.MessageMediaGeo{}}, ""},
	}
	for _, c := range cases {
		if got := Content(c.m); got != c.want {
			t.Errorf("Content = %q, want %q", got, c.want)
		}
	}
	if Content(nil) != "" {
		t.Fatal("nil message")
	}
}

func TestNoChannelsFilter(t *testing.T) {
	in := []tg.UpdateClass{&tg.UpdateNewChannelMessage{}, &tg.UpdateNewMessage{}, &tg.UpdateChannelTooLong{},
		&tg.UpdateEditMessage{}}
	out := withoutChannels(in)
	if len(out) != 2 {
		t.Fatalf("kept %d updates, want 2", len(out))
	}
	if _, ok := out[0].(*tg.UpdateNewMessage); !ok {
		t.Fatalf("order changed: %T", out[0])
	}
}

func TestAPIConfig(t *testing.T) {
	root := t.TempDir()
	dir := filepath.Join(root, "accounts", "telegram-1")
	t.Setenv("TELEGRAM_API_ID", "")
	t.Setenv("TELEGRAM_API_HASH", "")
	if _, _, err := apiConfig(dir); err == nil || !contains(err.Error(), "my.telegram.org") {
		t.Fatalf("no config should explain where to get one: %v", err)
	}
	os.WriteFile(filepath.Join(root, "telegram.json"), []byte(`{"api_id": 42, "api_hash": "abc"}`), 0o600)
	if id, hash, err := apiConfig(dir); err != nil || id != 42 || hash != "abc" {
		t.Fatalf("file: %d %q %v", id, hash, err)
	}
	t.Setenv("TELEGRAM_API_ID", "7")
	t.Setenv("TELEGRAM_API_HASH", "envhash")
	if id, hash, err := apiConfig(dir); err != nil || id != 7 || hash != "envhash" {
		t.Fatalf("env: %d %q %v", id, hash, err)
	}
}

func TestEmitNeverBlocksAndKeepsOrder(t *testing.T) {
	a := newAdapter("t", t.TempDir())
	done := make(chan struct{})
	go func() { // nobody is reading Events: this must still return at once
		for i := 0; i < 5000; i++ {
			a.emit(adapter.Event{RemoteID: fmt.Sprint(i)})
		}
		close(done)
	}()
	select {
	case <-done:
	case <-time.After(2 * time.Second):
		t.Fatal("emit blocked with no consumer")
	}
	for i := 0; i < 5000; i++ {
		if ev := <-a.Events(); ev.RemoteID != fmt.Sprint(i) {
			t.Fatalf("event %d out of order: %s", i, ev.RemoteID)
		}
	}
}
