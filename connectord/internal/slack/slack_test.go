package slack

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/coder/websocket"
	"github.com/coder/websocket/wsjson"

	"github.com/yasharma117/soloyolo/connectord/internal/adapter"
)

// fakeSlack is a Web API stand-in: canned replies per method, a record of every call, and an
// optional Socket Mode endpoint. No real network, no real tokens.
type fakeSlack struct {
	t   *testing.T
	srv *httptest.Server

	mu       sync.Mutex
	calls    []string       // "method key=value..." in order
	limited  map[string]int // method → 429s still to send
	acks     chan string
	socketCh chan []byte // envelopes to push to a socket client
}

const (
	me    = "U0ME"
	sam   = "U0SAM"
	priya = "U0PRI"
	tok   = "xoxp-test-not-real"
)

func newFake(t *testing.T) *fakeSlack {
	f := &fakeSlack{t: t, limited: map[string]int{}, acks: make(chan string, 8), socketCh: make(chan []byte, 8)}
	f.srv = httptest.NewServer(http.HandlerFunc(f.serve))
	t.Cleanup(f.srv.Close)
	return f
}

func (f *fakeSlack) record(method string, r *http.Request) {
	r.ParseForm()
	var kv []string
	for _, k := range []string{"channel", "cursor", "oldest", "ts", "user", "types", "limit"} {
		if v := r.Form.Get(k); v != "" {
			kv = append(kv, k+"="+v)
		}
	}
	f.mu.Lock()
	f.calls = append(f.calls, strings.TrimSpace(method+" "+strings.Join(kv, " ")))
	f.mu.Unlock()
}

func (f *fakeSlack) called(prefix string) []string {
	f.mu.Lock()
	defer f.mu.Unlock()
	var out []string
	for _, c := range f.calls {
		if strings.HasPrefix(c, prefix) {
			out = append(out, c)
		}
	}
	return out
}

func (f *fakeSlack) reply(w http.ResponseWriter, v map[string]any) {
	v["ok"] = true
	json.NewEncoder(w).Encode(v)
}

func msg(user, ts, text string, extra ...map[string]any) map[string]any {
	m := map[string]any{"type": "message", "user": user, "ts": ts, "text": text}
	for _, e := range extra {
		for k, v := range e {
			m[k] = v
		}
	}
	return m
}

func (f *fakeSlack) serve(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path == "/socket" {
		f.socket(w, r)
		return
	}
	method := strings.TrimPrefix(r.URL.Path, "/api/")
	f.record(method, r)
	want := "Bearer " + tok
	if method == "apps.connections.open" {
		want = "Bearer xapp-test-not-real"
	}
	if r.Header.Get("Authorization") != want {
		json.NewEncoder(w).Encode(map[string]any{"ok": false, "error": "invalid_auth"})
		return
	}
	f.mu.Lock()
	if f.limited[method] > 0 {
		f.limited[method]--
		f.mu.Unlock()
		w.Header().Set("Retry-After", "7")
		w.WriteHeader(http.StatusTooManyRequests)
		w.Write([]byte(`{"ok":false,"error":"ratelimited"}`))
		return
	}
	f.mu.Unlock()
	switch method {
	case "auth.test":
		f.reply(w, map[string]any{"user_id": me, "user": "me", "team_id": "T0TEAM"})
	case "users.conversations":
		if r.Form.Get("cursor") == "" { // two pages, to prove pagination
			f.reply(w, map[string]any{"channels": []any{
				map[string]any{"id": "D0SAM", "is_im": true, "user": sam},
				map[string]any{"id": "D0SELF", "is_im": true, "user": me},
			}, "response_metadata": map[string]any{"next_cursor": "page2"}})
			return
		}
		f.reply(w, map[string]any{"channels": []any{
			map[string]any{"id": "G0MP", "is_mpim": true, "name": "mpdm-me--sam--priya-1"},
			map[string]any{"id": "C0GEN", "name": "launch"},
		}})
	case "conversations.history":
		f.history(w, r)
	case "conversations.replies":
		f.reply(w, map[string]any{"messages": []any{
			msg(priya, "1760000100.000100", "can you check the numbers <@U0ME>?", map[string]any{"reply_count": 2}),
			msg(me, "1760000150.000100", "numbers look right, shipped", map[string]any{"thread_ts": "1760000100.000100"}),
			msg(priya, "1760000160.000100", "thanks!", map[string]any{"thread_ts": "1760000100.000100"}),
		}})
	case "conversations.info":
		f.reply(w, map[string]any{"channel": map[string]any{"id": r.Form.Get("channel"), "is_im": true, "user": priya}})
	case "users.info":
		names := map[string][2]string{sam: {"Sam Lee", "Sam@Example.com"}, priya: {"Priya Rao", ""}, me: {"Me Myself", "me@example.com"}}
		n := names[r.Form.Get("user")]
		f.reply(w, map[string]any{"user": map[string]any{"id": r.Form.Get("user"), "name": strings.ToLower(n[0]),
			"profile": map[string]any{"real_name": n[0], "email": n[1]}}})
	case "users.list":
		f.reply(w, map[string]any{"members": []any{
			map[string]any{"id": sam, "name": "sam", "profile": map[string]any{"real_name": "Sam Lee"}},
			map[string]any{"id": "U0BOT", "name": "jira", "is_bot": true},
		}})
	case "apps.connections.open":
		f.reply(w, map[string]any{"url": "ws" + strings.TrimPrefix(f.srv.URL, "http") + "/socket"})
	default:
		json.NewEncoder(w).Encode(map[string]any{"ok": false, "error": "unknown_method"})
	}
}

func (f *fakeSlack) history(w http.ResponseWriter, r *http.Request) {
	ch, cursor := r.Form.Get("channel"), r.Form.Get("cursor")
	var msgs []any
	next := ""
	switch {
	case ch == "D0SAM" && cursor == "":
		msgs = []any{
			msg(sam, "1760000300.000100", "great, see <https://deck.example/v2|the deck> when you can",
				map[string]any{"reactions": []any{map[string]any{"name": "white_check_mark", "users": []string{me}}}}),
			msg(me, "1760000200.000100", "I'll send the deck by EOD"),
		}
		next = "older"
	case ch == "D0SAM" && cursor == "older":
		msgs = []any{
			msg(sam, "1760000010.000100", "", map[string]any{"subtype": "channel_join"}),
			msg(sam, "1760000000.000100", "can you intro me to <@U0PRI>?",
				map[string]any{"files": []any{map[string]any{"name": "cv.pdf", "mimetype": "application/pdf"}}}),
		}
	case ch == "D0SELF":
		msgs = []any{msg(me, "1760000000.000200", "note to self: buy milk")}
	case ch == "G0MP":
		msgs = []any{msg(priya, "1760000400.000100", "booked the room")}
	case ch == "C0GEN":
		msgs = []any{
			msg(sam, "1760000500.000100", "lunch anyone?"), // not about you: dropped
			msg(me, "1760000450.000100", "PR is merged <!here>"),
			msg(priya, "1760000100.000100", "can you check the numbers <@U0ME>?",
				map[string]any{"reply_count": 2, "reply_users": []string{me, priya}}),
			msg(sam, "1760000050.000100", "big launch thread", map[string]any{"reply_count": 40, "reply_users": []string{sam}}),
		}
	}
	if latest := r.Form.Get("latest"); latest != "" { // a single-message lookup
		var one []any
		for _, m := range msgs {
			if m.(map[string]any)["ts"] == latest {
				one = append(one, m)
			}
		}
		msgs, next = one, ""
	}
	f.reply(w, map[string]any{"messages": msgs, "response_metadata": map[string]any{"next_cursor": next}})
}

func (f *fakeSlack) socket(w http.ResponseWriter, r *http.Request) {
	c, err := websocket.Accept(w, r, nil)
	if err != nil {
		return
	}
	defer c.CloseNow()
	ctx := r.Context()
	c.Write(ctx, websocket.MessageText, []byte(`{"type":"hello"}`))
	go func() {
		for {
			var ack map[string]string
			if wsjson.Read(ctx, c, &ack) != nil {
				return
			}
			f.acks <- ack["envelope_id"]
		}
	}()
	for {
		select {
		case b := <-f.socketCh:
			c.Write(ctx, websocket.MessageText, b)
		case <-ctx.Done():
			return
		}
	}
}

type memKeychain struct {
	mu sync.Mutex
	m  map[string]string
}

func (k *memKeychain) Get(s, a string) (string, error) {
	k.mu.Lock()
	defer k.mu.Unlock()
	if v, ok := k.m[s+"/"+a]; ok {
		return v, nil
	}
	return "", fmt.Errorf("not found")
}
func (k *memKeychain) Set(s, a, v string) error {
	k.mu.Lock()
	defer k.mu.Unlock()
	k.m[s+"/"+a] = v
	return nil
}

// testAdapter points an adapter at the fake, with instant sleeps (recorded) and no polling.
func testAdapter(t *testing.T, f *fakeSlack) (*Adapter, *[]time.Duration) {
	t.Setenv("SLACK_USER_TOKEN", "")
	t.Setenv("SLACK_APP_TOKEN", "")
	a := newAdapter("slack-1", t.TempDir())
	a.BaseURL = f.srv.URL + "/api/"
	a.Keychain = &memKeychain{m: map[string]string{}}
	a.Since = time.Unix(1750000000, 0)
	var mu sync.Mutex
	var slept []time.Duration
	a.sleep = func(ctx context.Context, d time.Duration) error {
		if d >= time.Hour { // the polling interval: park until Close
			<-ctx.Done()
			return ctx.Err()
		}
		mu.Lock()
		if d > 0 {
			slept = append(slept, d)
		}
		mu.Unlock()
		return ctx.Err()
	}
	a.PollInterval = 24 * time.Hour
	return a, &slept
}

// collect reads events until none arrive for a moment.
func collect(t *testing.T, a *Adapter) []adapter.Event {
	var out []adapter.Event
	for {
		select {
		case ev := <-a.Events():
			out = append(out, ev)
		case <-time.After(300 * time.Millisecond):
			return out
		}
	}
}

func find(evs []adapter.Event, pred func(adapter.Event) bool) (adapter.Event, bool) {
	for _, e := range evs {
		if pred(e) {
			return e, true
		}
	}
	return adapter.Event{}, false
}

func TestLogin(t *testing.T) {
	f := newFake(t)
	a, _ := testAdapter(t, f)
	ctx := context.Background()
	step, err := a.Login(ctx, adapter.LoginInput{})
	if err != nil || step.Kind != "code" || !strings.Contains(step.Payload, "im:history") {
		t.Fatalf("no token: %+v %v", step, err)
	}
	if _, err := a.Login(ctx, adapter.LoginInput{Value: "xoxb-bot"}); err == nil {
		t.Fatal("a bot token must be refused")
	}
	if _, err := a.Login(ctx, adapter.LoginInput{Value: "xoxp-wrong"}); err == nil {
		t.Fatal("a token Slack rejects must fail login")
	}
	step, err = a.Login(ctx, adapter.LoginInput{Value: tok})
	if err != nil || step.Kind != "done" || step.Payload != "T0TEAM:"+me {
		t.Fatalf("login: %+v %v", step, err)
	}
	// The token went to the keychain, so a fresh adapter (a restart) finds it there.
	b := newAdapter("slack-1", t.TempDir())
	b.Keychain, b.BaseURL = a.Keychain, a.BaseURL
	if b.userToken() != tok {
		t.Fatal("token not saved to the keychain")
	}
}

func TestBackfillMapsDMsGroupsAndChannels(t *testing.T) {
	f := newFake(t)
	a, _ := testAdapter(t, f)
	t.Setenv("SLACK_USER_TOKEN", tok)
	if err := a.Connect(context.Background()); err != nil {
		t.Fatal(err)
	}
	defer a.Close()
	evs := collect(t, a)

	samID, gen := "T0TEAM:"+sam, "T0TEAM:C0GEN"
	// DMs are messages, from you or from them, with readable text.
	mine, ok := find(evs, func(e adapter.Event) bool { return e.Text == "I'll send the deck by EOD" })
	if !ok || !mine.FromMe || mine.ChatID != samID || mine.Group != "" || !mine.History ||
		mine.RemoteID != "T0TEAM:D0SAM:1760000200.000100" || mine.Time.Unix() != 1760000200 {
		t.Fatalf("my DM: %+v", mine)
	}
	theirs, ok := find(evs, func(e adapter.Event) bool { return strings.HasPrefix(e.Text, "great") })
	if !ok || theirs.FromMe || theirs.Sender != samID || theirs.Name != "Sam Lee" ||
		theirs.Text != "great, see the deck (https://deck.example/v2) when you can" {
		t.Fatalf("their DM: %+v", theirs)
	}
	// Page two (cursor) arrived, with a file marker and a rendered mention; the join was dropped.
	if _, ok := find(evs, func(e adapter.Event) bool { return e.Text == "[document] cv.pdf can you intro me to @Priya Rao?" }); !ok {
		t.Fatalf("page 2 missing: %+v", evs)
	}
	if len(f.called("conversations.history channel=D0SAM cursor=older")) != 1 {
		t.Fatalf("no second page: %v", f.called("conversations.history"))
	}
	// Your ✅ on their message is a line from you.
	if r, ok := find(evs, func(e adapter.Event) bool { return strings.HasPrefix(e.Text, "[✅") }); !ok || !r.FromMe || r.ChatID != samID {
		t.Fatalf("reaction: %+v", r)
	}
	// Group DMs are evidence, labelled by the other people.
	g, ok := find(evs, func(e adapter.Event) bool { return e.Text == "booked the room" })
	if !ok || g.Group != "T0TEAM:G0MP" || g.GroupName != "sam, priya" || g.Name != "Priya Rao" {
		t.Fatalf("group DM: %+v", g)
	}
	// Channels: your lines, lines to you, and your threads. Not the rest.
	for _, text := range []string{"PR is merged @here", "numbers look right, shipped", "thanks!"} {
		e, ok := find(evs, func(e adapter.Event) bool { return e.Text == text })
		if !ok || e.Group != gen || e.GroupName != "#launch" {
			t.Fatalf("channel line %q: %+v", text, e)
		}
	}
	if _, ok := find(evs, func(e adapter.Event) bool { return strings.HasPrefix(e.Text, "can you check the numbers") }); !ok {
		t.Fatal("a line mentioning you should be kept")
	}
	if _, ok := find(evs, func(e adapter.Event) bool { return e.Text == "lunch anyone?" || e.Text == "big launch thread" }); ok {
		t.Fatal("channel chatter that isn't about you must be dropped")
	}
	if n := len(f.called("conversations.replies")); n != 1 {
		t.Fatalf("only your thread should be fetched, got %d replies calls", n)
	}
	// Notes to self are skipped (no other person); the thread parent is stored once.
	count := 0
	for _, e := range evs {
		if strings.Contains(e.Text, "buy milk") {
			t.Fatal("self-DM stored")
		}
		if strings.HasPrefix(e.Text, "can you check the numbers") {
			count++
		}
	}
	if count != 1 {
		t.Fatalf("thread parent stored %d times", count)
	}
	// People become contacts carrying their email, lower-cased; one users.info per person.
	c, ok := find(evs, func(e adapter.Event) bool { return e.Kind == adapter.EventContact && e.ChatID == samID })
	if !ok || c.Name != "Sam Lee" || c.Email != "sam@example.com" {
		t.Fatalf("contact: %+v", c)
	}
	if n := len(f.called("users.info user=" + sam)); n != 1 {
		t.Fatalf("users.info for Sam %d times", n)
	}
	// DMs are read before channels.
	hist := f.called("conversations.history")
	if !strings.Contains(hist[0], "D0") || !strings.Contains(hist[len(hist)-1], "C0GEN") {
		t.Fatalf("order: %v", hist)
	}
}

func TestRestartIsIncremental(t *testing.T) {
	f := newFake(t)
	a, _ := testAdapter(t, f)
	t.Setenv("SLACK_USER_TOKEN", tok)
	dir := a.dataDir
	a.Connect(context.Background())
	collect(t, a)
	a.Close()

	b, _ := testAdapter(t, f)
	b.dataDir = dir
	t.Setenv("SLACK_USER_TOKEN", tok)
	b.Connect(context.Background())
	collect(t, b)
	b.Close()
	got := f.called("conversations.history channel=D0SAM")
	last := got[len(got)-1]
	if !strings.Contains(last, "oldest=1760000300.000100") {
		t.Fatalf("restart should read from the newest stored ts: %v", got)
	}
}

func TestRetryAfterIsHonoured(t *testing.T) {
	f := newFake(t)
	a, slept := testAdapter(t, f)
	f.limited["conversations.history"] = 2
	a.userTok = tok
	if _, err := a.authTest(context.Background(), tok); err != nil {
		t.Fatal(err)
	}
	evs, cur, err := a.Backfill(context.Background(), "D0SAM", "")
	if err != nil || len(evs) == 0 || cur != "older" {
		t.Fatalf("backfill: %d events, cursor %q, %v", len(evs), cur, err)
	}
	n7 := 0
	for _, d := range *slept {
		if d > 6*time.Second { // Retry-After: 7, never less (the tier spacing can add a little)
			n7++
		}
	}
	if n7 != 2 {
		t.Fatalf("expected two ~7s waits for Retry-After, slept %v", *slept)
	}
	// Backfill by person id finds the DM.
	evs, cur, err = a.Backfill(context.Background(), "T0TEAM:"+sam, "older")
	if err != nil || len(evs) != 1 || cur != "" {
		t.Fatalf("backfill page 2: %+v %q %v", evs, cur, err)
	}
}

func TestLimiterSpacesCallsByTier(t *testing.T) {
	var l limiter
	now := time.Unix(0, 0)
	if d := l.reserve("conversations.history", 50, now); d != 0 {
		t.Fatalf("first call waits %v", d)
	}
	if d := l.reserve("conversations.history", 50, now); d != 1200*time.Millisecond {
		t.Fatalf("Tier 3 spacing %v", d)
	}
	if d := l.reserve("conversations.history", 1, now.Add(2*time.Second)); d != 400*time.Millisecond {
		t.Fatalf("after the last slot %v", d)
	}
	l.pause("users.info", now.Add(30*time.Second))
	if d := l.reserve("users.info", 100, now); d != 30*time.Second {
		t.Fatalf("pause %v", d)
	}
}

func TestRevokedTokenLogsOut(t *testing.T) {
	f := newFake(t)
	a, _ := testAdapter(t, f)
	t.Setenv("SLACK_USER_TOKEN", "xoxp-revoked")
	if err := a.Connect(context.Background()); err == nil {
		t.Fatal("connect with a dead token should fail")
	}
	if ev := <-a.Events(); ev.Kind != adapter.EventLogout {
		t.Fatalf("want logout, got %+v", ev)
	}
}

func TestSocketModeDeliversLiveEvents(t *testing.T) {
	f := newFake(t)
	a, _ := testAdapter(t, f)
	t.Setenv("SLACK_USER_TOKEN", tok)
	t.Setenv("SLACK_APP_TOKEN", "xapp-test-not-real")
	if err := a.Connect(context.Background()); err != nil {
		t.Fatal(err)
	}
	defer a.Close()
	collect(t, a) // the backfill
	push := func(id string, event map[string]any) {
		b, _ := json.Marshal(map[string]any{"type": "events_api", "envelope_id": id,
			"payload": map[string]any{"event": event}})
		f.socketCh <- b
	}
	// A DM from someone new: the adapter asks conversations.info about the channel.
	push("E1", map[string]any{"type": "message", "channel": "D0NEW", "channel_type": "im",
		"user": priya, "text": "sent you the contract", "ts": "1760001000.000100"})
	select {
	case id := <-f.acks:
		if id != "E1" {
			t.Fatalf("ack %q", id)
		}
	case <-time.After(3 * time.Second):
		t.Fatal("envelope not acknowledged")
	}
	evs := collect(t, a)
	live, ok := find(evs, func(e adapter.Event) bool { return e.Text == "sent you the contract" })
	if !ok || live.History || live.ChatID != "T0TEAM:"+priya || live.Name != "Priya Rao" {
		t.Fatalf("live DM: %+v (all %+v)", live, evs)
	}
	// A ✅ from Sam on your channel message, live.
	push("E2", map[string]any{"type": "reaction_added", "user": sam, "reaction": "white_check_mark",
		"item_user": me, "event_ts": "1760001100.000200",
		"item": map[string]any{"type": "message", "channel": "C0GEN", "ts": "1760000450.000100"}})
	<-f.acks
	evs = collect(t, a)
	r, ok := find(evs, func(e adapter.Event) bool { return strings.HasPrefix(e.Text, "[✅") })
	if !ok || r.Text != "[✅ on: PR is merged @here]" || r.Group != "T0TEAM:C0GEN" || r.Sender != "T0TEAM:"+sam || r.FromMe ||
		r.RemoteID != "T0TEAM:C0GEN:1760000450.000100:r:white_check_mark:"+sam {
		t.Fatalf("live reaction: %+v", r)
	}
	// Chatter in a channel that isn't about you stays out, live too.
	push("E3", map[string]any{"type": "message", "channel": "C0GEN", "channel_type": "channel",
		"user": sam, "text": "coffee?", "ts": "1760001200.000100"})
	<-f.acks
	if evs := collect(t, a); len(evs) != 0 {
		t.Fatalf("channel chatter delivered: %+v", evs)
	}
}

func TestContacts(t *testing.T) {
	f := newFake(t)
	a, _ := testAdapter(t, f)
	a.userTok = tok
	a.authTest(context.Background(), tok)
	cs, err := a.Contacts(context.Background())
	if err != nil || len(cs) != 1 || cs[0].Address != "T0TEAM:"+sam || cs[0].Name != "Sam Lee" {
		t.Fatalf("contacts %+v %v", cs, err)
	}
}

func TestRenderAndLabels(t *testing.T) {
	a := newAdapter("x", t.TempDir())
	u := user{ID: "U1", Name: "sam"}
	u.Profile.RealName = "Sam Lee"
	a.users["U1"] = u
	a.convs["C1"] = conv{conversation: conversation{ID: "C1", Name: "ops"}}
	cases := map[string]string{
		"<@U1> done":              "@Sam Lee done",
		"see <#C1> and <#C2|eng>": "see #ops and #eng",
		"<https://x.io/a|spec> &amp; <https://y.io>": "spec (https://x.io/a) & https://y.io",
		"<mailto:a@b.co|a@b.co>":                     "a@b.co",
		"<!channel> &lt;3":                           "@channel <3",
		"<!subteam^S1|@design> ping":                 "@design ping",
	}
	for in, want := range cases {
		if got := a.render(context.Background(), in); got != want {
			t.Errorf("render(%q) = %q, want %q", in, got, want)
		}
	}
	if got := mpimLabel("mpdm-me--sam--priya-1", "me"); got != "sam, priya" {
		t.Errorf("mpimLabel = %q", got)
	}
	if got := parseTS("1760000000.000100"); got.Unix() != 1760000000 || got.Nanosecond() != 100000 {
		t.Errorf("parseTS = %v", got)
	}
}
